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
from versions import (
    InstallStrategy,
    JarInstall,
    NpmInstall,
    PipInstall,
    UrlBinaryInstall,
)


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
    # how to install/locate versions (None = not installable). Any InstallStrategy
    # subclass — PipInstall today; npm/go/binary-download strategies later.
    install: InstallStrategy | None = None
    known_versions: tuple[str, ...] = ()  # quick-add suggestions
    patchable: bool = False  # top-level key patch (whatif/--set) applies to its config
    # optional one-liner shown behind a "?" in the UI — what this formatter
    # actually does (e.g. ruff runs check --fix then format)
    description: str = ""


# ── built-in formatters ───────────────────────────────────────────────────────
def _run_clang_format(code: str, config: str | None, binary: str | None) -> str:
    return _fmt.format_cpp(code, clang_format_bin=binary, config=config)


def _run_ruff(code: str, config: str | None, binary: str | None) -> str:
    return _fmt.format_python(code, config=config, binary=binary)


def _run_black(code: str, config: str | None, binary: str | None) -> str:
    return _fmt.format_black(code, config=config, binary=binary)


# Quick-add version suggestions per formatter (latest patch of recent releases;
# any valid X.Y.Z can still be added by hand). Each is probed against PyPI for an
# installable wheel before it's offered, so an unavailable one is dropped.
_CLANG_KNOWN = (
    "14.0.6", "15.0.7", "16.0.6", "17.0.6", "18.1.8",
    "19.1.7", "20.1.8", "21.1.8", "22.1.5",
)
# ruff ships a binary wheel per release (X.Y.Z); a spread of recent minors
_RUFF_KNOWN = (
    "0.6.9", "0.7.4", "0.8.6", "0.9.10", "0.11.13", "0.12.7",
)
# black uses calendar versioning (YY.M.patch); a spread of recent stable releases
_BLACK_KNOWN = (
    "24.4.2", "24.8.0", "24.10.0", "25.1.0",
    "25.9.0", "25.12.0", "26.1.0", "26.3.1", "26.5.0",
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
        install=PipInstall("clang-format", "clang-format", base_binary=_fmt.CLANG_FORMAT_BIN),
        known_versions=_CLANG_KNOWN,
        patchable=True,
    )
)
_register(
    Formatter(
        id="ruff",
        label="ruff",
        language="python",
        default=True,
        config=ConfigSpec("ruff.toml", "toml", _fmt.RUFF_CONFIG),
        run=_run_ruff,
        versioned=True,
        install=PipInstall("ruff", "ruff", base_binary=_fmt.RUFF_BIN),
        known_versions=_RUFF_KNOWN,
        patchable=False,
        description=(
            "Runs the full ruff pass: `ruff check --fix` (safe lint autofixes — "
            "e.g. removing unused imports) followed by `ruff format` (layout). "
            "Both use the ruff.toml config."
        ),
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
        versioned=True,
        install=PipInstall("black", "black", base_binary=_fmt.BLACK_BIN),
        known_versions=_BLACK_KNOWN,
        patchable=False,
    )
)

# ── classic-language formatters ───────────────────────────────────────────────
# Each is that language's default. Those with a pluggable install strategy carry
# a full version axis (install arbitrary versions, pick one to format with, see
# them in the matrix); per-version *configs* are still a follow-up (issue #2).
# gofmt and rustfmt stay unversioned: gofmt has no standalone version (it tracks
# the Go release and has no --version), and rustfmt ships only inside a full Rust
# toolchain — neither offers per-version binaries to install.

# quick-add version suggestions (probed for real availability before being shown)
_PRETTIER_KNOWN = ("3.0.3", "3.1.1", "3.2.5", "3.3.3", "3.4.2", "3.5.3", "3.6.2")
_TAPLO_KNOWN = ("0.4.1", "0.5.2", "0.6.0", "0.7.0")
_SHFMT_KNOWN = ("3.7.0", "3.8.0", "3.9.0", "3.10.0", "3.11.0", "3.12.0", "3.13.1")
_GJF_KNOWN = ("1.19.2", "1.21.0", "1.22.0", "1.23.0", "1.24.0", "1.25.0", "1.25.2")

# google-java-format needs the compiler internals opened on JDK 16+ (mirrors the
# image wrapper) so an installed version runs the same way the base one does.
_GJF_JAVA_ARGS = tuple(
    f"--add-exports jdk.compiler/com.sun.tools.javac.{m}=ALL-UNNAMED"
    for m in ("api", "file", "parser", "tree", "util")
)
_SHFMT_URL = "https://github.com/mvdan/sh/releases/download/v{version}/shfmt_v{version}_linux_{arch}"
_GJF_URL = (
    "https://github.com/google/google-java-format/releases/download/"
    "v{version}/google-java-format-{version}-all-deps.jar"
)

# prettier's 7 language entries share one npm install strategy (same package)
_prettier_strategy = NpmInstall("prettier", "prettier", base_binary=_fmt.PRETTIER_BIN)

# prettier backs several languages from one binary; registered once per language
# (distinct id, all labelled "prettier"), each passing its parser extension. They
# share one npm install strategy (the same prettier package).
_PRETTIER_LANGS = [
    ("prettier-js", "javascript", "js"),
    ("prettier-ts", "typescript", "ts"),
    ("prettier-json", "json", "json"),
    ("prettier-css", "css", "css"),
    ("prettier-html", "html", "html"),
    ("prettier-md", "markdown", "md"),
    ("prettier-yaml", "yaml", "yaml"),
]
for _pid, _plang, _pext in _PRETTIER_LANGS:
    _register(
        Formatter(
            id=_pid, label="prettier", language=_plang, default=True,
            config=None, run=_fmt.make_prettier(_pext),
            versioned=True, install=_prettier_strategy, known_versions=_PRETTIER_KNOWN,
        )
    )

# (id, label, language, run, install-or-None, known_versions)
_CLASSIC = [
    ("gofmt", "gofmt", "go", _fmt.format_go, None, ()),
    ("rustfmt", "rustfmt", "rust", _fmt.format_rust, None, ()),
    ("shfmt", "shfmt", "shell", _fmt.format_shell,
     UrlBinaryInstall(_SHFMT_URL, "shfmt", base_binary=_fmt.SHFMT_BIN), _SHFMT_KNOWN),
    ("taplo", "taplo", "toml", _fmt.format_toml,
     NpmInstall("@taplo/cli", "taplo", base_binary=_fmt.TAPLO_BIN), _TAPLO_KNOWN),
    ("google-java-format", "google-java-format", "java", _fmt.format_java,
     JarInstall(_GJF_URL, "google-java-format", base_binary=_fmt.GJF_BIN,
                java_args=_GJF_JAVA_ARGS), _GJF_KNOWN),
]
for _fid, _flabel, _flang, _frun, _finstall, _fknown in _CLASSIC:
    _register(
        Formatter(id=_fid, label=_flabel, language=_flang, default=True,
                  config=None, run=_frun, versioned=bool(_finstall),
                  install=_finstall, known_versions=_fknown)
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
            "description": f.description,
            "config": (
                {"filename": f.config.filename, "syntax": f.config.syntax}
                if f.config
                else None
            ),
        }
        for f in FORMATTERS.values()
    ]
