# Agentic Guardrails and Evaluation Harness (Lab 2 Part 6, Pair 15)

Code: `backend/services/assistant/guardrails.py` (all eight checks),
`backend/services/assistant/agent/loop.py` (where they run),
`backend/harness/agent_harness.py` (the harness).

## Where each guardrail runs

```
model reply ──► G7 deadline / model_error check
   │
   ├─ text answer ──► (one nudge if no tool was used) ──► G6 redact ──► G8 grounding ──► student
   │
   └─ tool call ──► G1 allowlist ──► parse JSON ──► G3 drop app-owned args, scope to JWT student
                      ──► G2 strict JSON schema + semantic checks ──► invalid? one repair re-prompt (G7), then stop
                      ──► G4 write tool? pause for the student's Yes/No
                      ──► execute (G7: one retry if the tool raised)
                      ──► G6 redact secrets ──► G5 remove instruction-like text, wrap as untrusted ──► model
```

| # | Guardrail | Implementation | Evidence (harness case) |
|---|---|---|---|
| G1 | Tool allowlist | `TOOL_POLICY` lists the six tools; anything else is rejected with the valid list | `unknown_tool`: `find_jobs` rejected, then repaired to `search_jobs` |
| G2 | Schema validation | `jsonschema` against strict schemas: `additionalProperties: false`, enums, `YYYY-MM-DD` patterns, bounds, exactly-one of `job_id`/`event_id`; then semantic checks (rank only ids from the last search, `date_from <= date_to`) | `malformed_arguments_repaired`: Lab 1's `{"function": …, "parameters": …}` call is now rejected **before** execution |
| G3 | Authorization | `student_id` and `auto_approve` are app-owned: removed from model output; `student_id` comes from the JWT. HTTP routes keep role and ownership checks (403) | `authorization_other_student`, `model_cannot_self_approve` |
| G4 | Read/write control | Read tools run automatically; `save_job_or_event` stores a pending action (MongoDB, TTL, single use, owner-only) and waits. A declined save cannot be retried | `accepted_state_change`, `declined_state_change` |
| G5 | Prompt-injection defense | Tool results are delimited in `<untrusted_data source=…>` with `<`/`>` escaped, **and** instruction-like sentences are replaced by `[removed: instruction-like text]` | `prompt_injection_before_defense` vs `_after_defense` |
| G6 | Privacy and secrets | Redacts JWTs, bearer tokens, bcrypt hashes, password/API-key fields, AWS/`sk-` keys and DB URLs with credentials from tool results, answers and **logs**; other people's e-mail from answers | `privacy_redaction` |
| G7 | Bounded execution | Request deadline (`ASSISTANT_TIMEOUT_SECONDS`, 150 s; each model call capped at the time left), `MAX_ITERATIONS = 6`, one repair re-prompt, one retry of a failed tool; an unreachable model returns `model_error`, never the error text | `iteration_ceiling`, `request_timeout`, `tool_recovery_retry`, `repair_fails_cleanly`, `model_unavailable` |
| G8 | Reliable answers | Tools return explicit no-match/error strings. Answers naming a `Pair 15 Company ####` or a salary that no tool returned are flagged; a listing with no tool data at all is replaced | `no_match`, `ungrounded_answer_blocked` |

## Changes from Lab 1

- **Lab 1:** "The loop does not check argument names." **Lab 2:** G2 rejects
  unknown arguments before the tool runs.
- **Lab 1:** the wrapper delimited injected text, but the model still
  repeated it to the student. **Lab 2:** G5 also removes instruction-like
  sentences, so the model never sees them.
- **Lab 1:** with Ollama down, the error text came back as a "completed"
  answer. **Lab 2:** G7 returns `status: model_error` with a clear message.
- **Lab 1:** answers without a tool call sometimes invented companies and
  salaries. **Lab 2:** G8 catches values no tool returned.
- **Lab 1:** pending confirmations were held in process memory. **Lab 2:**
  they're in MongoDB, single-use and atomic, so they work across replicas.

Every guardrail decision is returned in the response as `guardrails`
(`{guardrail, name, action, detail}`) and printed to the service log
(`GUARDRAIL G2 rejected: …`), with secrets redacted.

## Evaluation harness

```bash
cd backend
python -m harness.agent_harness      # MongoDB must be running
```

It builds a fresh `p15_harness` database from the Pair 15 seed, then runs
18 cases through the **production** loop, guardrails, tools and MongoDB.
Only the model is replaced, by deterministic scripted clients, so results
repeat exactly. Output:

- `backend/harness/output/agent_harness.jsonl`: one record per case with
  the input, model messages, tool names and arguments, tool results, final
  answer, guardrail outcome, errors, repairs, retries, iteration and
  tool-call counts, elapsed time and timing breakdown, and per-check pass/fail
- `backend/harness/output/agent_harness_summary.md`: the pass/fail table,
  reliability before and after repair, and the blocked-injection,
  declined-confirmation, repaired-call and bounded-stop evidence

The harness supplements the real Ollama transcripts; it doesn't replace
them. The pytest suite runs it too (`tests/test_agent_harness.py`).
