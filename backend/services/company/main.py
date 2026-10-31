"""p15-company service (port 9152). Run from backend/:

    uvicorn services.company.main:app --port 9152
"""
from services.common.app_factory import build_service_app

app = build_service_app("company")
