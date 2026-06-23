"""format-quorum backend (FastAPI).

Serves the built React frontend and exposes the formatting API. Replaces the
previous Node/Express `server.js`.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from formatters import FormatError, format_code

BACKEND_DIR = Path(__file__).resolve().parent
# Where the built frontend lives. Set FRONTEND_DIST in Docker.
FRONTEND_DIST = Path(
    os.environ.get("FRONTEND_DIST", str(BACKEND_DIR.parent / "app" / "dist"))
).resolve()

app = FastAPI(title="format-quorum", version="0.4.0")

# Allow the Vite dev server (localhost:5173) to call the API directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class FormatRequest(BaseModel):
    code: str
    language: str = "cpp"


@app.post("/api/format")
def api_format(req: FormatRequest):
    try:
        formatted = format_code(req.code, req.language)
    except FormatError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    return {"formatted": formatted}


# ── Static frontend (production) ──────────────────────────────────────────────
# A single catch-all serves built assets and falls back to index.html so the
# client-side routes (/cpp, /python) and the bundled config files all resolve.
@app.get("/{full_path:path}")
def spa(full_path: str):
    if FRONTEND_DIST.is_dir():
        candidate = (FRONTEND_DIST / full_path).resolve()
        if candidate.is_file() and FRONTEND_DIST in candidate.parents:
            return FileResponse(candidate)
        index = FRONTEND_DIST / "index.html"
        if index.is_file():
            return FileResponse(index)
    return JSONResponse({"error": "frontend not built"}, status_code=404)
