"""FastAPI app: the gateway API, the demo runner and (if present) the dashboard in /frontend."""
import json
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .cases import ALL, DEMO_IDS
from .config import ROOT, Config
from .executors import GatewayExecutor
from .gateway import Gateway
from .llm_agent import LLMAgent, LLMError, llm_status, make_client_from_env
from .scripted import ScenarioRunner
from .store import Store

RESULTS = ROOT / "harness" / "results" / "results.json"


class SessionIn(BaseModel):
    user: str = "hr@company.com"
    scenario: Optional[str] = None   # lets a session see that scenario's seeded emails


class SeedIn(BaseModel):
    scenario_id: str


class UserMessageIn(BaseModel):
    session_id: str
    text: str


class ToolCallIn(BaseModel):
    session_id: str
    tool: str
    args: dict = {}


class ApprovalIn(BaseModel):
    approve: bool


class AgentChatIn(BaseModel):
    text: str
    session_id: str = None
    scenario_id: str = None     # loads that scenario's inbox (e.g. a poisoned email) for the real agent
    style: str = "default"      # default | naive


class DemoStartIn(BaseModel):
    scenario_id: str
    approver: str = "pause"   # pause | approve | reject


def create_app(db_path=None, llm_transport=None):
    db_path = db_path or os.environ.get("GASENTRA_DB", ":memory:")
    cfg = Config()
    store = Store(db_path)
    gw = Gateway(store, cfg)
    runs = {}   # demo runs kept in memory
    agents = {}  # real-LLM agents kept in memory, keyed by session id

    app = FastAPI(title="GASENTRA gateway", version="0.1")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.store, app.state.gateway = store, gw

    def wrap(fn):
        try:
            return fn()
        except KeyError as e:
            raise HTTPException(404, str(e))
        except ValueError as e:
            raise HTTPException(409, str(e))

    @app.get("/api/health")
    def health():
        return {"ok": True, "tools": list(cfg.tools), "denial_limit": cfg.policy["denial_limit"]}

    # ---- gateway ----
    @app.post("/api/session")
    def new_session(body: SessionIn):
        return gw.start_session(body.user, body.scenario)

    @app.post("/api/gateway/user-message")
    def user_message(body: UserMessageIn):
        return wrap(lambda: gw.user_message(body.session_id, body.text))

    @app.post("/api/gateway/tool-call")
    def tool_call(body: ToolCallIn):
        return wrap(lambda: gw.tool_call(body.session_id, body.tool, body.args))


    # ---- dev only: store a scenario's emails so an outside agent's read_inbox returns them ----
    @app.post("/api/dev/seed-inbox")
    def dev_seed_inbox(body: SeedIn):
        if os.environ.get("GASENTRA_DEV") != "1":
            raise HTTPException(404, "Not found")
        sc = ALL.get(body.scenario_id)
        if not sc:
            raise HTTPException(404, "Unknown scenario")
        if not store._all("SELECT 1 FROM emails WHERE scenario=? LIMIT 1", (sc["id"],)):
            for e in sc["inbox"]:
                store.add_email(e["sender"], e["subject"], e["body"], scenario=sc["id"])
        return {"scenario": sc["id"], "emails": len(sc["inbox"])}

    # ---- approvals ----
    @app.get("/api/approvals")
    def approvals(status: str = None):
        return store.list_approvals(status)

    @app.post("/api/approvals/{aid}")
    def resolve(aid: str, body: ApprovalIn):
        return wrap(lambda: gw.resolve_approval(aid, body.approve))

    # ---- sessions ----
    @app.get("/api/sessions")
    def sessions(frozen: bool = None):
        return store.list_sessions(frozen)

    @app.get("/api/sessions/{sid}")
    def session(sid: str):
        s = store.get_session(sid)
        if not s:
            raise HTTPException(404, "Unknown session")
        return dict(s, user_messages=store.user_texts(sid), outputs=[
            {k: o[k] for k in ("tool", "resource", "label", "ts")} for o in store.outputs(sid)])

    @app.post("/api/sessions/{sid}/unfreeze")
    def unfreeze(sid: str):
        return wrap(lambda: gw.unfreeze(sid))

    # ---- audit ----
    @app.get("/api/audit")
    def audit(session_id: str = None, limit: int = 200):
        return store.list_audit(session_id, limit)

    @app.get("/api/sent")
    def sent(session_id: str = None):
        return store.sent_items(session_id)

    # ---- demo scenarios ----
    @app.get("/api/scenarios")
    def scenarios():
        return [{"id": i, "title": ALL[i]["title"], "kind": ALL[i]["kind"], "class": ALL[i]["class"]}
                for i in DEMO_IDS]

    def _state(run_id):
        r = runs[run_id]
        sid = r["ex"].sid
        return {"run_id": run_id, "scenario": r["sc"]["id"], "title": r["sc"]["title"], "session_id": sid,
                "done": r["runner"].done, "paused": r["runner"].pending is not None,
                "pending_approval": (r["runner"].pending or {}).get("resp", {}).get("approval_id"),
                "records": r["runner"].records, "session": store.get_session(sid),
                "audit": list(reversed(store.list_audit(sid)))}

    @app.post("/api/demo/start")
    def demo_start(body: DemoStartIn):
        sc = ALL.get(body.scenario_id)
        if not sc:
            raise HTTPException(404, "Unknown scenario")
        for e in sc["inbox"]:
            store.add_email(e["sender"], e["subject"], e["body"], scenario=sc["id"])
        ex = GatewayExecutor(gw, scenario=sc["id"])
        ex.start()
        runner = ScenarioRunner(sc, ex, cfg, approver=body.approver).run()
        run_id = "R-" + uuid.uuid4().hex[:6]
        runs[run_id] = {"sc": sc, "ex": ex, "runner": runner}
        return _state(run_id)

    @app.post("/api/demo/{run_id}/resume")
    def demo_resume(run_id: str):
        if run_id not in runs:
            raise HTTPException(404, "Unknown run")
        runs[run_id]["runner"].resume()
        return _state(run_id)

    @app.get("/api/demo/{run_id}")
    def demo_state(run_id: str):
        if run_id not in runs:
            raise HTTPException(404, "Unknown run")
        return _state(run_id)

    # ---- real LLM agent (every call still goes through the gateway) ----
    @app.get("/api/agent/status")
    def agent_status():
        return llm_status()

    def _agent_out(agent, out):
        return dict(out, session_id=agent.sid, audit=list(reversed(store.list_audit(agent.sid))))

    @app.post("/api/agent/chat")
    def agent_chat(body: AgentChatIn):
        try:
            if body.session_id and body.session_id in agents:
                agent = agents[body.session_id]
            else:
                client = make_client_from_env(llm_transport)
                sc = ALL.get(body.scenario_id) if body.scenario_id else None
                if body.scenario_id and not sc:
                    raise HTTPException(404, "Unknown scenario")
                if sc:
                    for e in sc["inbox"]:
                        store.add_email(e["sender"], e["subject"], e["body"], scenario=sc["id"])
                sid = gw.start_session(scenario=sc["id"] if sc else None)["id"]
                agent = agents[sid] = LLMAgent(gw, client, sid, style=body.style)
            return _agent_out(agent, agent.say(body.text))
        except LLMError as e:
            raise HTTPException(503 if "No LLM configured" in str(e) else 502, str(e))
        except ValueError as e:
            raise HTTPException(409, str(e))

    @app.post("/api/agent/{sid}/resume")
    def agent_resume(sid: str):
        if sid not in agents:
            raise HTTPException(404, "Unknown agent session")
        try:
            return _agent_out(agents[sid], agents[sid].resume())
        except LLMError as e:
            raise HTTPException(502, str(e))

    @app.get("/api/agent/{sid}")
    def agent_state(sid: str):
        if sid not in agents:
            raise HTTPException(404, "Unknown agent session")
        return _agent_out(agents[sid], agents[sid].result())

    # ---- evaluation results ----
    @app.get("/api/results")
    def results():
        if not RESULTS.exists():
            raise HTTPException(404, "Run: python -m harness.run_eval")
        return json.loads(RESULTS.read_text(encoding="utf-8"))

    @app.post("/api/results/run")
    def results_run():
        from harness.run_eval import main as run_eval   # takes a couple of seconds, uses its own in-memory data
        return run_eval()

    # ---- dashboard (static files) ----
    fe = ROOT / "frontend"
    if (fe / "index.html").exists():
        # Mounted last: every /api/* route above is matched first. "/" serves index.html,
        # and /session.html, /css/..., /js/... are served from the frontend folder.
        app.mount("/", StaticFiles(directory=str(fe), html=True), name="frontend")

    return app


app = create_app()
