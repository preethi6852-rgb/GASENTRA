# API reference (for the front end)

Base URL: same origin as the page. All bodies are JSON. Interactive docs: `/docs`.

## Gateway (what a bot calls)
- `POST /api/session` `{user?}` -> session `{id, tainted, frozen, denial_count, ...}`
- `POST /api/gateway/user-message` `{session_id, text}`
- `POST /api/gateway/tool-call` `{session_id, tool, args}` -> decision object

Decision object: `decision` (allow | hold | block | frozen), `rule`, `reason`, `risk` (normal | high),
`evidence` (recipients, matched_fields, safer_option, old_value, new_value, source), `approval_id` (when held),
`tainted`, `denial_count`, `frozen`, `result`, `label`, `agent_message`.
**A real bot must only receive `agent_message`.** The other fields are for the admin dashboard.

## Approvals
- `GET /api/approvals?status=pending`
- `POST /api/approvals/{id}` `{approve: true|false}`

## Sessions and audit
- `GET /api/sessions?frozen=true`, `GET /api/sessions/{id}`, `POST /api/sessions/{id}/unfreeze`
- `GET /api/audit?session_id=&limit=` (newest first), `GET /api/sent` (simulated outbox)

## Demo runner (scripted hijacked agent)
- `GET /api/scenarios`
- `POST /api/demo/start` `{scenario_id, approver: "pause"|"approve"|"reject"}` -> run state
- `POST /api/demo/{run_id}/resume` (after resolving the pending approval), `GET /api/demo/{run_id}`

Run state: `run_id, scenario, title, session_id, done, paused, pending_approval, records[], session, audit[]`.

## Results
- `GET /api/results` -> `configs[]`, `attack_rows[]`, `legit_rows[]`, `notes[]` (from `python -m harness.run_eval`)
