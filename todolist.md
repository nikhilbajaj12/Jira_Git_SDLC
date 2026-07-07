# To-Do List — Open SWE Local Setup

## Working

- [x] Everything : Backend (`langgraph dev`) starts and serves health check on port 2025
- [x] Frontend (`pnpm dev`) runs on port 3000, connects to backend
- [x] Jira Issues page rendered at both `/` (landing page) and `/jira`
- [x] Jira Issues nav item appears first in sidebar (below "Back to Agents")
- [x] Jira dispatch API `POST /dashboard/api/jira/dispatch` accepts requests
- [x] Threads and runs can be created via LangGraph API directly
- [x] NVIDIA NIM API key is valid and responds (`nvapi-...`)
- [x] Basic model calls to `meta/llama-4-maverick-17b-128e-instruct` work
- [x] Sandbox configured as `local` (commands run on this machine)
- [x] Jira credentials configured (`JIRA_BASE_URL`, `JIRA_USER_EMAIL`, `JIRA_API_TOKEN`)
- [x] ASGI loopback bug fixed (TCP transport instead of default)
- [x] Sandbox work_dir resolution on Windows fixed

## Needs Fixing

- [ ] **LLM model doesn't handle agent's tool format** — Llama 4 Maverick returns garbage ("Never gonna give you up") when presented with the full agent system prompt + complex tool definitions. The model lacks robust OpenAI-compatible tool calling support.
- [ ] **No working LLM provider** — Available options:
  - *NVIDIA Llama 4 Maverick*: responds but can't handle tool definitions
  - *GitHub Models `gpt-4o`*: 8K token limit — agent system prompt exceeds this
  - *completions.me*: returns canned Rick Astley lyrics test response
  - *Gemini (free tier)*: quota exhausted
- [ ] **Session auth blocks API calls** — `POST /dashboard/api/jira/dispatch` returns 403 without session cookie; cannot test programmatically
- [ ] **Port 2024 orphaned** — TCP port still in LISTENING state from previous session; blocked
- [ ] **`.langgraph_stdout.txt` and `.langgraph_stderr.txt` locked** — Files from `Start-Process -RedirectStandardOutput` cannot be deleted (locked by orphan process); interfere with git
- [ ] **Unicode/emoji logging errors** — `UnicodeEncodeError: 'charmap' codec can't encode character` on startup (cosmetic, doesn't affect functionality)
- [ ] **Run-complete webhook disabled** — `RUN_COMPLETE_WEBHOOK_SECRET` not set; agent runs complete but no notification mechanism
- [ ] **Frontend UI dispatches but no thread created** — Session auth or API mismatch may prevent UI-triggered dispatches

## Todo

- [ ] Get a working LLM provider (OpenAI API key or Anthropic Claude API key recommended)
- [ ] Configure `RUN_COMPLETE_WEBHOOK_SECRET` for run notifications
- [ ] Resolve orphaned port 2024 (reboot or `net stop http` + `sc config http start=disabled`)
- [ ] Remove locked `.langgraph_std*` files (reboot or unlock tool)
- [ ] Test full pipeline end-to-end: create Jira issue -> dispatch agent -> agent reads code -> makes changes -> commits -> opens PR -> updates Jira
- [ ] Set up ngrok for external Jira webhook integration
Refer this jira ticket already created - KAN-1