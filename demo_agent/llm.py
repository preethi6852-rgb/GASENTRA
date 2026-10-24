"""Provider adapter. One neutral message format in, one neutral reply out.

Neutral messages (kept by agent.py):
  {"role": "user", "content": str}
  {"role": "assistant", "content": str, "tool_calls": [{"id", "name", "args"}]}
  {"role": "tool", "id": str, "name": str, "content": str}
Neutral reply: {"text": str, "tool_calls": [{"id", "name", "args"}]}   (args is None if the model sent bad JSON)

Settings come from the environment or demo_agent/.env. Nothing is hard-coded.
"""
import json
import os

import requests

TIMEOUT = 60


class LLMError(Exception):
    pass


def load_env(path=None):
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class LLM:
    def __init__(self):
        load_env()
        self.provider = (os.environ.get("LLM_PROVIDER") or "openai").lower()
        self.key = os.environ.get("LLM_API_KEY", "")
        self.model = os.environ.get("LLM_MODEL", "")
        self.base = (os.environ.get("LLM_BASE_URL") or "").rstrip("/")
        if self.provider not in ("openai", "anthropic"):
            raise LLMError("LLM_PROVIDER must be openai or anthropic.")
        if not self.key or not self.model:
            raise LLMError("Set LLM_API_KEY and LLM_MODEL in demo_agent/.env (see .env.example).")

    def chat(self, system, messages, tools):
        try:
            return (self._openai if self.provider == "openai" else self._anthropic)(system, messages, tools)
        except LLMError:
            raise
        except requests.RequestException as e:
            raise LLMError("LLM request failed: %s" % type(e).__name__)

    # ---- helpers ----
    @staticmethod
    def _args(raw):
        if isinstance(raw, dict):
            return raw
        try:
            v = json.loads(raw or "{}")
            return v if isinstance(v, dict) else None
        except ValueError:
            return None

    def _post(self, url, headers, body):
        r = requests.post(url, headers=headers, json=body, timeout=TIMEOUT)
        if r.status_code != 200:
            raise LLMError("LLM request failed (HTTP %d): %s" % (r.status_code, r.text[:200]))
        return r.json()

    # ---- OpenAI-style chat completions ----
    def _openai(self, system, messages, tools):
        msgs = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "assistant":
                o = {"role": "assistant", "content": m["content"] or None}
                if m.get("tool_calls"):
                    o["tool_calls"] = [{"id": c["id"], "type": "function",
                                        "function": {"name": c["name"], "arguments": json.dumps(c["args"] or {})}}
                                       for c in m["tool_calls"]]
                msgs.append(o)
            elif m["role"] == "tool":
                msgs.append({"role": "tool", "tool_call_id": m["id"], "content": m["content"]})
            else:
                msgs.append({"role": "user", "content": m["content"]})
        body = {"model": self.model, "messages": msgs,
                "tools": [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                            "parameters": t["parameters"]}} for t in tools]}
        data = self._post((self.base or "https://api.openai.com/v1") + "/chat/completions",
                          {"Authorization": "Bearer " + self.key}, body)
        try:
            msg = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise LLMError("Unexpected reply from the LLM provider.")
        calls = [{"id": c["id"], "name": c["function"]["name"], "args": self._args(c["function"].get("arguments"))}
                 for c in (msg.get("tool_calls") or [])]
        return {"text": msg.get("content") or "", "tool_calls": calls}

    # ---- Anthropic messages ----
    def _anthropic(self, system, messages, tools):
        msgs = []
        for m in messages:
            if m["role"] == "assistant":
                blocks = [{"type": "text", "text": m["content"]}] if m["content"] else []
                blocks += [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["args"] or {}}
                           for c in m.get("tool_calls") or []]
                msgs.append({"role": "assistant", "content": blocks})
            elif m["role"] == "tool":
                block = {"type": "tool_result", "tool_use_id": m["id"], "content": m["content"]}
                if msgs and msgs[-1]["role"] == "user" and isinstance(msgs[-1]["content"], list):
                    msgs[-1]["content"].append(block)      # all results of one round go in one user turn
                else:
                    msgs.append({"role": "user", "content": [block]})
            else:
                msgs.append({"role": "user", "content": m["content"]})
        body = {"model": self.model, "max_tokens": 1024, "system": system, "messages": msgs,
                "tools": [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
                          for t in tools]}
        data = self._post((self.base or "https://api.anthropic.com") + "/v1/messages",
                          {"x-api-key": self.key, "anthropic-version": "2023-06-01"}, body)
        text, calls = [], []
        for b in data.get("content") or []:
            if b.get("type") == "text":
                text.append(b.get("text", ""))
            elif b.get("type") == "tool_use":
                calls.append({"id": b["id"], "name": b["name"], "args": self._args(b.get("input"))})
        return {"text": "".join(text), "tool_calls": calls}
