"""p15-event service (port 9155). Run from backend/:

    uvicorn services.event.main:app --port 9155
"""
from services.common.app_factory import build_service_app

app = build_service_app("event")
