"""Service boundaries for the Pair 15 Handshake platform (Lab 2).

Every HTTP path is owned by exactly one service. Ownership is decided by
the LONGEST matching path prefix, so "/companies/me/jobs" belongs to the
Job service even though "/companies" belongs to the Company service.

This one table is the source of truth for:
  * which routes each FastAPI service mounts (services/common/app_factory.py)
  * how the gateway / Kubernetes Ingress forwards requests
  * tests/test_service_split.py, which proves every Lab 1 route is owned
    by exactly one service and none were lost.
"""

PAIR = 15
PORT_BASE = 9000 + PAIR * 10  # 9150, the gateway / public API port

# service name -> container port (PORT_BASE + n)
SERVICE_PORTS = {
    "student": PORT_BASE + 1,      # 9151
    "company": PORT_BASE + 2,      # 9152
    "job": PORT_BASE + 3,          # 9153
    "application": PORT_BASE + 4,  # 9154
    "event": PORT_BASE + 5,        # 9155
    "assistant": PORT_BASE + 6,    # 9156
}

# path prefix -> owning service
ROUTE_TABLE = {
    # Student service: identity for both roles, student profiles,
    # directory, resumes, profile media, preferences and saved items.
    "/users": "student",
    "/students": "student",
    "/directory": "student",
    "/profiles": "student",
    "/resumes": "student",
    "/media": "student",
    "/saved-items": "student",
    # Company service
    "/companies": "company",
    # Job service (company-owned job listings live here too)
    "/jobs": "job",
    "/companies/me/jobs": "job",
    # Application service (company applicant review lives here too)
    "/applications": "application",
    "/companies/me/applications": "application",
    # Event service
    "/events": "event",
    "/event-registrations": "event",
    # Assistant service
    "/assistant": "assistant",
}


def _matches(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def owner_of(path: str) -> str | None:
    """Return the service that owns ``path`` (longest prefix wins)."""
    best = None
    for prefix, service in ROUTE_TABLE.items():
        if _matches(path, prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, service)
    return best[1] if best else None
