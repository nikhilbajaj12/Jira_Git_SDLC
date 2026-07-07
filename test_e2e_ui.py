import asyncio
import httpx


async def test():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:2024") as c:
        headers = {
            "Origin": "http://localhost:3000",
            "Content-Type": "application/json",
        }
        body = {
            "repo_owner": "nikhilbajaj12",
            "repo_name": "bfsi_proactive_proposals",
            "summary": "E2E test from UI",
            "description": "Testing end-to-end Jira dispatch flow",
        }
        r = await c.post("/dashboard/api/jira/dispatch", json=body, headers=headers)
        print(f"Status: {r.status_code}")
        print(f"Body: {r.text}")
        if r.status_code != 200:
            return

        data = r.json()
        tid = data["thread_id"]
        print(f"Thread: {tid}")
        print(f"Run ID: {data.get('run_id', '')}")

        # Wait and poll for run
        for i in range(6):
            await asyncio.sleep(10)
            r2 = await c.get(f"/threads/{tid}/runs")
            runs = r2.json()
            print(f"[{(i+1)*10}s] Runs: {len(runs)}")
            for run in runs:
                rid = run["run_id"][:8]
                st = run["status"]
                et = run.get("error_type", "")
                em = run.get("error_message", "")
                print(f"  run={rid} status={st} err={et} msg={em}")
            if runs and runs[0]["status"] not in ("pending", "running"):
                break

        # Check state
        r3 = await c.get(f"/threads/{tid}/state")
        state = r3.json()
        msgs = state.get("values", {}).get("messages", [])
        print(f"Messages: {len(msgs)}")
        for m in msgs[:2]:
            role = m.get("role", "?")
            content = m.get("content", "")
            if isinstance(content, str):
                print(f"  [{role}] {content[:120]}")


asyncio.run(test())
