# Authenticated assistant integration

The existing UI posts `message` and the last canonical `conversation` to
`/assistant/chat` with its bearer JWT. Both assistant endpoints require a student
account. The legacy `student_id` chat field is accepted but ignored; identity
comes from the validated token. Companies see an explanatory disabled composer.

Read-only tools remain available. A `save_job_or_event` call returns a validated,
student-bound pending action, never an immediate write. Model-provided IDs for
student identity and `confirmed` flags do not authorize anything. The UI shows
the target and explicit Yes/No controls. `/assistant/confirm` accepts only
`pending_id` and a strict boolean `approve`; its ownership/expiry check and
single-use claim run in the same transaction as the save. Rejection consumes the
pending action without saving. Replays, expired IDs, and other students' IDs
return 409. Multi-tool batches containing writes pause for one approval at a time;
other calls are marked unexecuted in the canonical tool history.

## Database setup

Run once per database from the project root before starting the updated backend:

```sh
PYTHONPATH=backend python backend/scripts/init_assistant_pending.py
```

This idempotently adds only `assistant_pending_actions` using the configured
SQLAlchemy database. MySQL student IDs use the existing unsigned BIGINT type.
It does not modify or replace existing tables. The local development database
was provisioned during implementation. Other deployments must run this command.
Pending IDs are random, stored hashed, expire after ten minutes, and survive
process restarts and multiple workers sharing the database. Records retain their
conversation context; deployments can delete expired rows as maintenance.

Ollama configuration remains `OLLAMA_BASE_URL` and `OLLAMA_MODEL`. Unavailable
service calls return HTTP 503, displayed by the UI. No live-model availability
is assumed by the tests. No conversation text is rendered as HTML.

History lives in the mounted chat component and is preserved exactly as returned
by the backend, including tool messages. Clear resets visible messages, history,
and the pending UI; abandoned server actions remain unusable after expiry. Page
reload, logout, or leaving the dashboard ends this client chat session. A network
failure after a successful confirmation may leave the UI uncertain; retry cannot
execute the same approval twice. The saved-items page shows the persisted result.

## Focused verification

```sh
python -m pytest backend/tests/test_assistant_integration.py backend/tests/test_event_integration.py -q
cd frontend
node --test tests/assistant.test.mjs
./node_modules/.bin/eslint src/components/AssistantChat.jsx src/components/StudentDashboard.jsx src/App.jsx
npm run build
```

Frontend tests use React's test renderer and mocked HTTP responses; backend tests
use isolated SQLite databases and scripted LLM responses. These verify behavior,
not browser layout or a live Ollama model. The test renderer is development-only.
