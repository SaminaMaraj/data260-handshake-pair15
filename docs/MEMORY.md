# Assistant Memory (Lab 2 Part 3, Pair 15)

Code: `backend/services/assistant/memory.py` (layers, injection, `/memory`),
`consolidation.py` (merge and resolve, with validation), `memory_worker.py`
(the Kafka consumer), `memory_seed.py` (the 62-entry test fixture).

## Three layers

| Layer | Collection | Contents | How it reaches the model |
|---|---|---|---|
| Instructions | `assistant_rules` | 14 rules: the 12 Lab 1 prompt rules plus "never reveal another student's private information" and "always state eligibility requirements" | Loaded from MongoDB and numbered into the system prompt on **every** model call, so editing a rule changes behavior with no redeploy |
| Learned memory | `student_memory` | One document per entry, shown as one line: `YYYY-MM-DD \| category \| description` | Up to 40 newest entries, inside `<untrusted_data source="student_memory">` with `<` and `>` escaped, because the text came from conversations. The prompt says newer entries win if two disagree. |
| Session | `conversations` | The current conversation only, keyed by `session_id` | Sent as the message history. At session end it is passed to the consumer, which extracts lasting facts into learned memory and then **deletes** the conversation. |

## The `/memory` command

These are answered by code, never by the model, so they're deterministic and
cost no inference time:

| Command | Effect |
|---|---|
| `/memory` (or `/memory show`) | Numbered list of everything remembered about the signed-in student |
| `/memory add <category>: <text>` | Adds an entry dated today; categories: preference, location, skill, goal, experience, education, availability, constraint, other |
| `/memory forget <n>` | Deletes entry *n* from the list |
| `/memory consolidate` | **Publishes** a message to `p15.memory.consolidate` and returns at once |

API additions: `GET /assistant/memory`, `POST /assistant/session/end`, and
`session_id` on `POST /assistant/chat` and `POST /assistant/confirm`.

## Consolidation runs as a Kafka consumer

```
/memory consolidate ─┐                              ┌─ model (qwen3:8b), JSON mode
session/end ─────────┼─► p15.memory.consolidate ─► p15-memory-worker ─┤
                     │      (Kafka, key=student)        │              └─ MongoDB: student_memory,
                     └── returns immediately            │                 memory_consolidations
                                                         └─ after 3 failed attempts ─► p15.memory.consolidate.dlq
```

- **Never blocks a request:** the API only publishes; the worker does the
  model call (tens of seconds) and the writes.
- **Offset committed after the write:** `enable.auto.commit=false`, then
  `commit(message)` once MongoDB has the result.
- **Exactly-once effect:** `processed_events` records each `event_id`, so a
  redelivered message is skipped. New entries are tagged with the
  `event_id`, so a crash between "insert new" and "delete old" is cleaned up
  on retry. The test kills the write half-way and checks that 27 entries
  remain, not 89.
- **Bounded retries:** 3 attempts with 1 s and 3 s backoff (e.g. Ollama
  unreachable), then the dead-letter topic. A poison message (not JSON, or
  missing envelope fields) goes to the DLQ immediately.

## How consolidation decides

1. **Code** merges exact duplicates, ignoring case and punctuation, so
   `Strong in Python.` and `strong in python` become one. It keeps the
   newest date and the original wording.
2. **The model** gets the remaining entries as numbered lines and returns
   JSON. Each output entry lists its `sources`, an `action`
   (`kept`/`merged`/`resolved`) and a `reason`. Rule: for contradictions, keep
   only the **newest** fact.
3. **Code validates** the model's answer:

| Check | If it fails |
|---|---|
| Every input used exactly once | Re-prompt with the missing or doubled numbers |
| Sources exist | Re-prompt ("cites sources that do not exist") |
| Fewer than 40 entries | Re-prompt |
| Date = newest source date | **Corrected by code** and logged |
| Category valid | **Corrected** (taken from the newest source) and logged |

   After one re-prompt, the deterministic fallback runs (near-duplicate merge
   at ≥ 75% word overlap). It cannot detect contradictions, and the record
   says so.
4. Everything (before, after, decisions, corrections, rejected answers,
   timing) is stored in `memory_consolidations` under the `event_id`.

## The 62-entry verification

`memory_seed.py`: one student, **62 entries** describing **27 facts**, with
**4 exact-duplicate groups** and **5 contradictions**:

| | Older fact | Newer fact |
|---|---|---|
| C1 | Lives in Sunnyvale (Aug 3, Aug 25) | Moved to Palo Alto (Oct 2, Oct 15) |
| C2 | Internships only (Aug–Sep, 3 entries) | Full-time roles (Oct 12, Oct 22) |
| C3 | On-site only, no remote (Aug 5, Aug 30) | Open to fully remote (Oct 18) |
| C4 | Graduate May 2027 (Aug 3, Aug 21) | December 2027 (Oct 20) |
| C5 | Minimum salary 70,000 (Aug 5, Sep 10) | 85,000 (Oct 24) |

`memory_seed.check()` verifies the result automatically: fewer than 40
entries, each duplicate group present at most once, and for each
contradiction the old fact is **gone** and the new one is **present**.

Evidence run (real model, through Kafka):

```bash
cd backend
python scripts/memory_consolidation_report.py --student 1 --via-kafka \
  | tee ../docs/evidence/memory_consolidation.txt
```

The tests (`tests/test_memory.py`, 16 cases) check the same pipeline with
scripted models: a correct one, one that drops facts and gets dates wrong
(caught and re-prompted), one that returns no JSON (fallback), and one that
is offline (3 attempts, then the DLQ).

## Incident from the first real run (Oct 31) and the fix

The first run against qwen3:8b on a MacBook failed, and the failure is
recorded here because it exercised the reliability design for real:

1. Each consolidation call **timed out at 180 s**. The model spent most of
   its time on qwen3's hidden "thinking" before writing a long JSON answer.
2. After 3 attempts (about 11 minutes) the message was **dead-lettered**, and
   the 62 entries were left untouched, as designed.
3. The processing had exceeded Kafka's **`max.poll.interval.ms` (5 min)**.
   Kafka removed the worker from its group, `commit()` failed with
   `UNKNOWN_MEMBER_ID`, the worker crashed, Docker restarted it, and Kafka
   **redelivered** the uncommitted message, which started the cycle again.
   Nothing was lost or duplicated, but the loop never ended.

Fixes (`memory_worker.py`, `agent/client.py`), each covered by a test in
`tests/test_memory.py`:

- **A separate model client for the worker:** `think: false`,
  `num_ctx` 16384, 600 s per call.
- **`max.poll.interval.ms`** is set to the worst case (3 x 600 s + backoff +
  margin, about 32 min).
- **A failed commit is logged, not raised.** The redelivered message is
  skipped through `processed_events`.
- **Dead-lettered messages are recorded in `processed_events`**, so a
  redelivery does not retry them and dead-letter them a second time.
- **The report script prints progress as it waits** and stops early with a
  clear message if the worker dead-letters the event.
