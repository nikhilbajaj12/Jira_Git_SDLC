"""Jira webhook handler for Open SWE.

Processes Jira webhook events and dispatches agent runs. Mirrors the
structure of agent/webhooks/linear.py so the patterns stay consistent.

Jira webhook events supported:
- jira:issue_created  — new issue assigned to open-swe label/component
- jira:issue_updated  — status change or comment added that mentions @open-swe
- comment_created     — new comment on an issue that mentions @open-swe
"""

from __future__ import annotations

import logging
import os
from typing import Any

from agent import webapp

from ..utils.jira import (
    extract_repo_from_jira_issue,
    fetch_jira_issue,
    format_jira_issue_for_prompt,
    generate_thread_id_from_jira_issue,
)
from ..utils.jira_risk import score_jira_issue

logger = logging.getLogger(__name__)

# The label or component name that opts an issue into open-swe automation
OPEN_SWE_JIRA_LABEL = "open-swe"

# Bot comment prefixes to skip when looking for follow-up trigger comments
_BOT_COMMENT_PREFIXES = (
    "✅ **Pull Request",
    "**Pull Request",
    "🤖 **Agent",
    "❌ **Agent Error",
    "🔐 **GitHub",
)


def _is_bot_comment(body: str) -> bool:
    return any(body.startswith(p) for p in _BOT_COMMENT_PREFIXES)


def _mentions_open_swe(text: str) -> bool:
    return "@open-swe" in text.lower() or "open-swe" in text.lower()


def build_jira_issue_prompt(
    issue_key: str,
    formatted_issue: str,
    repo_config: dict[str, str],
    triggered_by: str = "",
    triggering_comment: str = "",
) -> str:
    """Build the initial agent prompt from a Jira issue."""
    triggered_by_line = f"## Triggered by: {triggered_by}\n\n" if triggered_by else ""
    comment_section = (
        f"\n\n## Triggering Comment:\n{triggering_comment}" if triggering_comment else ""
    )

    return (
        f"Please work on the following Jira issue:\n\n"
        f"## Repository: {repo_config.get('owner')}/{repo_config.get('name')}\n\n"
        f"{triggered_by_line}"
        f"{formatted_issue}"
        f"{comment_section}\n\n"
        "Please analyze this issue and implement the necessary changes.\n"
        "When you have finished implementing and tests pass:\n"
        "1. Commit and push your changes to a new branch.\n"
        "2. Open a draft pull request using the `open_pull_request` tool.\n"
        "3. Add the PR link to the Jira issue using the `jira_add_link` tool.\n"
        "4. Post a comment to the Jira issue with the PR URL and a brief summary "
        "using the `jira_comment` tool.\n"
        "5. Transition the Jira issue to 'In Review' using the `jira_transition` tool.\n\n"
        f"The Jira issue key is: {issue_key}\n"
        "Use `jira_comment` to post updates and `jira_get_issue` to re-read ticket details."
    )


def build_jira_followup_prompt(issue_key: str, comment_author: str, comment_body: str) -> str:
    """Build a follow-up prompt from a new Jira comment."""
    return (
        f"**{comment_author}** added a comment on Jira issue {issue_key}:\n\n"
        f"{comment_body}\n\n"
        "Please act on this follow-up. Use `jira_comment` to reply when done."
    )


