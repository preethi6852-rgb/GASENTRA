import pytest

from gasentra.gateway import Gateway
from gasentra.store import Store


@pytest.fixture
def gw():
    return Gateway(Store(":memory:"))


@pytest.fixture
def session(gw):
    return gw.start_session()["id"]


def read_record(gw, sid, cid="cand-001"):
    r = gw.tool_call(sid, "read_file", {"path": "candidates/%s.json" % cid})
    assert r["decision"] == "allow"
    return r["result"]
