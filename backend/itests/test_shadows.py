"""POST/DELETE /api/shadow-configs — named alt configs on an installed binary."""


def _base(appctx):
    return appctx.default_version("clang-format")


def test_create_shadow_and_its_config(appctx):
    r = appctx.client.post(
        "/api/shadow-configs",
        json={"id": "shadow-a", "base": _base(appctx), "name": "no-align",
              "content": "BasedOnStyle: LLVM\nColumnLimit: 0\n"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert any(s["id"] == "shadow-a" for s in body["shadows"])
    # its config history exists under the formatter key and serves the content
    cfg = appctx.client.get("/api/config/clang-format?version=shadow-a").json()
    assert "ColumnLimit: 0" in cfg["content"]
    # and it surfaces in the formatter's version state
    st = appctx.client.get("/api/formatters/clang-format/versions").json()
    assert any(s["id"] == "shadow-a" for s in st["shadows"])


def test_shadow_defaults_to_clang_format(appctx):
    r = appctx.client.post(
        "/api/shadow-configs",
        json={"id": "shadow-b", "base": _base(appctx), "content": "BasedOnStyle: LLVM\n"},
    )
    assert r.status_code == 200
    assert r.json()["shadow"]["formatter"] == "clang-format"


def test_invalid_shadow_id_400(appctx):
    r = appctx.client.post(
        "/api/shadow-configs",
        json={"id": "not-a-shadow", "base": _base(appctx), "content": "x"},
    )
    assert r.status_code == 400
    assert "invalid shadow id" in r.json()["error"]


def test_shadow_id_cannot_escape_config_directory(appctx):
    r = appctx.client.post(
        "/api/shadow-configs",
        json={
            "id": "shadow-../../escaped",
            "base": _base(appctx),
            "content": "x",
        },
    )
    assert r.status_code == 400


def test_unknown_shadow_formatter_is_400(appctx):
    r = appctx.client.post(
        "/api/shadow-configs",
        json={
            "id": "shadow-x",
            "base": _base(appctx),
            "content": "x",
            "formatter": "missing",
        },
    )
    assert r.status_code == 400


def test_shadow_base_not_installed_400(appctx):
    r = appctx.client.post(
        "/api/shadow-configs",
        json={"id": "shadow-c", "base": "99.9.9", "content": "x"},
    )
    assert r.status_code == 400
    assert "not installed" in r.json()["error"]


def test_delete_shadow_drops_config(appctx):
    appctx.client.post(
        "/api/shadow-configs",
        json={"id": "shadow-d", "base": _base(appctx), "content": "BasedOnStyle: LLVM\n"},
    )
    r = appctx.client.delete("/api/shadow-configs/shadow-d")
    assert r.status_code == 200
    assert all(s["id"] != "shadow-d" for s in r.json()["shadows"])


def test_delete_missing_shadow_404(appctx):
    r = appctx.client.delete("/api/shadow-configs/shadow-nope")
    assert r.status_code == 404
