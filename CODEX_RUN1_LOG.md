# Codex Run 1 audit

Scope: student profile, company profile, company job posting only. No commits,
pushes, resets, schema changes, deletion, or work in another repository.

## Inspection and commands

- `git status`: main branch; intentional Week 2 modifications in .env.example,
  main.py, routers/core.py, schemas.py, App.css, App.jsx; untracked auth.py,
  backend/tests/, docs/week2-verification.md. Preserved.
- `cat` inspected auth.py, routers/core.py, schemas.py, models/core.py,
  models/additional.py, schema.sql, App.jsx, App.css, index.css, package.json,
  tests/week2_smoke.py; focused `sed -n '1,115p' backend/schema.sql` confirmed
  column lengths, YEAR, DECIMAL, enums and foreign keys.
- `cat backend/app/main.py backend/app/database.py`: inspected CORS, health,
  database configuration loading. Real .env was not read or copied.
- `rg --files -g AGENTS.md -g '!node_modules'` found no repository instructions
  (exit 1 means no matches); ancestor AGENTS.md checks also found none.
- Filesystem/network permission obtained for this repository/local tests.

## Plan and findings

Existing create/read routes and JWT dependencies are suitable. No profile
update routes exist. Add PUT on existing resource URLs with owner/role checks,
reuse base Pydantic schemas, add DB-compatible input constraints. Use small
React pages and a shared authenticated API helper; preserve dashboards.

## Changes and verification

Implementation and test results will be appended below as work proceeds.

### Implementation

- Python file edits added PUT `/students/{user_id}` and PUT `/companies/{user_id}`
  to routers/core.py, reusing StudentBase/CompanyBase and existing JWT roles.
  Owner ID checked before lookup (403); missing own profile gives 404.
- schemas.py: DB-compatible string/numeric/year bounds, nonblank required names,
  job text validation, deadline >= posting date. No model/schema migration.
- App.jsx: small page state, wired profile/job buttons, stable 401 reset callback.
- api.js: shared bearer fetch, readable validation/network errors, 401 handling.
- components/ProfilePage.jsx: load/create/edit, empty/error/success/retry states.
- components/JobPostPage.jsx: typed form, profile-required guidance, success ID.
- components/fields.jsx: shared controls and lossless JSON array editing.
- App.css: appended scoped responsive form styles; existing rules preserved.
- Shell commands: `mkdir -p frontend/src/components`; heredoc writes and focused
  Python string edits above. No secrets recorded or modified.

### First verification results

- `npm --prefix frontend run build`: PASS initially and after utility split.
- `npm --prefix frontend run lint`: initially FAILED on two Fast Refresh export
  errors in fields.jsx. Moved non-component utilities into formValues.js and
  updated imports; rerun PASS.
- `python3 backend/tests/run1_smoke.py`: PASS. Four fresh accounts; POST register
  201, login 200; own absent GET/PUT 404; create 201; update/read 200;
  unauthenticated/invalid token 401; wrong-role and same-role foreign-owner 403;
  invalid names/lengths/year/CGPA/skills 422. Jobs: no auth 401, student 403,
  foreign company 403, missing company profile 409, bad category/date/salary 422,
  successful create 201 and independent GET 200 with all field values verified.
  CORS PUT preflight from localhost:5174 returned 200 and matching origin.
- `python3 backend/tests/week2_smoke.py`: PASS, including root/DB health 200,
  both dashboard endpoints 200/403, missing/invalid tokens 401, duplicate 409,
  existing student/company/job create/read/list routes and CORS 200.
- `git diff --check`: PASS.
- Created backend/tests/run1_smoke.py; tests retain all new data.

### Browser progress and additional checks

- Browser student: signup success; login -> Student Dashboard; My Profile showed
  empty state; created name/college/year/CGPA/skills; success message observed;
  updated name; reopened profile and verified persisted values; logout -> Login.
- `node --input-type=module` with mocked fetch: shared helper 401 callback PASS;
  network error messaging PASS. No real tokens used or recorded.
