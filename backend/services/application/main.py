"""p15-application service (port 9154). Run from backend/:

    uvicorn services.application.main:app --port 9154
"""
from services.common.app_factory import build_service_app

app = build_service_app("application")
