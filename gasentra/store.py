"""SQLite store: sessions, ledger (labelled tool outputs), audit log, approvals, synthetic data."""
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from .config import DATA_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions(
  id TEXT PRIMARY KEY, user TEXT, created TEXT, tainted INTEGER DEFAULT 0,
  frozen INTEGER DEFAULT 0, freeze_reason TEXT, frozen_at TEXT,
  denial_count INTEGER DEFAULT 0, scenario TEXT);
CREATE TABLE IF NOT EXISTS user_messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, text TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, ts TEXT, kind TEXT, tool TEXT,
  args TEXT, label TEXT, tainted INTEGER, decision TEXT, rule TEXT, reason TEXT,
  evidence TEXT, denial_count INTEGER, outcome TEXT);
CREATE TABLE IF NOT EXISTS outputs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, tool TEXT, resource TEXT,
  label TEXT, text TEXT, fingerprint TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS resources(
  path TEXT PRIMARY KEY, label TEXT, content TEXT, written_by TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS approvals(
  id TEXT PRIMARY KEY, session_id TEXT, tool TEXT, args TEXT, evidence TEXT, rule TEXT,
  reason TEXT, risk TEXT, status TEXT, created TEXT, resolved TEXT, resolver TEXT,
  result_text TEXT, result_label TEXT);
CREATE TABLE IF NOT EXISTS sent(
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, tool TEXT, recipient TEXT,
  subject TEXT, content TEXT, via_approval INTEGER, ts TEXT);
CREATE TABLE IF NOT EXISTS candidates(id TEXT PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS emails(
  id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT, subject TEXT, body TEXT, scenario TEXT);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path=":memory:", seed=True):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(SCHEMA)
        if seed and not self._one("SELECT 1 FROM candidates LIMIT 1"):
            self.seed()

    # ---- helpers ----
    def _exec(self, sql, args=()):
        with self.lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur

    def _all(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def _one(self, sql, args=()):
        rows = self._all(sql, args)
        return rows[0] if rows else None

    # ---- seed synthetic data ----
    def seed(self):
        for c in json.loads((DATA_DIR / "candidates.json").read_text(encoding="utf-8")):
            self._exec("INSERT OR REPLACE INTO candidates VALUES(?,?)", (c["id"], json.dumps(c)))
        for e in json.loads((DATA_DIR / "emails.json").read_text(encoding="utf-8")):
            self._exec("INSERT INTO emails(sender,subject,body,scenario) VALUES(?,?,?,NULL)",
                       (e["sender"], e["subject"], e["body"]))
        for r in json.loads((DATA_DIR / "resources.json").read_text(encoding="utf-8")):
            self._exec("INSERT OR REPLACE INTO resources VALUES(?,?,?,?,?)",
                       (r["path"], r["label"], r["content"], None, now()))

    # ---- sessions ----
    def create_session(self, user="hr@company.com", scenario=None):
        sid = "S-" + uuid.uuid4().hex[:8]
        self._exec("INSERT INTO sessions(id,user,created,scenario) VALUES(?,?,?,?)",
                   (sid, user, now(), scenario))
        return sid

    def get_session(self, sid):
        s = self._one("SELECT * FROM sessions WHERE id=?", (sid,))
        if s:
            s["tainted"], s["frozen"] = bool(s["tainted"]), bool(s["frozen"])
        return s

    def list_sessions(self, frozen=None):
        sql = "SELECT * FROM sessions"
        if frozen is not None:
            sql += " WHERE frozen=%d" % (1 if frozen else 0)
        rows = self._all(sql + " ORDER BY created DESC")
        for s in rows:
            s["tainted"], s["frozen"] = bool(s["tainted"]), bool(s["frozen"])
        return rows

    def set_tainted(self, sid):
        self._exec("UPDATE sessions SET tainted=1 WHERE id=?", (sid,))

    def bump_denial(self, sid):
        with self.lock:
            self.conn.execute("UPDATE sessions SET denial_count=denial_count+1 WHERE id=?", (sid,))
            self.conn.commit()
        return self.get_session(sid)["denial_count"]

    def freeze(self, sid, reason):
        self._exec("UPDATE sessions SET frozen=1, freeze_reason=?, frozen_at=? WHERE id=?",
                   (reason, now(), sid))

    def unfreeze(self, sid):
        self._exec("UPDATE sessions SET frozen=0, freeze_reason=NULL, frozen_at=NULL, denial_count=0 WHERE id=?",
                   (sid,))

    # ---- user messages ----
    def add_user_message(self, sid, text):
        self._exec("INSERT INTO user_messages(session_id,text,ts) VALUES(?,?,?)", (sid, text, now()))

    def user_texts(self, sid):
        return [r["text"] for r in self._all("SELECT text FROM user_messages WHERE session_id=? ORDER BY id", (sid,))]

    # ---- ledger ----
    def add_output(self, sid, tool, resource, label, text, fingerprint):
        self._exec("INSERT INTO outputs(session_id,tool,resource,label,text,fingerprint,ts) VALUES(?,?,?,?,?,?,?)",
                   (sid, tool, resource, label, text, json.dumps(fingerprint), now()))

    def outputs(self, sid):
        return self._all("SELECT * FROM outputs WHERE session_id=? ORDER BY id", (sid,))

    def sensitive_outputs(self, sid, taint_labels):
        return [o for o in self.outputs(sid) if o["label"] in taint_labels]

    # ---- resources / files ----
    def get_resource(self, path):
        return self._one("SELECT * FROM resources WHERE path=?", (path,))

    def put_resource(self, path, label, content, sid):
        self._exec("INSERT OR REPLACE INTO resources VALUES(?,?,?,?,?)", (path, label, content, sid, now()))

    # ---- candidates ----
    def get_candidate(self, cid):
        r = self._one("SELECT data FROM candidates WHERE id=?", (cid,))
        return json.loads(r["data"]) if r else None

    def update_candidate(self, cid, field, value):
        c = self.get_candidate(cid)
        c[field] = value
        self._exec("UPDATE candidates SET data=? WHERE id=?", (json.dumps(c), cid))

    # ---- emails ----
    def add_email(self, sender, subject, body, scenario=None):
        self._exec("INSERT INTO emails(sender,subject,body,scenario) VALUES(?,?,?,?)",
                   (sender, subject, body, scenario))

    def emails_for(self, scenario):
        return self._all("SELECT * FROM emails WHERE scenario IS NULL OR scenario=? ORDER BY id", (scenario,))

    # ---- outbox (simulated: nothing is really sent) ----
    def add_sent(self, sid, tool, recipient, subject, content, via_approval=False):
        self._exec("INSERT INTO sent(session_id,tool,recipient,subject,content,via_approval,ts) VALUES(?,?,?,?,?,?,?)",
                   (sid, tool, recipient, subject, content, 1 if via_approval else 0, now()))

    def sent_items(self, sid=None):
        if sid:
            return self._all("SELECT * FROM sent WHERE session_id=? ORDER BY id", (sid,))
        return self._all("SELECT * FROM sent ORDER BY id")

    # ---- audit log ----
    def audit(self, session_id, kind, tool=None, args=None, label=None, tainted=False, decision=None,
              rule=None, reason=None, evidence=None, denial_count=None, outcome=None):
        cur = self._exec(
            "INSERT INTO events(session_id,ts,kind,tool,args,label,tainted,decision,rule,reason,evidence,"
            "denial_count,outcome) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (session_id, now(), kind, tool, json.dumps(args or {}), label, 1 if tainted else 0, decision, rule,
             reason, json.dumps(evidence or {}), denial_count, outcome))
        return cur.lastrowid

    def set_outcome(self, event_id, outcome):
        self._exec("UPDATE events SET outcome=? WHERE id=?", (outcome, event_id))

    def list_audit(self, session_id=None, limit=200):
        if session_id:
            rows = self._all("SELECT * FROM events WHERE session_id=? ORDER BY id DESC LIMIT ?", (session_id, limit))
        else:
            rows = self._all("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))
        for r in rows:
            r["args"], r["evidence"] = json.loads(r["args"] or "{}"), json.loads(r["evidence"] or "{}")
            r["tainted"] = bool(r["tainted"])
        return rows

    # ---- approvals ----
    def create_approval(self, sid, tool, args, evidence, rule, reason, risk):
        aid = "AP-" + uuid.uuid4().hex[:6]
        self._exec("INSERT INTO approvals(id,session_id,tool,args,evidence,rule,reason,risk,status,created) "
                   "VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (aid, sid, tool, json.dumps(args), json.dumps(evidence), rule, reason, risk, "pending", now()))
        return aid

    def get_approval(self, aid):
        a = self._one("SELECT * FROM approvals WHERE id=?", (aid,))
        if a:
            a["args"], a["evidence"] = json.loads(a["args"]), json.loads(a["evidence"])
        return a

    def list_approvals(self, status=None):
        rows = self._all("SELECT * FROM approvals" + (" WHERE status=?" if status else "") + " ORDER BY created DESC",
                         (status,) if status else ())
        for a in rows:
            a["args"], a["evidence"] = json.loads(a["args"]), json.loads(a["evidence"])
        return rows

    def resolve_approval(self, aid, status, resolver, result_text=None, result_label=None):
        self._exec("UPDATE approvals SET status=?, resolved=?, resolver=?, result_text=?, result_label=? WHERE id=?",
                   (status, now(), resolver, result_text, result_label, aid))
