from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_analysis import router as analysis_router
from app.api.routes_reports import router as reports_router
from app.config import settings


app = FastAPI(
    title="ModernizeAI",
    description="Multi-Agent Legacy Application Modernization Assistant",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis_router)
app.include_router(reports_router)


@app.on_event("startup")
def on_startup() -> None:
    settings.ensure_directories()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

