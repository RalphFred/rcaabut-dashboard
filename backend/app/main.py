from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import auth, compacts, courses, jobs, reports, sources, users
from app.core.config import settings
from app.db.init_db import init_database
from app.db.session import engine


app = FastAPI(title="RCAABUT Dashboard API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_database()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/health/ready")
def readiness() -> dict:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(compacts.router)
app.include_router(courses.router)
app.include_router(jobs.router)
app.include_router(reports.router)
app.include_router(sources.router)
