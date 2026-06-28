"""GET /api/formatters and the per-formatter version endpoints (+ clang aliases)."""


def test_registry_shape(appctx):
    fmts = {f["id"]: f for f in appctx.client.get("/api/formatters").json()["formatters"]}
    assert fmts["clang-format"]["language"] == "cpp"
    assert fmts["clang-format"]["versioned"] is True
    assert fmts["clang-format"]["patchable"] is True
    assert fmts["clang-format"]["config"]["filename"] == ".clang-format"
    assert fmts["ruff"]["language"] == "python"
    assert fmts["ruff"]["default"] is True
    assert fmts["ruff"]["patchable"] is False
    assert "ruff check --fix" in fmts["ruff"]["description"]
    assert fmts["black"]["default"] is False


def test_versions_state(appctx):
    st = appctx.client.get("/api/formatters/ruff/versions").json()
    base = appctx.default_version("ruff")
    assert st["default"] == base
    assert base in st["versions"]
    assert st["installing"] == []
    assert isinstance(st["suggestions"], list)
    assert isinstance(st["shadows"], list)


def test_versions_unknown_formatter_400(appctx):
    r = appctx.client.get("/api/formatters/nope/versions")
    assert r.status_code == 400
    assert "no version axis" in r.json()["error"]


def test_add_version_bad_format_400(appctx, enable_fake_install):
    r = appctx.client.post("/api/formatters/ruff/versions", json={"version": "not-a-version"})
    assert r.status_code == 400
    assert "three numbers" in r.json()["error"]


def test_add_and_remove_version_roundtrip(appctx, enable_fake_install):
    r = appctx.client.post("/api/formatters/ruff/versions", json={"version": "0.9.10"})
    assert r.status_code == 200
    assert "0.9.10" in r.json()["versions"]
    # its own config was seeded
    cfg = appctx.client.get("/api/config/ruff?version=0.9.10")
    assert cfg.status_code == 200
    assert cfg.json()["version"] == "0.9.10"
    # remove it
    r = appctx.client.delete("/api/formatters/ruff/versions/0.9.10")
    assert r.status_code == 200
    assert "0.9.10" not in r.json()["versions"]


def test_cannot_remove_base_version(appctx):
    base = appctx.default_version("ruff")
    r = appctx.client.delete(f"/api/formatters/ruff/versions/{base}")
    assert r.status_code == 400
    assert "default" in r.json()["error"]


def test_remove_uninstalled_version_400(appctx):
    r = appctx.client.delete("/api/formatters/ruff/versions/9.9.9")
    assert r.status_code == 400
    assert "not installed" in r.json()["error"]


def test_add_version_unknown_formatter_400(appctx):
    r = appctx.client.post("/api/formatters/nope/versions", json={"version": "1.2.3"})
    assert r.status_code == 400


# ── legacy clang-format aliases ───────────────────────────────────────────────
def test_clang_versions_alias_matches_generic(appctx):
    a = appctx.client.get("/api/clang-versions").json()
    b = appctx.client.get("/api/formatters/clang-format/versions").json()
    assert a == b
    assert a["default"] == appctx.default_version("clang-format")


def test_clang_versions_add_remove_alias(appctx, enable_fake_install):
    base = appctx.default_version("clang-format")
    # pick any installable-looking version that isn't the base
    r = appctx.client.post("/api/clang-versions", json={"version": "18.1.8"})
    assert r.status_code == 200
    assert "18.1.8" in r.json()["versions"]
    if "18.1.8" != base:
        assert appctx.client.delete("/api/clang-versions/18.1.8").status_code == 200
