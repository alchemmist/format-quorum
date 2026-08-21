"""POST /api/tests/matrix — tests x versions (+ shadow configs) grid."""

from conftest import CPP_MESSY, seed_passing_test


def test_matrix_base_only(appctx):
    rec = seed_passing_test(appctx.client, "cpp", CPP_MESSY, name="m1")
    base = appctx.default_version("clang-format")
    out = appctx.client.post("/api/tests/matrix", json={"formatter": "clang-format"}).json()
    assert out["language"] == "cpp"
    assert base in out["versions"]
    row = next(r for r in out["tests"] if r["id"] == rec["id"])
    assert row["cells"][base]["passed"] is True


def test_matrix_includes_installed_extra_version(appctx, install_version):
    seed_passing_test(appctx.client, "cpp", CPP_MESSY, name="m2")
    # a version distinct from the probed base, so it's a genuine extra column
    extra = "14.0.6"
    assert extra != appctx.default_version("clang-format")  # else the check is vacuous
    install_version("clang-format", extra)
    out = appctx.client.post("/api/tests/matrix", json={"formatter": "clang-format"}).json()
    assert extra in out["versions"]


def test_matrix_includes_published_shadow(appctx):
    seed_passing_test(appctx.client, "cpp", CPP_MESSY, name="m3")
    base = appctx.default_version("clang-format")
    appctx.client.post(
        "/api/shadow-configs",
        json={"id": "shadow-m", "base": base, "name": "s", "content": "BasedOnStyle: LLVM\n"},
    )
    out = appctx.client.post("/api/tests/matrix", json={"formatter": "clang-format"}).json()
    assert "shadow-m" in out["versions"]
    assert any(s["id"] == "shadow-m" for s in out["shadows"])


def test_matrix_adhoc_unpublished_shadow_column(appctx):
    seed_passing_test(appctx.client, "cpp", CPP_MESSY, name="m4")
    base = appctx.default_version("clang-format")
    out = appctx.client.post(
        "/api/tests/matrix",
        json={"formatter": "clang-format",
              "shadows": [{"id": "shadow-draft", "base": base, "name": "draft",
                           "content": "BasedOnStyle: LLVM\nIndentWidth: 8\n"}]},
    ).json()
    assert "shadow-draft" in out["versions"]


def test_matrix_rejects_uninstalled_draft_shadow_base(appctx):
    r = appctx.client.post(
        "/api/tests/matrix",
        json={
            "formatter": "clang-format",
            "shadows": [
                {
                    "id": "shadow-draft",
                    "base": "99.9.9",
                    "name": "draft",
                    "content": "BasedOnStyle: LLVM\n",
                }
            ],
        },
    )
    assert r.status_code == 400


def test_matrix_python(appctx):
    rec = seed_passing_test(appctx.client, "python", "x=1\n", name="pm")
    base = appctx.default_version("ruff")
    out = appctx.client.post("/api/tests/matrix", json={"formatter": "ruff"}).json()
    assert out["language"] == "python"
    assert base in out["versions"]
    row = next(r for r in out["tests"] if r["id"] == rec["id"])
    assert row["cells"][base]["passed"] is True


def test_matrix_unknown_language_400(appctx):
    r = appctx.client.post("/api/tests/matrix", json={"language": "klingon"})
    assert r.status_code == 400
