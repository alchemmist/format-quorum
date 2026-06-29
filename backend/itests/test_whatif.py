"""POST /api/tests/whatif — the "config hypothesis" diff."""

from conftest import CPP_MESSY, seed_passing_test


def test_patch_flips_a_passing_test_to_fail(appctx):
    rec = seed_passing_test(appctx.client, "cpp", CPP_MESSY, name="indent")
    out = appctx.client.post(
        "/api/tests/whatif",
        json={"formatter": "clang-format", "patch": {"IndentWidth": 8}},
    ).json()
    assert out["formatter"] == "clang-format"
    assert rec["name"] in out["flips"]["now_fail"]
    assert out["summary"]["baseline"]["passed"] >= 1
    # the patched config is echoed back and actually contains the override
    assert "IndentWidth: 8" in out["effective_config"]


def test_patch_unsupported_for_non_patchable_400(appctx):
    seed_passing_test(appctx.client, "python", "x=1\n")
    r = appctx.client.post(
        "/api/tests/whatif", json={"formatter": "ruff", "patch": {"x": 1}}
    )
    assert r.status_code == 400
    assert "patch is not supported" in r.json()["error"]


def test_full_config_candidate(appctx):
    rec = seed_passing_test(appctx.client, "cpp", CPP_MESSY, name="full")
    out = appctx.client.post(
        "/api/tests/whatif",
        json={"formatter": "clang-format", "config": "BasedOnStyle: LLVM\nIndentWidth: 8\n"},
    ).json()
    assert rec["name"] in out["flips"]["now_fail"]


def test_targets_called_out(appctx):
    rec = seed_passing_test(appctx.client, "cpp", CPP_MESSY, name="target-me")
    out = appctx.client.post(
        "/api/tests/whatif",
        json={"formatter": "clang-format", "patch": {"IndentWidth": 8},
              "targets": [rec["id"]]},
    ).json()
    assert any(t["id"] == rec["id"] for t in out["targets"])


def test_whatif_unknown_language_400(appctx):
    r = appctx.client.post("/api/tests/whatif", json={"language": "klingon"})
    assert r.status_code == 400
