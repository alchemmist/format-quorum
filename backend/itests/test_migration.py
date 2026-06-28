"""The one-time legacy-key data migration (language-keyed → formatter-keyed)."""

import json


def _seed_legacy(d):
    (d / "python.json").write_text('{"base": "py-cfg", "versions": []}', encoding="utf-8")
    (d / "cpp.json").write_text('{"base": "cpp-cfg", "versions": []}', encoding="utf-8")
    (d / "cpp@22.1.8.json").write_text('{"base": "v-cfg", "versions": []}', encoding="utf-8")
    (d / "cpp@shadow-1.json").write_text('{"base": "s-cfg", "versions": []}', encoding="utf-8")
    (d / "shadows.json").write_text(
        '[{"id": "shadow-1", "base": "22.1.8", "name": "x"}]', encoding="utf-8"
    )


def test_migration_renames_and_tags(appctx, tmp_path, monkeypatch):
    d = tmp_path / "legacy_hist"
    d.mkdir()
    _seed_legacy(d)
    monkeypatch.setattr(appctx.main, "CONFIG_HISTORY_DIR", d)

    appctx.main._migrate_legacy_keys()

    # renamed to the formatter scheme, originals kept as .bak
    assert (d / "ruff.json").exists()
    assert (d / "python.json.bak").exists()
    assert not (d / "python.json").exists()
    assert (d / "clang-format.json").exists()
    assert (d / "clang-format@22.1.8.json").exists()
    assert (d / "clang-format@shadow-1.json").exists()
    # content carried over verbatim
    assert json.loads((d / "ruff.json").read_text())["base"] == "py-cfg"
    # shadows tagged with their formatter
    shadows = json.loads((d / "shadows.json").read_text())
    assert shadows[0]["formatter"] == "clang-format"


def test_migration_is_idempotent(appctx, tmp_path, monkeypatch):
    d = tmp_path / "legacy_hist"
    d.mkdir()
    _seed_legacy(d)
    monkeypatch.setattr(appctx.main, "CONFIG_HISTORY_DIR", d)

    appctx.main._migrate_legacy_keys()
    appctx.main._migrate_legacy_keys()  # second pass must be a no-op

    # no double-migration: the already-migrated files aren't re-.bak'd
    assert not (d / "ruff.json.bak").exists()
    assert not (d / "clang-format@22.1.8.json.bak").exists()


def test_migration_skips_when_target_exists(appctx, tmp_path, monkeypatch):
    d = tmp_path / "legacy_hist"
    d.mkdir()
    (d / "python.json").write_text('{"base": "old", "versions": []}', encoding="utf-8")
    (d / "ruff.json").write_text('{"base": "new", "versions": []}', encoding="utf-8")
    monkeypatch.setattr(appctx.main, "CONFIG_HISTORY_DIR", d)

    appctx.main._migrate_legacy_keys()

    # existing ruff.json is not clobbered, python.json left untouched (no .bak)
    assert json.loads((d / "ruff.json").read_text())["base"] == "new"
    assert (d / "python.json").exists()
    assert not (d / "python.json.bak").exists()
