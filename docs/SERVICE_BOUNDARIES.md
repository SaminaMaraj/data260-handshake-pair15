# Lab 2 Service Boundaries (Pair 15)

Source of truth: `backend/services/common/routing.py`. If a route moves,
change it there, regenerate the gateway config, and rerun
`tests/test_service_split.py`.

## Services

| Service | Container / K8s name | Port | Uvicorn target | Owns paths |
|---|---|---|---|---|
| Gateway (nginx) | `p15-gateway` | 9150 | `gateway/nginx.conf` | everything below, forwarded |
| Student | `p15-student` | 9151 | `services.student.main:app` | `/users` (login and register for **both** roles), `/students`, `/directory`, `/profiles`, `/resumes`, `/media`, `/saved-items` |
| Company | `p15-company` | 9152 | `services.company.main:app` | `/companies` (except the two below) |
| Job | `p15-job` | 9153 | `services.job.main:app` | `/jobs`, `/companies/me/jobs` |
| Application | `p15-application` | 9154 | `services.application.main:app` | `/applications`, `/companies/me/applications` |
| Event | `p15-event` | 9155 | `services.event.main:app` | `/events`, `/event-registrations` |
| Assistant | `p15-assistant` | 9156 | `services.assistant.main:app` | `/assistant` |

Ownership is by **longest path prefix**, so `/companies/me/jobs` goes to
the Job service, not Company. Together the six services serve all 55
Lab 1 routes, each exactly once.

## What every service has

- `GET /health`: liveness, no dependencies. Use it for the Docker
  `HEALTHCHECK` and the Kubernetes `livenessProbe`.
- `GET /health/db`: readiness, checks the database. Use it for the
  Kubernetes `readinessProbe`.
- An `X-Service: p15-<name>` response header, so screenshots and logs show
  which service answered.

## Notes for Dockerfiles, Compose and Kubernetes (Bhavana)

- **Build context:** `backend/`. All six images share the same code; only
  the start command and port differ. One parameterized Dockerfile is fine,
  but the handout asks for **a separate Dockerfile per service**, so write
  six (e.g. `backend/services/<name>/Dockerfile`) that each `COPY app/ services/`
  and run their own target:
  `CMD ["uvicorn", "services.job.main:app", "--host", "0.0.0.0", "--port", "9153"]`
- **Working directory** inside the image must be the `backend/` root so
  `import app...` and `import services...` resolve.
- **Environment** (from `.env` in Compose and a Secret in Kubernetes, never
  committed):
  - `MONGO_URL`, e.g. `mongodb://p15-mongo:27017`
  - `MONGO_DB`, default `handshake_p15`
  - `JWT_SECRET_KEY`: 32+ chars, and **it must be identical in every service**,
    or a token from Student is rejected by Job
  - `CORS_ORIGINS`: comma-separated; defaults to the localhost dev ports
  - `DATABASE_URL` is no longer used by the services; only the migration
    script reads a SQL URL
- **Assistant only:** `OLLAMA_BASE_URL` (e.g. `http://p15-ollama:11434`) and
  `OLLAMA_MODEL` (default `qwen3:8b`).
- **Seeding Mongo in a container or pod:** run this once (e.g. as a Kubernetes Job):
  `python scripts/migrate_to_mongo.py --from-seed --drop`
  It generates the Pair 15 dataset (seed 15) and loads it: 250 users,
  300 jobs, 1,500 applications and 100 events.
- **Gateway:** the image is `nginx:alpine` with `gateway/nginx.conf` mounted at
  `/etc/nginx/nginx.conf`. Upstream hosts are already the `p15-<service>` DNS
  names, so it works unchanged in Compose (service names) and Kubernetes
  (Service names in namespace `p15`). The frontend's API base URL stays
  `http://<host>:9150`.
- **Regenerating the gateway config** after any routing change, from `backend/`:
  `python scripts/gen_gateway_conf.py docker > ../gateway/nginx.conf`

## Running locally without Docker

From `backend/`, with `MONGO_URL` and `JWT_SECRET_KEY` set and MongoDB running:

```bash
bash scripts/run_services.sh                    # six services on 9151–9156
nginx -c "$PWD/../gateway/nginx.local.conf"     # gateway on 9150
python -m pytest tests/test_*.py -q             # all unit and parity tests
```

## For the Kafka workers (Bhavana)

- **Collections and storage rules:** `docs/MONGODB_SCHEMA.md`.
- **Write through `services/common/repo.py`, not raw inserts,** so the worker
  and the API produce identical documents:
  - `repo.create_application(db, job_id=, student_id=, resume_id=, trace_id=, application_id=)`
  - `repo.update_application_status(db, application_id=, company_id=, status=, trace_id=)`
  - `repo.create_registration(db, event_id=, student_id=, user=, trace_id=, registration_id=)`

  Each raises `repo.DomainError(status, message)` on a business error (e.g.
  deadline passed); send that to the dead-letter topic instead of retrying.
- **Idempotency is built in:** pass the id carried in the message
  (`application_id=` / `registration_id=`). A replay hits the `_id` and
  `(job_id, student_id)` unique indexes and raises a 409 `DomainError`
  instead of creating a duplicate.
- **Producer hooks.** The routes already call these lists after a successful
  write, so a producer can be attached with no route edits:
  - `services/job/routes.py`: `on_job_saved`, called as `(job, created=True|False)`
  - `services/application/routes.py`: `on_application_created`, called as `(row)`,
    and `on_status_changed`, called as `(row, old_status)`
  - `services/event/routes.py`: `on_registration_created`, called as
    `(registration, event)`
- **Kafka message envelope:** `services/common/events.py` (next on Samina's list):
  `{event_id, trace_id, type, key, payload, created_at}`.
