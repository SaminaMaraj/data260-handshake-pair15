# Tracing, Token Tracking and Compaction (Lab 2 Part 6, Pair 15)

Code: `backend/services/common/tracing.py`, `services/assistant/agent/client.py`
(token and timing capture), `services/assistant/agent/loop.py`,
`services/assistant/compaction.py`, `scripts/trace_report.py`,
`scripts/compaction_demo.py`.

## Tracing

- **trace_id:** every request to every service gets one, taken from an incoming
  `X-Trace-Id` (or the gateway's `X-Request-ID`) if it is a safe 8 to 64
  character id, otherwise generated. It is returned as the `X-Trace-Id`
  response header and as `trace_id` in assistant responses.
- **Logs:** one JSON line per request (`event: request`) and per model call
  (`event: model_call`), always with `service` and `trace_id`. To follow one
  request across services:
  `grep <trace_id>` over the service logs (in Kubernetes, `kubectl logs` for each `p15` pod).
- **Kafka:** `events.make_event()` copies the current request's trace_id into
  the message (and the `trace_id` Kafka header). The memory worker continues
  that trace, records how long the message waited in Kafka, and writes its own
  trace under the same id. Business writes (`applications`,
  `event_registrations`, `activity_logs`) store the trace_id too.
- **Stored traces:** assistant requests and memory-worker messages go into the
  `traces` collection with their spans.

### The five stages

| Stage | How it is measured |
|---|---|
| `queue_wait` | Wall time of each model call minus Ollama's own `total_duration`: time spent queued behind other requests (and the network) |
| `model` | Ollama's `total_duration` (load + prompt evaluation + generation) |
| `db` | Every MongoDB command, timed by a pymongo `CommandListener` on the request's thread |
| `tool` | Tool code, excluding the database time inside it |
| `other` | The rest: auth, validation, guardrails, serialization |

The stages add up to the request's total (checked in `tests/test_tracing.py`).

### 50-request analysis

```bash
cd backend
python scripts/trace_report.py load --n 50 --concurrency 1   # or 3, 5 ... to see queueing
python scripts/trace_report.py report --last 50 | tee ../docs/evidence/trace_report.txt
```

The report prints mean, p50 and p95 per stage, each stage's share of the
total, the **dominant stage**, and the full timeline of one successful and one
failed trace. For a failed trace, stop Ollama and send one request: it is
recorded as `model_error`.

A dry run with a stand-in model (one request at a time, 300 ms each, 3
concurrent users) gave queue wait 62.5%, model 36.4%, database 0.4%. With one
model replica, extra concurrent assistant users mostly add **waiting**, not
work. The real qwen3:8b numbers go in the report.

## Token tracking

After every model call the client records Ollama's `prompt_eval_count` and
`eval_count` (or a 4-characters-per-token estimate, flagged `estimated`, for
a model that reports none). Each call is stored in `token_usage`, and each
session keeps `tokens_total` and `last_context_pct`. The context window is
fixed with Ollama's `num_ctx` (`OLLAMA_NUM_CTX`, default 8192), so the
percentage has a real denominator.

**Response fields for the UI** (`POST /assistant/chat` and `/assistant/confirm`):

```json
"tokens": {
  "model_calls": 2, "prompt_tokens": 3600, "completion_tokens": 120, "total_tokens": 3720,
  "context_used": 2060, "context_window": 8192, "context_pct": 25.1,
  "warning": false, "estimated": false,
  "calls": [{"call": 1, "prompt_tokens": 1600, "completion_tokens": 60,
             "inference_ms": 30.0, "queue_wait_ms": 20.1}, ...]
},
"compaction": { ... present only when this turn compacted the session ... },
"trace_id": "4b7e...", "session_id": "..."
```

UI rule: show `context_used / context_window` and `context_pct`. When
`warning` is true (above 70%), show the warning and offer the **Compact**
button, which sends `/compact`.

## Compaction

- **Triggers:** automatically when a turn ends above **75%** of the window,
  or on the `/compact` command.
- **What it keeps:** the summary is built by **code**, so values are copied
  exactly, never paraphrased. It contains:
  - the student's preferences, read fresh from the database
  - every job the session's tools returned, as id, title, company, location,
    category, salary, deadline and remote; plus the list of companies
  - every event, as id, name, date, location and eligibility
  - the student's applications with their status
  - the questions asked so far and the current request
  - the **last `search_jobs` result, kept verbatim**, so "make it higher
    paying" still passes `rank_jobs` validation
- **Labeling:** the summary is labeled and delimited as untrusted data.
- **Reporting:** each compaction reports token counts and context % before
  and after, and is stored in the `compactions` collection.
- **Proof of recall:** `tests/test_compaction.py` checks every fact is kept
  word for word and that a follow-up after compaction works.
  `scripts/compaction_demo.py` asks the real model three recall questions
  and checks the answers.
