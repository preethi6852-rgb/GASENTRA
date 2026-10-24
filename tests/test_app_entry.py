"""app.py is the single entry point: it must wire the API and the dashboard together."""
import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent


def _entry():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return importlib.import_module("app")


def test_entry_point_serves_dashboard_and_api_from_one_app():
    c = TestClient(_entry().app)
    assert "GASENTRA" in c.get("/").text
    assert c.get("/api/health").json()["ok"] is True
    assert c.get("/api/results").status_code == 200


def test_entry_point_project_check_passes_and_free_port_is_found():
    m = _entry()
    m.check_project()
    assert 8000 <= m.free_port("127.0.0.1", 8000) < 8020
