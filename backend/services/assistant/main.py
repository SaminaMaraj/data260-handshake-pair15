"""p15-assistant service (port 9156). Run from backend/:

    uvicorn services.assistant.main:app --port 9156
"""
from services.common.app_factory import build_service_app

app = build_service_app("assistant")
