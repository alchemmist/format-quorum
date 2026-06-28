"""Config endpoints: GET/PUT/history/rollback + the raw config files."""


def test_get_config_clang(appctx):
    c = appctx.client.get("/api/config/clang-format").json()
    assert c["language"] == "cpp"
    assert c["formatter"] == "clang-format"
    assert c["version"] == appctx.default_version("clang-format")
    assert c["filename"] == "clang-format"
    assert "Language: Cpp" in c["content"]


def test_get_config_language_alias(appctx):
    a = appctx.client.get("/api/config/cpp").json()
    b = appctx.client.get("/api/config/clang-format").json()
    assert a["formatter"] == b["formatter"] == "clang-format"
    py = appctx.client.get("/api/config/python").json()
    assert py["formatter"] == "ruff"


def test_get_config_unknown_400(appctx):
    r = appctx.client.get("/api/config/nope")
    assert r.status_code == 400


def test_put_records_and_materializes(appctx):
    new = "BasedOnStyle: LLVM\nColumnLimit: 100\n"
    r = appctx.client.put("/api/config/clang-format", json={"content": new, "author": "me"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # current content reflects it, and the raw file is materialized
    assert appctx.client.get("/api/config/clang-format").json()["content"] == new
    raw = appctx.client.get("/clang-format")
    assert raw.status_code == 200
    assert "ColumnLimit: 100" in raw.text


def test_put_identical_content_is_noop(appctx):
    cur = appctx.client.get("/api/config/ruff").json()["content"]
    r = appctx.client.put("/api/config/ruff", json={"content": cur})
    assert r.status_code == 200
    assert r.json().get("unchanged") is True


def test_history_grows_and_serves_versions(appctx):
    appctx.client.put("/api/config/clang-format", json={"content": "BasedOnStyle: LLVM\nA: 1\n"})
    appctx.client.put("/api/config/clang-format", json={"content": "BasedOnStyle: LLVM\nA: 2\n"})
    hist = appctx.client.get("/api/config/clang-format/history").json()
    assert hist["head"] == 2
    seqs = [v["seq"] for v in hist["versions"]]
    assert seqs == [0, 1, 2]  # base + two records
    v1 = appctx.client.get("/api/config/clang-format/history/1").json()
    assert "A: 1" in v1["content"]


def test_history_missing_seq_404(appctx):
    r = appctx.client.get("/api/config/clang-format/history/99")
    assert r.status_code == 404


def test_rollback(appctx):
    appctx.client.put("/api/config/clang-format", json={"content": "BasedOnStyle: LLVM\nA: 1\n"})
    appctx.client.put("/api/config/clang-format", json={"content": "BasedOnStyle: LLVM\nA: 2\n"})
    r = appctx.client.post("/api/config/clang-format/rollback", json={"seq": 1})
    assert r.status_code == 200
    # rollback is append-only: current == v1 content, head advanced to 3
    assert "A: 1" in appctx.client.get("/api/config/clang-format").json()["content"]
    assert appctx.client.get("/api/config/clang-format/history").json()["head"] == 3


def test_rollback_bad_seq_404(appctx):
    r = appctx.client.post("/api/config/clang-format/rollback", json={"seq": 99})
    assert r.status_code == 404


def test_config_unknown_key_paths_400(appctx):
    assert appctx.client.put("/api/config/nope", json={"content": "x"}).status_code == 400
    assert appctx.client.get("/api/config/nope/history").status_code == 400
    assert appctx.client.get("/api/config/nope/history/0").status_code == 400
    assert appctx.client.post("/api/config/nope/rollback", json={"seq": 0}).status_code == 400


def test_raw_config_files(appctx):
    assert "Language: Cpp" in appctx.client.get("/clang-format").text
    assert appctx.client.get("/ruff.toml").status_code == 200
