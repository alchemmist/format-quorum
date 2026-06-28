"""The catch-all SPA route that serves the built frontend (or 404 when absent)."""


def test_frontend_not_built_404(appctx):
    r = appctx.client.get("/")
    assert r.status_code == 404
    assert r.json()["error"] == "frontend not built"


def test_serves_index_and_assets_when_built(appctx):
    dist = appctx.main.FRONTEND_DIST
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "index.html").write_text("<html>spa</html>", encoding="utf-8")
    (dist / "app.js").write_text("// bundle", encoding="utf-8")

    assert appctx.client.get("/").text == "<html>spa</html>"
    assert appctx.client.get("/app.js").text == "// bundle"
    # unknown client route falls back to index.html
    assert appctx.client.get("/cpp").text == "<html>spa</html>"
