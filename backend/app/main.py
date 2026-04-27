"""
FastAPI application: CORS for Angular dev server, PV and system routes.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import pv, system

app = FastAPI(
    title="Home Power System",
    version="0.1.0",
    description="Max theoretical clear-sky PV and system config API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pv.router)
app.include_router(system.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
