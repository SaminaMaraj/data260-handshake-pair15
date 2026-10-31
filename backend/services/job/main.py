"""p15-job service (port 9153). Run from backend/:

    uvicorn services.job.main:app --port 9153
"""
from services.common.app_factory import build_service_app

app = build_service_app("job")
