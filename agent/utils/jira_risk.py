"""Heuristic risk scorer for Jira-triggered agent runs.

Scores a Jira issue to determine whether it represents a high-risk change
that should require human approval (plan mode) before the agent opens a PR.

Risk factors:
- Issue labels containing "high-risk", "breaking", "security", "infra", "database", "migration"
- Issue type is Epic or Bug with high/critical priority
- Description mentions DB migrations, infra changes, or security-sensitive keywords
- More than N comments (lots of discussion = potentially complex/contested change)

Output is a RiskResult dataclass with level ("low" | "medium" | "high") and
a list of human-readable reasons. High-risk runs should be started with
``plan_mode=True`` in the configurable so the agent must produce a plan and
await human approval before any destructive actions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

RiskLevel = Literal["low", "medium", "high"]

# Keywords in labels that immediately flag high risk
_HIGH_RISK_LABELS = frozenset(
    {
        "high-risk",
        "breaking-change",
        "breaking",
        "security",
        "infrastructure",
        "infra",
        "database",
        "migration",
        "data-migration",
        "production",
        "prod",
        "critical",
        "hotfix",
    }
)

# Keywords in free text that suggest elevated risk
_HIGH_RISK_TEXT_PATTERNS = [
    r"\bdrop\s+table\b",
    r"\bdelete\s+from\b",
    r"\balter\s+table\b",
    r"\bmigrat",
    r"\bschema\s+change",
    r"\bbreaking\s+change",
    r"\bremove\s+api",
    r"\bdeprecate",
    r"\bauth(entication|orization)?\b",
    r"\bsecret\b",
    r"\btoken\b",
    r"\bpermission",
    r"\benv(ironment)?\s+var",
    r"\binfrastructure\b",
    r"\bterraform\b",
    r"\bkubernetes\b",
    r"\bk8s\b",
    r"\bdeploy(ment)?\b",
]

_MEDIUM_RISK_LABELS = frozenset(
    {
        "refactor",
        "api-change",
        "performance",
        "dependency-update",
    }
)

# High priority names from Jira
_CRITICAL_PRIORITIES = frozenset({"highest", "critical", "blocker"})
_HIGH_PRIORITIES = frozenset({"high"})


@dataclass
class RiskResult:
    level: RiskLevel
    reasons: list[str] = field(default_factory=list)
    plan_mode_recommended: bool = False


def _extract_text(fields: dict[str, Any]) -> str:
    """Pull description + comment text from Jira fields for keyword scanning."""
    from .jira import _extract_text_from_adf  # local import to avoid circular

    parts: list[str] = []
    desc = fields.get("description")
    if desc:
        parts.append(_extract_text_from_adf(desc))
    comments = (fields.get("comment") or {}).get("comments") or []
    for c in comments:
        body = c.get("body")
        if body:
            parts.append(_extract_text_from_adf(body))
    return " ".join(parts).lower()


def score_jira_issue(issue: dict[str, Any]) -> RiskResult:
    """Analyse a Jira issue dict and return a RiskResult.

    The issue dict is the raw Jira REST API response (with ``fields`` key).
    """
    fields = issue.get("fields") or {}
    reasons: list[str] = []
    score = 0  # accumulate points; ≥3 = high, ≥1 = medium

    # --- Labels -------------------------------------------------------
    labels: list[str] = [lbl.lower() for lbl in (fields.get("labels") or [])]
    matched_high = _HIGH_RISK_LABELS.intersection(labels)
    if matched_high:
        reasons.append(f"High-risk labels: {', '.join(sorted(matched_high))}")
        score += 3

    matched_medium = _MEDIUM_RISK_LABELS.intersection(labels)
    if matched_medium:
        reasons.append(f"Medium-risk labels: {', '.join(sorted(matched_medium))}")
        score += 1

    # --- Issue type ---------------------------------------------------
    issue_type = (fields.get("issuetype") or {}).get("name", "").lower()
    if issue_type == "epic":
        reasons.append("Issue type is Epic (large scope)")
        score += 1

    # --- Priority -----------------------------------------------------
    priority_name = (fields.get("priority") or {}).get("name", "").lower()
    if priority_name in _CRITICAL_PRIORITIES:
        reasons.append(f"Critical/blocker priority: {priority_name}")
        score += 2
    elif priority_name in _HIGH_PRIORITIES:
        reasons.append("High priority issue")
        score += 1

    # --- Text keyword scan -------------------------------------------
    full_text = _extract_text(fields)
    matched_patterns = [
        p for p in _HIGH_RISK_TEXT_PATTERNS if re.search(p, full_text, re.IGNORECASE)
    ]
    if matched_patterns:
        reasons.append(
            f"Description/comments mention high-risk patterns ({len(matched_patterns)} matches)"
        )
        score += len(matched_patterns)

    # --- Comment volume (contested/complex) ---------------------------
    comment_count = (fields.get("comment") or {}).get("total", 0)
    if comment_count >= 10:
        reasons.append(f"High discussion volume ({comment_count} comments)")
        score += 1

    # --- Determine level ----------------------------------------------
    if score >= 3:
        level: RiskLevel = "high"
    elif score >= 1:
        level = "medium"
    else:
        level = "low"

    return RiskResult(
        level=level,
        reasons=reasons,
        plan_mode_recommended=(level == "high"),
    )
