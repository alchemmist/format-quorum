"""Versioned storage for the formatter configs.

A formatter config is no longer just a file that ``PUT`` overwrites: every
published change is appended to a per-*key* history so a good, working config
can't be *permanently* broken — anyone can still change it, but we can always
roll back.

Keys, not languages
-------------------
Originally there was one config per language ("cpp", "python"). Now each
clang-format *version* keeps its own config — the whole point of installing a
newer clang-format is to use options it adds — so cpp configs are keyed by
version: ``cpp@22.1.8``. Python stays a single key ``python``. The store itself
is key-agnostic; ``main.py`` owns the key scheme and the cloning/migration.

Storage model (one JSON file per key in a persistent dir)::

    {
      "base": "<the original config the history started from>",
      "versions": [
        {"seq": 1, "ts": "...", "author": "...", "message": "...",
         "patch": "<unified diff vs the previous version>",
         "content": "<full snapshot of this version>"},
        ...
      ]
    }

The current config is ``versions[-1].content`` (or ``base`` when empty). We keep
a full snapshot *and* the patch for each step on purpose: the patch is the
human-readable audit trail ("what this change did"), while the snapshot makes
assembly and rollback impossible to corrupt — a bad patch can never wedge the
config. A key may also be *materialized* to a file the formatter reads (the
default cpp version → the ``.clang-format`` file, python → ``ruff.toml``) so the
raw config endpoints keep working and the published config survives a deploy
that resets the git-backed file.
"""

from __future__ import annotations

import difflib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path


KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]*$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConfigStore:
    def __init__(self, history_dir: Path | str):
        self.dir = Path(history_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # keys that mirror their current content to a file the formatter reads
        self._materialize_paths: dict[str, Path] = {}

    # ── persistence ──────────────────────────────────────────────────────────
    def _hist_path(self, key: str) -> Path:
        if KEY_RE.fullmatch(key) is None:
            raise ValueError(f"invalid config key: {key}")
        return self.dir / f"{key}.json"

    def _load(self, key: str) -> dict:
        path = self._hist_path(key)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"base": None, "versions": []}

    def _save(self, key: str, data: dict) -> None:
        self._hist_path(key).write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    # ── materialization ──────────────────────────────────────────────────────
    def set_materialize(self, key: str, path: Path | str) -> None:
        """Mirror this key's current content into `path` on every change."""
        self._materialize_paths[key] = Path(path)

    def _materialize(self, key: str) -> None:
        path = self._materialize_paths.get(key)
        if path is not None:
            path.write_text(self.current(key), encoding="utf-8")

    def materialize(self, key: str) -> None:
        """Public re-materialize (call on startup so a deploy that reset the
        git-backed file gets the stored current config written back)."""
        self._materialize(key)

    # ── seeding / migration ──────────────────────────────────────────────────
    def exists(self, key: str) -> bool:
        return self._load(key).get("base") is not None

    def ensure_seeded(
        self, key: str, *, seed_text: str | None = None, seed_from_key: str | None = None
    ) -> bool:
        """Create the history for `key` if it has none yet. Seed its base from
        explicit `seed_text`, else from the current content of `seed_from_key`
        (a one-time independent copy). Returns True if it was newly seeded."""
        with self._lock:
            data = self._load(key)
            if data.get("base") is not None:
                return False
            if seed_text is not None:
                base = seed_text
            elif seed_from_key is not None:
                base = self.current(seed_from_key)
            else:
                base = ""
            data["base"] = base
            self._save(key, data)
        self._materialize(key)
        return True

    def drop(self, key: str) -> bool:
        """Delete a key's whole history (used when a shadow config is removed).
        Returns True if a history file existed and was deleted."""
        with self._lock:
            self._materialize_paths.pop(key, None)
            path = self._hist_path(key)
            if path.exists():
                path.unlink()
                return True
        return False

    def migrate(self, old_key: str, new_key: str) -> bool:
        """Move a key's history to a new name if the old exists and the new
        doesn't (used to retro-key the single `cpp` config to the default
        version). Keeps the old file as a backup."""
        with self._lock:
            old, new = self._hist_path(old_key), self._hist_path(new_key)
            if old.exists() and not new.exists():
                new.write_text(old.read_text(encoding="utf-8"), encoding="utf-8")
                return True
        return False

    # ── reads ────────────────────────────────────────────────────────────────
    def current(self, key: str) -> str:
        data = self._load(key)
        versions = data.get("versions") or []
        return versions[-1]["content"] if versions else (data.get("base") or "")

    def head_seq(self, key: str) -> int:
        return len(self._load(key).get("versions") or [])

    def history(self, key: str) -> list[dict]:
        """Version metadata + patch, newest last. Omits the full snapshot to keep
        the listing light (fetch a version's content with ``get_version``)."""
        data = self._load(key)
        out = [
            {
                "seq": 0,
                "ts": None,
                "author": "",
                "message": "base (original config)",
                "patch": "",
            }
        ]
        for entry in data.get("versions") or []:
            out.append({k: v for k, v in entry.items() if k != "content"})
        return out

    def get_version(self, key: str, seq: int) -> str | None:
        data = self._load(key)
        if seq == 0:
            return data.get("base")
        for entry in data.get("versions") or []:
            if entry["seq"] == seq:
                return entry["content"]
        return None

    # ── writes ───────────────────────────────────────────────────────────────
    def record(self, key: str, content: str, author: str = "", message: str = "") -> dict:
        """Append a new version. No-op (returns ``unchanged``) if the content
        matches the current config, so re-publishing an identical config doesn't
        litter the history."""
        with self._lock:
            data = self._load(key)
            prev = self.current(key)
            seq = len(data.get("versions") or [])
            if content == prev:
                return {"unchanged": True, "seq": seq}
            patch = "".join(
                difflib.unified_diff(
                    prev.splitlines(keepends=True),
                    content.splitlines(keepends=True),
                    fromfile=f"{key}@v{seq}",
                    tofile=f"{key}@v{seq + 1}",
                )
            )
            entry = {
                "seq": seq + 1,
                "ts": _now(),
                "author": author or "",
                "message": message or "",
                "patch": patch,
                "content": content,
            }
            data.setdefault("versions", []).append(entry)
            self._save(key, data)
            self._materialize(key)
            return {k: v for k, v in entry.items() if k != "content"}

    def rollback(self, key: str, seq: int, author: str = "", message: str = "") -> dict | None:
        """Roll back to version ``seq`` by recording its content as a new version
        (history is append-only — the rollback itself is auditable and reversible)."""
        target = self.get_version(key, seq)
        if target is None:
            return None
        return self.record(
            key, target, author=author or "rollback",
            message=message or f"rollback to v{seq}",
        )
