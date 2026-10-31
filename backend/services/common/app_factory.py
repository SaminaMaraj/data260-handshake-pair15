"""Build one FastAPI app per service from the shared Lab 1 routers.

Each service mounts only the routes that ROUTE_TABLE assigns to it, in the
same order as the Lab 1 monolith (order matters: static paths such as
/events/search must be registered before /events/{event_id}).

Every service also exposes:
  GET /health      liveness: the process is up (no dependencies checked)
  GET /health/db   readiness: the service can reach its database
and stamps each response with an X-Service header so the gateway, logs and
screenshots show which service answered.
"""
import os

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from services.common.routing import SERVICE_PORTS, owner_of

# Lab 1 routers in the monolith's include order (see app/main.py).
# routers/resumes.py is intentionally absent: Lab 1 removed that
# unprotected upload route from the app.
def _lab1_routers():
    from app.routers.core import router as core
    from app.routers.applications import router as applications
    from app.routers.assistant import router as assistant
    from app.routers.events import router as events
    from app.routers.part_a import router as part_a
    from app.routers.preferences import router as preferences
    return [core, applications, assistant, events, part_a, preferences]


DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,"
    "http://localhost:5175,http://localhost:5273,http://localhost:9150"
)


def owned_router(service: str) -> APIRouter:
    """An APIRouter holding only the Lab 1 routes owned by ``service``."""
    owned = APIRouter()
    for source in _lab1_routers():
        for route in source.routes:
            if owner_of(route.path) == service:
                owned.routes.append(route)
    return owned


def build_service_app(service: str) -> FastAPI:
    if service not in SERVICE_PORTS:
        raise ValueError(f"Unknown service {service!r}")

    app = FastAPI(
        title=f"Handshake Pair 15 - {service} service",
        version="2.0.0",
    )

    origins = os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def stamp_service(request, call_next):
        response = await call_next(request)
        response.headers["X-Service"] = f"p15-{service}"
        return response

    app.include_router(owned_router(service))

    @app.get("/health", tags=["Health"])
    def health():
        return {"status": "ok", "service": f"p15-{service}",
                "port": SERVICE_PORTS[service]}

    @app.get("/health/db", tags=["Health"])
    def health_db():
        from app.database import engine
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            raise HTTPException(status_code=503, detail="Database connection failed")
        return {"status": "ok", "service": f"p15-{service}", "database": "reachable"}

    return app
