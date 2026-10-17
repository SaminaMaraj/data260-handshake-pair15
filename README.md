# Handshake Pair 15

DATA 260 Lab 1: a Handshake-style career platform for students and
companies (React, FastAPI, MySQL) with a hand-built AI assistant that
uses tools against the application's own data.

Partners: Kazi Samina Maraj Mumu and Bhavana (GitHub: venkatasaibhavanay).

## Pair configuration

| Parameter | Derivation | Value |
|---|---|---|
| PAIR | Assigned on Canvas | 15 |
| PORT_BASE | 9000 + (PAIR × 10) | 9150 (backend port) |
| Database and Kafka prefix | p{PAIR} | p15 |
| SEED | PAIR, used as `random_state` | 15 |
| CITY_SET | Assigned on Canvas | Sunnyvale, Cupertino, Palo Alto |

Other local settings:

| Setting | Value |
|---|---|
| Database name | handshake_pair15 |
| MySQL host port | 3307 (Docker container port 3306) |
| Frontend dev server | http://localhost:5173 |
| Ollama model | qwen3:8b |

## Technology stack

- Frontend: React (Vite), Bootstrap
- Backend: Python, FastAPI, SQLAlchemy, PyJWT, bcrypt
- Database: MySQL 8.4 in Docker
- Model runtime: Ollama with qwen3:8b (no paid API key)

## Repository layout

```text
backend/
  app/
    main.py               FastAPI app and routers
    auth.py               JWT creation and role checks
    database.py           SQLAlchemy engine and sessions
    models/               SQLAlchemy models
    routers/              REST endpoints (part_a.py, assistant.py, ...)
    assistant/
      client.py           OllamaClient.complete(messages, tools)
      tools.py            Tool functions and JSON schemas
      loop.py             Hand-built agent loop, repair path, pending saves
      confirm.py          confirm_action(tool_name, arguments, auto_approve=False)
      followup_test.py    Test 4: follow-up in the same conversation
      confirm_flow_test.py  Confirmation gate tests
      reliability_run.py  20-turn reliability run
  seed_generator.py       Pair 15 seed generator (SEED = 15)
  schema.sql
  tests/
frontend/                 React application
docs/                     Schema and verification notes
METRICS.md  RUN_LOG.txt  AI_USE.md
```

## Setup

### 1. Environment file

```bash
cd ~/Desktop/data260-handshake-pair15
cp .env.example .env
```

Edit `.env` and set the MySQL passwords and `DATABASE_URL`, and set
`JWT_SECRET_KEY` to a random string of at least 32 characters. One way
to generate it:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Never commit `.env`.

### 2. MySQL

```bash
docker compose up -d
```

