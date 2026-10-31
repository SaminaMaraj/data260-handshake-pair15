# p15-company: Company service: company profiles and dashboard.
# Build from the repository root:
#   docker build -f backend/services/company/Dockerfile -t p15-company:latest .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SERVICE_NAME=p15-company

WORKDIR /app

# Only this service's dependencies (backend/requirements/company.txt).
COPY backend/requirements/base.txt backend/requirements/company.txt requirements/
RUN pip install -r requirements/company.txt

# Only the code this service runs: the shared package and its own routes.
COPY backend/app/schemas.py app/schemas.py
COPY backend/services/__init__.py services/__init__.py
COPY backend/services/common services/common
COPY backend/services/company services/company

RUN useradd --uid 10015 --no-create-home --shell /usr/sbin/nologin p15
USER p15

EXPOSE 9152
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:9152/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "services.company.main:app", "--host", "0.0.0.0", "--port", "9152"]
