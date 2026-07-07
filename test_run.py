import asyncio
import os

os.environ["LANGGRAPH_URL"] = "http://localhost:2024"
from langgraph_sdk import get_client


async def test():
    c = get_client()

    # Just create a simple run
    thread = await c.threads.create()
    tid = thread.get("thread_id")
    print(f"Created thread: {tid}")

    run = await c.runs.create(
        tid,
        "agent",
        input={"messages": [{"role": "user", "content": "Just say hello and nothing else."}]},
        config={"configurable": {"__is_for_execution__": True}},
        multitask_strategy="interrupt",
        durability="sync",
        if_not_exists="create",
    )
    print(f"Run result type: {type(run).__name__}")
    if isinstance(run, dict):
        print(f"  run_id={run.get('run_id')} status={run.get('status')}")
    else:
        print(f"  unexpected type: {run}")

    # Poll
    for i in range(12):
        await asyncio.sleep(5)
        runs = await c.threads.get_runs(tid)
        print(f"  [{i*5}s] Runs: {len(runs)}")
        for r in runs:
            rid = r["run_id"][:8]
            st = r["status"]
            et = r.get("error_type", "")
            em = r.get("error_message", "")
            print(f"    run={rid} status={st} err={et} msg={em}")
        if runs and runs[0]["status"] not in ("pending", "running"):
            break

    # Check state
    state = await c.threads.get_state(tid)
    msgs = state.get("values", {}).get("messages", [])
    print(f"Messages: {len(msgs)}")
    for m in msgs[:3]:
        role = m.get("role", "?")
        content = m.get("content", "")
        if isinstance(content, str):
            print(f"  [{role}] {content[:120]}")
        elif isinstance(content, list):
            print(f"  [{role}] <{len(content)} blocks>")


asyncio.run(test())
