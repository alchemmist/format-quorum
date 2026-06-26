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

from formatters import (
    CLANG_FORMAT_BIN,
    CLANG_FORMAT_CONFIG,
    RUFF_CONFIG,
    FormatError,
    apply_config_patch,
    format_code,
)
from test_store import TestStore, run_all, run_test
from versions import VERSION_RE, VersionManager
from config_store import ConfigStore
from shadow_store import ShadowStore

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
# Where the per-language config history (base + patches) is persisted. A named
# volume in Docker so published config changes — and the ability to roll them
# back — survive a deploy that resets the git-backed config files.
CONFIG_HISTORY_DIR = Path(
    os.environ.get("CONFIG_HISTORY_DIR", str(BACKEND_DIR / "config_history"))
)

# Languages that have a config (the "Config" UI knows these two).
CONFIG_LANGS = ("cpp", "python")

app = FastAPI(title="format-quorum", version="0.8.0")
versions = VersionManager(VERSIONS_DIR, CLANG_FORMAT_BIN)
tests = TestStore(TESTS_DIR)
configs = ConfigStore(CONFIG_HISTORY_DIR)
# shadow configs: named alt configs that reuse an installed binary (their `base`)
# but carry their own .clang-format. They surface as pseudo-versions everywhere.
shadows = ShadowStore(CONFIG_HISTORY_DIR / "shadows.json")

# The default clang-format version (the image's built-in). Its config is the
# template new versions clone from, and the one materialized to the .clang-format
# file the raw endpoint serves.
DEFAULT_CPP_VERSION = versions.base_version


def _cpp_key(version: str | None) -> str:
    """Config-store key for a clang-format version OR a shadow id (each keeps its
    own config). Default version when None; legacy 'cpp' if there's no probed
    version."""
    v = version or DEFAULT_CPP_VERSION
    return f"cpp@{v}" if v else "cpp"


def _real_version(version: str | None) -> str | None:
    """Map a shadow id to the real clang-format version it runs on (its `base`);
    pass real version strings through unchanged."""
    sh = shadows.get(version)
    return sh["base"] if sh else version


def _ensure_cpp_config(version: str | None) -> str:
    """Resolve the config key for a cpp version or shadow id, lazily seeding it if
    it doesn't exist yet: a real version clones from the default version's config;
    a shadow clones from its base version's config."""
    key = _cpp_key(version)
    if configs.exists(key):
        return key
    sh = shadows.get(version)
    seed_key = _cpp_key(sh["base"]) if sh else _cpp_key(None)
    if key != seed_key:
        configs.ensure_seeded(key, seed_from_key=seed_key)
    return key


def _init_configs() -> None:
    # python — one config, mirrored to ruff.toml
    configs.set_materialize("python", RUFF_CONFIG)
    configs.ensure_seeded(
        "python", seed_text=Path(RUFF_CONFIG).read_text(encoding="utf-8")
    )
    configs.materialize("python")

    # cpp default version — mirrored to the .clang-format file. Inherit the
    # legacy single 'cpp' history (preserves published changes + rollbacks from
    # before configs went per-version) before seeding fresh.
    default_key = _cpp_key(None)
    configs.set_materialize(default_key, CLANG_FORMAT_CONFIG)
    if default_key != "cpp":
        configs.migrate("cpp", default_key)
    configs.ensure_seeded(
        default_key, seed_text=Path(CLANG_FORMAT_CONFIG).read_text(encoding="utf-8")
    )
    configs.materialize(default_key)

    # every other already-installed version gets its own config, cloned once
    for v in versions.state().get("versions", []):
        if _cpp_key(v) != default_key:
            configs.ensure_seeded(_cpp_key(v), seed_from_key=default_key)


_init_configs()


def _clang_bin(version: str | None) -> str | None:
    """clang-format binary for a version string or shadow id (None = default)."""
    return versions.get_binary(_real_version(version))


def _resolve_clang(version: str | None):
    """Return (binary_or_None, error_response_or_None) for a version string or
    shadow id (a shadow resolves to its base version's binary)."""
    if not version:
        return None, None
    binary = _clang_bin(version)
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
    code: str
    language: str = "cpp"
    # Optional clang-format version (X.Y.Z); defaults to the built-in version.
    clang_version: str | None = None
    # Optional ad-hoc style config to use instead of the stored one (lets the
    # tuning bench try variants without overwriting the saved config).
    config: str | None = None


