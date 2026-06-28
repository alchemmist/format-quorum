"""/api/tests/run and /api/tests/{id}/run — running the suite."""

from conftest import CPP_MESSY, seed_passing_test


def test_run_all_summary(appctx):
    seed_passing_test(appctx.client, "cpp", CPP_MESSY, name="cpp-ok")
    seed_passing_test(appctx.client, "python", "x=1\n", name="py-ok")
    out = appctx.client.post("/api/tests/run", json={}).json()
    assert out["summary"]["total"] == 2
    assert out["summary"]["passed"] == 2
    assert out["summary"]["failed"] == 0


def test_run_reports_failures_and_muted(appctx):
    seed_passing_test(appctx.client, "python", "x=1\n", name="ok")
    appctx.client.post(
        "/api/tests",
        json={"name": "bad", "language": "python", "input": "x=1\n", "expected": "WRONG\n"},
    )
    seed_passing_test(appctx.client, "python", "y=2\n", name="muted", muted=True)
    s = appctx.client.post("/api/tests/run", json={}).json()["summary"]
    assert s["total"] == 3
    assert s["passed"] == 1
    assert s["failed"] == 1
    assert s["muted"] == 1


def test_run_filtered_by_language(appctx):
    seed_passing_test(appctx.client, "cpp", CPP_MESSY, name="cpp-ok")
    seed_passing_test(appctx.client, "python", "x=1\n", name="py-ok")
    out = appctx.client.post("/api/tests/run", json={"language": "python"}).json()
    assert out["summary"]["total"] == 1
    assert all(r["language"] == "python" for r in out["results"])


def test_run_uninstalled_version_400(appctx):
    seed_passing_test(appctx.client, "python", "x=1\n")
    r = appctx.client.post("/api/tests/run", json={"formatter": "ruff", "version": "0.0.1"})
    assert r.status_code == 400


def test_run_one_found(appctx):
    rec = seed_passing_test(appctx.client, "python", "x=1\n", name="solo")
    out = appctx.client.post(f"/api/tests/{rec['id']}/run", json={}).json()
    assert out["id"] == rec["id"]
    assert out["status"] == "pass"
    assert out["passed"] is True


def test_run_one_not_found_404(appctx):
    r = appctx.client.post("/api/tests/deadbeef/run", json={})
    assert r.status_code == 404


def test_run_one_explicit_formatter(appctx):
    rec = seed_passing_test(appctx.client, "python", "x=1\n", formatter="black", name="b")
    out = appctx.client.post(
        f"/api/tests/{rec['id']}/run", json={"formatter": "black"}
    ).json()
    assert out["status"] == "pass"
