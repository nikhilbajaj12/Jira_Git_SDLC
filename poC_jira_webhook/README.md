# Jira → Open SWE PoC

FastAPI webhook that connects Jira ticket creation to the open-swe LangGraph agent.

## Flow

1. Jira sends a webhook to `POST /webhook/jira` when an issue is created
2. The webhook checks for the `ai-ready` label and a project-to-repo mapping
3. The Jira summary & description are formatted into an agent prompt
4. The open-swe agent is dispatched via the LangGraph SDK (`dispatch_agent_run`)
5. The adapter polls thread metadata for the PR URL
6. The Jira ticket is updated with a comment, remote link, and status transition

## Run

```bash
cp .env.example .env
# edit .env with your credentials

uvicorn poC_jira_webhook.jira_webhook:app --reload --port 8001
```

## Environment

| Variable | Required | Description |
|---|---|---|
| `JIRA_URL` | Yes | Jira Cloud instance URL |
| `JIRA_EMAIL` | Yes | Jira user email |
| `JIRA_API_TOKEN` | Yes | Jira API token |
| `GITHUB_TOKEN` | Yes | PAT with `repo` scope |
| `OPENAI_API_KEY` | One of | OpenAI API key |
| `ANTHROPIC_API_KEY` | or this | Anthropic API key |
| `LANGGRAPH_URL` | No | LangGraph runtime URL (default: `http://localhost:2024`) |
| `LANGSMITH_API_KEY` | No | LangSmith tracing |
| `JIRA_PROJECT_REPO_MAP` | No | Override project→repo mapping |
| `ALLOWED_JIRA_PROJECTS` | No | Comma-separated allowlist |
