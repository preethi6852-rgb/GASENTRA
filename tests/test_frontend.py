"""The dashboard is served by the same app, from the same origin as the API."""
import re
from pathlib import Path

from fastapi.testclient import TestClient

from gasentra.api import create_app

FE = Path(__file__).resolve().parent.parent / "frontend"


def test_every_page_is_served_and_loads_its_assets():
    c = TestClient(create_app())
    for page in ["", "index.html", "session.html", "approvals.html", "audit.html", "frozen.html",
                 "results.html", "settings.html"]:
        r = c.get("/" + page)
        assert r.status_code == 200 and "GASENTRA" in r.text, page
    assert c.get("/css/style.css").status_code == 200
    assert c.get("/js/common.js").status_code == 200 and c.get("/js/boot.js").status_code == 200


def test_every_page_references_files_that_exist():
    for html in FE.glob("*.html"):
        for ref in re.findall(r'(?:src|href)="([^"]+)"', html.read_text(encoding="utf-8")):
            assert (FE / ref).exists(), (html.name, ref)


def test_every_page_link_in_the_sidebar_exists():
    boot = (FE / "js" / "boot.js").read_text(encoding="utf-8")
    for target in re.findall(r"'([a-z]+\.html)'", boot):
        assert (FE / target).exists(), target


def test_api_still_wins_over_the_static_mount():
    c = TestClient(create_app())
    assert c.get("/api/health").json()["ok"] is True
    assert c.get("/docs").status_code == 200


def test_health_exposes_the_denial_limit():
    assert TestClient(create_app()).get("/api/health").json()["denial_limit"] == 3


def test_run_evaluation_from_the_dashboard_returns_fresh_results():
    c = TestClient(create_app())
    r = c.post("/api/results/run").json()
    assert [x["id"] for x in r["configs"]] == ["no_guard", "pattern_dlp", "gasentra_careful", "gasentra_careless"]
    assert r["configs"][2]["attacks"]["silent"] == 0
    assert c.get("/api/results").json()["configs"][0]["attacks"]["total"] == r["configs"][0]["attacks"]["total"]


def test_no_invented_sample_data_is_left_in_the_frontend():
    js = (FE / "js" / "common.js").read_text(encoding="utf-8")
    for fake in ("sarah@company.com", "Sample numbers", "#S-003", "AP-s1"):
        assert fake not in js, fake
