"""Build one FastAPI app per p15 service.

Each service mounts its own routes module (services/<name>/routes.py),
all on MongoDB. Every service also exposes:
  GET /health      liveness: the process is up (no dependencies checked)
  GET /health/db   readiness: the service can reach MongoDB
and stamps each response with an X-Service header so the gateway, logs and
screenshots show which service answered.

Ownership of paths is declared once in services/common/routing.py;
tests/test_service_split.py checks every mounted route against it.
"""
import importlib
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from services.common.mongo import database, ensure_indexes
from services.common.routing import SERVICE_PORTS

DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,"
    "http://localhost:5175,http://localhost:5273,http://localhost:9150"
)


def build_service_app(service: str) -> FastAPI:
    if service not in SERVICE_PORTS:
        raise ValueError(f"Unknown service {service!r}")
    routes = importlib.import_module(f"services.{service}.routes")

    @asynccontextmanager
    async def lifespan(app):
        try:
            ensure_indexes(database())
        except Exception as exc:  # readiness probe reports it; don't crash-loop
            print(f"p15-{service}: could not ensure MongoDB indexes yet: {exc}")
        startup = getattr(routes, "on_startup", None)
        if startup:
            startup()
        yield

    app = FastAPI(title=f"Handshake Pair 15 - {service} service", version="2.0.0",
                  lifespan=lifespan)

    origins = os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in origins if o.strip()],
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def stamp_service(request, call_next):
        response = await call_next(request)
        response.headers["X-Service"] = f"p15-{service}"
        return response

    app.include_router(routes.router)

    @app.get("/health", tags=["Health"])
    def health():
        return {"status": "ok", "service": f"p15-{service}", "port": SERVICE_PORTS[service]}

    @app.get("/health/db", tags=["Health"])
    def health_db():
        db = database()
        try:
            db.command("ping")
        except Exception:
            raise HTTPException(status_code=503, detail="Database connection failed")
        return {"status": "ok", "service": f"p15-{service}", "database": db.name}

    return app
