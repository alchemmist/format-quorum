def test_cors_allows_local_vite_origin(appctx):
    r = appctx.client.options(
        "/api/formatters",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_rejects_untrusted_origin(appctx):
    r = appctx.client.options(
        "/api/formatters",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers
