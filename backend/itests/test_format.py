"""POST /api/format — the core formatting endpoint across formatters & aliases."""

from conftest import CPP_MESSY, PY_MESSY, PY_UNUSED_IMPORT


def test_format_cpp(appctx):
    r = appctx.client.post("/api/format", json={"code": CPP_MESSY, "formatter": "clang-format"})
    assert r.status_code == 200
    out = r.json()["formatted"]
    assert "int main()" in out
    assert out != CPP_MESSY  # it actually reformatted (added line breaks/indent)
    assert "\n" in out.rstrip("\n")


def test_format_python_ruff_runs_full_pass(appctx):
    """ruff = check --fix (drops the unused import) + format."""
    code = "import os\nimport sys\nx=1\nprint(sys)\n"
    r = appctx.client.post("/api/format", json={"code": code, "formatter": "ruff"})
    assert r.status_code == 200
    out = r.json()["formatted"]
    assert "import os" not in out  # unused import removed by check --fix
    assert "import sys" in out
    assert "x = 1" in out  # formatted


def test_format_black(appctx):
    r = appctx.client.post("/api/format", json={"code": PY_MESSY, "formatter": "black"})
    assert r.status_code == 200
    assert r.json()["formatted"] == "x = 1\n"


def test_language_alias_python_resolves_to_ruff(appctx):
    """Legacy `language` param still works (python → ruff)."""
    r = appctx.client.post("/api/format", json={"code": PY_UNUSED_IMPORT, "language": "python"})
    assert r.status_code == 200
    assert "import os" not in r.json()["formatted"]


def test_language_alias_cpp_resolves_to_clang_format(appctx):
    r = appctx.client.post("/api/format", json={"code": CPP_MESSY, "language": "cpp"})
    assert r.status_code == 200
    assert "int main()" in r.json()["formatted"]


def test_adhoc_config_overrides_stored(appctx):
    """A config passed in the request is used instead of the stored one."""
    cfg = "BasedOnStyle: LLVM\nIndentWidth: 8\n"
    r = appctx.client.post(
        "/api/format",
        json={"code": CPP_MESSY, "formatter": "clang-format", "config": cfg},
    )
    assert r.status_code == 200
    # IndentWidth: 8 → the body line is indented by 8 spaces
    assert "\n        " in r.json()["formatted"]


def test_unknown_language_is_400(appctx):
    r = appctx.client.post("/api/format", json={"code": "x", "language": "klingon"})
    assert r.status_code == 400
    assert "error" in r.json()


def test_explicit_unknown_formatter_does_not_fall_back(appctx):
    r = appctx.client.post(
        "/api/format", json={"code": CPP_MESSY, "formatter": "missing"}
    )
    assert r.status_code == 400


def test_formatter_language_mismatch_is_400(appctx):
    r = appctx.client.post(
        "/api/format",
        json={"code": CPP_MESSY, "formatter": "ruff", "language": "cpp"},
    )
    assert r.status_code == 400


def test_uninstalled_version_is_400(appctx):
    r = appctx.client.post(
        "/api/format", json={"code": PY_MESSY, "formatter": "ruff", "version": "0.0.1"}
    )
    assert r.status_code == 400
    assert "not installed" in r.json()["error"]


def test_clang_version_alias_default(appctx):
    """Legacy `clang_version` alias, pointed at the base version, formats fine."""
    base = appctx.default_version("clang-format")
    r = appctx.client.post(
        "/api/format",
        json={"code": CPP_MESSY, "language": "cpp", "clang_version": base},
    )
    assert r.status_code == 200
    assert "int main()" in r.json()["formatted"]


def test_invalid_source_yields_500(appctx):
    """A formatter that errors (ruff can't parse) surfaces as a 500 FormatError."""
    r = appctx.client.post(
        "/api/format", json={"code": "def (:\n  pass\n", "formatter": "ruff"}
    )
    assert r.status_code == 500
    assert "error" in r.json()
