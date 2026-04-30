"""
FastAPI application: CORS for Angular dev server; PV, forecast, FoxESS, and system routes.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# Load .env before any code reads FOXESS_PAT. Use override=True so values from the
# file win over empty or placeholder FOXESS_PAT in the machine/IDE environment
# (python-dotenv default override=False would skip the file in that case).
_backend_dir = Path(__file__).resolve().parent.parent
_repo_root = _backend_dir.parent
_env_paths = [_repo_root / ".env", _backend_dir / ".env"]
for _env_path in _env_paths:
    if _env_path.is_file():
        load_dotenv(_env_path, override=True, encoding="utf-8-sig")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import forecast, foxess, pv, system

app = FastAPI(
    title="Home Power System",
    version="0.3.0",
    description="Clear-sky PV, weather forecast PV, FoxESS measured PV, and system config API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://localhost:4201",
        "http://127.0.0.1:4201",
    ],
    # Any dev-server port on loopback (avoids CORS breaks when ng picks a random port).
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pv.router)
app.include_router(forecast.router)
app.include_router(system.router)
app.include_router(foxess.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
