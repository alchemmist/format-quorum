"""Formatter invocation: clang-format (C++) and ruff (Python).

Both formatters read the source from stdin and write the formatted result to
stdout, so we never touch the filesystem for user code.
"""

from __future__ import annotations

import os
import subprocess
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


def format_cpp(code: str, clang_format_bin: str | None = None) -> str:
    """Format C++ source with clang-format using the house style config.

    `clang_format_bin` lets callers pick a specific clang-format version
    (used by the version-management feature); defaults to the base binary.
    """
    binary = clang_format_bin or CLANG_FORMAT_BIN
    return _run(
        [
            binary,
            # Older clang-format versions error on config keys they don't know
            # yet; downgrade those to warnings so one config works across
            # versions.
            "--Wno-error=unknown",
            "--assume-filename=input.cpp",
            f"--style=file:{CLANG_FORMAT_CONFIG}",
        ],
        code,
    )


def format_python(code: str) -> str:
    """Format Python source with `ruff format` using the house style config."""
    return _run(
        [RUFF_BIN, "format", "--config", RUFF_CONFIG, "-"],
        code,
    )


def format_code(code: str, language: str, clang_format_bin: str | None = None) -> str:
    if language == "python":
        return format_python(code)
    return format_cpp(code, clang_format_bin=clang_format_bin)