@app.post("/api/format")
def api_format(req: FormatRequest):
    clang_bin: str | None = None
    config = req.config
    if req.language != "python":
        clang_bin, err = _resolve_clang(req.clang_version)
        if err:
            return err
        # use the selected version's stored config unless an ad-hoc one is given
        if config is None:
            config = configs.current(_ensure_cpp_config(req.clang_version))
    try:
        formatted = format_code(
            req.code, req.language, clang_format_bin=clang_bin, config=config
        )
    except FormatError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    return {"formatted": formatted}


# ── clang-format version management ───────────────────────────────────────────
class AddVersionRequest(BaseModel):
    version: str


@app.get("/api/clang-versions")
def api_list_versions():
    # shadows ride along so the UI can list them as pseudo-versions ("👻 name")
    return {**versions.state(), "shadows": shadows.list()}


@app.post("/api/clang-versions")
def api_add_version(req: AddVersionRequest):
    ok, error = versions.add_version(req.version)
    if not ok:
        return JSONResponse({"error": error}, status_code=400)
    # give the new version its own config, copied once from the default version
    configs.ensure_seeded(_cpp_key(req.version), seed_from_key=_cpp_key(None))
    return {**versions.state(), "shadows": shadows.list()}


@app.delete("/api/clang-versions/{version}")
def api_remove_version(version: str):
    ok, error = versions.remove_version(version)
    if not ok:
        return JSONResponse({"error": error}, status_code=400)
    return {**versions.state(), "shadows": shadows.list()}


# ── shadow configs ────────────────────────────────────────────────────────────
class ShadowCreate(BaseModel):
    id: str
    base: str  # an installed clang-format version whose binary the shadow runs on
    name: str = "shadow"
    content: str  # the shadow's .clang-format text


@app.post("/api/shadow-configs")
def api_shadow_create(body: ShadowCreate):
    """Register a shadow config and seed its config text. The id is client-chosen
    (so an unpublished draft and its publish refer to the same shadow); it must
    look like a shadow id, not a real version."""
    sid = body.id.strip()
    if not sid.startswith("shadow-") or VERSION_RE.match(sid):
        return JSONResponse({"error": "invalid shadow id"}, status_code=400)
    if versions.get_binary(body.base) is None:
        return JSONResponse(
            {"error": f"base clang-format {body.base} is not installed"}, status_code=400
        )
    sh = shadows.create(sid, body.base, (body.name or "shadow").strip() or "shadow")
    key = _cpp_key(sid)
    # the shadow's config is an independent snapshot; if it somehow already exists
    # (re-publish), record the new content as a fresh version instead
    if configs.exists(key):
        configs.record(key, body.content, message="shadow config update")
    else:
        configs.ensure_seeded(key, seed_text=body.content)
    return {"ok": True, "shadow": sh, "shadows": shadows.list()}


@app.delete("/api/shadow-configs/{shadow_id}")
def api_shadow_delete(shadow_id: str):
    if not shadows.delete(shadow_id):
        return JSONResponse({"error": "shadow config not found"}, status_code=404)
    configs.drop(_cpp_key(shadow_id))  # drop its config history too
    return {"ok": True, "shadows": shadows.list()}


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
    language: str | None = None
    clang_version: str | None = None
    # Optional ad-hoc style config to run the suite against (tuning bench).
    config: str | None = None


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
    config = body.config
    if config is None and body.language == "cpp":
        config = configs.current(_ensure_cpp_config(body.clang_version))
    return run_all(tests, language=body.language, clang_bin=clang_bin, config=config)


@app.post("/api/tests/{test_id}/run")
def api_tests_run_one(test_id: str, body: RunRequest):
    rec = tests.get(test_id)
    if rec is None:
        return JSONResponse({"error": "test not found"}, status_code=404)
    clang_bin, err = _resolve_clang(body.clang_version)
    if err:
        return err
    config = body.config
    if config is None and rec.get("language") == "cpp":
        config = configs.current(_ensure_cpp_config(body.clang_version))
    return run_test(rec, clang_bin, config=config)


class WhatIfRequest(BaseModel):
    """A "config hypothesis": format every test against the live config and
    against a candidate, then report which tests flip pass/fail."""

    language: str = "cpp"
    clang_version: str | None = None
    # Top-level clang-format key overrides applied on top of the LIVE stored
    # config (cpp only). e.g. {"AlignAfterOpenBracket": "DontAlign"}.
    patch: dict | None = None
    # Alternative to `patch`: a full config string to try as-is (either language).
    config: str | None = None
    # Optional test ids or name substrings to call out individually in `targets`.
    targets: list[str] | None = None


