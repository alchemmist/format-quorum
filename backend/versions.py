"""Dynamic formatter version management.

One :class:`VersionManager` per *versioned* formatter (clang-format, ruff,
black…). The user can ask the backend to make an arbitrary version of that
formatter available; the manager keeps each version in its own subdirectory and
tracks which are installed / installing / suggestable.

**How** a version is actually installed is deliberately *not* baked in. A
:class:`VersionManager` delegates that to an :class:`InstallStrategy`:

- :class:`PipInstall` — ``pip install <pypi_name>==X.Y.Z`` into an isolated venv
  (clang-format, ruff, black all happen to ship as pip wheels).

Other formatters won't be pip-installable — a Go formatter via ``go install``, a
Node one via ``npm``, a prebuilt binary fetched from a release page. Each is a
new ``InstallStrategy`` subclass; the manager, the API and the UI are unchanged.
A strategy owns three things: where a version's binary lands, how to install one,
and how to tell (cheaply) whether a given version is installable here.

This ports the capability of the `clang-format-docker` scripts (cfmt.py picking
a version, generate_dockerfile.py probing wheel availability) into the runtime.
"""

from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
import venv
from abc import ABC, abstractmethod
from pathlib import Path

# Strictly three dot-separated numbers, e.g. 22.1.5.
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

INSTALL_TIMEOUT_SEC = 600


# ── install strategies ────────────────────────────────────────────────────────
class InstallStrategy(ABC):
    """How to install and locate a specific version of one formatter.

    A version lives under ``version_dir`` (``<versions_root>/<X.Y.Z>``). The
    strategy decides what goes in there and where the runnable binary ends up.
    ``base_binary`` is the formatter already on PATH (the built-in default
    version); ``--version`` is run against it to learn the default version.
    """

    #: the formatter's default binary (on PATH / from the image)
    base_binary: str

    @abstractmethod
    def installed_binary(self, version_dir: Path) -> Path | None:
        """The runnable binary for a version installed in ``version_dir``, or
        ``None`` if nothing is installed there."""

    @abstractmethod
    def install(self, version: str, version_dir: Path) -> tuple[bool, str | None]:
        """Install ``version`` into the (freshly emptied) ``version_dir``.
        Returns ``(ok, error)``; on failure the manager removes ``version_dir``."""

    @abstractmethod
    def available(self, version: str) -> bool:
        """Cheap pre-check: is ``version`` installable on this platform? Used to
        filter quick-add suggestions. May be a best-effort guess."""


class PipInstall(InstallStrategy):
    """Install a version as a pip wheel into its own virtualenv.

    ``pip install <pypi_name>==X.Y.Z`` — the wheel ships the bundled binary,
    which lands at ``<version_dir>/bin/<binary_name>``. If pip has no installable
    wheel for that exact version / platform, the version simply does not exist.
    """

    def __init__(self, pypi_name: str, binary_name: str, *, base_binary: str | None = None):
        self.pypi_name = pypi_name
        self.binary_name = binary_name
        self.base_binary = base_binary or binary_name

    def installed_binary(self, version_dir: Path) -> Path | None:
        p = version_dir / "bin" / self.binary_name
        return p if p.exists() else None

    def install(self, version: str, version_dir: Path) -> tuple[bool, str | None]:
        try:
            venv.EnvBuilder(with_pip=True).create(version_dir)
            pip = version_dir / "bin" / "pip"
            proc = subprocess.run(
                [str(pip), "install", "--no-cache-dir", f"{self.pypi_name}=={version}"],
                capture_output=True,
                text=True,
                timeout=INSTALL_TIMEOUT_SEC,
            )
            if proc.returncode != 0 or self.installed_binary(version_dir) is None:
                return False, (
                    f"{self.pypi_name} {version} is not available "
                    "(no installable wheel for this version/platform)"
                )
            return True, None
        except subprocess.TimeoutExpired:
            return False, "Installation timed out"
        except Exception as exc:  # noqa: BLE001 - surface any setup failure
            return False, str(exc)

    # ── availability probe (mirrors pip's wheel/platform check) ───────────────
    @staticmethod
    def _wheel_compatible(filename: str) -> bool:
        name = filename.lower()
        if not name.endswith(".whl"):
            return False  # sdist only → no bundled binary we can use
        # a pure-Python wheel (…-none-any.whl) installs on ANY platform and still
        # ships the console script — e.g. black, which has no linux/arm64 compiled
        # wheel but installs fine everywhere via its py3-none-any wheel.
        if name.endswith("-none-any.whl"):
            return True
        machine = platform.machine().lower()
        plat: str = sys.platform
        if plat.startswith("linux"):
            linux_ok = "manylinux" in name or "musllinux" in name
            if machine in ("aarch64", "arm64"):
                return linux_ok and "aarch64" in name
            if machine in ("x86_64", "amd64"):
                return linux_ok and "x86_64" in name
            return linux_ok and machine in name
        if plat == "darwin":
            return "macosx" in name  # universal2 covers both arm64 and x86_64
        if plat.startswith("win"):
            return "win_amd64" in name or "win32" in name
        return True

    def available(self, version: str) -> bool:
        url = f"https://pypi.org/pypi/{self.pypi_name}/{version}/json"
        with urllib.request.urlopen(url, timeout=8) as resp:  # noqa: S310
            data = json.load(resp)
        return any(self._wheel_compatible(u["filename"]) for u in data.get("urls", []))


