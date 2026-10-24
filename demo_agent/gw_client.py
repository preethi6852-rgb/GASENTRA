"""Thin HTTP client for the GASENTRA gateway. No LLM code lives here.

Rules this file enforces:
  * allow             -> the model gets the tool result.
  * anything else     -> the model gets the gateway's agent_message and nothing more.
  * network or HTTP trouble -> "Tool unavailable". The call never runs locally (fail closed).
The rule, reason, evidence, risk and approval id are never returned from this module.
"""
import os
from collections import namedtuple

import requests

TIMEOUT = 10
UNAVAILABLE = "Tool unavailable"
KNOWN = ("allow", "block", "hold", "frozen")
FALLBACK = {"block": "This action is not permitted.",
            "hold": "This action is waiting for human approval.",
            "frozen": "Session is frozen; call rejected."}

# decision: allow | block | hold | frozen | error.   text: the only thing the model may see.
Outcome = namedtuple("Outcome", "decision text")


class GatewayClient:
    def __init__(self, url=None):
        self.base = (url or os.environ.get("GATEWAY_URL") or "http://127.0.0.1:8000").rstrip("/")

    def _post(self, path, body):
        r = requests.post(self.base + path, json=body, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            raise ValueError("unexpected response")
        return data

    def start(self, user, scenario=None):
        """Opens a session and returns its id."""
        body = {"user": user}
        if scenario:
            body["scenario"] = scenario
        return self._post("/api/session", body)["id"]

    def user_message(self, sid, text):
        """Records a real user message (provenance). Returns True on success."""
        try:
            return bool(self._post("/api/gateway/user-message", {"session_id": sid, "text": text}).get("ok"))
        except Exception:
            return False

    def tool_call(self, sid, tool, args):
        try:
            r = self._post("/api/gateway/tool-call", {"session_id": sid, "tool": tool, "args": args or {}})
            decision = r.get("decision")
            if decision == "allow":
                result = r.get("result")
                return Outcome("allow", "OK" if result in (None, "") else str(result))
            if decision in KNOWN:
                return Outcome(decision, r.get("agent_message") or FALLBACK[decision])
        except Exception:
            pass
        return Outcome("error", UNAVAILABLE)

    def seed_inbox(self, scenario_id):
        """Dev only: asks the gateway to store a scenario's emails. Returns (ok, message)."""
        try:
            r = requests.post(self.base + "/api/dev/seed-inbox", json={"scenario_id": scenario_id}, timeout=TIMEOUT)
        except Exception:
            return False, "Can't reach the gateway at %s. Is the server running?" % self.base
        if r.status_code == 200:
            return True, ""
        if r.status_code == 404:
            return False, "Seeding refused. Start the gateway with GASENTRA_DEV=1 and use a known scenario id."
        return False, "Seeding failed (HTTP %d)." % r.status_code