- Browser company: signup/login/dashboard PASS. Native date automation fill did
  not set the deadline; attempted navigation consequently found no profile-link
  button because HTML required validation prevented submit. Inspected DOM/date
  screenshot, entered date via native day/month/year keyboard segments. This
  was an automation issue; no application workaround or date-control change.
- `git diff -- backend/app/schemas.py | head -120`: reviewed focused validators.

### Completed browser verification

- Student profile: empty -> create -> success -> edit -> update success -> back
  to dashboard -> reopen shows saved name/college/year/CGPA/skills -> logout.
- Company: signup/login/dashboard; job submission before profile showed
  "Create your company profile before posting a job." and profile navigation.
  Company profile created; an unexpected browser session reset occurred before
  the next edit. Logged back in, verified saved profile, updated company name,
  observed update success, and reopened the updated profile later.
- Job posting: valid text/date/category form submitted; displayed
  "Job posted successfully. Run One Browser Job (Job #6)"; return to dashboard
  and company logout verified.
- Read-only SQLAlchemy check via `PYTHONPATH=backend
  /Users/bhavana/Desktop/Anaconda3/anaconda3/bin/python` verified browser job #6
  in MySQL and its company name update. No token/credential output.
- Browser screenshot/DOM checked mobile company form at 390x844: one column,
  content width 390 equals viewport 390; fields and controls usable.
- Tablet viewport change reset the in-memory browser session. A subsequent
  computed-style query found no form (TypeError); restored default viewport.
  Tablet visual verification and full browser invalid-session redirect were
  therefore not completed. No application failure was established.
- For attempted browser 401 test, only the newly created Run 1 browser company
  test account was temporarily marked inactive via SQLAlchemy, then restored
  active immediately after the session reset prevented the intended test.
  No existing user was modified. API 401 and helper callback tests passed.
- `curl -s -o /dev/null -w 'API health %{http_code}...' .../health/db`: 200.
- `git status --short`: intentional Week 2 changes still present; Run 1 additions
  listed below. No Git staging, commits, pushes, restores, or resets executed.

## Files changed in Run 1

Modified: backend/app/routers/core.py, backend/app/schemas.py,
frontend/src/App.jsx, frontend/src/App.css.
Created: CODEX_RUN1_LOG.md, backend/tests/run1_smoke.py, frontend/src/api.js,
frontend/src/components/ProfilePage.jsx, frontend/src/components/JobPostPage.jsx,
frontend/src/components/fields.jsx, frontend/src/components/formValues.js.
Build also regenerated ignored frontend/dist/ assets.
Existing auth.py, main.py, .env, .env.example, models, database schema,
week2_smoke.py and week2-verification.md were not changed in this run.

## Manual verification

If already running, reuse the existing servers. Otherwise separate terminals:

```sh
cd ~/Desktop/Lab1/data260-handshake-pair15-main
/Users/bhavana/Desktop/Anaconda3/anaconda3/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 9150 --reload
```

```sh
cd ~/Desktop/Lab1/data260-handshake-pair15-main/frontend
npm run dev -- --port 5174 --strictPort
```

```sh
cd ~/Desktop/Lab1/data260-handshake-pair15-main
python3 backend/tests/run1_smoke.py
python3 backend/tests/week2_smoke.py
npm --prefix frontend run build
npm --prefix frontend run lint
git diff --check
git status
```

Both smoke tests add fresh test data and never delete it. At localhost:5174,
register a fresh student, login, View Profile, create, edit, save, go back and
reopen to verify persistence, then logout. Register a fresh company; try Post
Job before profile creation and verify guidance; follow Create Company Profile,
create/edit/save; return to dashboard and post a job with all required fields.
Confirm success with job ID. API retrieval is available through /docs using
Authorize with a login token; do not share or record that token.

No Run 2 features implemented. Skills use a JSON-array field to preserve the
existing arbitrary-list schema. Unsaved form drafts are not retained when
navigating away. JWT lifetime/reload/logout behavior remains as in Week 2.
