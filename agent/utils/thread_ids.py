import hashlib
import uuid


def generate_thread_id_from_slack_thread(channel_id: str, thread_ts: str) -> str:
    """Generate a deterministic thread ID from a Slack thread identifier."""
    composite = f"{channel_id}:{thread_ts}"
    md5_hex = hashlib.md5(composite.encode("utf-8")).hexdigest()
    return str(uuid.UUID(hex=md5_hex))


def generate_thread_id_from_jira_issue(issue_key: str) -> str:
    """Generate a deterministic thread ID from a Jira issue key (e.g. 'PROJ-123')."""
    hash_hex = hashlib.sha256(f"jira-issue:{issue_key}".encode()).hexdigest()
    return str(uuid.UUID(hex=hash_hex[:32]))
