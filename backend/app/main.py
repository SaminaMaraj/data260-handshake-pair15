from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.routers.core import router as core_router
from app.routers.applications import router as applications_router
from app.database import engine

app = FastAPI(
    title="Handshake Pair 15 API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5273",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(core_router)
app.include_router(applications_router)
@app.get("/")
def root():
    return {
        "message": "Handshake Pair 15 API is running",
        "port": 9150,
    }


@app.get("/health/db")
def database_health():
    try:
        with engine.connect() as connection:
            database_name = connection.execute(
                text("SELECT DATABASE()")
            ).scalar_one()

        return {
            "status": "ok",
            "database": database_name,
        }

    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed",
        )
