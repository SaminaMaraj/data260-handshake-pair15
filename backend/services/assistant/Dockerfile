# p15-assistant: AI assistant service: agent loop, memory, guardrails; the same image runs the memory worker.
# Build from the repository root:
#   docker build -f backend/services/assistant/Dockerfile -t p15-assistant:latest .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SERVICE_NAME=p15-assistant

WORKDIR /app

# Only this service's dependencies (backend/requirements/assistant.txt).
COPY backend/requirements/base.txt backend/requirements/assistant.txt requirements/
RUN pip install -r requirements/assistant.txt

# Only the code this service runs: the shared package and its own routes.
COPY backend/app/schemas.py app/schemas.py
COPY backend/services/__init__.py services/__init__.py
COPY backend/services/common services/common
COPY backend/services/assistant services/assistant

RUN useradd --uid 10015 --no-create-home --shell /usr/sbin/nologin p15
USER p15

EXPOSE 9156
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:9156/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "services.assistant.main:app", "--host", "0.0.0.0", "--port", "9156"]
