"""The gateway: every tool call passes through here. The agent proposes, fixed rules decide."""
import json

from .config import Config
from .decision import Decision, decide_field_write, decide_outbound
from .matching import match, numbers_in
from .recipients import user_addresses
from .tools import execute_and_record

GENERIC_REFUSAL = "This action is not permitted."
PENDING_MESSAGE = "This action is waiting for human approval."
FROZEN_MESSAGE = "This session has been suspended."


class Gateway:
    def __init__(self, store, cfg=None):
        self.store = store
        self.cfg = cfg or Config()

    # ---- sessions and user messages ----
    def start_session(self, user="hr@company.com", scenario=None):
        sid = self.store.create_session(user, scenario)
        self.store.audit(sid, "session_start", reason="Session started for %s" % user)
        return self.store.get_session(sid)

    def user_message(self, sid, text):
        self._session(sid)
        self.store.add_user_message(sid, text)
        self.store.audit(sid, "user_message", reason=text[:200], decision="trusted")
        return {"ok": True}

    def _session(self, sid):
        s = self.store.get_session(sid)
        if not s:
            raise KeyError("Unknown session: %s" % sid)
        return s

    # ---- the main entry point ----
    def tool_call(self, sid, tool, args=None):
        s = self._session(sid)
        args = args or {}
        if s["frozen"]:
            self.store.audit(sid, "tool_call", tool, args, tainted=s["tainted"], decision="frozen",
                             rule="SESSION_FROZEN", reason="Session is frozen; call rejected.",
                             denial_count=s["denial_count"], outcome="rejected")
            return self._response("frozen", "SESSION_FROZEN", "Session is frozen; call rejected.",
                                  s, tool, agent_message=FROZEN_MESSAGE)
        meta = self.cfg.tools.get(tool)
        if meta is None:
            d = Decision("block", "UNKNOWN_TOOL", "Tool '%s' is not on the allowlist." % tool)
        else:
            try:
                d = self._evaluate(s, tool, args, meta)
            except Exception as exc:  # fail closed on any error
                d = Decision("block", "POLICY_ERROR", "Error while checking the call (fail closed): %s" % exc)
        return self._apply(s, tool, args, d)

    # ---- evaluation ----
    def _evaluate(self, s, tool, args, meta):
        sid, kind = s["id"], meta["kind"]
        texts = self.store.user_texts(sid)
        if kind == "outbound":
            content = self._outgoing_content(tool, args, meta)
            report = None
            if s["tainted"]:
                fps = [json.loads(o["fingerprint"]) for o in
                       self.store.sensitive_outputs(sid, self.cfg.taint_labels)]
                report = match(content, fps, self.cfg.policy["strong_match_min_chars"],
                               self.cfg.policy["strong_match_min_fields"])
            return decide_outbound(args.get(meta["recipient_arg"]), s["tainted"], report, self.cfg,
                                   user_addresses(texts))
        if kind == "field_write":
            cand = self.store.get_candidate(str(args.get(meta["id_arg"], "")))
            old = cand.get(str(args.get(meta["field_arg"], ""))) if cand else None
            untrusted = set()
            for o in self.store.outputs(sid):
                untrusted |= numbers_in(o["text"])
            return decide_field_write(args, meta, self.cfg, texts, old, untrusted)
        return Decision("allow", "SAFE_CALL", "Read or write of a non-protected resource.")

    def _outgoing_content(self, tool, args, meta):
        if "content_from_file" in meta:
            path = str(args.get(meta["content_from_file"], ""))
            res = self.store.get_resource(path)
            if res:
                return res["content"]
            if path.startswith("candidates/"):
                cand = self.store.get_candidate(path.split("/", 1)[1].replace(".json", ""))
                return json.dumps(cand, indent=2) if cand else ""
            return ""
        return " ".join(str(args.get(a, "")) for a in meta.get("content_args", []))

    # ---- applying the decision ----
    def _apply(self, s, tool, args, d):
        sid = s["id"]
        tainted = s["tainted"]
        if d.action == "allow":
            eid = self.store.audit(sid, "tool_call", tool, args, tainted=tainted, decision="allow",
                                   rule=d.rule, reason=d.reason, evidence=d.evidence,
                                   denial_count=s["denial_count"])
            result = execute_and_record(self.store, self.cfg, sid, tool, args)
            self.store.set_outcome(eid, "executed")
            now_s = self.store.get_session(sid)
            return self._response("allow", d.rule, d.reason, now_s, tool, evidence=d.evidence, risk=d.risk,
                                  result=result["text"], label=result["label"], agent_message=result["text"])
        if d.action == "hold":
            aid = self.store.create_approval(sid, tool, args, d.evidence, d.rule, d.reason, d.risk)
            self.store.audit(sid, "tool_call", tool, args, tainted=tainted, decision="hold", rule=d.rule,
                             reason=d.reason, evidence=dict(d.evidence, approval_id=aid),
                             denial_count=s["denial_count"], outcome="pending approval")
            return self._response("hold", d.rule, d.reason, s, tool, evidence=d.evidence, risk=d.risk,
                                  approval_id=aid, agent_message=PENDING_MESSAGE)
        # block
        count = self.store.bump_denial(sid)
        self.store.audit(sid, "tool_call", tool, args, tainted=tainted, decision="block", rule=d.rule,
                         reason=d.reason, evidence=d.evidence, denial_count=count, outcome="blocked")
        frozen = self._maybe_freeze(sid, count)
        return self._response("block", d.rule, d.reason, self.store.get_session(sid), tool, evidence=d.evidence,
                              risk=d.risk, frozen=frozen, agent_message=GENERIC_REFUSAL)

    def _maybe_freeze(self, sid, count):
        if count >= self.cfg.policy["denial_limit"]:
            reason = "Denial limit reached (%d denials)" % count
            self.store.freeze(sid, reason)
            self.store.audit(sid, "freeze", decision="freeze", rule="DENIAL_LIMIT", reason=reason,
                             denial_count=count, outcome="session frozen")
            return True
        return False

    def _response(self, decision, rule, reason, s, tool, evidence=None, risk="normal", result=None,
                  label=None, approval_id=None, frozen=None, agent_message=None):
        return {"decision": decision, "rule": rule, "reason": reason, "risk": risk, "tool": tool,
                "evidence": evidence or {}, "result": result, "label": label, "approval_id": approval_id,
                "tainted": s["tainted"], "denial_count": s["denial_count"],
                "frozen": s["frozen"] if frozen is None else frozen,
                "agent_message": agent_message}

    # ---- human approval ----
    def resolve_approval(self, aid, approve, resolver="human"):
        ap = self.store.get_approval(aid)
        if not ap:
            raise KeyError("Unknown approval: %s" % aid)
        if ap["status"] != "pending":
            raise ValueError("Approval already %s" % ap["status"])
        sid = ap["session_id"]
        s = self._session(sid)
        if approve and s["frozen"]:
            approve = False  # a frozen session cannot execute anything
        if approve:
            result = execute_and_record(self.store, self.cfg, sid, ap["tool"], ap["args"], via_approval=True)
            self.store.resolve_approval(aid, "approved", resolver, result["text"], result["label"])
            self.store.audit(sid, "approval", ap["tool"], ap["args"], tainted=self.store.get_session(sid)["tainted"],
                             decision="approved", rule=ap["rule"], reason="Approved by %s" % resolver,
                             evidence=ap["evidence"], outcome="executed after approval")
            return {"status": "approved", "result": result["text"], "label": result["label"],
                    "agent_message": result["text"], "frozen": False}
        self.store.resolve_approval(aid, "rejected", resolver)
        count = self.store.bump_denial(sid)
        self.store.audit(sid, "approval", ap["tool"], ap["args"], tainted=s["tainted"], decision="rejected",
                         rule=ap["rule"], reason="Rejected by %s" % resolver, evidence=ap["evidence"],
                         denial_count=count, outcome="rejected")
        frozen = self._maybe_freeze(sid, count)
        return {"status": "rejected", "result": None, "label": None, "agent_message": GENERIC_REFUSAL,
                "frozen": frozen}

    def unfreeze(self, sid, who="human"):
        self._session(sid)
        self.store.unfreeze(sid)
        self.store.audit(sid, "unfreeze", decision="unfreeze", reason="Unfrozen by %s" % who,
                         outcome="session reopened")
        return self.store.get_session(sid)