@app.post("/api/tests/whatif")
def api_tests_whatif(body: WhatIfRequest):
    """Check a "patch → which tests pass/fail" hypothesis without touching the
    stored config. Runs the suite twice (live config vs candidate) on one
    clang-format version and diffs the per-test results."""
    clang_bin, err = _resolve_clang(body.clang_version)
    if err:
        return err

    # Baseline = the live stored config for this language+version (cpp); for
    # python it's None (ruff's materialized config).
    live_cfg = (
        configs.current(_ensure_cpp_config(body.clang_version))
        if body.language == "cpp"
        else None
    )

    # Candidate config: a patch merges onto the live config; a full `config` is
    # used as-is.
    candidate = body.config
    if body.patch:
        if body.language != "cpp":
            return JSONResponse(
                {"error": "patch is cpp-only; pass a full `config` for python"},
                status_code=400,
            )
        candidate = apply_config_patch(body.config or live_cfg or "", body.patch)

    base_run = run_all(tests, language=body.language, clang_bin=clang_bin, config=live_cfg)
    cand_run = run_all(
        tests, language=body.language, clang_bin=clang_bin, config=candidate
    )

    by_id = {r["id"]: r for r in base_run["results"]}
    now_pass: list[str] = []
    now_fail: list[str] = []
    muted_would_pass: list[str] = []
    results: list[dict] = []
    for cand in cand_run["results"]:
        live = by_id[cand["id"]]
        results.append(
            {
                "id": cand["id"],
                "name": cand["name"],
                "muted": cand["muted"],
                "baseline_status": live["status"],
                "patched_status": cand["status"],
                "baseline_passed": live["passed"],
                "patched_passed": cand["passed"],
            }
        )
        if cand["muted"]:
            if cand["passed"] and not live["passed"]:
                muted_would_pass.append(cand["name"])
        elif cand["passed"] and not live["passed"]:
            now_pass.append(cand["name"])
        elif live["passed"] and not cand["passed"]:
            now_fail.append(cand["name"])

    out = {
        "language": body.language,
        "clang_version": body.clang_version,
        "effective_config": candidate,
        "summary": {"baseline": base_run["summary"], "patched": cand_run["summary"]},
        "flips": {
            "now_pass": now_pass,
            "now_fail": now_fail,
            "muted_would_pass": muted_would_pass,
        },
        "results": results,
    }
    if body.targets:
        wanted = [t.lower() for t in body.targets]
        out["targets"] = [
            r
            for r in results
            if r["id"] in body.targets
            or any(w in r["name"].lower() for w in wanted)
        ]
    return out


class MatrixRequest(BaseModel):
    # The matrix axis is clang-format versions, so it covers cpp tests; python
    # output doesn't depend on the clang version.
    language: str = "cpp"


def _version_key(v: str):
    return tuple(int(p) if p.isdigit() else 0 for p in v.replace("-", ".").split("."))


@app.post("/api/tests/matrix")
def api_tests_matrix(body: MatrixRequest):
    """Run every test of a language against every installed clang-format version
    and return a tests x versions grid. Each cell carries the status plus the raw
    `passed` flag, so the UI can flag a muted test that actually passes on some
    version (a candidate to un-mute / a behaviour change between versions)."""
    lang = body.language or "cpp"
    # real installed versions, then shadow configs as extra columns (each shadow
    # runs its base binary under its own config)
    shadow_list = shadows.list() if lang == "cpp" else []
    cols = sorted(versions.state()["versions"], key=_version_key) + [
        s["id"] for s in shadow_list
    ]
    test_list = [t for t in tests.list() if t["language"] == lang]

    per_version: dict[str, dict] = {}
    for v in cols:
        binary = _clang_bin(v)
        if binary is None:
            continue
        # each column runs against its OWN config (cpp); python is version-agnostic
        cfg = configs.current(_ensure_cpp_config(v)) if lang == "cpp" else None
        res = run_all(tests, language=lang, clang_bin=binary, config=cfg)
        per_version[v] = {
            r["id"]: {"status": r["status"], "passed": r["passed"]}
            for r in res["results"]
        }

    rows = []
    for t in test_list:
        cells = {v: per_version.get(v, {}).get(t["id"]) for v in cols}
        # a muted test that passes on some version but not all is a "surprise"
        passed_on = [v for v, c in cells.items() if c and c["passed"]]
        rows.append({
            "id": t["id"],
            "name": t["name"],
            "muted": t["muted"],
            "cells": cells,
            "muted_passes_somewhere": bool(t["muted"] and passed_on),
        })

    return {"language": lang, "versions": cols, "tests": rows, "shadows": shadow_list}


