"""Uploading a custom (patched) formatter binary as a build on the version axis.

The feature is gated behind ALLOW_BINARY_UPLOAD (it runs an arbitrary uploaded
executable). The end-to-end case uploads a *copy of the real base binary* as the
custom build, so the uploaded build genuinely runs and formats — no network, no
package manager. It skips when the base binary isn't installed locally.
"""

import base64
from pathlib import Path

import pytest

from conftest import binary_present, seed_passing_test

# a versioned formatter whose base binary is a plain executable we can copy+run
UPLOADABLE = ("shfmt", "shell", "if [ 1 ];then echo x;fi\n", "; then")


def _enable(appctx):
    appctx.main.ALLOW_BINARY_UPLOAD = True


def _base_bytes(appctx, fid: str) -> bytes:
    return Path(appctx.main.version_mgrs[fid].strategy.base_binary).read_bytes()


def _upload(appctx, fid: str, label: str, blob: bytes):
    return appctx.client.post(
        f"/api/formatters/{fid}/uploads",
        json={"label": label, "content_b64": base64.b64encode(blob).decode()},
    )


def test_upload_disabled_by_default(appctx):
    """With the flag off (the public default), the endpoint is a hard 403."""
    r = appctx.client.post(
        "/api/formatters/shfmt/uploads",
        json={"label": "patched", "content_b64": base64.b64encode(b"x").decode()},
    )
    assert r.status_code == 403


def test_upload_bad_input(appctx):
    _enable(appctx)
    # empty/garbage label → no usable slug
    r = _upload(appctx, "shfmt", "  #! ", b"data")
    assert r.status_code == 400
    # not base64
    r = appctx.client.post(
        "/api/formatters/shfmt/uploads",
        json={"label": "ok", "content_b64": "not base64!!"},
    )
    assert r.status_code == 400
    # unknown formatter (no version axis)
    r = _upload(appctx, "nope", "ok", b"data")
    assert r.status_code == 400


def test_upload_install_select_matrix_remove(appctx):
    fid, language, src, needle = UPLOADABLE
    if not binary_present(fid):
        pytest.skip(f"{fid} not installed")
    _enable(appctx)

    # upload a copy of the real base binary as a custom build
    r = _upload(appctx, fid, "my patch #1", _base_bytes(appctx, fid))
    assert r.status_code == 200, r.text
    data = r.json()
    vid = data["added"]
    assert vid == "custom-my-patch-1"  # free-form label → safe custom-<slug> id
    assert vid in data["versions"]  # on the axis (so format/matrix see it)
    assert vid in data["uploads"]  # surfaced separately for the UI

    # it genuinely formats — same output as the base binary
    out = appctx.client.post(
        "/api/format", json={"code": src, "formatter": fid, "version": vid}
    )
    assert out.status_code == 200, out.text
    assert needle in out.json()["formatted"]

    # the custom build gets its own editable config, seeded from the default
    cfg = appctx.client.get(f"/api/config/{fid}?version={vid}")
    assert cfg.status_code == 200

    # it's a column in the matrix, green for a passing test
    rec = seed_passing_test(appctx.client, language, src)
    matrix = appctx.client.post("/api/tests/matrix", json={"formatter": fid}).json()
    assert vid in matrix["versions"]
    row = next(rr for rr in matrix["tests"] if rr["id"] == rec["id"])
    assert row["cells"][vid]["passed"] is True

    # remove it
    r = appctx.client.delete(f"/api/formatters/{fid}/versions/{vid}")
    assert r.status_code == 200
    assert vid not in r.json()["versions"]


def test_upload_replaces_same_label(appctx):
    fid = UPLOADABLE[0]
    if not binary_present(fid):
        pytest.skip(f"{fid} not installed")
    _enable(appctx)
    blob = _base_bytes(appctx, fid)
    first = _upload(appctx, fid, "patched", blob).json()
    second = _upload(appctx, fid, "patched", blob).json()
    # same label → same id, not a duplicate
    assert first["added"] == second["added"] == "custom-patched"
    assert second["uploads"].count("custom-patched") == 1


def test_failed_reupload_keeps_previous_build(appctx):
    """A re-upload that fails to install must not destroy the working build under
    the same id (it stages first, swaps only on success)."""
    fid = UPLOADABLE[0]
    if not binary_present(fid):
        pytest.skip(f"{fid} not installed")
    _enable(appctx)
    _upload(appctx, fid, "patched", _base_bytes(appctx, fid))
    mgr = appctx.main.version_mgrs[fid]
    assert mgr.get_binary("custom-patched") is not None

    # make the next install fail, then re-upload under the same id
    mgr.strategy.install_upload = lambda src, vdir: (False, "boom")
    r = _upload(appctx, fid, "patched", b"whatever")
    assert r.status_code == 400
    # the original build is still installed and runnable
    assert mgr.get_binary("custom-patched") is not None
    assert "custom-patched" in appctx.client.get(f"/api/formatters/{fid}/versions").json()["uploads"]


def test_uploads_enabled_flag_in_registry(appctx):
    assert appctx.client.get("/api/formatters").json()["uploads_enabled"] is False
    _enable(appctx)
    assert appctx.client.get("/api/formatters").json()["uploads_enabled"] is True
