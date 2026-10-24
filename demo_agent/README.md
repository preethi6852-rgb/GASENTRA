# demo_agent

A deliberately gullible HR bot that shows GASENTRA protecting a third-party agent. It is its own
process with its own LLM key, and it talks to the gateway over HTTP only. It imports nothing from
the `gasentra` package.

```
user -> demo_agent (LLM tool-calling loop) -> [--guard on]  POST /api/gateway/tool-call
                                           -> [--guard off] local unguarded stubs
```

## Setup
```
cd demo_agent
pip install -r requirements.txt
copy .env.example .env        (macOS/Linux: cp)   then fill in LLM_PROVIDER, LLM_API_KEY, LLM_MODEL
```
`LLM_PROVIDER` is `openai` or `anthropic`. `LLM_BASE_URL` is optional (any OpenAI-compatible endpoint).
Never commit `.env`.

## Run the demo
1. Start the gateway in dev mode, from the gateway folder (the one with `app.py`):
   ```
   python app.py --dev
   ```
   `--dev` turns on the one dev-only endpoint this agent needs (`/api/dev/seed-inbox`). Leave it off in any real deployment.
2. The dashboard opens at http://127.0.0.1:8000/ . Useful pages: `/audit.html`, `/approvals.html`, `/frozen.html`.
   If the gateway runs on another port or machine, set `GATEWAY_URL` in this folder's `.env`.
3. Same prompt, two modes:
   ```
   python agent.py --guard off --scenario A1-01     # the bot obeys the hidden instruction; "SENT (UNGUARDED)" shows the record leaving
   python agent.py --guard on  --scenario A1-01     # the send is blocked and appears on the Audit page
   ```
4. Legitimate task that needs a person: `python agent.py --guard on --scenario L08 --message "Look up cand-001, then send a redacted summary to partner@agency.test."`
   It stops with "Waiting for human approval". Approve it on the Approvals page and the gateway runs it (see `/api/sent`).
5. Freeze: keep sending to new addresses. After 3 denials the next call returns the frozen message and the session appears on the Frozen page.

Flags: `--once` (exit after the first message), `--message "..."`, `--user`. Without `--once` you get a chat prompt; type `exit` to quit.

## No API key? Use the scripted stand-in
```
python dev/fake_llm_server.py 9100
# .env: LLM_PROVIDER=openai  LLM_API_KEY=anything  LLM_MODEL=fake  LLM_BASE_URL=http://127.0.0.1:9100/v1
```
It behaves like a gullible bot (reads the inbox, opens the named record, sends it where the email says).
Set `FAKE_RETRIES=4` in its environment to make it keep trying new addresses until the session freezes.

## Rules the agent follows
- Every real user message goes to `/api/gateway/user-message` before the model sees it (this records provenance).
- `allow` returns the tool result to the model. Any other decision returns only `agent_message`.
- The rule, reason, evidence, risk and approval id are never passed to the model or printed. The trace
  shows only the decision word: `[tool] send_email -> BLOCKED`.
- Gateway unreachable, timeout (10 s) or bad response: the model gets "Tool unavailable". The call never runs locally.
- `hold` ends the turn with "waiting for human approval". `frozen` ends the session.
- Local stubs (`local_tools.py`) are used only with `--guard off`.

## Files
| File | Job |
| --- | --- |
| `agent.py` | CLI chat loop, tool schemas, the LLM <-> tools loop (max 8 rounds) |
| `gw_client.py` | HTTP wrapper for the gateway, no LLM code |
| `local_tools.py` | Unguarded stubs for `--guard off`, reading copies in `data/` |
| `llm.py` | OpenAI / Anthropic adapter, settings from `.env` |
| `data/` | Copies of the synthetic data and the scenario inboxes |
| `dev/fake_llm_server.py` | Offline stand-in for the LLM (dev only) |

## Changes to the gateway this agent needs (already included in gasentra-project-with-app.zip)
- `POST /api/dev/seed-inbox {scenario_id}` stores a scenario's emails. It answers 404 unless the gateway runs with `--dev` (or `GASENTRA_DEV=1`).
- `POST /api/session` accepts an optional `scenario`, so `read_inbox` can find those emails.
- Decision logic is untouched. If you use your own copy of the gateway, merge these two changes into `gasentra/api.py`.

## Notes
- `write_note` takes `content` (and optional `path`), because that is what the gateway reads.
- All data is synthetic and nothing is really sent.
- The scenario emails are the same on both sides: `data/scenarios.json` here is a copy of the gateway's cases.
