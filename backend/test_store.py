"""Storage and execution for the formatting test suite.

Each test is a BEFORE/AFTER case stored as one JSON file under
``<base>/<language>/<id>.json`` so the suite is git-friendly. A run formats the
``input`` with the current config and compares against the author-written
``expected`` output. See docs/test-system-design.md.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import formatter_registry as registry
from formatters import FormatError, format_code
from persistence import atomic_write_json

# the code languages we accept, derived from the registered formatters
LANGUAGES = registry.languages()
_FIELDS = ("name", "language", "input", "expected", "muted", "note")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(text: str) -> str:
    """Compare leniently only on the trailing newline / line endings."""
    return text.replace("\r\n", "\n").rstrip("\n")


class TestStore:
    def __init__(self, base_dir: Path | str):
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, language: str, test_id: str) -> Path:
        return self.base / language / f"{test_id}.json"

    def list(self) -> list[dict]:
        records: list[dict] = []
        for lang in sorted(LANGUAGES):
            lang_dir = self.base / lang
            if not lang_dir.is_dir():
                continue
            for f in lang_dir.glob("*.json"):
                try:
                    records.append(json.loads(f.read_text(encoding="utf-8")))
                except (json.JSONDecodeError, OSError):
                    continue
        records.sort(key=lambda r: (r.get("language", ""), r.get("name", "")))
        return records

    def get(self, test_id: str) -> dict | None:
        return next((t for t in self.list() if t["id"] == test_id), None)

    def _write(self, rec: dict) -> None:
        path = self._path(rec["language"], rec["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, rec)

    def create(self, data: dict) -> dict:
        language = data.get("language", "cpp")
        if language not in LANGUAGES:
            raise ValueError(f"invalid language: {language}")
        rec = {
            "id": uuid.uuid4().hex[:12],
            "name": (data.get("name") or "untitled").strip(),
            "language": language,
            "input": data.get("input", ""),
            "expected": data.get("expected", ""),
            "muted": bool(data.get("muted", False)),
            "note": data.get("note", ""),
            "created_at": _now(),
        }
        self._write(rec)
        return rec

    def update(self, test_id: str, data: dict) -> dict | None:
        rec = self.get(test_id)
        if rec is None:
            return None
        old_language = rec["language"]
        for key in _FIELDS:
            if data.get(key) is not None:
                rec[key] = data[key]
        if rec["language"] not in LANGUAGES:
            raise ValueError(f"invalid language: {rec['language']}")
        rec["muted"] = bool(rec["muted"])
        if rec["language"] != old_language:
            self._path(old_language, test_id).unlink(missing_ok=True)
        self._write(rec)
        return rec

    def delete(self, test_id: str) -> bool:
        rec = self.get(test_id)
        if rec is None:
            return False
        self._path(rec["language"], test_id).unlink(missing_ok=True)
        return True


def run_test(
    rec: dict,
    formatter: str | None = None,
    binary: str | None = None,
    config: str | None = None,
) -> dict:
    """Format a test's input with `formatter` (default: the default formatter for
    the test's language) and compare to its expected output. `binary`/`config`
    are only applied when the formatter matches the test's language (so a clang
    binary/config never leaks into a python test on a mixed run)."""
    lang = rec["language"]
    fmt = registry.resolve(formatter) if formatter else registry.default_for_language(lang)
    error: str | None = None
    try:
        if fmt is None:
            raise FormatError(f"no formatter for language: {lang}")
        if fmt.language != lang:
            raise FormatError(f"formatter {fmt.id} does not support {lang}")
        actual = format_code(rec["input"], fmt.id, binary=binary, config=config)
    except FormatError as exc:
        actual = ""
        error = str(exc)

    passed = error is None and _normalize(actual) == _normalize(rec["expected"])
    if rec["muted"]:
        status = "muted"
    else:
        status = "pass" if passed else "fail"

    return {
        "id": rec["id"],
        "name": rec["name"],
        "language": rec["language"],
        "muted": rec["muted"],
        "note": rec.get("note", ""),
        "input": rec["input"],
        "expected": rec["expected"],
        "actual": actual,
        "passed": passed,
        "status": status,
        "error": error,
    }


def run_all(
    store: TestStore,
    language: str | None = None,
    formatter: str | None = None,
    binary: str | None = None,
    config: str | None = None,
) -> dict:
    results = [
        run_test(t, formatter=formatter, binary=binary, config=config)
        for t in store.list()
        if language is None or t["language"] == language
    ]
    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r["status"] == "pass"),
        "failed": sum(1 for r in results if r["status"] == "fail"),
        "muted": sum(1 for r in results if r["status"] == "muted"),
    }
    return {"results": results, "summary": summary}
