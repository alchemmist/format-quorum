"""Unit coverage for store/version internals that the HTTP layer can't reach
cheaply: pure helpers, the wheel probe, append-only history semantics."""

import io
import json

import config_store
import shadow_store
import test_store
import versions
from versions import VERSION_RE, PipInstall


# ── version string validation ─────────────────────────────────────────────────
def test_version_re():
    assert VERSION_RE.match("22.1.5")
    assert not VERSION_RE.match("22.1")
    assert not VERSION_RE.match("22.1.5.1")
    assert not VERSION_RE.match("v22.1.5")


# ── wheel compatibility (platform-independent invariants) ─────────────────────
def test_wheel_compatible_pure_python_and_sdist():
    # pure-Python wheel installs anywhere (the black linux/arm64 fix)
    assert PipInstall._wheel_compatible("black-26.5.1-py3-none-any.whl") is True
    # sdists ship no usable bundled binary
    assert PipInstall._wheel_compatible("black-26.5.1.tar.gz") is False
    assert PipInstall._wheel_compatible("foo.zip") is False


def test_available_probes_wheels(monkeypatch):
    """available() parses the PyPI files list (mocked — offline)."""
    payload = {"urls": [
        {"filename": "ruff-0.1.0.tar.gz"},
        {"filename": "ruff-0.1.0-py3-none-any.whl"},
    ]}

    def fake_urlopen(url, timeout=0):  # noqa: ARG001
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(versions.urllib.request, "urlopen", fake_urlopen)
    assert PipInstall("ruff", "ruff").available("0.1.0") is True

    payload["urls"] = [{"filename": "ruff-0.1.0.tar.gz"}]  # sdist only
    assert PipInstall("ruff", "ruff").available("0.1.0") is False


# ── ConfigStore: history semantics ────────────────────────────────────────────
def test_config_store_record_and_rollback(tmp_path):
    store = config_store.ConfigStore(tmp_path)
    store.ensure_seeded("k", seed_text="base\n")
    assert store.current("k") == "base\n"

    store.record("k", "v1\n")
    store.record("k", "v2\n")
    assert store.current("k") == "v2\n"
    assert store.head_seq("k") == 2

    # re-recording identical content is a no-op
    res = store.record("k", "v2\n")
    assert res.get("unchanged") is True
    assert store.head_seq("k") == 2

    # rollback is append-only: history grows, current becomes the target content
    store.rollback("k", 1)
    assert store.current("k") == "v1\n"
    assert store.head_seq("k") == 3
    assert store.rollback("k", 99) is None


def test_config_store_ensure_seeded_and_migrate(tmp_path):
    store = config_store.ConfigStore(tmp_path)
    assert store.ensure_seeded("a", seed_text="x") is True
    assert store.ensure_seeded("a", seed_text="y") is False  # already seeded
    # seed_from_key copies the current content of another key once
    store.ensure_seeded("b", seed_from_key="a")
    assert store.current("b") == "x"
    # migrate moves history to a new key, keeping the old as a backup
    assert store.migrate("a", "c") is True
    assert store.current("c") == "x"


# ── ShadowStore ───────────────────────────────────────────────────────────────
def test_shadow_store_crud(tmp_path):
    store = shadow_store.ShadowStore(tmp_path / "shadows.json")
    store.create("shadow-1", "22.1.8", "n", formatter="clang-format")
    assert store.is_shadow("shadow-1")
    # create is idempotent on id (updates in place)
    store.create("shadow-1", "22.1.8", "renamed")
    entry = store.get("shadow-1")
    assert entry is not None and entry["name"] == "renamed"
    assert len(store.list()) == 1
    assert store.delete("shadow-1") is True
    assert store.delete("shadow-1") is False
    assert store.get(None) is None


# ── test_store normalization ──────────────────────────────────────────────────
def test_normalize_is_lenient_on_trailing_newlines():
    assert test_store._normalize("a\nb\n\n") == test_store._normalize("a\nb")
    assert test_store._normalize("a\r\nb") == test_store._normalize("a\nb")
