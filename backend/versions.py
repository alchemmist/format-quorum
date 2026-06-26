"""Dynamic clang-format version management.

The user can ask the backend to make an arbitrary clang-format version
available. Each version is installed into its own virtualenv via
`pip install clang-format==X.Y.Z` (the wheel ships a bundled binary). If pip
has no installable wheel for that exact version / platform, the version simply
does not exist and we report that back.

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
from pathlib import Path

# Strictly three dot-separated numbers, e.g. 22.1.5.
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

# Suggested versions surfaced in the UI as quick-add chips (latest patch per
# major). Any valid X.Y.Z can still be added by hand.
KNOWN_VERSIONS = [
    "14.0.6",
    "15.0.7",
    "16.0.6",
    "17.0.6",
    "18.1.8",
    "19.1.7",
    "20.1.8",
    "21.1.8",
    "22.1.5",
]

INSTALL_TIMEOUT_SEC = 600


class VersionManager:
    def __init__(self, versions_dir: Path, base_bin: str):
        self.dir = Path(versions_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.base_bin = base_bin
        self.base_version = self._probe(base_bin)
        self._lock = threading.Lock()
        self._installing: set[str] = set()
        # which KNOWN_VERSIONS actually have an installable wheel for *this*
        # platform — probed against PyPI in the background. None until ready;
        # until then state() shows the full list (best effort).
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

    def _venv_bin(self, version: str) -> Path:
        return self.dir / version / "bin" / "clang-format"

    # ── suggestion availability ──────────────────────────────────────────────
    @staticmethod
    def _wheel_compatible(filename: str) -> bool:
        """Mirror pip's wheel/platform check well enough to know whether a
        `clang-format==X.Y.Z` install would find a binary wheel here."""
        name = filename.lower()
        if not name.endswith(".whl"):
            return False  # sdist only → no bundled binary we can use
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

    def _has_compatible_wheel(self, version: str) -> bool:
        url = f"https://pypi.org/pypi/clang-format/{version}/json"
        with urllib.request.urlopen(url, timeout=8) as resp:  # noqa: S310
            data = json.load(resp)
        return any(self._wheel_compatible(u["filename"]) for u in data.get("urls", []))

    def _warm_suggestions(self) -> None:
        installable: set[str] = set()
        for v in KNOWN_VERSIONS:
            try:
                if self._has_compatible_wheel(v):
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
                if (child / "bin" / "clang-format").exists():
                    found.append(child.name)
        # de-dupe, preserve order
        seen: set[str] = set()
        return [v for v in found if not (v in seen or seen.add(v))]

    def get_binary(self, version: str | None) -> str | None:
        """Resolve a version string to a clang-format binary path, or None."""
        if not version:
            return self.base_bin
        if version == self.base_version:
            return self.base_bin
        bin_path = self._venv_bin(version)
        return str(bin_path) if bin_path.exists() else None

    def state(self) -> dict:
        installed = self._installed()
        with self._lock:
            installing = sorted(self._installing)
        with self._suggest_lock:
            installable = self._installable
        # before the probe finishes, fall back to the full list
        pool = KNOWN_VERSIONS if installable is None else [v for v in KNOWN_VERSIONS if v in installable]
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
        try:
            venv.EnvBuilder(with_pip=True).create(target)
            pip = target / "bin" / "pip"
            proc = subprocess.run(
                [str(pip), "install", "--no-cache-dir", f"clang-format=={version}"],
                capture_output=True,
                text=True,
                timeout=INSTALL_TIMEOUT_SEC,
            )
            if proc.returncode != 0 or not self._venv_bin(version).exists():
                shutil.rmtree(target, ignore_errors=True)
                return False, (
                    f"clang-format {version} is not available "
                    "(no installable wheel for this version/platform)"
                )
            return True, None
        except subprocess.TimeoutExpired:
            shutil.rmtree(target, ignore_errors=True)
            return False, "Installation timed out"
        except Exception as exc:  # noqa: BLE001 - surface any setup failure
            shutil.rmtree(target, ignore_errors=True)
            return False, str(exc)

    def remove_version(self, version: str) -> tuple[bool, str | None]:
        if version == self.base_version:
            return False, "Cannot remove the built-in default version"
        target = self.dir / version
        if not (target / "bin" / "clang-format").exists():
            return False, "Version is not installed"
        shutil.rmtree(target, ignore_errors=True)
        return True, None
