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
from pydantic import BaseModel, Field

from formatters import CLANG_FORMAT_BIN, FormatError, format_code
from test_store import TestStore, run_all, run_test
from versions import VersionManager

BACKEND_DIR = Path(__file__).resolve().parent
# Where the built frontend lives. Set FRONTEND_DIST in Docker.
FRONTEND_DIST = Path(
    os.environ.get("FRONTEND_DIST", str(BACKEND_DIR.parent / "app" / "dist"))
).resolve()
# Where dynamically-installed clang-format versions live (persist via a volume).
VERSIONS_DIR = Path(
    os.environ.get("VERSIONS_DIR", str(BACKEND_DIR / "clang_versions"))
)
# Where BEFORE/AFTER tests live (git-backed, bind-mounted in Docker).
TESTS_DIR = Path(os.environ.get("TESTS_DIR", str(BACKEND_DIR / "tests")))

app = FastAPI(title="format-quorum", version="0.4.0")
versions = VersionManager(VERSIONS_DIR, CLANG_FORMAT_BIN)
tests = TestStore(TESTS_DIR)


def _resolve_clang(version: str | None):
    """Return (binary_or_None, error_response_or_None) for a version string."""
    if not version:
        return None, None
    binary = versions.get_binary(version)
    if binary is None:
        return None, JSONResponse(
            {"error": f"clang-format {version} is not installed"}, status_code=400
        )
    return binary, None

# Allow the Vite dev server (localhost:5173) to call the API directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class FormatRequest(BaseModel):
    model_config = {"populate_by_name": True}

    code: str
    language: str = "cpp"
    # Optional clang-format version (X.Y.Z); defaults to the built-in version.
    clang_version: str | None = Field(default=None, alias="clangVersion")


@app.post("/api/format")
def api_format(req: FormatRequest):
    clang_bin: str | None = None
    if req.language != "python":
        clang_bin, err = _resolve_clang(req.clang_version)
        if err:
            return err
    try:
        formatted = format_code(req.code, req.language, clang_format_bin=clang_bin)
    except FormatError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    return {"formatted": formatted}


# ── clang-format version management ───────────────────────────────────────────
class AddVersionRequest(BaseModel):
    version: str


@app.get("/api/clang-versions")
def api_list_versions():
    return versions.state()


@app.post("/api/clang-versions")
def api_add_version(req: AddVersionRequest):
    ok, error = versions.add_version(req.version)
    if not ok:
        return JSONResponse({"error": error}, status_code=400)
    return versions.state()


@app.delete("/api/clang-versions/{version}")
def api_remove_version(version: str):
    ok, error = versions.remove_version(version)
    if not ok:
        return JSONResponse({"error": error}, status_code=400)
    return versions.state()


# ── Formatting test suite ─────────────────────────────────────────────────────
class TestIn(BaseModel):
    name: str = "untitled"
    language: str = "cpp"
    input: str = ""
    expected: str = ""
    muted: bool = False
    note: str = ""


class TestPatch(BaseModel):
    name: str | None = None
    language: str | None = None
    input: str | None = None
    expected: str | None = None
    muted: bool | None = None
    note: str | None = None


class RunRequest(BaseModel):
    model_config = {"populate_by_name": True}

    language: str | None = None
    clang_version: str | None = Field(default=None, alias="clangVersion")


@app.get("/api/tests")
def api_tests_list():
    return tests.list()


@app.post("/api/tests")
def api_tests_create(body: TestIn):
    try:
        return tests.create(body.model_dump())
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.put("/api/tests/{test_id}")
def api_tests_update(test_id: str, body: TestPatch):
    try:
        rec = tests.update(test_id, body.model_dump())
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    if rec is None:
        return JSONResponse({"error": "test not found"}, status_code=404)
    return rec


@app.delete("/api/tests/{test_id}")
def api_tests_delete(test_id: str):
    if not tests.delete(test_id):
        return JSONResponse({"error": "test not found"}, status_code=404)
    return {"ok": True}


@app.post("/api/tests/run")
def api_tests_run(body: RunRequest):
    clang_bin, err = _resolve_clang(body.clang_version)
    if err:
        return err
    return run_all(tests, language=body.language, clang_bin=clang_bin)


@app.post("/api/tests/{test_id}/run")
def api_tests_run_one(test_id: str, body: RunRequest):
    rec = tests.get(test_id)
    if rec is None:
        return JSONResponse({"error": "test not found"}, status_code=404)
    clang_bin, err = _resolve_clang(body.clang_version)
    if err:
        return err
    return run_test(rec, clang_bin)


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
