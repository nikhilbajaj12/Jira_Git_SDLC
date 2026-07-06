from typing import Any

from ..utils.jira import post_jira_comment


async def jira_comment(issue_key: str, comment_body: str) -> dict[str, Any]:
    """Post a comment to a Jira issue.

    Use this tool to communicate progress, completion, and PR links back to
    the Jira ticket so stakeholders can track the work.

    **When to use:**
    - After opening a draft PR: post the PR link so stakeholders see it in Jira.
    - When a task is blocked: post an explanation requesting clarification.
    - When answering a question triggered by a Jira comment.

    Args:
        issue_key: The Jira issue key, e.g. "PROJ-123".
        comment_body: Plain-text comment to post. Markdown is rendered in Jira Cloud.

    Returns:
        Dictionary with 'success' (bool) key.
    """
    success = await post_jira_comment(issue_key, comment_body)
    return {"success": success}
