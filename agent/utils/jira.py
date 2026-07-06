"""Jira REST API client for Open SWE integration.

Provides helpers to fetch issue details, post comments, transition statuses,
and add remote links (PR URLs) back to Jira tickets.

All functions read JIRA_BASE_URL, JIRA_API_TOKEN, and JIRA_USER_EMAIL from
environment variables. They are best-effort: callers receive None / False on
failure rather than raising so a single Jira API hiccup never aborts an agent run.
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)

JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "")  # e.g. https://myorg.atlassian.net
JIRA_USER_EMAIL = os.environ.get("JIRA_USER_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")
JIRA_WEBHOOK_SECRET = os.environ.get("JIRA_WEBHOOK_SECRET", "")

_TIMEOUT = 20.0

# Jira field names that commonly hold acceptance criteria
_AC_FIELD_CANDIDATES = (
    "customfield_10016",  # common AC field in many Jira configs
    "customfield_10034",
    "acceptance_criteria",
)


def _auth() -> tuple[str, str]:
    return (JIRA_USER_EMAIL, JIRA_API_TOKEN)


def _base() -> str:
    return JIRA_BASE_URL.rstrip("/")


def _configured() -> bool:
    return bool(JIRA_BASE_URL and JIRA_USER_EMAIL and JIRA_API_TOKEN)


# ---------------------------------------------------------------------------
# Thread ID helpers
# ---------------------------------------------------------------------------


def generate_thread_id_from_jira_issue(issue_key: str) -> str:
    """Return a deterministic UUID thread ID for a Jira issue key (e.g. 'PROJ-123')."""
    hash_hex = hashlib.sha256(f"jira-issue:{issue_key}".encode()).hexdigest()
    return str(uuid.UUID(hex=hash_hex[:32]))


# ---------------------------------------------------------------------------
# Issue fetching
# ---------------------------------------------------------------------------


async def fetch_jira_issue(issue_key: str) -> dict[str, Any] | None:
    """Fetch full issue details including description, comments, and attachments.

    Returns the raw Jira REST API issue dict, or None on failure.
    """
    if not _configured():
        logger.warning("Jira not configured — skipping issue fetch for %s", issue_key)
        return None

    url = f"{_base()}/rest/api/3/issue/{issue_key}"
    params = {
        "expand": "renderedFields,names,changelog",
        "fields": (
            "summary,description,status,priority,labels,issuetype,"
            "assignee,reporter,project,comment,attachment,"
            "customfield_10016,customfield_10034,acceptance_criteria,"
            "components,fixVersions,subtasks,parent,issuelinks"
        ),
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.get(url, auth=_auth(), params=params)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.warning("Failed to fetch Jira issue %s", issue_key, exc_info=True)
            return None


def extract_repo_from_jira_issue(issue: dict[str, Any]) -> dict[str, str] | None:
    """Try to extract a GitHub repo (owner/name) from the Jira issue.

    Looks in:
    1. Description text for patterns like github.com/owner/name
    2. Custom field 'customfield_10100' (repo field used in some configs)
    3. Labels like 'repo:owner/name'
    """
    import re

    fields = issue.get("fields", {}) or {}

    # Check labels for repo:owner/name pattern
    labels: list[str] = fields.get("labels") or []
    for label in labels:
        m = re.match(r"^repo:([^/]+)/(.+)$", label, re.IGNORECASE)
        if m:
            return {"owner": m.group(1), "name": m.group(2)}

    # Check description text
    description_obj = fields.get("description") or {}
    description_text = _extract_text_from_adf(description_obj)
    m = re.search(r"github\.com/([^/\s]+)/([^/\s\)]+)", description_text)
    if m:
        return {"owner": m.group(1), "name": m.group(2).rstrip(".")}

    return None


def _extract_text_from_adf(node: Any, depth: int = 0) -> str:
    """Recursively extract plain text from an Atlassian Document Format (ADF) node."""
    if depth > 20:
        return ""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    text = node.get("text", "")
    children = node.get("content") or []
    parts = [text] + [_extract_text_from_adf(child, depth + 1) for child in children]
    return " ".join(p for p in parts if p)


def _extract_acceptance_criteria(fields: dict[str, Any]) -> str:
    """Pull acceptance criteria from known custom fields."""
    for field_key in _AC_FIELD_CANDIDATES:
        value = fields.get(field_key)
        if not value:
            continue
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return _extract_text_from_adf(value)
    return ""


def format_jira_issue_for_prompt(issue: dict[str, Any]) -> str:
    """Convert a Jira issue dict into a structured agent prompt string."""
    fields = issue.get("fields", {}) or {}
    issue_key = issue.get("key", "")
    summary = fields.get("summary", "")
    status = (fields.get("status") or {}).get("name", "")
    priority = (fields.get("priority") or {}).get("name", "")
    issue_type = (fields.get("issuetype") or {}).get("name", "")
    reporter = (fields.get("reporter") or {}).get("displayName", "")
    assignee = (fields.get("assignee") or {}).get("displayName", "") or "Unassigned"
    labels: list[str] = fields.get("labels") or []

    description_obj = fields.get("description") or {}
    description = _extract_text_from_adf(description_obj).strip() or "No description"

    acceptance_criteria = _extract_acceptance_criteria(fields)

    # Comments
    comments_data = (fields.get("comment") or {}).get("comments") or []
    comments_text = ""
    if comments_data:
        lines = []
        for c in comments_data[-10:]:  # last 10 comments
            author = (c.get("author") or {}).get("displayName", "User")
            body_obj = c.get("body") or {}
            body = _extract_text_from_adf(body_obj).strip()
            if body:
                lines.append(f"**{author}:** {body}")
        if lines:
            comments_text = "\n\n### Comments:\n" + "\n\n".join(lines)

    # Attachments
    attachments: list[dict[str, Any]] = fields.get("attachment") or []
    attachments_text = ""
    if attachments:
        att_lines = [
            f"- [{a.get('filename', '')}]({a.get('content', '')})" for a in attachments[:10]
        ]
        attachments_text = "\n\n### Attachments:\n" + "\n".join(att_lines)

    return (
        f"## Jira Issue: {issue_key}\n\n"
        f"**Summary:** {summary}\n"
        f"**Type:** {issue_type} | **Status:** {status} | **Priority:** {priority}\n"
        f"**Reporter:** {reporter} | **Assignee:** {assignee}\n"
        f"**Labels:** {', '.join(labels) if labels else 'none'}\n\n"
        f"### Description:\n{description}"
        + (f"\n\n### Acceptance Criteria:\n{acceptance_criteria}" if acceptance_criteria else "")
        + comments_text
        + attachments_text
    )


# ---------------------------------------------------------------------------
# Write-back operations
# ---------------------------------------------------------------------------


async def post_jira_comment(issue_key: str, body_text: str) -> bool:
    """Post a plain-text comment to a Jira issue using ADF format.

    Returns True on success.
    """
    if not _configured():
        logger.warning("Jira not configured — cannot post comment to %s", issue_key)
        return False

    url = f"{_base()}/rest/api/3/issue/{issue_key}/comment"
    payload = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": body_text}],
                }
            ],
        }
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.post(url, auth=_auth(), json=payload)
            resp.raise_for_status()
            return True
        except Exception:
            logger.warning("Failed to post comment to Jira issue %s", issue_key, exc_info=True)
            return False


async def transition_jira_issue(issue_key: str, transition_name: str) -> bool:
    """Move a Jira issue to a new status by transition name (case-insensitive match).

    Fetches available transitions and picks the first one whose name contains
    ``transition_name``. Returns True on success.
    """
    if not _configured():
        logger.warning("Jira not configured — cannot transition %s", issue_key)
        return False

    transitions_url = f"{_base()}/rest/api/3/issue/{issue_key}/transitions"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.get(transitions_url, auth=_auth())
            resp.raise_for_status()
            transitions: list[dict[str, Any]] = resp.json().get("transitions", [])
        except Exception:
            logger.warning("Failed to fetch transitions for %s", issue_key, exc_info=True)
            return False

        target = transition_name.lower()
        matched = next(
            (t for t in transitions if target in t.get("name", "").lower()), None
        )
        if not matched:
            available = [t.get("name") for t in transitions]
            logger.warning(
                "No transition matching %r for %s. Available: %s",
                transition_name,
                issue_key,
                available,
            )
            return False

        try:
            resp = await client.post(
                transitions_url,
                auth=_auth(),
                json={"transition": {"id": matched["id"]}},
            )
            resp.raise_for_status()
            return True
        except Exception:
            logger.warning(
                "Failed to apply transition %r to %s", transition_name, issue_key, exc_info=True
            )
            return False


async def add_remote_link(issue_key: str, url: str, title: str) -> bool:
    """Attach a remote link (e.g. a PR URL) to a Jira issue.

    Returns True on success.
    """
    if not _configured():
        logger.warning("Jira not configured — cannot add remote link to %s", issue_key)
        return False

    link_url = f"{_base()}/rest/api/3/issue/{issue_key}/remotelink"
    payload = {
        "object": {
            "url": url,
            "title": title,
            "icon": {
                "url16x16": "https://github.com/favicon.ico",
                "title": "GitHub",
            },
        }
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.post(link_url, auth=_auth(), json=payload)
            resp.raise_for_status()
            return True
        except Exception:
            logger.warning("Failed to add remote link to %s", issue_key, exc_info=True)
            return False


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------


def verify_jira_webhook_secret(token: str) -> bool:
    """Verify Jira webhook shared secret (simple token equality).

    Jira Cloud webhooks send the secret as a query param (?token=...) or in
    the Authorization header. Use constant-time comparison to avoid timing
    attacks. Returns True when the secret matches or when JIRA_WEBHOOK_SECRET
    is not set (open for local dev only — warn loudly).
    """
    import hmac as _hmac

    if not JIRA_WEBHOOK_SECRET:
        logger.warning(
            "JIRA_WEBHOOK_SECRET is not set — accepting all Jira webhooks (dev mode only)"
        )
        return True
    return _hmac.compare_digest(JIRA_WEBHOOK_SECRET.encode(), token.encode())
