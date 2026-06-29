"""/api/tests CRUD — the BEFORE/AFTER suite storage."""


def test_list_starts_empty(appctx):
    assert appctx.client.get("/api/tests").json() == []


def test_create_and_list(appctx):
    rec = appctx.client.post(
        "/api/tests",
        json={"name": "case", "language": "python", "input": "x=1\n", "expected": "x = 1\n"},
    ).json()
    assert rec["id"]
    assert rec["language"] == "python"
    listed = appctx.client.get("/api/tests").json()
    assert [t["id"] for t in listed] == [rec["id"]]


def test_create_invalid_language_400(appctx):
    r = appctx.client.post("/api/tests", json={"name": "x", "language": "klingon"})
    assert r.status_code == 400
    assert "invalid language" in r.json()["error"]


def test_update_fields(appctx):
    rec = appctx.client.post("/api/tests", json={"language": "cpp", "input": "a"}).json()
    r = appctx.client.put(f"/api/tests/{rec['id']}", json={"name": "renamed", "muted": True})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "renamed"
    assert body["muted"] is True


def test_update_language_moves_record(appctx):
    rec = appctx.client.post("/api/tests", json={"language": "cpp", "input": "a"}).json()
    r = appctx.client.put(f"/api/tests/{rec['id']}", json={"language": "python"})
    assert r.status_code == 200
    assert r.json()["language"] == "python"
    assert r.json()["id"] == rec["id"]  # moved in place, not deleted + recreated
    # still exactly one record, now python, same id
    listed = appctx.client.get("/api/tests").json()
    assert len(listed) == 1
    assert listed[0]["language"] == "python"
    assert listed[0]["id"] == rec["id"]


def test_update_not_found_404(appctx):
    r = appctx.client.put("/api/tests/deadbeef", json={"name": "x"})
    assert r.status_code == 404


def test_update_invalid_language_400(appctx):
    rec = appctx.client.post("/api/tests", json={"language": "cpp", "input": "a"}).json()
    r = appctx.client.put(f"/api/tests/{rec['id']}", json={"language": "klingon"})
    assert r.status_code == 400


def test_delete(appctx):
    rec = appctx.client.post("/api/tests", json={"language": "cpp", "input": "a"}).json()
    assert appctx.client.delete(f"/api/tests/{rec['id']}").status_code == 200
    assert appctx.client.get("/api/tests").json() == []


def test_delete_not_found_404(appctx):
    assert appctx.client.delete("/api/tests/deadbeef").status_code == 404