### 3. Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 9150 --reload
```

Check: http://127.0.0.1:9150/health/db should return `{"status": "ok"}`.

API documentation (Swagger UI): http://127.0.0.1:9150/docs

Protected endpoints need a JWT. Log in with `POST /users/login`, then
click **Authorize** in Swagger and paste the access token.

### 4. Seed data

The seed counts reported for this lab were produced by
`backend/seed_generator.py` (`random.Random(15)`, cities from CITY_SET):

```bash
cd backend
python seed_generator.py
```

| Table | Count |
|---|---:|
| Students | 200 |
| Companies | 50 |
| Jobs | 300 |
| Applications | 1,500 |
| Events | 100 |
| Resumes | 200 |
| Student preferences | 200 |

`backend/scripts/seed_data.py` is a second, additive generator written
during frontend integration. It was not used for the counts above.

### 5. Ollama

```bash
ollama pull qwen3:8b
ollama serve
```

All model calls go through `OllamaClient.complete(messages, tools)` in
`backend/app/assistant/client.py`. Nothing else calls Ollama directly.

### 6. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The frontend calls the backend at
http://127.0.0.1:9150.

## Features

### Student

- Sign up (name, email, password, college) and log in or out with JWT
- Profile with personal details, education, experience, skills, profile
  picture, and contact information
- Job search by title or company, with category and city filters
- Job details with company information
- Apply with a PDF resume and track application status
  (pending, reviewed, declined)
- Upcoming events: search, view details, register when eligible, view
  registered events
- Student directory search
- Saved jobs and job preferences
- AI Assistant panel on the dashboard

### Company

- Sign up (company name, email, password, location) and log in or out
- Post and edit jobs; view owned jobs and their applicants
- Preview applicant PDF resumes and update application status
- Company profile with picture
- Search students by name, college, or skills
- Post events with eligibility and view registered students

Role checks (`require_student`, `require_company`) and ownership checks
restrict users to their own actions, such as a company reviewing only
its own applicants.

## AI assistant

The assistant is a hand-built loop in `backend/app/assistant/loop.py`.
No agent framework is used.

### Loop

1. The system prompt, conversation history, user message, and tool
   schemas are sent to the model through `OllamaClient.complete`.
2. If the model requests tools, the loop validates each call, runs it,
   and appends the result to the conversation.
3. The loop repeats until the model gives a final answer, a save needs
   confirmation, a repair fails, or the iteration ceiling
   (`MAX_ITERATIONS = 6`) is reached.
4. One `TOOL_CALL <name> <arguments>` line is printed per tool call, and
   `TOTAL_TOOL_CALLS <n>` is printed after each run.

The student ID always comes from the application (the JWT on the API),
never from the model.

### Tools

| Tool | Purpose |
|---|---|
| get_student_preferences | The signed-in student's saved preferences |
| search_jobs | Filter jobs by title, company, category, city, salary, skills, deadline, remote status |
| rank_jobs | Sort jobs from the most recent search by salary |
| get_job_details | One job with company details |
| search_events | Upcoming events by name, city, date range, eligibility |
| save_job_or_event | Save a job or event (gated by confirmation) |

Every tool returns a string and catches its own errors.

`search_jobs` returns a `JOB_IDS: [...]` line followed by the job list,
so follow-ups such as "show me the higher-paying ones" use real job IDs.
`rank_jobs` only accepts IDs from the most recent `search_jobs` result.

### Repair path

Invalid tool calls (malformed arguments, unknown tool names, invalid
categories or dates, job IDs not in the latest search) are not run.
The loop sends the model one specific error message and lets it retry
once (`MAX_REPAIRS = 1`). If the next attempt is still invalid, the run
stops with status `repair_failed`.

If the model answers in plain text on its first step without calling a
tool, the loop re-prompts it once (`MAX_TEXT_REPAIRS = 1`).

Each run returns a `failures` list (`malformed_arguments`,
`unknown_tool`, `text_instead_of_tool`) used for the reliability table
in METRICS.md. Setting both limits to 0 gives the "before repair"
measurement with the same code.

### Prompt-injection defense

Database results are wrapped before they go back to the model:

```text
<untrusted_data source="search_jobs"> ... </untrusted_data>
```

`<` and `>` inside the data are escaped so stored text cannot close the
tag. The system prompt says everything inside these tags is data, not
instructions. Loop-generated messages such as repair errors are not
wrapped.

### Confirmation gate

`confirm_action(tool_name, arguments, auto_approve=False)` is in
`backend/app/assistant/confirm.py`. Only `save_job_or_event` is gated.

- On the website (API mode), a save request stops the loop with status
  `pending_confirmation`. The server stores the pending action under a
  random `pending_id`, together with the student and the checked
  arguments. The frontend shows Yes and No.
- `POST /assistant/confirm` with `{pending_id, approve}`:
  - Yes saves exactly the stored arguments.
  - No sends `Cancelled: the student declined to save <item> <id>.` to
    the model, which then replies without retrying.
- A pending ID can be used only once and only by the same student.
- The model cannot approve its own save, and a retry after a decline is
  blocked.
- In terminal tests, `CONFIRM_MODE = "terminal"` asks with `input()`.

### Assistant endpoints

| Method | Path | Body |
|---|---|---|
| POST | /assistant/chat | `{message, conversation}` (student from JWT) |
| POST | /assistant/confirm | `{pending_id, approve}` (student from JWT) |

## Running the assistant tests

From the `backend` folder, with Ollama running:

```bash
python -m app.assistant.followup_test
python -m app.assistant.confirm_flow_test scripted
python -m app.assistant.confirm_flow_test decline
python -m app.assistant.confirm_flow_test approve
python -m app.assistant.reliability_run
```

Results are recorded in METRICS.md and RUN_LOG.txt.



### Final frontend status

The React frontend is merged into `main`. The production build and ESLint checks pass. Browser end-to-end testing of the authenticated assistant chat and Yes/No confirmation flow is still pending.

The Part A pages—authentication, profiles, jobs, applications, resumes, events, directory, and company dashboard—are merged into `main`.

## Submission files

- `METRICS.md`
- `RUN_LOG.txt`
- `AI_USE.md`
- Report: `LabPair-15_Lab1_Report.pdf`
- Git tag: `lab1`