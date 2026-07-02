"""The version axis for the classic formatters: install / select / matrix / remove.

Installs are faked offline (the harness symlinks the version's binary to the real
base tool), so these exercise the full version machinery — generically, the same
code path clang-format/ruff/black use — for the npm/url/jar-installed formatters.
Each case skips when its base binary isn't installed locally.
"""

import pytest

from conftest import binary_present, seed_passing_test

# (formatter id, base binary, language, a fresh version to "install", sample, needle)
VERSIONED = [
    ("prettier-ts", "prettier", "typescript", "3.3.3", "const x={a:1}\n", "const x = { a: 1 };"),
    ("taplo", "taplo", "toml", "0.6.0", "a={b=1}\n", "a = { b = 1 }"),
    ("shfmt", "shfmt", "shell", "3.10.0", 'if [ 1 ];then echo x;fi\n', "; then"),
]
IDS = [c[0] for c in VERSIONED]


@pytest.mark.parametrize("fid,binary,language,ver,src,needle", VERSIONED, ids=IDS)
def test_version_state_has_probed_default(appctx, fid, binary, language, ver, src, needle):
    if not binary_present(binary):
        pytest.skip(f"{binary} not installed")
    st = appctx.client.get(f"/api/formatters/{fid}/versions").json()
    base = appctx.default_version(fid)
    assert base is not None  # probed from the base binary's --version
    assert st["default"] == base
    assert base in st["versions"]
    assert isinstance(st["suggestions"], list)


@pytest.mark.parametrize("fid,binary,language,ver,src,needle", VERSIONED, ids=IDS)
def test_install_select_matrix_remove(appctx, install_version, fid, binary, language, ver, src, needle):
    if not binary_present(binary):
        pytest.skip(f"{binary} not installed")

    # install an extra version (offline) and confirm it shows up
    install_version(fid, ver)
    st = appctx.client.get(f"/api/formatters/{fid}/versions").json()
    assert ver in st["versions"]

    # format with that specific version
    r = appctx.client.post("/api/format", json={"code": src, "formatter": fid, "version": ver})
    assert r.status_code == 200, r.text
    assert needle in r.json()["formatted"]

    # the installed version is a column in the matrix, green for a passing test
    rec = seed_passing_test(appctx.client, language, src)
    matrix = appctx.client.post("/api/tests/matrix", json={"formatter": fid}).json()
    assert ver in matrix["versions"]
    row = next(rrow for rrow in matrix["tests"] if rrow["id"] == rec["id"])
    assert row["cells"][ver]["passed"] is True

    # remove it
    r = appctx.client.delete(f"/api/formatters/{fid}/versions/{ver}")
    assert r.status_code == 200
    assert ver not in r.json()["versions"]


def test_versioned_classic_formatters_are_marked_versioned(appctx):
    fmts = {f["id"]: f for f in appctx.client.get("/api/formatters").json()["formatters"]}
    for fid in ("prettier-ts", "prettier-css", "taplo", "shfmt", "google-java-format", "rustfmt"):
        assert fmts[fid]["versioned"] is True, fid


def test_rustfmt_is_versioned_by_toolchain(appctx):
    """rustfmt now has a version axis (ToolchainInstall via rustup); the axis is
    keyed by the rust *toolchain* version, probed from rustc — not by rustfmt's
    own version, which differs."""
    fmts = {f["id"]: f for f in appctx.client.get("/api/formatters").json()["formatters"]}
    assert fmts["rustfmt"]["versioned"] is True
    r = appctx.client.get("/api/formatters/rustfmt/versions")
    assert r.status_code == 200
    base = appctx.default_version("rustfmt")
    if base is None:
        pytest.skip("rustc not available to probe the toolchain version")
    st = r.json()
    assert st["default"] == base
    assert base in st["versions"]


def test_rustfmt_version_install_select_matrix_remove(appctx, install_version):
    """Full axis cycle for rustfmt, with the toolchain install faked offline (the
    harness symlinks the version's rustfmt under a toolchains/ dir, which
    ToolchainInstall.installed_binary discovers exactly like a real rustup one)."""
    if not binary_present("rustfmt"):
        pytest.skip("rustfmt not installed")
    if appctx.default_version("rustfmt") is None:
        pytest.skip("rustc not available to probe the toolchain version")

    ver = "1.82.0"
    install_version("rustfmt", ver)
    st = appctx.client.get("/api/formatters/rustfmt/versions").json()
    assert ver in st["versions"]

    src = "fn main(){let x=1;println!(\"{}\",x);}\n"
    r = appctx.client.post("/api/format", json={"code": src, "formatter": "rustfmt", "version": ver})
    assert r.status_code == 200, r.text
    assert "fn main()" in r.json()["formatted"]

    rec = seed_passing_test(appctx.client, "rust", src)
    matrix = appctx.client.post("/api/tests/matrix", json={"formatter": "rustfmt"}).json()
    assert ver in matrix["versions"]
    row = next(rrow for rrow in matrix["tests"] if rrow["id"] == rec["id"])
    assert row["cells"][ver]["passed"] is True

    r = appctx.client.delete(f"/api/formatters/rustfmt/versions/{ver}")
    assert r.status_code == 200
    assert ver not in r.json()["versions"]
