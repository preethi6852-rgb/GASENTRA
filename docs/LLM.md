# Real LLM agent

The scripted agent (default) is for repeatable tests. The real agent lets an actual model propose the tool
calls. **Every call still goes through the GASENTRA gateway**, so this is the real product flow:

    user message -> model proposes call -> GASENTRA decides -> result or refusal goes back to the model

## 1. Set it up
1. Copy `.env.example` to `.env` (the file must be named exactly `.env`).
2. Fill in `LLM_API_KEY` and `LLM_MODEL` (and `LLM_PROVIDER` / `LLM_BASE_URL` if you are not using OpenAI).
3. Restart the server. Check `GET /api/agent/status`, it must say `"configured": true`.
`.env` is in `.gitignore`. **Never commit a key.** The key is only read by the server, never sent to a browser.

Providers:
- `LLM_PROVIDER=openai`: any OpenAI-compatible chat API. Set `LLM_BASE_URL` for another vendor or a local server.
- `LLM_PROVIDER=anthropic`: Anthropic's Messages API.
Use a model that supports tool calling. Model names change often, so copy the current name from your provider's docs.

## 2. Try it in /docs
`POST /api/agent/chat`
```
{"text": "Please check my inbox and summarize the new candidate emails.", "scenario_id": "A1-01"}
```
`scenario_id` loads that scenario's poisoned inbox so the real model reads the hidden instruction.
You get back `events` (what the model said and every tool call with the GASENTRA decision), `status`, `session_id`.
- `status: "done"` means the model finished.
- `status: "paused"` means a call was HELD. Approve it with `POST /api/approvals/{pending_approval}` then
  `POST /api/agent/{session_id}/resume`.
- `status: "frozen"` means the denial limit was reached.
Add `"session_id"` to keep chatting in the same conversation. Add `"style": "naive"` for a deliberately gullible
bot prompt (stands in for a poorly built custom bot).

## 3. Measure it (this makes the claim "we tested with a real model" true)
```
python -m harness.run_llm_eval --runs 1
python -m harness.run_llm_eval --runs 3 --style naive
```
It runs poisoned-inbox cases with and without GASENTRA and prints how many times the model **actually followed**
the hidden instruction, and what GASENTRA did. Results are saved to `harness/results/llm_results.json`.
These are real API calls and cost a little. Start with `--runs 1`.

IMPORTANT: modern models often refuse hidden instructions. If your model never follows the injection, report
that honestly ("0 of N followed"), then use `--style naive` or the scripted agent to test the guard itself.
The guard is tested under the assumption that the agent IS fooled.

## 4. What to say on the slides
"We test with a scripted agent for repeatability and with a real model through an API." Only say it after
`run_llm_eval` has produced a results file.
