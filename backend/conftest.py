"""Test harness for the backend integration suite.

Every test gets a **freshly imported app** rooted at its own temp directories, so
nothing touches the real ``tests/`` suite, the ``config_history`` volume or the
materialized config files — and tests can't leak state into each other.

Isolation is done by (1) pointing every path/binary env var at a temp tree and
(2) re-importing the backend modules from scratch per test. Network is stubbed:
``PipInstall.available`` (the PyPI wheel probe the suggestion thread runs) is
patched to a no-op so the suite is offline and deterministic.
"""

from __future__ import annotations

import importlib
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent
REAL_CONFIGS = BACKEND_DIR / "configs"
VENV_BIN = BACKEND_DIR / ".venv" / "bin"

# backend modules re-imported fresh per test (dependency order doesn't matter for
# popping; importing `main` pulls the rest back in)
_BACKEND_MODULES = (
    "main",
    "formatters",
    "formatter_registry",
    "config_store",
    "shadow_store",
    "test_store",
    "versions",
)


def _resolve_bin(name: str) -> str:
    """Prefer the venv binary, then PATH; fall back to the bare name."""
    venv_bin = VENV_BIN / name
    if venv_bin.exists():
        return str(venv_bin)
    return shutil.which(name) or name


def binary_present(name: str) -> bool:
    """Is a runnable binary for `name` available here? Tests for the classic
    formatters skip when their toolchain isn't installed (CI/Docker have them)."""
    resolved = _resolve_bin(name)
    return Path(resolved).exists() or shutil.which(resolved) is not None


@dataclass
class AppCtx:
    client: "object"  # starlette TestClient
    main: "object"  # the freshly imported main module
    tmp: Path
    configs_dir: Path

    def default_version(self, formatter_id: str) -> str | None:
        """The probed base version of a formatter (its default column/key)."""
        mgr = self.main.version_mgrs.get(formatter_id)
        return mgr.base_version if mgr else None


def _fake_install_fn(strategy):
    """An InstallStrategy.install replacement that 'installs' a version offline by
    symlinking the strategy's expected binary path (pip/npm/url/jar layout differ)
    to the real base binary — so the 'installed version' is a genuinely runnable
    formatter and matrix/format tests are real, with no network or package manager."""
    src = Path(shutil.which(strategy.base_binary) or strategy.base_binary).resolve()

    def _install(version: str, version_dir: Path):  # noqa: ARG001
        dst = strategy.bin_path(Path(version_dir))
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        dst.symlink_to(src)
        return True, None

    return _install


@pytest.fixture
def appctx(tmp_path, monkeypatch):
    """A fresh, fully isolated app + TestClient for one test."""
    # 1) temp tree
    cfg = tmp_path / "configs"
    shutil.copytree(REAL_CONFIGS, cfg)
    (tmp_path / "config_history").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "versions").mkdir()

    # 2) env: every path + binary points into the temp tree / known binaries
    env = {
        "CONFIG_HISTORY_DIR": str(tmp_path / "config_history"),
        "TESTS_DIR": str(tmp_path / "tests"),
        "VERSIONS_DIR": str(tmp_path / "versions"),
        "FRONTEND_DIST": str(tmp_path / "dist"),  # absent → SPA returns 404
        "CLANG_FORMAT_CONFIG": str(cfg / "clang-format"),
        "RUFF_CONFIG": str(cfg / "ruff.toml"),
        "BLACK_CONFIG": str(cfg / "black.toml"),
        "PRETTIER_CONFIG": str(cfg / "prettierrc"),
        "RUSTFMT_CONFIG": str(cfg / "rustfmt.toml"),
        "TAPLO_CONFIG": str(cfg / "taplo.toml"),
        "CLANG_FORMAT_BIN": _resolve_bin("clang-format"),
        "RUFF_BIN": _resolve_bin("ruff"),
        "BLACK_BIN": _resolve_bin("black"),
        # classic-language formatters (skipped in tests when their binary is absent)
        "GOFMT_BIN": _resolve_bin("gofmt"),
        "RUSTFMT_BIN": _resolve_bin("rustfmt"),
        "PRETTIER_BIN": _resolve_bin("prettier"),
        "SHFMT_BIN": _resolve_bin("shfmt"),
        "TAPLO_BIN": _resolve_bin("taplo"),
        "GJF_BIN": _resolve_bin("google-java-format"),
        "PATH": f"{VENV_BIN}{os.pathsep}{os.environ.get('PATH', '')}",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    # 3) fresh import — patch the network probe before `main` builds the managers
    for mod in _BACKEND_MODULES:
        sys.modules.pop(mod, None)
    versions = importlib.import_module("versions")
    for _cls in ("PipInstall", "NpmInstall", "UrlBinaryInstall", "JarInstall"):
        monkeypatch.setattr(getattr(versions, _cls), "available", lambda self, v: True)
    main = importlib.import_module("main")

    from starlette.testclient import TestClient

    with TestClient(main.app) as client:
        yield AppCtx(client=client, main=main, tmp=tmp_path, configs_dir=cfg)

    # leave a clean module table for the next test
    for mod in _BACKEND_MODULES:
        sys.modules.pop(mod, None)


@pytest.fixture
def install_version(appctx):
    """Factory: make ``version`` of ``formatter_id`` 'installed' (offline, by
    copying the base binary) the way the real install path would, both directly
    and through the POST endpoint (its strategy.install is faked)."""

    def _do(formatter_id: str, version: str) -> None:
        mgr = appctx.main.version_mgrs[formatter_id]
        mgr.strategy.install = _fake_install_fn(mgr.strategy)
        ok, err = mgr.add_version(version)
        assert ok, err
        # give it a config like the API would
        key = appctx.main._config_key(formatter_id, version)
        appctx.main.configs.ensure_seeded(
            key, seed_from_key=appctx.main._config_key(formatter_id, None)
        )

    return _do


@pytest.fixture
def enable_fake_install(appctx):
    """Make the POST add-version endpoint install offline (copy the base binary)
    for every versioned formatter, so the real install path is exercised without
    pip or the network."""
    for mgr in appctx.main.version_mgrs.values():
        mgr.strategy.install = _fake_install_fn(mgr.strategy)
    return appctx


# ── tiny sample programs (deterministic across formatter versions) ─────────────
CPP_MESSY = "int main(){int x=1;return x;}\n"
PY_MESSY = "x=1\n"
PY_UNUSED_IMPORT = "import os\nimport sys\n\nx = 1\nprint(sys)\n"


def seed_passing_test(client, language: str, src: str, *, formatter=None, name="t",
                      muted=False):
    """Create a suite test whose ``expected`` is exactly what the current config
    produces, so it's guaranteed to pass — lets run/matrix/whatif assert on real
    pass/fail without hardcoding a formatter's exact output."""
    body = {"code": src, "language": language}
    if formatter:
        body["formatter"] = formatter
    expected = client.post("/api/format", json=body).json()["formatted"]
    rec = client.post(
        "/api/tests",
        json={"name": name, "language": language, "input": src,
              "expected": expected, "muted": muted},
    ).json()
    return rec
