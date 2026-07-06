from typing import Any

from ..utils.jira import add_remote_link


async def jira_add_link(issue_key: str, url: str, title: str) -> dict[str, Any]:
    """Attach a remote link to a Jira issue (e.g. a GitHub PR URL).

    Use this tool after opening a pull request to add the PR link directly to
    the Jira issue so it appears in the "Web Links" section, giving stakeholders
    a one-click path from the ticket to the code change.

    Args:
        issue_key: The Jira issue key, e.g. "PROJ-123".
        url: The full URL to attach, e.g. "https://github.com/owner/repo/pull/42".
        title: Human-readable link title, e.g. "Draft PR: Add user auth endpoint".

    Returns:
        Dictionary with 'success' (bool), 'url', and 'title' keys.
    """
    success = await add_remote_link(issue_key, url, title)
    return {"success": success, "url": url, "title": title}