# ── Formatter configs (single source of truth, versioned) ─────────────────────
# The "Config" link in the UI points here, so it always shows the config that
# formatting actually uses. Every change is recorded by the config store so it
# can be rolled back; GET/PUT keep their original shape.


@app.get("/clang-format")
def serve_clang_config():
    return FileResponse(CLANG_FORMAT_CONFIG, media_type="text/plain")


@app.get("/ruff.toml")
def serve_ruff_config():
    return FileResponse(RUFF_CONFIG, media_type="text/plain")


class ConfigBody(BaseModel):
    content: str
    # cpp only: which clang-format version's config to write (default version
    # when omitted). python ignores it.
    version: str | None = None
    # Optional provenance for the history entry — who/why. Externally GET/PUT
    # look the same as before; these just enrich the audit trail.
    author: str | None = None
    message: str | None = None


class RollbackBody(BaseModel):
    seq: int
    version: str | None = None
    author: str | None = None
    message: str | None = None


def _resolved_version(lang: str, version: str | None) -> str | None:
    """The concrete clang-format version a cpp config request resolves to (so the
    client can show which version it's editing); None for python."""
    return None if lang == "python" else (version or DEFAULT_CPP_VERSION)


@app.get("/api/config/{lang}")
def api_get_config(lang: str, version: str | None = None):
    if lang not in CONFIG_LANGS:
        return JSONResponse({"error": f"unknown config: {lang}"}, status_code=400)
    key = "python" if lang == "python" else _ensure_cpp_config(version)
    return {
        "language": lang,
        "version": _resolved_version(lang, version),
        "filename": "clang-format" if lang == "cpp" else "ruff.toml",
        "content": configs.current(key),
    }


@app.put("/api/config/{lang}")
def api_put_config(lang: str, body: ConfigBody):
    """Record the config as a new version (and materialize it for the formatter).
    Looks the same to callers — but the change is now reversible."""
    if lang not in CONFIG_LANGS:
        return JSONResponse({"error": f"unknown config: {lang}"}, status_code=400)
    key = "python" if lang == "python" else _ensure_cpp_config(body.version)
    try:
        result = configs.record(
            key, body.content, author=body.author or "", message=body.message or ""
        )
    except OSError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    return {"ok": True, "version": _resolved_version(lang, body.version), **result}


@app.get("/api/config/{lang}/history")
def api_config_history(lang: str, version: str | None = None):
    """List the version history (base + each published change with its patch)."""
    if lang not in CONFIG_LANGS:
        return JSONResponse({"error": f"unknown config: {lang}"}, status_code=400)
    key = "python" if lang == "python" else _ensure_cpp_config(version)
    return {"language": lang, "version": _resolved_version(lang, version),
            "head": configs.head_seq(key), "versions": configs.history(key)}


@app.get("/api/config/{lang}/history/{seq}")
def api_config_version(lang: str, seq: int, version: str | None = None):
    """Full config content at a given version (0 = the original base)."""
    if lang not in CONFIG_LANGS:
        return JSONResponse({"error": f"unknown config: {lang}"}, status_code=400)
    key = "python" if lang == "python" else _ensure_cpp_config(version)
    content = configs.get_version(key, seq)
    if content is None:
        return JSONResponse({"error": f"no version {seq}"}, status_code=404)
    return {"language": lang, "version": _resolved_version(lang, version),
            "seq": seq, "content": content}


@app.post("/api/config/{lang}/rollback")
def api_config_rollback(lang: str, body: RollbackBody):
    """Roll the live config back to an earlier version. Append-only: the rollback
    is itself a new version, so it's auditable and can be undone."""
    if lang not in CONFIG_LANGS:
        return JSONResponse({"error": f"unknown config: {lang}"}, status_code=400)
    key = "python" if lang == "python" else _ensure_cpp_config(body.version)
    result = configs.rollback(
        key, body.seq, author=body.author or "", message=body.message or ""
    )
    if result is None:
        return JSONResponse({"error": f"no version {body.seq}"}, status_code=404)
    return {"ok": True, "version": _resolved_version(lang, body.version), **result}


# ── Static frontend (production) ──────────────────────────────────────────────
# A single catch-all serves built assets and falls back to index.html so the
# client-side routes (/cpp, /python) resolve.
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
