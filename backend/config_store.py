"""Versioned storage for the formatter configs.

A formatter config is no longer just a file that ``PUT`` overwrites: every
published change is appended to a per-language history so a good, working config
can't be *permanently* broken — anyone can still change it, but we can always
roll back.

Storage model (one JSON file per language in a persistent dir):

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
config. The current config is also *materialized* to the file the formatter
reads, so formatting and the raw ``/clang-format`` endpoint keep working
unchanged, and it is re-materialized on startup so the published config survives
a deploy that resets the git-backed file.
"""

from __future__ import annotations

import difflib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConfigStore:
    def __init__(self, history_dir: Path | str, config_paths: dict[str, str]):
        # config_paths: language -> path of the file the formatter actually reads
        # (the "materialized current").
        self.dir = Path(history_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.config_paths = {k: Path(v) for k, v in config_paths.items()}
        self._lock = threading.Lock()
        for lang in self.config_paths:
            self._ensure_base(lang)
            self._materialize(lang)

    # ── persistence ──────────────────────────────────────────────────────────
    def _hist_path(self, lang: str) -> Path:
        return self.dir / f"{lang}.json"

    def _load(self, lang: str) -> dict:
        path = self._hist_path(lang)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"base": None, "versions": []}

    def _save(self, lang: str, data: dict) -> None:
        self._hist_path(lang).write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def _ensure_base(self, lang: str) -> None:
        data = self._load(lang)
        if data.get("base") is None:
            # Seed the base from the config file shipped in the image / repo.
            data["base"] = self.config_paths[lang].read_text(encoding="utf-8")
            self._save(lang, data)

    def _materialize(self, lang: str) -> None:
        self.config_paths[lang].write_text(self.current(lang), encoding="utf-8")

    # ── reads ────────────────────────────────────────────────────────────────
    def current(self, lang: str) -> str:
        data = self._load(lang)
        versions = data.get("versions") or []
        return versions[-1]["content"] if versions else data.get("base", "")

    def head_seq(self, lang: str) -> int:
        return len(self._load(lang).get("versions") or [])

    def history(self, lang: str) -> list[dict]:
        """Version metadata + patch, newest last. Omits the full snapshot to keep
        the listing light (fetch a version's content with ``get_version``)."""
        data = self._load(lang)
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

    def get_version(self, lang: str, seq: int) -> str | None:
        data = self._load(lang)
        if seq == 0:
            return data.get("base")
        for entry in data.get("versions") or []:
            if entry["seq"] == seq:
                return entry["content"]
        return None

    # ── writes ───────────────────────────────────────────────────────────────
    def record(self, lang: str, content: str, author: str = "", message: str = "") -> dict:
        """Append a new version. No-op (returns ``unchanged``) if the content
        matches the current config, so re-publishing an identical config doesn't
        litter the history."""
        with self._lock:
            data = self._load(lang)
            prev = self.current(lang)
            seq = len(data.get("versions") or [])
            if content == prev:
                return {"unchanged": True, "seq": seq}
            patch = "".join(
                difflib.unified_diff(
                    prev.splitlines(keepends=True),
                    content.splitlines(keepends=True),
                    fromfile=f"{lang}@v{seq}",
                    tofile=f"{lang}@v{seq + 1}",
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
            self._save(lang, data)
            self._materialize(lang)
            return {k: v for k, v in entry.items() if k != "content"}

    def rollback(self, lang: str, seq: int, author: str = "", message: str = "") -> dict | None:
        """Roll back to version ``seq`` by recording its content as a new version
        (history is append-only — the rollback itself is auditable and reversible)."""
        target = self.get_version(lang, seq)
        if target is None:
            return None
        return self.record(
            lang, target, author=author or "rollback",
            message=message or f"rollback to v{seq}",
        )
