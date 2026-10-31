# p15-event: Event service: events and registrations (publishes p15.event.registration_created).
# Build from the repository root:
#   docker build -f backend/services/event/Dockerfile -t p15-event:latest .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SERVICE_NAME=p15-event

WORKDIR /app

# Only this service's dependencies (backend/requirements/event.txt).
COPY backend/requirements/base.txt backend/requirements/event.txt requirements/
RUN pip install -r requirements/event.txt

# Only the code this service runs: the shared package and its own routes.
COPY backend/app/schemas.py app/schemas.py
COPY backend/services/__init__.py services/__init__.py
COPY backend/services/common services/common
COPY backend/services/event services/event

RUN useradd --uid 10015 --no-create-home --shell /usr/sbin/nologin p15
USER p15

EXPOSE 9155
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:9155/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "services.event.main:app", "--host", "0.0.0.0", "--port", "9155"]
