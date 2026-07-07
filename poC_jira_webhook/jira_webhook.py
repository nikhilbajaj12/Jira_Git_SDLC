from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .jira_adapter import PROJECT_REPO_MAP, run_agent_and_create_pr

logger = logging.getLogger(__name__)

app = FastAPI(title="Jira -> Open SWE Webhook")

# ── Constants ────────────────────────────────────────────────────────

ALLOWED_JIRA_PROJECTS: list[str] = [
    p.strip()
    for p in os.environ.get("ALLOWED_JIRA_PROJECTS", "").split(",")
    if p.strip()
]


# ── Webhook endpoint ─────────────────────────────────────────────────


@app.post("/webhook/jira")
async def jira_webhook(request: Request) -> JSONResponse:
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "reason": "Invalid JSON"}, status_code=400)

    webhook_event = payload.get("webhookEvent", "")
    if webhook_event != "jira:issue_created":
        return JSONResponse({"status": "ignored", "reason": f"Unhandled event: {webhook_event}"})

    issue = payload.get("issue", {})
    issue_key = issue.get("key", "")
    if not issue_key:
        return JSONResponse({"status": "error", "reason": "No issue key"}, status_code=400)

    fields = issue.get("fields", {}) or {}
    labels: list[str] = [l.lower() for l in (fields.get("labels") or [])]

    if "ai-ready" not in labels:
        logger.debug("Ignoring %s — missing 'ai-ready' label", issue_key)
        return JSONResponse(
            {"status": "ignored", "reason": "Issue does not have 'ai-ready' label"}
        )

    project_key = issue_key.split("-")[0]
    repo_url = PROJECT_REPO_MAP.get(project_key)
    if not repo_url:
        logger.warning("No repo mapping for project %s (issue %s)", project_key, issue_key)
        return JSONResponse(
            {"status": "error", "reason": f"No repo configured for project {project_key}"},
            status_code=404,
        )

    summary = fields.get("summary", "")
    description_obj = fields.get("description") or {}
    description = _extract_text_from_adf(description_obj) or ""

    ticket_data = {
        "key": issue_key,
        "summary": summary,
        "description": description,
    }

    asyncio.create_task(run_agent_and_create_pr(ticket_data, repo_url))

    return JSONResponse({"status": "ok", "issue_key": issue_key})


# ── Health check ─────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


# ── ADF text extraction ──────────────────────────────────────────────


def _extract_text_from_adf(node: Any, depth: int = 0) -> str:
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
