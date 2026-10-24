"""Unguarded tool stubs, used only with --guard off. Nothing is really sent anywhere.
Reads copies of the synthetic data in demo_agent/data/."""
import json
import os

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def known_scenarios():
    return _load("scenarios.json")


class LocalTools:
    def __init__(self, scenario=None):
        self.candidates = {c["id"]: c for c in _load("candidates.json")}
        self.resources = {r["path"]: r for r in _load("resources.json")}
        self.emails = list(_load("emails.json"))
        if scenario:
            self.emails += known_scenarios()[scenario]["inbox"]

    def run(self, name, args):
        fn = getattr(self, "t_" + name, None)
        return fn(args) if fn else "Unknown tool: " + name

    def t_read_inbox(self, a):
        return "\n\n".join("From: %s\nSubject: %s\n\n%s" % (m["sender"], m["subject"], m["body"])
                           for m in self.emails) or "Inbox is empty."

    def _file(self, path):
        path = str(path or "").strip()
        if path.startswith("candidates/"):
            c = self.candidates.get(path.split("/", 1)[1].replace(".json", ""))
            return json.dumps(c, indent=2) if c else None
        r = self.resources.get(path)
        return r["content"] if r else None

    def t_read_file(self, a):
        text = self._file(a.get("path"))
        return text if text is not None else "File not found: %s" % a.get("path")

    def t_write_note(self, a):
        return "Note saved to notes/%s" % str(a.get("path", "untitled.txt")).lstrip("/")

    def t_send_email(self, a):
        print("SENT (UNGUARDED): to=%s subject=%s" % (a.get("to"), a.get("subject")))
        print("  " + str(a.get("body", "")).replace("\n", "\n  "))
        return "Email sent to %s" % a.get("to")

    def t_share_file(self, a):
        print("SENT (UNGUARDED): to=%s file=%s" % (a.get("share_with"), a.get("path")))
        print("  " + str(self._file(a.get("path")) or "").replace("\n", "\n  "))
        return "Shared %s with %s" % (a.get("path"), a.get("share_with"))

    def t_update_offer(self, a):
        c = self.candidates.get(str(a.get("candidate_id")))
        if not c:
            return "Candidate not found: %s" % a.get("candidate_id")
        field, old = str(a.get("field")), c.get(str(a.get("field")))
        c[field] = a.get("value")
        print("CHANGED (UNGUARDED): %s %s %s -> %s" % (c["id"], field, old, a.get("value")))
        return json.dumps({"candidate": c["id"], "field": field, "before": old, "after": a.get("value")})
