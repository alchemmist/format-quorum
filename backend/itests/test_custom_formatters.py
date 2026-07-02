"""User-defined (custom) formatters: upload your own binary as a *formatter*.

A custom formatter is its own entry for a language (alongside the built-ins), with
its own version axis (the uploaded binaries) and its own config. It borrows the
run/config semantics of the language's default formatter, so the end-to-end case
uploads a copy of that default's real binary — the custom formatter then genuinely
formats. Gated behind ALLOW_BINARY_UPLOAD; skips when the base binary is absent.
"""

import base64
from pathlib import Path

import pytest

from conftest import binary_present, seed_passing_test

# a language whose default formatter is a self-contained binary we can copy+run
#   python/ruff — ruff ships a standalone binary AND has a config (ruff.toml)
BASE = ("python", "ruff")


def _enable(appctx):
    appctx.main.ALLOW_BINARY_UPLOAD = True


def _base_binary_bytes(appctx, language: str) -> bytes:
    base = appctx.main.registry.default_for_language(language)
    return Path(appctx.main.version_mgrs[base.id].strategy.base_binary).read_bytes()


def _create(appctx, language, name, blob, *, version=None, config=None):
    body = {"language": language, "name": name,
            "content_b64": base64.b64encode(blob).decode()}
    if version is not None:
        body["version"] = version
    if config is not None:
        body["config"] = config
    return appctx.client.post("/api/custom-formatters", json=body)


def test_disabled_by_default(appctx):
    r = _create(appctx, "python", "mytool", b"x")
    assert r.status_code == 403


def test_bad_input(appctx):
    _enable(appctx)
    # unknown language (no built-in base)
    assert _create(appctx, "cobol", "x", b"data").status_code == 400
    # empty name → no slug
    assert _create(appctx, "python", "  #! ", b"data").status_code == 400
    # not base64
    r = appctx.client.post("/api/custom-formatters",
                           json={"language": "python", "name": "x", "content_b64": "!!"})
    assert r.status_code == 400


def test_custom_formatter_is_its_own_formatter(appctx):
    language, _base = BASE
    if not binary_present(_base):
        pytest.skip(f"{_base} not installed")
    _enable(appctx)

    blob = _base_binary_bytes(appctx, language)
    r = _create(appctx, language, "My Tool", blob, version="1.0",
                config="line-length = 100\n")
    assert r.status_code == 200, r.text
    data = r.json()
    fid = data["formatter"]["id"]
    assert fid == "cf-my-tool"
    assert data["added"] == "1.0"

    # it shows up as its OWN formatter for the language, not a version of ruff
    fmts = {f["id"]: f for f in appctx.client.get("/api/formatters").json()["formatters"]}
    assert fid in fmts
    assert fmts[fid]["language"] == language
    assert fmts[fid]["custom"] is True
    assert fmts[fid]["default"] is False
    # the built-in default is still there and separate
    assert fmts[_base]["custom"] is False

    # it genuinely formats (runs the uploaded binary)
    out = appctx.client.post("/api/format",
                             json={"code": "x=1\n", "formatter": fid, "version": "1.0"})
    assert out.status_code == 200, out.text

    # its config is the one we uploaded
    cfg = appctx.client.get(f"/api/config/{fid}?version=1.0").json()
    assert "line-length = 100" in cfg["content"]

    # a second uploaded binary is a second version on ITS axis
    r2 = _create(appctx, language, "My Tool", blob, version="2.0")
    assert r2.status_code == 200
    assert set(r2.json()["versions"]) >= {"1.0", "2.0"}

    # it's a column in the matrix
    seed_passing_test(appctx.client, language, "x=1\n", formatter=fid)
    matrix = appctx.client.post("/api/tests/matrix", json={"formatter": fid}).json()
    assert "1.0" in matrix["versions"]

    # deleting it removes the whole formatter
    d = appctx.client.delete(f"/api/custom-formatters/{fid}")
    assert d.status_code == 200
    fmts2 = {f["id"] for f in appctx.client.get("/api/formatters").json()["formatters"]}
    assert fid not in fmts2


def test_default_version_label(appctx):
    language, _base = BASE
    if not binary_present(_base):
        pytest.skip(f"{_base} not installed")
    _enable(appctx)
    r = _create(appctx, language, "notter", _base_binary_bytes(appctx, language))
    assert r.status_code == 200
    assert r.json()["added"] == "v1"  # default label when none given


def test_definition_persists(appctx):
    """The definition is written to the store so it survives a restart."""
    language, _base = BASE
    if not binary_present(_base):
        pytest.skip(f"{_base} not installed")
    _enable(appctx)
    _create(appctx, language, "persistme", _base_binary_bytes(appctx, language))
    saved = {d["id"] for d in appctx.main.custom_formatters.list()}
    assert "cf-persistme" in saved
