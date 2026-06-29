"""format-quorum backend (FastAPI).

Serves the built React frontend and exposes the formatting API. Replaces the
previous Node/Express `server.js`.

The primitive is a **formatter** (see ``formatter_registry``), not a language.
Config, versions, shadows and the matrix are keyed by ``formatter.id``. The old
``language`` (cpp/python) and ``clang_version`` params are still accepted as
aliases (cpp→clang-format, python→ruff) so existing clients keep working.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import formatter_registry as registry
from formatters import (
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
# Where dynamically-installed formatter versions live (persist via a volume).
VERSIONS_DIR = Path(os.environ.get("VERSIONS_DIR", str(BACKEND_DIR / "clang_versions")))
# Where BEFORE/AFTER tests live (git-backed, bind-mounted in Docker).
TESTS_DIR = Path(os.environ.get("TESTS_DIR", str(BACKEND_DIR / "tests")))
# Where the per-key config history (base + patches) is persisted. A named volume
# in Docker so published config changes — and the ability to roll them back —
# survive a deploy that resets the git-backed config files.
CONFIG_HISTORY_DIR = Path(
    os.environ.get("CONFIG_HISTORY_DIR", str(BACKEND_DIR / "config_history"))
)

app = FastAPI(title="format-quorum", version="0.9.0")
tests = TestStore(TESTS_DIR)
configs = ConfigStore(CONFIG_HISTORY_DIR)
# shadow configs: named alt configs that reuse an installed binary (their `base`)
# but carry their own config text. They surface as pseudo-versions.
shadows = ShadowStore(CONFIG_HISTORY_DIR / "shadows.json")

# one VersionManager per *versioned* formatter, each driven by its formatter's
# install strategy (pip today, anything later). clang-format keeps the existing
# layout (rooted at VERSIONS_DIR) so its persisted volume is untouched; any other
# versioned formatter gets its own subdir.
version_mgrs: dict[str, VersionManager] = {}
for _f in registry.FORMATTERS.values():
    if _f.versioned and _f.install:
        _root = VERSIONS_DIR if _f.id == "clang-format" else VERSIONS_DIR / _f.id
        version_mgrs[_f.id] = VersionManager(
            _root, _f.install, known_versions=list(_f.known_versions)
        )

# the languages that have a config (derived from the registry)
CONFIG_LANGS = tuple(sorted(registry.languages()))


# ── formatter / version / config resolution ───────────────────────────────────
def _default_version(formatter_id: str) -> str | None:
    mgr = version_mgrs.get(formatter_id)
    return mgr.base_version if mgr else None


def _config_key(formatter_id: str, version: str | None = None) -> str:
    """Config-store key for a formatter (+version): ``<id>`` or ``<id>@<version>``.
    A version (or shadow id) only applies to versioned formatters."""
    f = registry.get(formatter_id)
    if f and f.versioned:
        v = version or _default_version(formatter_id)
        return f"{formatter_id}@{v}" if v else formatter_id
    return formatter_id


def _real_version(version: str | None) -> str | None:
    """Map a shadow id to the real version it runs on (its base); pass real
    versions through."""
    sh = shadows.get(version)
    return sh["base"] if sh else version


def _formatter_bin(formatter_id: str, version: str | None) -> str | None:
    """The installed binary for a version/shadow of a formatter, or None (None =
    use the formatter's default binary on PATH)."""
    mgr = version_mgrs.get(formatter_id)
    if mgr is None:
        return None
    return mgr.get_binary(_real_version(version))


def _ensure_config(formatter_id: str, version: str | None = None) -> str:
    """Resolve the config key for a formatter version/shadow, lazily seeding it:
    a new real version clones the formatter's default config; a shadow clones its
    base version's config."""
    key = _config_key(formatter_id, version)
    if configs.exists(key):
        return key
    sh = shadows.get(version)
    if sh:
        seed_key = _config_key(sh.get("formatter", formatter_id), sh["base"])
    else:
        seed_key = _config_key(formatter_id, None)
    if key != seed_key:
        configs.ensure_seeded(key, seed_from_key=seed_key)
    return key


def _resolve_request(formatter: str | None, language: str | None = None):
    """The Formatter a request targets: explicit `formatter` id wins, else the
    legacy `language` alias (cpp→clang-format, python→ruff)."""
    return registry.resolve(formatter) or registry.default_for_language(language)


def _resolve_binary(formatter_id: str, version: str | None):
    """Return (binary_or_None, error_response_or_None). None binary = use the
    formatter's default binary (unversioned formatter, or no version requested)."""
    f = registry.get(formatter_id)
    if f is None:
        return None, JSONResponse(
            {"error": f"unknown formatter: {formatter_id}"}, status_code=400
        )
    if not f.versioned or not version:
        return None, None
    binary = _formatter_bin(formatter_id, version)
    if binary is None:
        return None, JSONResponse(
            {"error": f"{f.label} {version} is not installed"}, status_code=400
        )
    return binary, None


def _resolved_version(fmt, version: str | None) -> str | None:
    """The concrete version a config request resolves to (for the client to show);
    None for unversioned formatters."""
    if not fmt.versioned:
        return None
    return version or _default_version(fmt.id)


# ── one-time data migration: language-keyed history → formatter-keyed ──────────
def _migrate_legacy_keys() -> None:
    """Rename ``config_history`` files from the old language scheme to the new
    formatter scheme (idempotent; leaves ``.bak`` copies). Safe on the persisted
    prod volume and across restarts."""
    d = CONFIG_HISTORY_DIR
    if not d.exists():
        return
    for p in list(d.glob("*.json")):
        name = p.name
        if name == "shadows.json":
            continue
        if name == "python.json":
            new = "ruff.json"
        elif name == "cpp.json":
            new = "clang-format.json"
        elif name.startswith("cpp@"):  # cpp@<version> and cpp@shadow-*
            new = "clang-format@" + name[len("cpp@") :]
        else:
            continue
        dst = d / new
        if dst.exists():
            continue
        dst.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
        p.rename(p.with_name(p.name + ".bak"))
    # tag existing shadows with their formatter (all legacy shadows are clang-format)
    sp = d / "shadows.json"
    if sp.exists():
        try:
            items = json.loads(sp.read_text(encoding="utf-8"))
            if isinstance(items, list):
                changed = False
                for s in items:
                    if isinstance(s, dict) and "formatter" not in s:
                        s["formatter"] = "clang-format"
                        changed = True
                if changed:
                    sp.write_text(
                        json.dumps(items, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
        except (json.JSONDecodeError, OSError):
            pass


def _init_configs() -> None:
    _migrate_legacy_keys()
    # a formatter that just gained a version axis (ruff/black): its old single
    # config history (`<id>`) becomes the default version's config (`<id>@<base>`),
    # once, so a previously-published config survives the switch. Idempotent.
    for fid, mgr in version_mgrs.items():
        default_key = _config_key(fid, None)
        if default_key != fid and configs.exists(fid) and not configs.exists(default_key):
            configs.migrate(fid, default_key)
    # seed (+ optionally materialize) each formatter's default-version config
    for f in registry.FORMATTERS.values():
        if f.config is None:
            continue
        key = _config_key(f.id, None)
        if f.config.materialize:
            configs.set_materialize(key, f.config.seed_path)
        configs.ensure_seeded(
            key, seed_text=Path(f.config.seed_path).read_text(encoding="utf-8")
        )
        if f.config.materialize:
            configs.materialize(key)
    # every other already-installed version of a versioned formatter gets its own
    # config, cloned once from that formatter's default (skip configless formatters
    # like prettier/shfmt — they have a version axis but no per-version config)
    for fid, mgr in version_mgrs.items():
        f = registry.get(fid)
        if f is None or f.config is None:
            continue
        default_key = _config_key(fid, None)
        for v in mgr.state().get("versions", []):
            k = _config_key(fid, v)
            if k != default_key:
                configs.ensure_seeded(k, seed_from_key=default_key)


_init_configs()


# Allow the Vite dev server (localhost:5173) to call the API directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── formatting ────────────────────────────────────────────────────────────────
class FormatRequest(BaseModel):
    code: str
    # primary: which formatter to use. `language` is the legacy alias.
    formatter: str | None = None
    language: str = "cpp"
    version: str | None = None
    clang_version: str | None = None  # legacy alias for `version`
    # Optional ad-hoc style config to use instead of the stored one (lets the
    # tuning bench try variants without overwriting the saved config).
    config: str | None = None


@app.post("/api/format")
def api_format(req: FormatRequest):
    fmt = _resolve_request(req.formatter, req.language)
    if fmt is None:
        return JSONResponse({"error": "unknown formatter/language"}, status_code=400)
    version = req.version or req.clang_version
    binary, err = _resolve_binary(fmt.id, version)
    if err:
        return err
    config = req.config
    if config is None and fmt.config is not None:
        config = configs.current(_ensure_config(fmt.id, version))
    try:
        formatted = format_code(req.code, fmt.id, binary=binary, config=config)
    except FormatError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    return {"formatted": formatted}


# ── formatter registry + version management ───────────────────────────────────
class AddVersionRequest(BaseModel):
    version: str


def _versions_state(formatter_id: str) -> dict:
    mgr = version_mgrs.get(formatter_id)
    state = (
        mgr.state()
        if mgr
        else {"versions": [], "default": None, "installing": [], "suggestions": []}
    )
    sh = [s for s in shadows.list() if s.get("formatter", "clang-format") == formatter_id]
    return {**state, "shadows": sh}


@app.get("/api/formatters")
def api_formatters():
    """The formatter registry — what the frontend builds its pickers from."""
    return {"formatters": registry.public_list()}


@app.get("/api/formatters/{formatter_id}/versions")
def api_formatter_versions(formatter_id: str):
    if formatter_id not in version_mgrs:
        return JSONResponse(
            {"error": f"formatter {formatter_id} has no version axis"}, status_code=400
        )
    return _versions_state(formatter_id)


@app.post("/api/formatters/{formatter_id}/versions")
def api_formatter_add_version(formatter_id: str, req: AddVersionRequest):
    mgr = version_mgrs.get(formatter_id)
    if mgr is None:
        return JSONResponse(
            {"error": f"formatter {formatter_id} has no version axis"}, status_code=400
        )
    ok, error = mgr.add_version(req.version)
    if not ok:
        return JSONResponse({"error": error}, status_code=400)
    # give the new version its own config, copied once from the default version
    configs.ensure_seeded(
        _config_key(formatter_id, req.version), seed_from_key=_config_key(formatter_id, None)
    )
    return _versions_state(formatter_id)


@app.delete("/api/formatters/{formatter_id}/versions/{version}")
def api_formatter_remove_version(formatter_id: str, version: str):
    mgr = version_mgrs.get(formatter_id)
    if mgr is None:
        return JSONResponse(
            {"error": f"formatter {formatter_id} has no version axis"}, status_code=400
        )
    ok, error = mgr.remove_version(version)
    if not ok:
        return JSONResponse({"error": error}, status_code=400)
    return _versions_state(formatter_id)


# legacy aliases — clang-format version management
@app.get("/api/clang-versions")
def api_list_versions():
    return _versions_state("clang-format")


@app.post("/api/clang-versions")
def api_add_version(req: AddVersionRequest):
    return api_formatter_add_version("clang-format", req)


@app.delete("/api/clang-versions/{version}")
def api_remove_version(version: str):
    return api_formatter_remove_version("clang-format", version)


# ── shadow configs ────────────────────────────────────────────────────────────
class ShadowCreate(BaseModel):
    id: str
    base: str  # an installed version of `formatter` whose binary the shadow runs on
    name: str = "shadow"
    content: str  # the shadow's config text
    formatter: str = "clang-format"


@app.post("/api/shadow-configs")
def api_shadow_create(body: ShadowCreate):
    """Register a shadow config and seed its config text. The id is client-chosen
    (so an unpublished draft and its publish refer to the same shadow); it must
    look like a shadow id, not a real version."""
    sid = body.id.strip()
    if not sid.startswith("shadow-") or VERSION_RE.match(sid):
        return JSONResponse({"error": "invalid shadow id"}, status_code=400)
    fmt = registry.get(body.formatter) or registry.get("clang-format")
    mgr = version_mgrs.get(fmt.id)
    if mgr is None or mgr.get_binary(body.base) is None:
        return JSONResponse(
            {"error": f"base {fmt.label} {body.base} is not installed"}, status_code=400
        )
    sh = shadows.create(
        sid, body.base, (body.name or "shadow").strip() or "shadow", formatter=fmt.id
    )
    key = _config_key(fmt.id, sid)
    if configs.exists(key):
        configs.record(key, body.content, message="shadow config update")
    else:
        configs.ensure_seeded(key, seed_text=body.content)
    return {"ok": True, "shadow": sh, "shadows": shadows.list()}


@app.delete("/api/shadow-configs/{shadow_id}")
def api_shadow_delete(shadow_id: str):
    sh = shadows.get(shadow_id)
    if not shadows.delete(shadow_id):
        return JSONResponse({"error": "shadow config not found"}, status_code=404)
    fmt_id = (sh or {}).get("formatter", "clang-format")
    configs.drop(_config_key(fmt_id, shadow_id))  # drop its config history too
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
    formatter: str | None = None
    version: str | None = None
    clang_version: str | None = None  # legacy alias for `version`
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


def _run_context(formatter: str | None, language: str | None, version: str | None):
    """Resolve (Formatter|None, binary, error, config-or-None) for a run request.
    A formatter is only resolved when one is implied (explicit, or a language
    filter); otherwise each test self-resolves its default formatter."""
    if not formatter and not language:
        return None, None, None
    fmt = _resolve_request(formatter, language)
    if fmt is None:
        return None, None, None
    binary, err = _resolve_binary(fmt.id, version)
    return fmt, binary, err


@app.post("/api/tests/run")
def api_tests_run(body: RunRequest):
    version = body.version or body.clang_version
    fmt, binary, err = _run_context(body.formatter, body.language, version)
    if err:
        return err
    config = body.config
    if config is None and fmt is not None and fmt.config is not None:
        config = configs.current(_ensure_config(fmt.id, version))
    return run_all(
        tests,
        language=body.language,
        formatter=(fmt.id if fmt else None),
        binary=binary,
        config=config,
    )


@app.post("/api/tests/{test_id}/run")
def api_tests_run_one(test_id: str, body: RunRequest):
    rec = tests.get(test_id)
    if rec is None:
        return JSONResponse({"error": "test not found"}, status_code=404)
    version = body.version or body.clang_version
    fmt = _resolve_request(body.formatter, body.language) or registry.default_for_language(
        rec["language"]
    )
    if fmt is None:
        return JSONResponse({"error": "unknown formatter/language"}, status_code=400)
    binary, err = _resolve_binary(fmt.id, version)
    if err:
        return err
    config = body.config
    if config is None and fmt.config is not None:
        config = configs.current(_ensure_config(fmt.id, version))
    return run_test(rec, formatter=fmt.id, binary=binary, config=config)


class WhatIfRequest(BaseModel):
    """A "config hypothesis": format every test against the live config and
    against a candidate, then report which tests flip pass/fail."""

    language: str = "cpp"
    formatter: str | None = None
    version: str | None = None
    clang_version: str | None = None  # legacy alias
    # Top-level key overrides applied on top of the LIVE stored config (only for
    # `patchable` formatters, e.g. clang-format). e.g. {"AlignAfterOpenBracket": "DontAlign"}.
    patch: dict | None = None
    # Alternative to `patch`: a full config string to try as-is.
    config: str | None = None
    # Optional test ids or name substrings to call out individually in `targets`.
    targets: list[str] | None = None


@app.post("/api/tests/whatif")
def api_tests_whatif(body: WhatIfRequest):
    """Check a "patch → which tests pass/fail" hypothesis without touching the
    stored config. Runs the suite twice (live config vs candidate) and diffs the
    per-test results."""
    fmt = _resolve_request(body.formatter, body.language)
    if fmt is None:
        return JSONResponse({"error": "unknown formatter/language"}, status_code=400)
    version = body.version or body.clang_version
    binary, err = _resolve_binary(fmt.id, version)
    if err:
        return err

    live_cfg = (
        configs.current(_ensure_config(fmt.id, version)) if fmt.config is not None else None
    )

    # Candidate config: a patch merges onto the live config; a full `config` is used as-is.
    candidate = body.config
    if body.patch:
        if not fmt.patchable:
            return JSONResponse(
                {"error": f"patch is not supported for {fmt.label}; pass a full `config`"},
                status_code=400,
            )
        candidate = apply_config_patch(body.config or live_cfg or "", body.patch)

    base_run = run_all(
        tests, language=fmt.language, formatter=fmt.id, binary=binary, config=live_cfg
    )
    cand_run = run_all(
        tests, language=fmt.language, formatter=fmt.id, binary=binary, config=candidate
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
        "language": fmt.language,
        "formatter": fmt.id,
        "clang_version": version,
        "version": version,
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
            if r["id"] in body.targets or any(w in r["name"].lower() for w in wanted)
        ]
    return out


class MatrixShadow(BaseModel):
    id: str
    base: str
    name: str = "shadow"
    content: str
    formatter: str = "clang-format"


class MatrixRequest(BaseModel):
    # The matrix axis is a formatter's installed versions (+ shadow configs).
    language: str = "cpp"
    formatter: str | None = None
    # Ad-hoc, *unpublished* shadow configs to include as extra columns, so a
    # draft shadow shows in the matrix before it's published.
    shadows: list[MatrixShadow] | None = None


def _version_key(v: str):
    return tuple(int(p) if p.isdigit() else 0 for p in v.replace("-", ".").split("."))


@app.post("/api/tests/matrix")
def api_tests_matrix(body: MatrixRequest):
    """Run every test of a language against every installed version of a formatter
    (+ its shadow configs) and return a tests × versions grid."""
    fmt = _resolve_request(body.formatter, body.language)
    if fmt is None:
        return JSONResponse({"error": "unknown formatter/language"}, status_code=400)
    lang = fmt.language
    test_list = [t for t in tests.list() if t["language"] == lang]
    mgr = version_mgrs.get(fmt.id)

    # Column specs: (col_id, binary, config). Installed versions first, then
    # published shadow configs, then any ad-hoc (unpublished) draft shadows sent.
    col_specs: list[tuple[str, str | None, str | None]] = []
    if mgr:
        for v in sorted(mgr.state()["versions"], key=_version_key):
            cfg = configs.current(_ensure_config(fmt.id, v)) if fmt.config else None
            col_specs.append((v, mgr.get_binary(v), cfg))

    shadow_meta: dict[str, dict] = {}
    if fmt.versioned and mgr:
        for s in shadows.list():
            if s.get("formatter", "clang-format") != fmt.id:
                continue
            shadow_meta[s["id"]] = s
            cfg = configs.current(_ensure_config(fmt.id, s["id"]))
            col_specs.append((s["id"], _formatter_bin(fmt.id, s["id"]), cfg))
        for s in body.shadows or []:
            if s.id in shadow_meta:
                continue
            shadow_meta[s.id] = {"id": s.id, "base": s.base, "name": s.name}
            col_specs.append((s.id, mgr.get_binary(s.base), s.content))

    cols = [c[0] for c in col_specs]
    per_version: dict[str, dict] = {}
    for col_id, binary, cfg in col_specs:
        if binary is None:
            continue
        res = run_all(tests, language=lang, formatter=fmt.id, binary=binary, config=cfg)
        per_version[col_id] = {
            r["id"]: {"status": r["status"], "passed": r["passed"]}
            for r in res["results"]
        }
    shadow_list = list(shadow_meta.values())

    rows = []
    for t in test_list:
        cells = {v: per_version.get(v, {}).get(t["id"]) for v in cols}
        passed_on = [v for v, c in cells.items() if c and c["passed"]]
        rows.append(
            {
                "id": t["id"],
                "name": t["name"],
                "muted": t["muted"],
                "cells": cells,
                "muted_passes_somewhere": bool(t["muted"] and passed_on),
            }
        )

    return {"language": lang, "versions": cols, "tests": rows, "shadows": shadow_list}


# ── Formatter configs (single source of truth, versioned) ─────────────────────
@app.get("/clang-format")
def serve_clang_config():
    return FileResponse(CLANG_FORMAT_CONFIG, media_type="text/plain")


@app.get("/ruff.toml")
def serve_ruff_config():
    return FileResponse(RUFF_CONFIG, media_type="text/plain")


class ConfigBody(BaseModel):
    content: str
    # which version's config to write (versioned formatters; default when omitted)
    version: str | None = None
    author: str | None = None
    message: str | None = None


class RollbackBody(BaseModel):
    seq: int
    version: str | None = None
    author: str | None = None
    message: str | None = None


@app.get("/api/config/{key}")
def api_get_config(key: str, version: str | None = None):
    """`key` is a formatter id (or a legacy language: cpp/python)."""
    fmt = registry.resolve(key)
    if fmt is None:
        return JSONResponse({"error": f"unknown config: {key}"}, status_code=400)
    ck = _ensure_config(fmt.id, version)
    return {
        "language": fmt.language,
        "formatter": fmt.id,
        "version": _resolved_version(fmt, version),
        "filename": fmt.config.filename.lstrip(".") if fmt.config else None,
        "content": configs.current(ck),
    }


@app.put("/api/config/{key}")
def api_put_config(key: str, body: ConfigBody):
    """Record the config as a new version (and materialize it for the formatter)."""
    fmt = registry.resolve(key)
    if fmt is None:
        return JSONResponse({"error": f"unknown config: {key}"}, status_code=400)
    ck = _ensure_config(fmt.id, body.version)
    try:
        result = configs.record(
            ck, body.content, author=body.author or "", message=body.message or ""
        )
    except OSError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    return {"ok": True, "version": _resolved_version(fmt, body.version), **result}


@app.get("/api/config/{key}/history")
def api_config_history(key: str, version: str | None = None):
    fmt = registry.resolve(key)
    if fmt is None:
        return JSONResponse({"error": f"unknown config: {key}"}, status_code=400)
    ck = _ensure_config(fmt.id, version)
    return {
        "language": fmt.language,
        "formatter": fmt.id,
        "version": _resolved_version(fmt, version),
        "head": configs.head_seq(ck),
        "versions": configs.history(ck),
    }


@app.get("/api/config/{key}/history/{seq}")
def api_config_version(key: str, seq: int, version: str | None = None):
    fmt = registry.resolve(key)
    if fmt is None:
        return JSONResponse({"error": f"unknown config: {key}"}, status_code=400)
    ck = _ensure_config(fmt.id, version)
    content = configs.get_version(ck, seq)
    if content is None:
        return JSONResponse({"error": f"no version {seq}"}, status_code=404)
    return {
        "language": fmt.language,
        "formatter": fmt.id,
        "version": _resolved_version(fmt, version),
        "seq": seq,
        "content": content,
    }


@app.post("/api/config/{key}/rollback")
def api_config_rollback(key: str, body: RollbackBody):
    fmt = registry.resolve(key)
    if fmt is None:
        return JSONResponse({"error": f"unknown config: {key}"}, status_code=400)
    ck = _ensure_config(fmt.id, body.version)
    result = configs.rollback(
        ck, body.seq, author=body.author or "", message=body.message or ""
    )
    if result is None:
        return JSONResponse({"error": f"no version {body.seq}"}, status_code=404)
    return {"ok": True, "version": _resolved_version(fmt, body.version), **result}


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
