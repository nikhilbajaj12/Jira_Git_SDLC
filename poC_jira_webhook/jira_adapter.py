from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)

# ── open-swe integration ─────────────────────────────────────────────
# Import the open-swe dispatch mechanism. This module must be run from
# the project root so that the `agent` package is importable.

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.dispatch import dispatch_agent_run, _langgraph_url, dispatch_client
from agent.utils.jira import (
    generate_thread_id_from_jira_issue,
    format_jira_issue_for_prompt,
    post_jira_comment,
    transition_jira_issue,
    add_remote_link,
)
from langchain_core.messages.content import create_text_block

# ── Configuration ────────────────────────────────────────────────────

PROJECT_REPO_MAP: dict[str, str] = {
    # Example: "PROJ": "https://github.com/my-org/my-repo",
}

_POLL_INTERVAL = 10.0
_MAX_POLL_SECONDS = 600.0


def _repo_url_to_config(url: str) -> dict[str, str]:
    parts = url.rstrip("/").split("/")
    owner, name = parts[-2], parts[-1]
    return {"owner": owner, "name": name}


# ── PR URL extraction ────────────────────────────────────────────────


async def _wait_for_pr_url(
    thread_id: str, timeout: float = _MAX_POLL_SECONDS
) -> str | None:
    client = dispatch_client()
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            thread = await client.threads.get(thread_id)
            metadata = thread.get("metadata") or {}
            pr_url = metadata.get("pr_url")
            if pr_url:
                return str(pr_url)

            run_status = metadata.get("latest_run_status")
            if run_status == "error":
                state = await client.threads.get_state(thread_id)
                values = state.get("values", {})
                messages = values.get("messages", [])
                if messages:
                    last = messages[-1]
                    if isinstance(last, dict):
                        error = last.get("content", str(last))
                    else:
                        error = str(getattr(last, "content", ""))
                else:
                    error = "Unknown agent error"
                logger.warning("Agent run failed for thread %s: %s", thread_id, error)
                return None
        except Exception:
            logger.warning("Failed to poll thread %s", thread_id, exc_info=True)

        await asyncio.sleep(_POLL_INTERVAL)

    logger.warning("Timed out waiting for PR URL on thread %s", thread_id)
    return None


# ── Jira update helpers ──────────────────────────────────────────────


async def update_jira_with_pr(ticket_key: str, pr_url: str) -> None:
    try:
        await add_remote_link(
            ticket_key,
            url=pr_url,
            title=f"PR: {pr_url.split('/')[-1]}",
        )
        logger.info("Added remote link to Jira issue %s: %s", ticket_key, pr_url)
    except Exception as e:
        logger.warning("Failed to add remote link to %s: %s", ticket_key, e)

    try:
        await post_jira_comment(
            ticket_key,
            f"AI Agent has raised a draft PR: {pr_url}",
        )
        logger.info("Posted comment to Jira issue %s", ticket_key)
    except Exception as e:
        logger.warning("Failed to post comment to %s: %s", ticket_key, e)

    try:
        await transition_jira_issue(ticket_key, "In Review")
        logger.info("Transitioned Jira issue %s to 'In Review'", ticket_key)
    except Exception as e:
        logger.warning("Failed to transition Jira issue %s: %s", ticket_key, e)


async def update_jira_with_error(ticket_key: str, error: str) -> None:
    try:
        await post_jira_comment(
            ticket_key,
            f"AI Agent failed to process this ticket: {error}",
        )
    except Exception as e:
        logger.warning("Failed to post error comment to %s: %s", ticket_key, e)


# ── Main agent runner ────────────────────────────────────────────────


async def run_agent_and_create_pr(
    ticket_data: dict[str, Any],
    repo_url: str,
) -> str | None:
    ticket_key = ticket_data["key"]
    summary = ticket_data.get("summary", "")
    description = ticket_data.get("description", "")

    repo_config = _repo_url_to_config(repo_url)

    agent_prompt = (
        f"Fix the following issue:\n\n"
        f"Title: {summary}\n"
        f"Description:\n{description}\n\n"
        f"Repository: {repo_config['owner']}/{repo_config['name']}\n\n"
        "Please analyze, implement the fix, commit and push your changes, "
        "and open a draft pull request using the `open_pull_request` tool. "
        f"The Jira issue key is: {ticket_key}"
    )

    thread_id = generate_thread_id_from_jira_issue(ticket_key)
    content_blocks: list[Any] = [create_text_block(agent_prompt)]
    configurable: dict[str, Any] = {
        "repo": repo_config,
        "source": "jira",
        "jira_issue": {
            "key": ticket_key,
            "summary": summary,
        },
    }

    try:
        run = await dispatch_agent_run(
            thread_id,
            content_blocks,
            configurable,
            source="jira",
        )
        logger.info(
            "Dispatched agent run for %s (run=%s)",
            ticket_key,
            run.get("run_id") if isinstance(run, dict) else None,
        )
    except Exception as e:
        logger.error("Failed to dispatch agent run for %s: %s", ticket_key, e)
        await update_jira_with_error(ticket_key, str(e))
        return None

    pr_url = await _wait_for_pr_url(thread_id)
    if pr_url:
        logger.info("Agent created PR for %s: %s", ticket_key, pr_url)
        await update_jira_with_pr(ticket_key, pr_url)
    else:
        logger.error("Agent did not produce a PR URL for %s", ticket_key)
        await update_jira_with_error(ticket_key, "Agent did not produce a PR URL")
    return pr_url
