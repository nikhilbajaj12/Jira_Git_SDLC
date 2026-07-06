from typing import Any

from ..utils.jira import transition_jira_issue


async def jira_transition(issue_key: str, transition_name: str) -> dict[str, Any]:
    """Move a Jira issue to a new workflow status.

    Use this tool to update the Jira ticket status as work progresses.

    **When to use:**
    - After opening a draft PR: transition to "In Review".
    - When implementation is complete and tests pass: transition to "Done" or "Resolved".
    - When blocked: transition to "Blocked" or "On Hold".

    The transition is matched case-insensitively by name substring, so
    "In Review", "in review", and "review" all work for a transition named
    "In Review".

    Args:
        issue_key: The Jira issue key, e.g. "PROJ-123".
        transition_name: Name (or partial name) of the target workflow transition,
            e.g. "In Review", "Done", "In Progress".

    Returns:
        Dictionary with 'success' (bool) and 'transition_name' keys.
    """
    success = await transition_jira_issue(issue_key, transition_name)
    return {"success": success, "transition_name": transition_name}