async def process_jira_issue_event(payload: dict[str, Any]) -> dict[str, str]:
    """Process a jira:issue_created or jira:issue_updated webhook event.

    Returns a status dict for the HTTP response.
    """
    issue_data = payload.get("issue") or {}
    issue_key = issue_data.get("key", "")
    if not issue_key:
        return {"status": "ignored", "reason": "No issue key in payload"}

    fields = issue_data.get("fields") or {}
    labels: list[str] = [lbl.lower() for lbl in (fields.get("labels") or [])]

    # Only handle issues that carry the open-swe label
    if OPEN_SWE_JIRA_LABEL not in labels:
        logger.debug("Ignoring Jira issue %s — no '%s' label", issue_key, OPEN_SWE_JIRA_LABEL)
        return {"status": "ignored", "reason": f"Issue does not have '{OPEN_SWE_JIRA_LABEL}' label"}

    # Fetch full issue so we have comments, attachments, acceptance criteria
    full_issue = await fetch_jira_issue(issue_key)
    if not full_issue:
        logger.warning("Could not fetch full Jira issue %s — using webhook data", issue_key)
        full_issue = issue_data

    repo_config = extract_repo_from_jira_issue(full_issue or issue_data)
    if not repo_config:
        # Fall back to default repo from env
        default_owner = webapp.DEFAULT_REPO_OWNER
        default_name = webapp.DEFAULT_REPO_NAME
        if not default_name:
            return {
                "status": "error",
                "reason": (
                    f"Could not determine repo for {issue_key}. "
                    "Add 'repo:owner/name' label or set DEFAULT_REPO_OWNER/DEFAULT_REPO_NAME."
                ),
            }
        repo_config = {"owner": default_owner, "name": default_name}

    formatted = format_jira_issue_for_prompt(full_issue)

    # Risk analysis
    risk = score_jira_issue(full_issue)
    logger.info(
        "Jira issue %s risk level: %s (reasons: %s)",
        issue_key,
        risk.level,
        risk.reasons,
    )

    thread_id = generate_thread_id_from_jira_issue(issue_key)

    reporter = (fields.get("reporter") or {}).get("displayName", "")
    summary = fields.get("summary", "Jira issue")

    prompt = build_jira_issue_prompt(
        issue_key=issue_key,
        formatted_issue=formatted,
        repo_config=repo_config,
        triggered_by=reporter,
    )

    configurable: dict[str, Any] = {
        "repo": repo_config,
        "jira_issue": {
            "key": issue_key,
            "summary": summary,
            "url": (f"{os.environ.get('JIRA_BASE_URL', '').rstrip('/')}/browse/{issue_key}"),
        },
        "source": "jira",
        "plan_mode": risk.plan_mode_recommended,
        "__is_for_execution__": True,
    }

    if risk.plan_mode_recommended:
        logger.info(
            "High-risk Jira issue %s — enabling plan mode. Reasons: %s",
            issue_key,
            risk.reasons,
        )

    await webapp.upsert_agent_thread_owner_metadata(
        thread_id,
        source="jira",
        repo_config=repo_config,
        title=summary or issue_key,
        source_context={"jira_issue": configurable["jira_issue"]},
    )

    run = await webapp.dispatch_agent_run(
        thread_id,
        prompt,
        configurable,
        source="jira",
        metadata=webapp._AGENT_VERSION_METADATA,
    )
    logger.info(
        "Dispatched agent run for Jira issue %s on thread %s (run=%s, risk=%s)",
        issue_key,
        thread_id,
        run.get("run_id") if isinstance(run, dict) else None,
        risk.level,
    )
    return {"status": "ok", "thread_id": thread_id, "risk_level": risk.level}


async def process_jira_comment_event(payload: dict[str, Any]) -> dict[str, str]:
    """Process a comment_created webhook event.

    Dispatches a follow-up run to an existing thread when a Jira comment
    mentions @open-swe.
    """
    comment_data = payload.get("comment") or {}
    issue_data = payload.get("issue") or {}
    issue_key = issue_data.get("key", "")

    if not issue_key:
        return {"status": "ignored", "reason": "No issue key in payload"}

    # Extract author and body
    comment_author_data = comment_data.get("author") or {}
    comment_author = comment_author_data.get("displayName", "User")
    comment_author_email = comment_author_data.get("emailAddress", "")

    # Jira comments use ADF; extract plain text
    from ..utils.jira import _extract_text_from_adf

    body_obj = comment_data.get("body") or {}
    comment_body = _extract_text_from_adf(body_obj).strip()

    if not comment_body:
        return {"status": "ignored", "reason": "Empty comment body"}

    if _is_bot_comment(comment_body):
        return {"status": "ignored", "reason": "Comment is from the bot"}

    if not _mentions_open_swe(comment_body):
        return {"status": "ignored", "reason": "Comment does not mention @open-swe"}

    thread_id = generate_thread_id_from_jira_issue(issue_key)

    fields = issue_data.get("fields") or {}
    repo_config = extract_repo_from_jira_issue(issue_data)
    if not repo_config:
        default_owner = webapp.DEFAULT_REPO_OWNER
        default_name = webapp.DEFAULT_REPO_NAME
        if default_name:
            repo_config = {"owner": default_owner, "name": default_name}

    prompt = build_jira_followup_prompt(issue_key, comment_author, comment_body)

    configurable: dict[str, Any] = {
        "source": "jira",
        "jira_issue": {
            "key": issue_key,
            "summary": fields.get("summary", ""),
        },
        "user_email": comment_author_email,
        "__is_for_execution__": True,
    }
    if repo_config:
        configurable["repo"] = repo_config

    run = await webapp.dispatch_agent_run(
        thread_id,
        prompt,
        configurable,
        source="jira",
        metadata=webapp._AGENT_VERSION_METADATA,
    )
    logger.info(
        "Dispatched follow-up run for Jira issue %s on thread %s (run=%s)",
        issue_key,
        thread_id,
        run.get("run_id") if isinstance(run, dict) else None,
    )
    return {"status": "ok", "thread_id": thread_id}
