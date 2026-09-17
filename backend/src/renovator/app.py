"""Local FastAPI entrypoint. Run with:

    uv run uvicorn renovator.app:app --reload
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from renovator.api.routes import projects_router, settings_router
from renovator.api.routes import router as api_router

load_dotenv()

app = FastAPI(title="AI Agentic Home Renovator", version="0.1.0")

# Local-only app (design doc §4.7) — the frontend dev server runs on a
# different port (Vite default 5173), so it needs CORS to reach this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects_router)
app.include_router(settings_router)
app.include_router(api_router)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "has_llm_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }
