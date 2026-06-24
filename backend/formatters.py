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


def format_python(code: str, config: str | None = None) -> str:
    """Format Python source with `ruff format` using the house style config."""
    with _config_file(config, RUFF_CONFIG, ".toml") as cfg:
        return _run([RUFF_BIN, "format", "--config", cfg, "-"], code)


def format_code(
    code: str,
    language: str,
    clang_format_bin: str | None = None,
    config: str | None = None,
) -> str:
    if language == "python":
        return format_python(code, config=config)
    return format_cpp(code, clang_format_bin=clang_format_bin, config=config)
