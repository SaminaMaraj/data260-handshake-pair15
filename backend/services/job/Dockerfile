# p15-job: Job service: job postings and search (publishes p15.job.created).
# Build from the repository root:
#   docker build -f backend/services/job/Dockerfile -t p15-job:latest .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SERVICE_NAME=p15-job

WORKDIR /app

# Only this service's dependencies (backend/requirements/job.txt).
COPY backend/requirements/base.txt backend/requirements/job.txt requirements/
RUN pip install -r requirements/job.txt

# Only the code this service runs: the shared package and its own routes.
COPY backend/app/schemas.py app/schemas.py
COPY backend/services/__init__.py services/__init__.py
COPY backend/services/common services/common
COPY backend/services/job services/job

RUN useradd --uid 10015 --no-create-home --shell /usr/sbin/nologin p15
USER p15

EXPOSE 9153
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:9153/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "services.job.main:app", "--host", "0.0.0.0", "--port", "9153"]