# ── version manager ───────────────────────────────────────────────────────────
class VersionManager:
    """Manages the installed versions of one formatter via an InstallStrategy."""

    def __init__(
        self,
        versions_dir: Path,
        strategy: InstallStrategy,
        *,
        known_versions: list[str] | None = None,
    ):
        self.dir = Path(versions_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.strategy = strategy
        self.base_version = self._probe(strategy.base_binary)
        self.known_versions = list(known_versions or [])
        self._lock = threading.Lock()
        self._installing: set[str] = set()
        # which known_versions actually look installable here — probed in the
        # background. None until ready; until then state() shows the full list.
        self._suggest_lock = threading.Lock()
        self._installable: set[str] | None = None
        threading.Thread(target=self._warm_suggestions, daemon=True).start()

    # ── probing ──────────────────────────────────────────────────────────────
    @staticmethod
    def _probe(binary: str) -> str | None:
        try:
            out = subprocess.run(
                [binary, "--version"], capture_output=True, text=True, timeout=10
            )
        except Exception:
            return None
        m = re.search(r"(\d+\.\d+\.\d+)", out.stdout)
        return m.group(1) if m else None

    # ── suggestion availability ──────────────────────────────────────────────
    def _warm_suggestions(self) -> None:
        installable: set[str] = set()
        for v in self.known_versions:
            try:
                if self.strategy.available(v):
                    installable.add(v)
            except Exception:  # noqa: BLE001 - probe failure → keep, don't hide
                installable.add(v)
        with self._suggest_lock:
            self._installable = installable

    # ── queries ──────────────────────────────────────────────────────────────
    def _installed(self) -> list[str]:
        found: list[str] = []
        if self.base_version:
            found.append(self.base_version)
        if self.dir.exists():
            for child in sorted(self.dir.iterdir()):
                if child.is_dir() and self.strategy.installed_binary(child):
                    found.append(child.name)
        # de-dupe, preserve order
        seen: set[str] = set()
        return [v for v in found if not (v in seen or seen.add(v))]

    def get_binary(self, version: str | None) -> str | None:
        """Resolve a version string to a binary path, or None."""
        if not version or version == self.base_version:
            return self.strategy.base_binary
        bin_path = self.strategy.installed_binary(self.dir / version)
        return str(bin_path) if bin_path else None

    def state(self) -> dict:
        installed = self._installed()
        with self._lock:
            installing = sorted(self._installing)
        with self._suggest_lock:
            installable = self._installable
        # before the probe finishes, fall back to the full list
        pool = (
            self.known_versions
            if installable is None
            else [v for v in self.known_versions if v in installable]
        )
        suggestions = [v for v in pool if v not in installed]
        return {
            "versions": installed,
            "default": self.base_version,
            "installing": installing,
            "suggestions": suggestions,
        }

    # ── mutations ────────────────────────────────────────────────────────────
    def add_version(self, version: str) -> tuple[bool, str | None]:
        version = version.strip()
        if not VERSION_RE.match(version):
            return False, "Version must be exactly three numbers, e.g. 22.1.5"
        if self.get_binary(version):
            return True, None  # already available

        with self._lock:
            if version in self._installing:
                return False, "This version is already being installed"
            self._installing.add(version)
        try:
            return self._install(version)
        finally:
            with self._lock:
                self._installing.discard(version)

    def _install(self, version: str) -> tuple[bool, str | None]:
        target = self.dir / version
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        ok, error = self.strategy.install(version, target)
        if not ok:
            shutil.rmtree(target, ignore_errors=True)
        return ok, error

    def remove_version(self, version: str) -> tuple[bool, str | None]:
        if version == self.base_version:
            return False, "Cannot remove the built-in default version"
        target = self.dir / version
        if self.strategy.installed_binary(target) is None:
            return False, "Version is not installed"
        shutil.rmtree(target, ignore_errors=True)
        return True, None
