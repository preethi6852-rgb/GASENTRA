### GASENTRA

An action firewall for AI agents - GASENTRA sits between an AI bot and the tools it uses. The bot suggests an action and a set of fixed rules decides what happens: let it run, hold it for a human to approve, or block it. You don't have to change the AI model to use it.

> Built for Dexathon 2K26. This is a work in progress and it only uses synthetic data.
## Why we built it

AI assistants now read emails and documents, open private files and send messages for us. The trouble is that they can't reliably tell what the user asked for from instructions hidden inside the content they read. If an assistant gets hijacked, it can leak private data and nobody notices.

## What it does

- **Labels data.** Every tool result is stored with a sensitivity label.
- **Tracks taint.** Once the bot has seen sensitive data, everything it does for the rest of the conversation is treated as tainted.
- **Checks recipients.** Every recipient has to trace back to something the user actually said or to a trusted list.
- **Holds risky actions** for a person to review, and shows the evidence: the matched fields, the rule that fired and a safer alternative.
- **Protects fields** like salary. A change goes through only if the new value came from the user's own words.
- **Freezes sessions** after repeated denials and logs every decision.

## A quick example

Company Z emails Company X's HR team a fake "verification request" with a hidden instruction inside. X's assistant opens a candidate's record and tries to email it to Z. GASENTRA notices two things: the address came only from untrusted content and the session is already tainted. So the send is blocked or held and the decision goes into the log.

## How it works

1. The host app passes the user's messages to the gateway.
2. The bot proposes a tool call and the gateway sorts it by type.
3. The ledger and taint engine check the labels, the taint and the recipients.
4. The decision engine answers with allow, hold or block.
5. Tool results come back through the gateway and get labelled before the bot sees them.
6. Too many denials in a row trigger a session freeze.

When rules conflict, the order is: errors first, then blocks, then holds, then allows.

## Where we are

| Part | Status |
| --- | --- |
| Gateway, labels, taint, recipient checks, approvals | Planned |
| Denial counting and session freeze | Planned |
| Dashboard (approvals, audit log, frozen sessions, results) | Planned |


## Planned layout

`gateway/` `ledger/` `policy/` `tools/` `agent/` `harness/` `frontend/` `data/`

## Tech

Python, a lightweight web API (FastAPI, for example), a small database (such as SQLite), a web dashboard (such as React) .

## What's next

A connector mode for assistants that accept custom connectors and checks on messages passed between agents.

## References

Abdelnabi et al. (arXiv:2502.01822)

Lan and Kaul (arXiv:2603.23791)

Wutschitz et al. (arXiv:2505.23643) 

CERT-In advisory CIAD-2026-0049.

## Team  SOLARIS YAZHI

PREETHI S

J.S.KRITHIKA

PRIYA K

SANTHIYA ARIKRISHNAN
