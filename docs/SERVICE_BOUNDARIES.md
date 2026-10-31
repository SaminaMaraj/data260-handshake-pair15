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
  committed): `DATABASE_URL` (becomes `MONGO_URL` after the Mongo migration),
  `JWT_SECRET_KEY` (32+ chars, **must be identical in every service**, or a
  token from Student is rejected by Job), and `CORS_ORIGINS`
  (comma-separated; defaults to the localhost dev ports).
- **Assistant only:** `OLLAMA_HOST` (e.g. `http://p15-ollama:11434`).
- **Gateway:** the image is `nginx:alpine` with `gateway/nginx.conf` mounted at
  `/etc/nginx/nginx.conf`. Upstream hosts are already the `p15-<service>` DNS
  names, so it works unchanged in Compose (service names) and Kubernetes
  (Service names in namespace `p15`). The frontend's API base URL stays
  `http://<host>:9150`.
- **Regenerating the gateway config** after any routing change, from `backend/`:
  `python scripts/gen_gateway_conf.py docker > ../gateway/nginx.conf`

## Running locally without Docker

From `backend/`, with `DATABASE_URL` and `JWT_SECRET_KEY` set:

```bash
bash scripts/run_services.sh                    # six services on 9151–9156
nginx -c "$PWD/../gateway/nginx.local.conf"     # gateway on 9150
python -m pytest tests/test_service_split.py -q # 14 checks
```

## Coming next (Samina)

- **S3:** MongoDB collections and the data-access module that Kafka workers
  call (`services/common/db.py`).
- **S4:** the Kafka message envelope (`services/common/events.py`):
  `{event_id, trace_id, type, key, payload, created_at}`.
