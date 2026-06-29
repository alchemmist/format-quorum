"""Editable configs for the classic formatters that read one (prettier, rustfmt,
taplo). shfmt and google-java-format are config-less by design.

The format-honoring cases skip when the tool isn't installed locally; the config
storage/keying assertions run everywhere.
"""

import pytest

from conftest import binary_present


def test_config_present_for_configurable_formatters(appctx):
    get = lambda key: appctx.client.get(f"/api/config/{key}").json()  # noqa: E731
    assert get("prettier-ts")["filename"] == "prettierrc"
    assert get("rustfmt")["filename"] == "rustfmt.toml"
    assert get("taplo")["filename"] == "taplo.toml"
    # seed content is served
    assert "semi" in get("prettier-ts")["content"]
    assert "max_width" in get("rustfmt")["content"]


def test_configless_formatters_have_no_config(appctx):
    for fid in ("shfmt", "google-java-format"):
        assert appctx.client.get(f"/api/config/{fid}").json()["filename"] is None


def test_prettier_config_is_honored(appctx):
    if not binary_present("prettier"):
        pytest.skip("prettier not installed")
    appctx.client.put(
        "/api/config/prettier-ts",
        json={"content": '{\n  "singleQuote": true,\n  "semi": false\n}\n'},
    )
    out = appctx.client.post(
        "/api/format", json={"code": 'const x = "hi";\n', "formatter": "prettier-ts"}
    ).json()["formatted"]
    assert out == "const x = 'hi'\n"  # single quotes, no semicolon


def test_rustfmt_config_is_honored(appctx):
    if not binary_present("rustfmt"):
        pytest.skip("rustfmt not installed")
    appctx.client.put("/api/config/rustfmt", json={"content": "max_width = 30\n"})
    out = appctx.client.post(
        "/api/format",
        json={"code": "fn main(){let r=foo(aaaa,bbbb,cccc,dddd);}\n", "formatter": "rustfmt"},
    ).json()["formatted"]
    assert "\n        " in out  # narrow width forced the call to wrap


def test_taplo_config_is_honored(appctx):
    if not binary_present("taplo"):
        pytest.skip("taplo not installed")
    appctx.client.put(
        "/api/config/taplo", json={"content": "[formatting]\nalign_entries = true\n"}
    )
    out = appctx.client.post(
        "/api/format", json={"code": "aaa = 1\nb = 2\n", "formatter": "taplo"}
    ).json()["formatted"]
    assert "b   = 2" in out  # entries aligned


def test_prettier_config_is_per_version(appctx, install_version):
    if not binary_present("prettier"):
        pytest.skip("prettier not installed")
    base = appctx.default_version("prettier-ts")
    install_version("prettier-ts", "3.3.3")

    # edit only the 3.3.3 config
    appctx.client.put(
        "/api/config/prettier-ts",
        json={"version": "3.3.3", "content": '{ "semi": false }\n'},
    )
    v333 = appctx.client.get("/api/config/prettier-ts?version=3.3.3").json()
    vbase = appctx.client.get(f"/api/config/prettier-ts?version={base}").json()
    assert v333["version"] == "3.3.3"
    assert "semi" in v333["content"] and v333["content"] != vbase["content"]
    # the base version's config is untouched (independent per-version histories)
    assert "semi" in vbase["content"] and "true" in vbase["content"]


def test_config_history_and_rollback_for_prettier(appctx):
    appctx.client.put("/api/config/prettier-ts", json={"content": '{ "tabWidth": 4 }\n'})
    appctx.client.put("/api/config/prettier-ts", json={"content": '{ "tabWidth": 8 }\n'})
    hist = appctx.client.get("/api/config/prettier-ts/history").json()
    assert hist["head"] == 2
    appctx.client.post("/api/config/prettier-ts/rollback", json={"seq": 1})
    assert "tabWidth" in appctx.client.get("/api/config/prettier-ts").json()["content"]
    assert '4' in appctx.client.get("/api/config/prettier-ts").json()["content"]
