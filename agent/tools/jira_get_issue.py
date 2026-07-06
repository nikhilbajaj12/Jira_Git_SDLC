from typing import Any

from ..utils.jira import fetch_jira_issue, format_jira_issue_for_prompt


async def jira_get_issue(issue_key: str) -> dict[str, Any]:
    """Fetch full details of a Jira issue mid-run.

    Use this tool when you need to re-read the Jira ticket during a run, for
    example to check acceptance criteria, read the latest comments for
    clarification, or confirm the current status.

    Args:
        issue_key: The Jira issue key, e.g. "PROJ-123".

    Returns:
        Dictionary with:
        - 'found' (bool): whether the issue was fetched successfully
        - 'formatted' (str): human-readable summary for the agent
        - 'raw' (dict | None): raw Jira API response (fields, status, etc.)
    """
    issue = await fetch_jira_issue(issue_key)
    if not issue:
        return {"found": False, "formatted": f"Could not fetch Jira issue {issue_key}", "raw": None}
    return {
        "found": True,
        "formatted": format_jira_issue_for_prompt(issue),
        "raw": issue,
    }
