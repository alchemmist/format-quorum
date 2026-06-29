def test_app_boots_and_lists_formatters(appctx):
    r = appctx.client.get("/api/formatters")
    assert r.status_code == 200
    ids = {f["id"] for f in r.json()["formatters"]}
    assert {"clang-format", "ruff", "black"} <= ids
