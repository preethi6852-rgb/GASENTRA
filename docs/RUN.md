# Run the GASENTRA backend (Windows, Python 3.10+)

## 1. Put the files in your repo
Copy everything from this folder into your cloned `GASENTRA` repo (keep your README.md; do not overwrite it).

## 2. Install
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Run the tests (should print: all tests passed)
```
python -m pytest -q
```

## 4. Run the evaluation (writes harness/results/results.json)
```
python -m harness.run_eval
```

## 5. Start the website (backend and dashboard together)
```
python app.py
```
This one command starts the gateway API and the dashboard on the same address and opens your browser at
**http://127.0.0.1:8000/** (Home, Live session, Approvals, Audit and Frozen, Results, Settings).
API docs: http://127.0.0.1:8000/docs

Options: `--port 9000` (another port), `--reload` (restart on code changes), `--no-browser`, `--host 0.0.0.0` (share on your network).
If port 8000 is busy, app.py picks the next free one and prints it.
The older command still works too: `python -m uvicorn app:app --port 8000`.

## 6. Try the demo in /docs (2 minutes)
1. `GET /api/scenarios` to see the demo scenario ids.
2. `POST /api/demo/start` with `{"scenario_id": "A1-01", "approver": "pause"}`.
   You will see the read calls executed and the send to the unknown address **blocked**.
3. `POST /api/demo/start` with `{"scenario_id": "L08", "approver": "pause"}`.
   The run pauses on a held send. Copy `pending_approval`.
4. `GET /api/approvals?status=pending`, you will see the evidence (matched fields, rule, safer option).
5. `POST /api/approvals/{id}` with `{"approve": true}`, then `POST /api/demo/{run_id}/resume`.
6. `POST /api/demo/start` with `{"scenario_id": "A8-01", "approver": "pause"}` then `GET /api/sessions?frozen=true`.
   The session was frozen after 3 denials. `POST /api/sessions/{id}/unfreeze` reopens it.

## 7. Real LLM agent (optional)
See docs/LLM.md. Needs an API key in .env. Nothing else in this guide needs one.

## 8. Persistence (optional)
By default data lives in memory and resets when the server restarts.
To keep it: set `GASENTRA_DB=gasentra.db` before starting.

## Where things are
| File | What it does |
| --- | --- |
| app.py | Start here. Loads .env, checks both halves, starts the API and the dashboard together |
| config/*.json | Per-deployment settings: labels, trusted contacts, tools, denial limit. Change these to change industry |
| gasentra/gateway.py | The gateway. Every tool call passes through it |
| gasentra/decision.py | The decision rules (errors, blocks, holds, allows) |
| gasentra/store.py | Ledger (labelled outputs), taint, audit log, approvals (SQLite) |
| gasentra/matching.py | Content matching (exact, normalised, entity) |
| gasentra/recipients.py | Recipient provenance |
| gasentra/tools.py | Simulated tools on synthetic data (nothing is really sent) |
| gasentra/scripted.py | Scripted agent that always obeys the hidden instruction |
| gasentra/cases.py | 27 attacks and 20 legitimate tasks |
| harness/run_eval.py | Runs everything against 4 setups |
| tests/ | tests, one per decision-table row and per behaviour |

## Dashboard walk-through (what a judge will do)
1. **Live session**: pick "Hidden instruction in an email", approver "Wait for me", press Run scenario. The send is blocked.
2. Pick "Redacted summary to a partner" and run it. It pauses on a HOLD card. Press Review.
3. **Approvals**: read the evidence and the safer alternative, then Approve or Reject. Go back to Live session to see the run finish.
4. Run "Agent keeps trying other routes". The session freezes after 3 denials.
5. **Audit & Frozen**: see every decision, then Unfreeze the session.
6. **Results**: press Run evaluation. It re-runs all 47 cases against the 4 setups and shows the numbers.

## Optional: automated browser check of the dashboard
Needs Node.js. With the server running: `npm install jsdom` then `node scripts/ui_smoke_test.js`.
