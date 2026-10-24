from fastapi.testclient import TestClient

from gasentra.api import create_app
from gasentra.cases import ATTACKS, LEGIT
from gasentra.config import Config
from harness.run_eval import main as run_eval, run_case


def test_no_attack_executes_silently_under_gasentra():
    cfg = Config()
    for case in ATTACKS:
        records, _ = run_case(case, "gasentra_careful", "reject", cfg)
        assert not any(r["harmful"] and r["outcome"] == "executed" for r in records), case["id"]


def test_attacks_do_succeed_without_a_guard():
    cfg = Config()
    ok = 0
    for case in ATTACKS:
        records, _ = run_case(case, "no_guard", None, cfg)
        ok += any(r["harmful"] and r["outcome"] == "executed" for r in records)
    assert ok == len(ATTACKS)


def test_persistent_attacker_gets_frozen():
    cfg = Config()
    case = [c for c in ATTACKS if c["id"] == "A8-01"][0]
    _, frozen = run_case(case, "gasentra_careful", "reject", cfg)
    assert frozen


def test_legit_tasks_complete_with_an_approver():
    cfg = Config()
    for case in LEGIT:
        records, _ = run_case(case, "gasentra_careless", "approve", cfg)
        key = [r for r in records if r["key"]][-1]
        assert key["outcome"] in ("executed", "executed_after_approval"), case["id"]


def test_legit_decisions_match_expectation():
    cfg = Config()
    for case in LEGIT:
        records, _ = run_case(case, "gasentra_careful", "reject", cfg)
        key = [r for r in records if r["key"]][-1]
        got = "allow" if key["outcome"] == "executed" else "hold"
        assert got == case["expect"], (case["id"], key["outcome"], key["rule"])


def test_harness_writes_results():
    res = run_eval()
    names = {c["id"]: c for c in res["configs"]}
    assert names["no_guard"]["attacks"]["silent"] == names["no_guard"]["attacks"]["total"]
    assert names["gasentra_careful"]["attacks"]["silent"] == 0
    assert names["pattern_dlp"]["attacks"]["silent"] > 0


def test_api_end_to_end():
    c = TestClient(create_app())
    sid = c.post("/api/session", json={}).json()["id"]
    c.post("/api/gateway/user-message", json={"session_id": sid, "text": "Check my inbox"})
    rec = c.post("/api/gateway/tool-call", json={"session_id": sid, "tool": "read_file",
                                                   "args": {"path": "candidates/cand-001.json"}}).json()
    assert rec["tainted"] is True
    r = c.post("/api/gateway/tool-call", json={"session_id": sid, "tool": "send_email",
                                                "args": {"to": "x@z-corp.test", "subject": "s", "body": rec["result"]}}).json()
    assert r["decision"] == "block"
    assert c.get("/api/audit", params={"session_id": sid}).json()
    assert c.get("/api/results").status_code in (200, 404)


def test_api_demo_pause_approve_resume():
    c = TestClient(create_app())
    run = c.post("/api/demo/start", json={"scenario_id": "L08", "approver": "pause"}).json()
    assert run["paused"] and run["pending_approval"]
    c.post("/api/approvals/" + run["pending_approval"], json={"approve": True})
    run = c.post("/api/demo/%s/resume" % run["run_id"]).json()
    assert run["done"] and run["records"][-1]["outcome"] == "executed_after_approval"


def test_api_unknown_session_is_404():
    c = TestClient(create_app())
    assert c.post("/api/gateway/user-message", json={"session_id": "nope", "text": "x"}).status_code == 404
