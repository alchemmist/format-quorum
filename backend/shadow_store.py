"""Registry of *shadow configs*.

A shadow config is a named, alternative ``.clang-format`` that reuses an already
installed clang-format *binary* (its ``base`` version) but carries its own
config. It shows up in the UI as a pseudo-version ("👻 name") so you can run it
and put it in the version matrix right next to the real versions — the point is
to compare the same clang-format binary under two different configs.

This store only keeps the shadow's *identity* (``id`` → ``base``, ``name``). The
shadow's config text lives in the :class:`ConfigStore` under the key
``cpp@<id>``, exactly like a real version's config — so a shadow gets the same
history / rollback / impact machinery for free. ``main.py`` owns the key scheme.

Persisted as one JSON list in the config-history dir (the ``config_data`` volume
in Docker), so published shadows survive deploys::

    [{"id": "shadow-1719…", "base": "22.1.8", "name": "no-align"}, ...]
"""

from __future__ import annotations

import json
import threading
from pathlib import Path


class ShadowStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _load(self) -> list[dict]:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
            except (json.JSONDecodeError, OSError):
                pass
        return []

    def _save(self, items: list[dict]) -> None:
        self.path.write_text(
            json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    # ── reads ────────────────────────────────────────────────────────────────
    def list(self) -> list[dict]:
        return self._load()

    def get(self, shadow_id: str | None) -> dict | None:
        if not shadow_id:
            return None
        return next((s for s in self._load() if s["id"] == shadow_id), None)

    def is_shadow(self, version: str | None) -> bool:
        return self.get(version) is not None

    # ── writes ───────────────────────────────────────────────────────────────
    def create(
        self, shadow_id: str, base: str, name: str, formatter: str = "clang-format"
    ) -> dict:
        """Register (or update) a shadow's identity. Idempotent on ``id``."""
        entry = {"id": shadow_id, "base": base, "name": name, "formatter": formatter}
        with self._lock:
            items = self._load()
            existing = next((s for s in items if s["id"] == shadow_id), None)
            if existing is not None:
                existing.update(entry)
            else:
                items.append(entry)
            self._save(items)
        return entry

    def delete(self, shadow_id: str) -> bool:
        with self._lock:
            items = self._load()
            kept = [s for s in items if s["id"] != shadow_id]
            if len(kept) == len(items):
                return False
            self._save(kept)
        return True
