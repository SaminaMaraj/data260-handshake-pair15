# AI_USE.md

This file records how each partner used AI assistants while building
Lab 1 and Lab 2 (Lab 2 is at the end), with incorrect outputs, how they were detected, and how they
were fixed.

Two kinds of AI were involved:

- **Coding assistants** (ChatGPT and Claude) used during development
  for planning, code drafts, debugging, rubric review, and documentation
  review.
- **The runtime model** (qwen3:8b through Ollama) that powers the
  application's assistant.

All code was reviewed, run, and tested locally before it was committed.

---

## Kazi Samina Maraj Mumu

### How I used AI assistants

- ChatGPT: writing prompts for each weekly task, drafting FastAPI routes,
  SQLAlchemy models, the seed generator, and assistant tools, and
  debugging errors.
- Claude: reviewing the repository against the Lab 1 rubric, finding
  problems in the assistant loop, and writing fixes for the follow-up
  validation, repair path, and confirmation flow.
- Both: reviewing METRICS.md, RUN_LOG.txt, and this file.

### Incorrect output 1 (coding assistant): test-specific overrides in the loop

**What was wrong.** An early version of `loop.py` generated with a
coding assistant checked the user's message for exact phrases such as
"remote data science internship" and "computer science students next
month", then replaced the model's tool arguments with fixed values.
It also copied saved preferences over every `search_jobs` call. The
required tests passed, but because the code chose the arguments, not
the model. The preference overwrite also undid the model's
"higher-paying" change in the follow-up test.

**How it was detected.** A rubric review of the repository read the
loop line by line and found the phrase checks. Comparing the tool-call
log with the code showed the arguments came from the overrides.

**Fix.** The phrase checks and the preference overwrite were removed.
The real causes were fixed instead:

- Today's date is in the system prompt, so the model can compute
  "next month".
- `category` is an `enum` of the four valid values in the tool schema.
- Invalid arguments are rejected with a specific error and one retry
  (the repair path).

Only the student ID is still set by the code, for security.

### Incorrect output 2 (runtime model): company numbers used as job IDs

