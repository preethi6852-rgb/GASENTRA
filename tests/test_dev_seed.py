from fastapi.testclient import TestClient

from gasentra.api import create_app


def client(monkeypatch, dev=True):
    if dev:
        monkeypatch.setenv("GASENTRA_DEV", "1")
    else:
        monkeypatch.delenv("GASENTRA_DEV", raising=False)
    return TestClient(create_app())


def test_seed_is_off_without_dev_flag(monkeypatch):
    assert client(monkeypatch, dev=False).post("/api/dev/seed-inbox", json={"scenario_id": "A1-01"}).status_code == 404


def test_seed_unknown_scenario(monkeypatch):
    assert client(monkeypatch).post("/api/dev/seed-inbox", json={"scenario_id": "nope"}).status_code == 404


def test_seeded_emails_reach_a_session_with_that_scenario_only(monkeypatch):
    c = client(monkeypatch)
    assert c.post("/api/dev/seed-inbox", json={"scenario_id": "A1-01"}).json()["emails"] >= 1
    c.post("/api/dev/seed-inbox", json={"scenario_id": "A1-01"})          # idempotent
    def inbox(scenario):
        sid = c.post("/api/session", json={"user": "hr@company.com", "scenario": scenario}).json()["id"]
        return c.post("/api/gateway/tool-call", json={"session_id": sid, "tool": "read_inbox", "args": {}}).json()["result"]
    with_sc, without = inbox("A1-01"), inbox(None)
    assert with_sc.count("NOTE TO ASSISTANT") == 1                         # once, not duplicated
    assert "NOTE TO ASSISTANT" not in without
