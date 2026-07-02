"""Persistence for user-defined (custom) formatters.

A custom formatter is a formatter the user created by uploading a binary — it's
not in the code-defined registry, so its *definition* (id, label, language, and
the built-in formatter whose run/config semantics it borrows) is stored here and
re-registered on startup. Its binaries (versions) and config live in the normal
versions/config stores, keyed by its id like any other formatter.

Stored as one JSON file on the config-history volume so definitions survive a
deploy (like shadow configs).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path


class CustomFormatterStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._items: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._items = {d["id"]: d for d in data}
            except Exception:  # noqa: BLE001 - a corrupt file shouldn't kill startup
                self._items = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(list(self._items.values()), indent=2), encoding="utf-8"
        )

    def list(self) -> list[dict]:
        return list(self._items.values())

    def get(self, formatter_id: str) -> dict | None:
        return self._items.get(formatter_id)

    def upsert(self, formatter_id: str, label: str, language: str, base: str) -> dict:
        with self._lock:
            item = {"id": formatter_id, "label": label, "language": language, "base": base}
            self._items[formatter_id] = item
            self._save()
            return item

    def delete(self, formatter_id: str) -> bool:
        with self._lock:
            if formatter_id not in self._items:
                return False
            del self._items[formatter_id]
            self._save()
            return True
