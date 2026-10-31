"""p15-student service (port 9151). Run from backend/:

    uvicorn services.student.main:app --port 9151
"""
from services.common.app_factory import build_service_app

app = build_service_app("student")
