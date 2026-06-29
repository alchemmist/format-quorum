"""Formatter invocation: clang-format (C++) and ruff (Python).

Both formatters read the source from stdin and write the formatted result to
stdout, so we never touch the filesystem for user code.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
CONFIGS_DIR = BACKEND_DIR / "configs"

# Binary paths and config locations — overridable via env for Docker / CI.
CLANG_FORMAT_BIN = os.environ.get("CLANG_FORMAT_BIN", "clang-format")
CLANG_FORMAT_CONFIG = os.environ.get(
    "CLANG_FORMAT_CONFIG", str(CONFIGS_DIR / "clang-format")
)

RUFF_BIN = os.environ.get("RUFF_BIN", "ruff")
RUFF_CONFIG = os.environ.get("RUFF_CONFIG", str(CONFIGS_DIR / "ruff.toml"))

BLACK_BIN = os.environ.get("BLACK_BIN", "black")
BLACK_CONFIG = os.environ.get("BLACK_CONFIG", str(CONFIGS_DIR / "black.toml"))

# Classic-language formatters, run from the image's toolchains. Binary paths are
# overridable via env.
GOFMT_BIN = os.environ.get("GOFMT_BIN", "gofmt")
RUSTFMT_BIN = os.environ.get("RUSTFMT_BIN", "rustfmt")
PRETTIER_BIN = os.environ.get("PRETTIER_BIN", "prettier")
SHFMT_BIN = os.environ.get("SHFMT_BIN", "shfmt")
TAPLO_BIN = os.environ.get("TAPLO_BIN", "taplo")
GJF_BIN = os.environ.get("GJF_BIN", "google-java-format")

# config files for the formatters that read one (gofmt, shfmt and
# google-java-format are config-less by design, so they have none)
PRETTIER_CONFIG = os.environ.get("PRETTIER_CONFIG", str(CONFIGS_DIR / "prettierrc"))
RUSTFMT_CONFIG = os.environ.get("RUSTFMT_CONFIG", str(CONFIGS_DIR / "rustfmt.toml"))
TAPLO_CONFIG = os.environ.get("TAPLO_CONFIG", str(CONFIGS_DIR / "taplo.toml"))

# A formatter that hangs would block a worker thread forever.
FORMAT_TIMEOUT_SEC = 30


class FormatError(Exception):
    """Raised when a formatter exits non-zero or cannot be run."""


def _run(argv: list[str], code: str) -> str:
    try:
        proc = subprocess.run(
            argv,
            input=code,
            capture_output=True,
            text=True,
            timeout=FORMAT_TIMEOUT_SEC,
        )
    except FileNotFoundError as exc:
        raise FormatError(f"binary not found: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise FormatError(f"formatter timed out after {FORMAT_TIMEOUT_SEC}s") from exc

    if proc.returncode != 0:
        raise FormatError(proc.stderr.strip() or f"exit code {proc.returncode}")
    return proc.stdout


def apply_config_patch(base: str, patch: dict) -> str:
    """Apply top-level clang-format key overrides to a YAML config string.

    Existing top-level ``key:`` lines are replaced in place; unknown keys are
    appended at the end. Nested keys are not addressed (pass a full ``config``
    for those). Mirrors the tuning bench's own merge so a "config patch → which
    tests flip" hypothesis can be checked server-side.
    """
    def _fmt(value) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    remaining = {k: _fmt(v) for k, v in patch.items()}
    out: list[str] = []
    for line in base.split("\n"):
        stripped = line.strip()
        hit = next(
            (
                k
                for k in remaining
                if stripped.startswith(k + ":") and not line.startswith((" ", "\t"))
            ),
            None,
        )
        out.append(f"{hit}: {remaining.pop(hit)}" if hit is not None else line)
    out += [f"{k}: {v}" for k, v in remaining.items()]
    return "\n".join(out)


@contextmanager
def _config_file(config: str | None, default_path: str, suffix: str):
    """Yield a style/config file path. If `config` text is given, write it to a
    temp file (used by the tuning bench to try ad-hoc configs without touching
    the stored one); otherwise use the stored config path."""
    if config is None:
        yield default_path
        return
    tmp = tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, encoding="utf-8")
    try:
        tmp.write(config)
        tmp.close()
        yield tmp.name
    finally:
        os.unlink(tmp.name)


def format_cpp(
    code: str, clang_format_bin: str | None = None, config: str | None = None
) -> str:
    """Format C++ source with clang-format using the house style config.

    `clang_format_bin` lets callers pick a specific clang-format version
    (used by the version-management feature); defaults to the base binary.
    `config` lets callers pass ad-hoc style YAML to try without overwriting the
    stored config; defaults to the stored config file.
    """
    binary = clang_format_bin or CLANG_FORMAT_BIN
    with _config_file(config, CLANG_FORMAT_CONFIG, ".clang-format") as style:
        return _run(
            [
                binary,
                # Older clang-format versions error on config keys they don't know
                # yet; downgrade those to warnings so one config works across
                # versions.
                "--Wno-error=unknown",
                "--assume-filename=input.cpp",
                f"--style=file:{style}",
            ],
            code,
        )


def format_python(code: str, config: str | None = None, binary: str | None = None) -> str:
    """Run the full ruff pass on Python source: lint autofixes then formatting.

    This is what `ruff` does in practice: ``ruff check --fix`` applies safe lint
    fixes (e.g. removing unused imports, rewriting comprehensions), then
    ``ruff format`` lays the code out. Both use the house style config.

    `binary` lets callers pick a specific installed ruff version (the
    version-management feature); defaults to the base ruff on PATH.
    """
    ruff = binary or RUFF_BIN
    with _config_file(config, RUFF_CONFIG, ".toml") as cfg:
        # 1) lint autofix — reads stdin, writes the fixed source to stdout
        fixed = _run([ruff, "check", "--fix-only", "--config", cfg, "-"], code)
        # 2) format the fixed source
        return _run([ruff, "format", "--config", cfg, "-"], fixed)


def format_black(code: str, config: str | None = None, binary: str | None = None) -> str:
    """Format Python source with `black` using a pyproject-style config.

    `binary` lets callers pick a specific installed black version; defaults to
    the base black on PATH.
    """
    with _config_file(config, BLACK_CONFIG, ".toml") as cfg:
        return _run([binary or BLACK_BIN, "-q", "--config", cfg, "-"], code)


# ── classic-language formatters (stdin → stdout, canonical defaults) ───────────
def format_go(code: str, config: str | None = None, binary: str | None = None) -> str:
    """Format Go with gofmt. gofmt is opinionated and takes no config."""
    return _run([binary or GOFMT_BIN], code)


def format_rust(code: str, config: str | None = None, binary: str | None = None) -> str:
    """Format Rust with rustfmt. `config` is a rustfmt.toml passed via --config-path
    (the stored config when None); the edition is fixed on the CLI."""
    with _config_file(config, RUSTFMT_CONFIG, ".toml") as cfg:
        return _run(
            [binary or RUSTFMT_BIN, "--emit", "stdout", "--edition", "2021",
             "--config-path", cfg],
            code,
        )


def make_prettier(parser_ext: str):
    """Build a prettier runner for one language. prettier picks its parser from the
    stdin filename, so each language passes the matching extension (ts/css/…).
    `config` is a .prettierrc (JSON) passed via --config."""

    def _format(code: str, config: str | None = None, binary: str | None = None) -> str:
        prettier = binary or PRETTIER_BIN
        tail = ["--stdin-filepath", f"input.{parser_ext}"]
        if config is None:
            return _run([prettier, "--no-config", *tail], code)
        with _config_file(config, PRETTIER_CONFIG, ".json") as cfg:
            return _run([prettier, "--config", cfg, *tail], code)

    return _format


def format_shell(code: str, config: str | None = None, binary: str | None = None) -> str:
    """Format shell scripts with shfmt (reads stdin by default). shfmt is
    flag/.editorconfig driven and takes no config file."""
    return _run([binary or SHFMT_BIN], code)


def format_toml(code: str, config: str | None = None, binary: str | None = None) -> str:
    """Format TOML with taplo. `config` is a taplo.toml passed via --config (the
    stored config when None; --no-auto-config keeps it from finding a stray one)."""
    taplo = binary or TAPLO_BIN
    if config is None:
        return _run([taplo, "fmt", "--no-auto-config", "-"], code)
    with _config_file(config, TAPLO_CONFIG, ".toml") as cfg:
        return _run([taplo, "fmt", "--config", cfg, "-"], code)


def format_java(code: str, config: str | None = None, binary: str | None = None) -> str:
    """Format Java with google-java-format (reads stdin via the `-` arg)."""
    return _run([binary or GJF_BIN, "-"], code)


def format_code(
    code: str,
    target: str,
    binary: str | None = None,
    config: str | None = None,
    clang_format_bin: str | None = None,
) -> str:
    """Format `code` with the formatter `target` (a formatter id like
    ``clang-format``/``ruff`` OR a legacy language ``cpp``/``python``).

    `binary` overrides the formatter binary (a specific installed version);
    `clang_format_bin` is the old name for it, kept for existing callers.
    """
    # imported lazily to avoid a formatters<->registry import cycle
    from formatter_registry import resolve

    fmt = resolve(target)
    if fmt is None:
        raise FormatError(f"unknown formatter/language: {target}")
    return fmt.run(code, config, binary if binary is not None else clang_format_bin)