**What was wrong.** In the follow-up test ("From those results, show me
the higher-paying options"), qwen3:8b called `rank_jobs` with
`[18, 31, 49, 9, 45, 26, 19, 41, 40, 21]`. These were the numbers from
company names such as "Pair 15 Company 0018", not job IDs. The real IDs
from the previous search were different.

Before validation was added, the model had also sent made-up IDs such
as `[123, 456, 789]`. Because the database has 300 jobs, an ID like 123
is a real job that was not in the search, so it could have ranked the
wrong jobs silently.

**How it was detected.** The new validation compared the requested IDs
with the IDs from the most recent `search_jobs` result and rejected
them. The run stopped with `repair_failed` and failures
`['text_instead_of_tool', 'malformed_arguments']`.

**Fix.**

- `search_jobs` now starts its result with a `JOB_IDS: [...]` line,
  and each job's field is named `job_id`.
- The repair error says only the `job_id` values on the `JOB_IDS` line
  are valid, that numbers in company names are not job IDs, and lists
  the valid IDs.
- The text-only repair and the tool-call repair have separate one-time
  limits, so a text reply cannot use up the repair the ID error needs.

### Incorrect output 3 (coding assistant): confirmation the model could approve

**What was wrong.** The first `confirm_action` returned True when the
argument `confirmed` was True. The model filled in that argument, so the
model could approve its own save and the student was never asked.

A later coding-assistant version used `input()`. That worked in a
terminal test, but inside FastAPI it would make the server wait for
typing in its own terminal, so a save from the website would hang.

**How it was detected.** Code review against the rubric requirement
"If the student declines, return a cancellation string to the model".

**Fix.** `confirm_action` now returns `approved`, `declined`, or
`pending`. On the API it never calls `input()`: the loop stops with
`pending_confirmation`, the server stores the pending action, and the
student answers through `POST /assistant/confirm`. `confirmed` was
removed from the tool schema, and `auto_approve` is stripped from
anything the model sends.

### Incorrect output 4 (runtime model): wrong student ID

**What was wrong.** In the first assistant test, the model called
`get_student_preferences {"student_id": 123}` when the request was for
student 1.

**How it was detected.** The tool-call log was compared with the
`student_id` passed to `run_assistant()`.

**Fix.** The loop always sets `student_id` from the application, and
`student_id` was removed from the tool schemas so the model no longer
asks the student for it.

---

## Bhavana — AI Usage Disclosure

**1. Frontend UI Styling and Layout:** AI assistance was used to suggest improvements to the React frontend's layout, spacing, and navy-and-orange color scheme.

- *Detected:* The suggestions used fixed pixel widths for dashboard cards, which could cause overflow or misalignment on smaller screens. This was identified by resizing the browser window.
- *Corrected:* Replaced the fixed-width layout with a responsive CSS grid using flexible column widths so the cards adjust to different screen sizes.

**2. React Component Debugging:** AI assistance was used to identify possible causes of frontend rendering and navigation issues.

- *Detected:* Minor component rendering and navigation issues during frontend development.
- *Corrected:* Reviewed the suggested fixes and verified the affected components through testing.

**3. Frontend Testing and Validation:** AI assistance was used to interpret testing results and suggest troubleshooting approaches.

- *Detected:* Areas requiring verification through automated tests, ESLint, and production build checks.
- *Corrected:* Validated the frontend with 13 passing automated tests, successful ESLint checks, and a successful Vite production build.

**4. UI Documentation:** AI assistance was used to improve the organization and clarity of frontend documentation.

- *Detected:* Opportunities to improve descriptions and presentation of implemented features.
- *Corrected:* Organized descriptions and screenshots of the Student Portal, Company Portal, and AI Assistant interface.
---

# Lab 2

## Kazi Samina Maraj Mumu

### How I used AI assistants

- Claude: planning my part of Lab 2, writing and debugging code for the
  service split, the MongoDB migration, memory and consolidation, the
  guardrails, tracing, compaction, Docker and the JMeter scripts, and
  drafting documentation and the report.
- The runtime model (qwen3:8b) runs inside the app: the assistant and
  memory consolidation.
- I ran every step on my own laptop, checked the results against the
  running system, and made the commits.

### Incorrect output 1 (coding assistant): missing dependency

- **What happened:** Claude added `jsonschema` (used by guardrail G2) to
  the assistant's Docker requirements but not to the top-level
  `requirements.txt`. The Docker images worked, so nothing failed there.
- **How I detected it:** when I ran the tests from my own local
  environment for the report, `tests/test_guardrails.py` failed to
  import and the harness crashed with
  `ModuleNotFoundError: No module named 'jsonschema'`.
- **Fix:** added `jsonschema` to `requirements.txt` (commit `2cd01be`).
  Afterwards: 183 tests passed and the harness passed 18/18.

### Incorrect output 2 (coding assistant): a demo that failed for the wrong reason

- **What happened:** the compaction demo reported 2/3. It read the turn's
  tool calls from the conversation in the response, but automatic
  compaction had already replaced that conversation with a summary, so
  it saw no tool calls and failed the `rank_jobs` check.
- **How I detected it:** every compacted turn showed `tools: []` even
  though its answer listed real search results.
- **Fix:** the API now returns `tools_used` for each turn, recorded before
  compaction; `/compact` is skipped when it would not save tokens; the
  context window was raised to 16,384 (commit `f97a1c5`). Rerun: 3/3.

### Incorrect output 3 (runtime model): facts lost during consolidation

- **What happened:** with qwen3:8b, consolidation passed all 10 checks
  (62 -> 24 entries), but 3 of the 27 facts disappeared. The model
  grouped "studying for an MS in Applied Data Intelligence", "strong in
  Python" and "prefers small companies" with unrelated entries, and the
  newest-entry rule kept the other entry.
- **How I detected it:** I compared the facts before and after
  (`docs/evidence/memory_facts_kept.txt`) instead of trusting the check
  results; the checks only tested "at most one copy".
- **Fix / next step:** documented in `docs/MEMORY.md` and the report. The
  right fix is a check that every distinct fact survives, and rejecting
  groups whose entries share too few words.

### Incorrect output 4 (coding assistant): default gateway settings

- **What happened:** the generated nginx gateway used default settings
  (1 worker, 512 connections, a new upstream connection per request).
- **How I detected it:** the first JMeter run had 502s at 100-200 users
  and 89-99% errors from 300 users, while the service logs showed healthy
  responses.
- **Fix:** tuned workers, connections and upstream keepalive (commit
  `f3dcbb9`). Second run: 0% errors at every level.

---

## Bhavana

*To be added by Bhavana: how she used AI assistants in Lab 2, at least
one incorrect output, how it was detected, and the fix.*
