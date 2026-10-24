"""Executors run an agent's proposed calls under different setups: no guard, pattern DLP, or GASENTRA."""
import re

from .config import Config
from .gateway import GENERIC_REFUSAL, Gateway
from .store import Store
from .tools import execute_and_record


class GatewayExecutor:
    name = "gasentra"

    def __init__(self, gateway, user="hr@company.com", scenario=None):
        self.gw, self.user_name, self.scenario = gateway, user, scenario
        self.session = None
        self.sessions = []

    @property
    def sid(self):
        return self.session["id"]

    def start(self):
        self.session = self.gw.start_session(self.user_name, self.scenario)
        self.sessions.append(self.session["id"])
        return self.session

    def reset(self):
        """Context reset: a brand-new session (taint and denial count start fresh; stored labels stay)."""
        return self.start()

    def user(self, text):
        return self.gw.user_message(self.sid, text)

    def call(self, tool, args):
        return self.gw.tool_call(self.sid, tool, args)

    def resolve(self, aid, approve):
        return self.gw.resolve_approval(aid, approve, resolver="scripted approver")

    def approval_state(self, aid):
        return self.gw.store.get_approval(aid)


class UnguardedExecutor:
    """Baseline 1: every proposed call simply runs."""
    name = "no_guard"

    def __init__(self, store, cfg=None, user="hr@company.com", scenario=None):
        self.store, self.cfg = store, cfg or Config()
        self.user_name, self.scenario = user, scenario
        self.session_id = None
        self.sessions = []

    @property
    def sid(self):
        return self.session_id

    def start(self):
        self.session_id = self.store.create_session(self.user_name, self.scenario)
        self.sessions.append(self.session_id)

    def reset(self):
        self.start()

    def user(self, text):
        self.store.add_user_message(self.session_id, text)

    def _run(self, tool, args):
        r = execute_and_record(self.store, self.cfg, self.session_id, tool, args)
        return {"decision": "allow", "result": r["text"], "label": r["label"], "rule": "NO_GUARD",
                "agent_message": r["text"], "frozen": False}

    def call(self, tool, args):
        return self._run(tool, args)

    def resolve(self, aid, approve):
        raise NotImplementedError

    def approval_state(self, aid):
        return None


# Our own simplified emulation of gateway-style pattern DLP (not the real products).
DLP_PATTERNS = {
    "PHONE": re.compile(r"\b[6-9]\d{9}\b"),
    "EMAIL_IN_BODY": re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
    "CANDIDATE_ID": re.compile(r"\bcand-\d{3}\b", re.I),
    "SALARY_NUMBER": re.compile(r"salary[^\d]{0,20}\d{4,7}", re.I),
    "CURRENCY_AMOUNT": re.compile(r"(?:rs\.?|inr|₹)\s?\d", re.I),
}


class PatternDLPExecutor(UnguardedExecutor):
    """Baseline 2: blocks outbound calls whose content matches sensitive-looking patterns."""
    name = "pattern_dlp"

    def call(self, tool, args):
        meta = self.cfg.tools.get(tool, {})
        if meta.get("kind") == "outbound":
            if "content_from_file" in meta:
                path = str(args.get(meta["content_from_file"], ""))
                res = self.store.get_resource(path)
                content = res["content"] if res else ""
                if path.startswith("candidates/"):
                    import json
                    cand = self.store.get_candidate(path.split("/", 1)[1].replace(".json", ""))
                    content = json.dumps(cand, indent=2) if cand else ""
            else:
                content = " ".join(str(args.get(a, "")) for a in meta.get("content_args", []))
            for name, rx in DLP_PATTERNS.items():
                if rx.search(content):
                    return {"decision": "block", "result": None, "label": None, "rule": "DLP_" + name,
                            "agent_message": GENERIC_REFUSAL, "frozen": False}
        return self._run(tool, args)
