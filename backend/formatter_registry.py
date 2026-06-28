"""The formatter plugin registry.

format-quorum's primitive is a **formatter**, not a language. A language (the
code's syntax, e.g. ``cpp``/``python``) can have many formatters (python: ruff,
black, yapf…); versioning, the matrix and shadow configs are per-*formatter*
capabilities, not a cpp quirk.

Each formatter is described by a :class:`Formatter`. Everything else (config
keys, version managers, the API) keys off ``formatter.id``. Adding a new
formatter is a single ``_register(...)`` entry here (+ installing its binary).

Legacy callers still pass a *language* (``cpp``/``python``); :func:`resolve`
maps those to the default formatter for that language so the old API keeps
working.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import formatters as _fmt


@dataclass(frozen=True)
class InstallStrategy:
    """How to install a specific version of a formatter into an isolated venv."""

    pypi_name: str  # the PyPI package that ships the binary (pip install pypi_name==X)
    binary_name: str  # the executable inside the venv's bin/


@dataclass(frozen=True)
class ConfigSpec:
    """A formatter's config file: how the UI labels it and where it's seeded."""

    filename: str  # display name, e.g. ".clang-format" / "ruff.toml"
    syntax: str  # "yaml" | "toml" | "json" | "ini" | "none" (for the editor)
    seed_path: str  # the repo seed file; also the materialize target for the default


@dataclass(frozen=True)
class Formatter:
    id: str  # stable id used in keys & the API, e.g. "clang-format", "ruff"
    label: str  # human label
    language: str  # the code language it formats (for editor highlighting)
    default: bool  # the default formatter for its language (alias target)
    config: ConfigSpec | None  # None = the formatter takes no config (e.g. gofmt)
    # run(code, config_text_or_None, binary_or_None) -> formatted text
    run: Callable[[str, str | None, str | None], str]
    versioned: bool = False  # supports the version axis (matrix, shadows, versions)
    install: InstallStrategy | None = None  # how to install versions (None = not installable)
    known_versions: tuple[str, ...] = ()  # quick-add suggestions
    patchable: bool = False  # top-level key patch (whatif/--set) applies to its config


# ── built-in formatters ───────────────────────────────────────────────────────
def _run_clang_format(code: str, config: str | None, binary: str | None) -> str:
    return _fmt.format_cpp(code, clang_format_bin=binary, config=config)


def _run_ruff(code: str, config: str | None, binary: str | None) -> str:
    # ruff is a single binary here; `binary` is unused (no version axis yet)
    return _fmt.format_python(code, config=config)


def _run_black(code: str, config: str | None, binary: str | None) -> str:
    return _fmt.format_black(code, config=config)


# latest patch per major; any valid X.Y.Z can still be added by hand
_CLANG_KNOWN = (
    "14.0.6", "15.0.7", "16.0.6", "17.0.6", "18.1.8",
    "19.1.7", "20.1.8", "21.1.8", "22.1.5",
)

FORMATTERS: dict[str, Formatter] = {}


def _register(f: Formatter) -> None:
    FORMATTERS[f.id] = f


_register(
    Formatter(
        id="clang-format",
        label="clang-format",
        language="cpp",
        default=True,
        config=ConfigSpec(".clang-format", "yaml", _fmt.CLANG_FORMAT_CONFIG),
        run=_run_clang_format,
        versioned=True,
        install=InstallStrategy("clang-format", "clang-format"),
        known_versions=_CLANG_KNOWN,
        patchable=True,
    )
)
_register(
    Formatter(
        id="ruff",
        label="ruff format",
        language="python",
        default=True,
        config=ConfigSpec("ruff.toml", "toml", _fmt.RUFF_CONFIG),
        run=_run_ruff,
        versioned=False,
        patchable=False,
    )
)
_register(
    Formatter(
        id="black",
        label="black",
        language="python",
        default=False,
        config=ConfigSpec("black.toml", "toml", _fmt.BLACK_CONFIG),
        run=_run_black,
        versioned=False,
        patchable=False,
    )
)

# legacy language name → default formatter id (keeps the old API working)
_LANG_ALIAS = {f.language: f.id for f in FORMATTERS.values() if f.default}


# ── lookups ───────────────────────────────────────────────────────────────────
def get(formatter_id: str | None) -> Formatter | None:
    return FORMATTERS.get(formatter_id) if formatter_id else None


def default_for_language(language: str | None) -> Formatter | None:
    fid = _LANG_ALIAS.get(language or "")
    return FORMATTERS.get(fid) if fid else None


def for_language(language: str) -> list[Formatter]:
    return [f for f in FORMATTERS.values() if f.language == language]


def resolve(key: str | None) -> Formatter | None:
    """Accept a formatter id OR a legacy language name; return its Formatter."""
    if not key:
        return None
    if key in FORMATTERS:
        return FORMATTERS[key]
    return default_for_language(key)


def languages() -> set[str]:
    return {f.language for f in FORMATTERS.values()}


def public_list() -> list[dict]:
    """Serializable registry for the frontend (`GET /api/formatters`)."""
    return [
        {
            "id": f.id,
            "label": f.label,
            "language": f.language,
            "default": f.default,
            "versioned": f.versioned,
            "patchable": f.patchable,
            "config": (
                {"filename": f.config.filename, "syntax": f.config.syntax}
                if f.config
                else None
            ),
        }
        for f in FORMATTERS.values()
    ]
