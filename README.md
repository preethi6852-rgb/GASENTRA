### GASENTRA

**An action firewall for AI agents.** GASENTRA sits between an AI bot and its
tools. The bot proposes actions, and fixed rules decide: allow, hold for human
approval, or block. It works without changing the AI model.

> Hackathon prototype (Dexathon 2K26). Work in progress. Uses synthetic data only.

## The problem
AI assistants read emails and documents, open private files and send messages.
They can't reliably tell the user's instructions from instructions hidden in
the content they read. A hijacked assistant can leak private data without
anyone noticing.

## What GASENTRA does
- **Labels data:** every tool result is saved with a sensitivity label.
- **Tracks taint:** once the bot has seen sensitive data, everything it does
  for the rest of the conversation is treated as tainted.
- **Checks recipients:** every recipient must trace to the user's own words or
  a trusted list.
- **Holds risky actions** for a human, with evidence: matched fields, the rule
  and a safer alternative.
- **Protects fields** such as salary: changes are allowed only if the value
  comes from the user's own words.
- **Freezes sessions** after repeated denials, and logs every decision.

## Example scenario
Company Z emails Company X's HR a fake "verification request" with a hidden
instruction. X's assistant opens a candidate's record and tries to email it to
Z. GASENTRA sees that the address came only from untrusted content, and the
session is tainted, so the send is blocked or held. The decision is logged.

## How it works
1. The host app forwards the user's messages to the gateway.
2. The bot proposes a tool call. The gateway routes it by type.
3. The ledger and taint engine check labels, taint and recipients.
4. The decision engine returns allow, hold or block.
5. Tool results return through the gateway and are labelled before the bot
   sees them.
6. Repeated denials trigger a session freeze.

Decision order: errors, then blocks, then holds, then allows.

## Status
| Component | Status |
| --- | --- |
| Gateway, labels, taint, recipient checks, approval | Planned |
| Denial counting and session freeze | Planned |
| Front-end dashboard (approvals, audit log, frozen sessions, results) | Planned |
| Test harness  | Planned |




## Tech stack

| Layer | Technology |
|---|---|
| Backend Language | Python  |
| Web Framework | FastAPI |
| Application Server | Uvicorn |
| Data Validation | Pydantic |
| Database | SQLite |
| Configuration | JSON |
| Frontend | HTML, CSS, Vanilla JavaScript |
| HTTP Clients | HTTPX, Requests |
| LLM Integration | OpenAI-compatible APIs, Anthropic API |
| Backend Testing | Pytest, FastAPI TestClient |
| Frontend Testing | jsdom |
| Evaluation | Python-based evaluation harness |


## Roadmap

Connector mode for assistants that accept custom connectors.

Agent-to-agent message checks.


## References


Abdelnabi et al. (arXiv:2502.01822)


Lan and Kaul (arXiv:2603.23791)


Wutschitz et al. (arXiv:2505.23643)


CERT-In advisory CIAD-2026-0049.

## Team
TEAM NAME : SOLARIS YAZHI

PREETHI S

J.S.KRITHIKA

PRIYA K

SANTHIYA ARIKRISHNAN

