# Codex Run 2 audit

Scope: job browse/filter/details, student application creation and private status
list. No Git staging/commits/pushes/resets/restores; no data deletion.

## Inspection

- `git status`: main; all intentional Week 2/Run 1 modifications/untracked files
  present and preserved.
- `cat` inspected models/core.py, models/additional.py, schemas.py,
  routers/core.py, auth.py, App.jsx, api.js, App.css, ProfilePage.jsx,
  JobPostPage.jsx, week2_smoke.py, run1_smoke.py.
- `rg -n 'resume_id|CREATE TABLE applications|UNIQUE' backend/schema.sql`:
  applications requires resume_id and has unique(job_id,student_id).
- `rg --files backend/tests frontend/src/components`: existing files inventoried.
- `rg --files -g AGENTS.md -g '!node_modules'`: no instructions found (exit 1).
- Permission granted for repository writes and local network testing.

## Scope conflict

Both model and schema require a resume. Resume upload is excluded from Run 2.
Asked user for the narrow exception to allow nullable applications.resume_id;
no schema change will be made without that answer. Independent browsing work
continues meanwhile. Real .env contents/secrets are not read into this log.

## Decision and implementation

User explicitly chose: keep resume required; block applications without one.
No model/schema/DDL changes. Added read-only existing-resume choices so a student
can select an owned resume; no upload functionality. New test fixtures will be
created only for unique smoke-test accounts to verify successful applications.

- Created jobFilters.js, useApiData.js, JobInfo.jsx, JobsPage.jsx,
  JobDetailsPage.jsx, ApplicationsPage.jsx. Reuses api.js and existing job APIs.
- Modified App.jsx navigation and appended scoped styles to App.css.
- Added ApplicationCreate (extra fields forbidden), ApplicationRead and
  ResumeOption schemas; no status or student identity accepted from browser.
- Created routers/applications.py: GET/POST /applications; GET
  /applications/resume-options. Student role, private list, owned resumes,
  missing-job 404, duplicate 409 with existing DB uniqueness race protection.
- main.py includes the new router. No company applicant endpoints.
- Commands: heredoc file creation and focused Python edits; no destructive edits.

## Tests and environment failure

- First build and lint PASS. `python3 backend/tests/run2_smoke.py` failed at first
  registration: expected 201, got 500. No application success claimed.
- `curl --max-time 5 .../health/db`: timeout (000). API imports successfully via
  backend interpreter. `lsof` shows existing API/Vite listeners and Docker 3307.
- Direct SQLAlchemy connection with 3-second connection/read timeouts:
  OperationalError, driver code 2013. Error contents suppressed to avoid secrets.
- `docker context show`: desktop-linux. `docker ps` and `docker info` timed out
  under an 8-second subprocess limit. Docker Desktop UI request also timed out.
  Asked user to resume/restart Docker; no containers recreated or deleted.
- Created run2_smoke.py plus run2_db_fixture.py and fixtures/run2_resume.txt.
  Fixtures are synthetic documents for new test accounts, not an upload feature.
  Smoke test uses backend interpreter for MySQL setup and persistence verification.
- Created frontend/tests/run2.test.mjs. `node frontend/tests/run2.test.mjs` PASS:
  combined case-insensitive filters, zero results, clear, empty list, remote/onsite,
  API helper 401 reset, 403, duplicate error and network errors.
- api.js now handles non-JSON error bodies and triggers 401 reset before parsing.
- Repeated build/lint/diff checks after helper change recorded in final section.

## Final verification before external blocker

- `python3 backend/tests/week2_smoke.py` under 12-second subprocess limit:
  root 200 PASS; then timed out on database health. FAIL/environment blocked.
- `python3 backend/tests/run1_smoke.py` under same limit: timed out at database
  registration. FAIL/environment blocked. Existing tests were not edited.
- FastAPI TestClient using actual application/auth dependencies (no DB overrides):
  missing and malformed tokens on GET /applications, GET
  /applications/resume-options, POST /applications all returned 401 PASS.
  OPTIONS /applications returned 200 with localhost:5174 allow-origin PASS.
- Frontend browser opened the live Login screen. Authenticated browser flows,
  duplicate/no-resume messages, navigation and responsive Run 2 verification:
  NOT AUTOMATED because live login depends on the unavailable database.
- `node frontend/tests/run2.test.mjs`: PASS; filter and helper behavior automated
  independently of browser/MySQL. This is not a browser-flow success claim.
- `npm --prefix frontend run build`: PASS after final helper change.
- `npm --prefix frontend run lint`: PASS after final helper change.
- `git diff --check`: PASS. `git status --short` recorded below.
- Run 2 smoke has bounded socket/fixture subprocess timeouts for reruns.

## Remaining blocker

Docker engine does not respond to ps/info; MySQL driver code 2013; health timed
out. Successful applications, duplicates, ownership, status, persistence and
full regressions remain UNVERIFIED in this run. Resume remains mandatory by
user instruction. Students with no stored resume are intentionally blocked;
Run 3 upload is not implemented. No schema changes or data deletion.

## Run 2 file inventory

Modified: backend/app/main.py, backend/app/schemas.py, frontend/src/App.jsx,
frontend/src/App.css, frontend/src/api.js.
Created: CODEX_RUN2_LOG.md; backend/app/routers/applications.py;
backend/tests/run2_smoke.py; backend/tests/run2_db_fixture.py;
backend/tests/fixtures/run2_resume.txt; frontend/tests/run2.test.mjs;
frontend/src/components/jobFilters.js; frontend/src/components/useApiData.js;
frontend/src/components/JobInfo.jsx; frontend/src/components/JobsPage.jsx;
frontend/src/components/JobDetailsPage.jsx; frontend/src/components/ApplicationsPage.jsx.
Ignored frontend/dist assets regenerated by Vite build.

Final working tree (includes preserved prior work):

```text
 M .env.example
 M backend/app/main.py
 M backend/app/routers/core.py
 M backend/app/schemas.py
 M frontend/src/App.css
 M frontend/src/App.jsx
?? CODEX_RUN1_LOG.md
?? CODEX_RUN2_LOG.md
?? backend/app/auth.py
?? backend/app/routers/applications.py
?? backend/tests/
?? docs/week2-verification.md
?? frontend/src/api.js
?? frontend/src/components/
?? frontend/tests/
```

After Docker is restored, rerun automatically:
`python3 backend/tests/week2_smoke.py`, `python3 backend/tests/run1_smoke.py`,
`python3 backend/tests/run2_smoke.py`, then browser flows. Do not delete fixtures.
No commits/pushes/staging/destructive Git commands. Run 3 not started.
