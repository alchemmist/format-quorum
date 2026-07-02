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
import os
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
# A user-uploaded custom build reuses the version axis under its own namespace, so
# it never collides with an X.Y.Z release and is easy to tell apart everywhere.
CUSTOM_RE = re.compile(r"^custom-[a-z0-9][a-z0-9._-]*$")


def custom_label_to_id(label: str) -> str | None:
    """Turn a free-form label ("my patch", "fork#1") into a safe ``custom-<slug>``
    id, or None if there's nothing usable in it."""
    slug = re.sub(r"[^a-z0-9._-]+", "-", label.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-.")
    return f"custom-{slug}" if slug else None

INSTALL_TIMEOUT_SEC = 600
DOWNLOAD_TIMEOUT_SEC = 120  # per-call ceiling so a stalled download can't hang an install


def _download(url: str, dst: Path) -> None:
    """Stream ``url`` to ``dst`` with a per-call timeout (urlretrieve has none)."""
    with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SEC) as resp:  # noqa: S310
        with open(dst, "wb") as fh:
            shutil.copyfileobj(resp, fh)


def _probe_version(binary: str) -> str | None:
    """Run ``<binary> --version`` and return the first X.Y.Z it prints, or None."""
    try:
        out = subprocess.run(
            [binary, "--version"], capture_output=True, text=True, timeout=10
        )
    except Exception:  # noqa: BLE001
        return None
    # some tools print their version to stderr (e.g. google-java-format)
    m = re.search(r"(\d+\.\d+\.\d+)", f"{out.stdout}\n{out.stderr}")
    return m.group(1) if m else None


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

    def default_version(self) -> str | None:
        """The version of the built-in (``base_binary``) install. Defaults to
        ``<base_binary> --version``; override when that binary reports something
        other than the version axis's key (e.g. rustfmt prints its own version,
        not the rust toolchain version the axis is keyed by)."""
        return _probe_version(self.base_binary)

    def install_upload(self, src: Path, version_dir: Path) -> tuple[bool, str | None]:
        """Place a user-uploaded prebuilt binary as a custom 'version'. Default:
        copy it to where :meth:`installed_binary` looks and mark it executable, so
        it's invoked exactly like a fetched build. Strategies whose runnable
        artifact isn't a bare executable (a jar) override this."""
        try:
            dst = self.bin_path(version_dir)  # type: ignore[attr-defined]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            dst.chmod(0o755)
            return True, None
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)


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

    def bin_path(self, version_dir: Path) -> Path:
        return version_dir / "bin" / self.binary_name

    def installed_binary(self, version_dir: Path) -> Path | None:
        p = self.bin_path(version_dir)
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


def _machine_arch() -> str:
    """This host's arch as the common release-asset token (amd64 / arm64).

    Unknown architectures return their raw token rather than masquerading as
    amd64 — an unsupported host should miss availability, not download and try
    to run an incompatible binary."""
    m = platform.machine().lower()
    if m in ("aarch64", "arm64"):
        return "arm64"
    if m in ("x86_64", "amd64"):
        return "amd64"
    return m


class NpmInstall(InstallStrategy):
    """Install a version as an npm package into its own prefix.

    ``npm install --prefix <version_dir> <package>@X.Y.Z`` drops the package's
    console script at ``<version_dir>/node_modules/.bin/<binary_name>`` — e.g.
    ``prettier`` and ``@taplo/cli`` (whose binary is ``taplo``)."""

    def __init__(self, package: str, binary_name: str, *, base_binary: str | None = None):
        self.package = package
        self.binary_name = binary_name
        self.base_binary = base_binary or binary_name

    def bin_path(self, version_dir: Path) -> Path:
        return version_dir / "node_modules" / ".bin" / self.binary_name

    def installed_binary(self, version_dir: Path) -> Path | None:
        p = self.bin_path(version_dir)
        return p if p.exists() else None

    def install(self, version: str, version_dir: Path) -> tuple[bool, str | None]:
        version_dir.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                # --ignore-scripts: never run package lifecycle hooks — the version
                # string is user-supplied, and prettier/@taplo/cli need no install hooks.
                ["npm", "install", "--prefix", str(version_dir), "--ignore-scripts",
                 "--no-save", "--no-audit", "--no-fund", f"{self.package}@{version}"],
                capture_output=True, text=True, timeout=INSTALL_TIMEOUT_SEC,
            )
            if proc.returncode != 0 or self.installed_binary(version_dir) is None:
                return False, (proc.stderr.strip()[:400] or
                               f"npm install {self.package}@{version} failed")
            return True, None
        except subprocess.TimeoutExpired:
            return False, "Installation timed out"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def available(self, version: str) -> bool:
        # the npm registry returns 200 for a published version, 404 otherwise
        url = f"https://registry.npmjs.org/{self.package}/{version}"
        try:
            with urllib.request.urlopen(url, timeout=8) as resp:  # noqa: S310
                return resp.status == 200
        except Exception:  # noqa: BLE001
            return False


class UrlBinaryInstall(InstallStrategy):
    """Download a single prebuilt executable per version from a templated URL.

    ``url_template`` is formatted with ``{version}`` and ``{arch}`` (amd64/arm64)
    — e.g. shfmt's GitHub release assets. The file is saved to
    ``<version_dir>/bin/<binary_name>`` and made executable."""

    def __init__(self, url_template: str, binary_name: str, *, base_binary: str):
        self.url_template = url_template
        self.binary_name = binary_name
        self.base_binary = base_binary

    def _url(self, version: str) -> str:
        return self.url_template.format(version=version, arch=_machine_arch())

    def bin_path(self, version_dir: Path) -> Path:
        return version_dir / "bin" / self.binary_name

    def installed_binary(self, version_dir: Path) -> Path | None:
        p = self.bin_path(version_dir)
        return p if p.exists() else None

    def install(self, version: str, version_dir: Path) -> tuple[bool, str | None]:
        dst = self.bin_path(version_dir)
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            _download(self._url(version), dst)
            dst.chmod(0o755)
            return True, None
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def available(self, version: str) -> bool:
        req = urllib.request.Request(self._url(version), method="HEAD")  # noqa: S310
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310
                return resp.status == 200
        except Exception:  # noqa: BLE001
            return False


class JarInstall(InstallStrategy):
    """Download a runnable jar per version and wrap it in a launcher script.

    The jar is fetched to ``<version_dir>/app.jar`` and a ``<version_dir>/bin/
    <binary_name>`` shell wrapper runs it via ``java [java_args] -jar`` — e.g.
    google-java-format, whose ``java_args`` open the compiler internals."""

    def __init__(self, url_template: str, binary_name: str, *, base_binary: str,
                 java_args: tuple[str, ...] = ()):
        self.url_template = url_template
        self.binary_name = binary_name
        self.base_binary = base_binary
        self.java_args = list(java_args)

    def _jar(self, version_dir: Path) -> Path:
        return version_dir / "app.jar"

    def bin_path(self, version_dir: Path) -> Path:
        return version_dir / "bin" / self.binary_name

    def installed_binary(self, version_dir: Path) -> Path | None:
        p = self.bin_path(version_dir)
        return p if p.exists() and self._jar(version_dir).exists() else None

    def _write_wrapper(self, version_dir: Path) -> None:
        wrapper = self.bin_path(version_dir)
        wrapper.parent.mkdir(parents=True, exist_ok=True)
        flags = " ".join(self.java_args)
        wrapper.write_text(
            f'#!/bin/sh\nexec java {flags} -jar "{self._jar(version_dir)}" "$@"\n'
        )
        wrapper.chmod(0o755)

    def install(self, version: str, version_dir: Path) -> tuple[bool, str | None]:
        jar = self._jar(version_dir)
        jar.parent.mkdir(parents=True, exist_ok=True)
        try:
            _download(self.url_template.format(version=version), jar)
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
        self._write_wrapper(version_dir)
        return True, None

    def install_upload(self, src: Path, version_dir: Path) -> tuple[bool, str | None]:
        # the uploaded artifact is a jar: place it and (re)generate the launcher
        jar = self._jar(version_dir)
        jar.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(src, jar)
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
        self._write_wrapper(version_dir)
        return True, None

    def available(self, version: str) -> bool:
        req = urllib.request.Request(  # noqa: S310
            self.url_template.format(version=version), method="HEAD"
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310
                return resp.status == 200
        except Exception:  # noqa: BLE001
            return False


class ToolchainInstall(InstallStrategy):
    """Install a formatter that ships only inside a language toolchain, by
    installing the whole toolchain via its manager (rustup) into the version dir.

    Unlike the other strategies a *version* here is the **toolchain** version
    (e.g. rust ``1.83.0``), not the formatter's own version — rustfmt reports
    ``1.9.0`` but is pinned to a rust release, so the axis is keyed by the rust
    version and :meth:`default_version` probes ``version_binary`` (rustc) rather
    than the rustfmt base binary.

    ``rustup toolchain install <ver> --profile minimal --component <comp>`` with
    ``RUSTUP_HOME=<version_dir>`` drops the toolchain under
    ``<version_dir>/toolchains/<ver>-<triple>/`` and the real (non-proxy) binary
    at ``…/bin/<binary_name>``."""

    def __init__(self, manager_binary: str, component: str, binary_name: str, *,
                 base_binary: str, version_binary: str, manifest_url: str):
        self.manager_binary = manager_binary  # "rustup"
        self.component = component  # "rustfmt"
        self.binary_name = binary_name  # "rustfmt"
        self.base_binary = base_binary  # the image's default rustfmt
        self.version_binary = version_binary  # reports the toolchain version (rustc)
        self.manifest_url = manifest_url  # {version} → a release-existence URL

    def default_version(self) -> str | None:
        return _probe_version(self.version_binary)

    def bin_path(self, version_dir: Path) -> Path:
        # A real rustup install drops the binary under a ``<ver>-<triple>``
        # toolchain dir; this fixed location is what the offline test harness
        # symlinks to. :meth:`installed_binary` globs for either layout.
        return version_dir / "toolchains" / "installed" / "bin" / self.binary_name

    def installed_binary(self, version_dir: Path) -> Path | None:
        root = version_dir / "toolchains"
        if not root.is_dir():
            return None
        for tc in sorted(root.iterdir()):
            cand = tc / "bin" / self.binary_name
            if cand.exists():
                return cand
        return None

    def install(self, version: str, version_dir: Path) -> tuple[bool, str | None]:
        version_dir.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, RUSTUP_HOME=str(version_dir))
        try:
            proc = subprocess.run(
                [self.manager_binary, "toolchain", "install", version,
                 "--profile", "minimal", "--component", self.component,
                 "--no-self-update"],
                capture_output=True, text=True, timeout=INSTALL_TIMEOUT_SEC, env=env,
            )
            if proc.returncode != 0 or self.installed_binary(version_dir) is None:
                return False, (proc.stderr.strip()[:400] or
                               f"rustup toolchain install {version} failed")
            return True, None
        except subprocess.TimeoutExpired:
            return False, "Installation timed out"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def available(self, version: str) -> bool:
        req = urllib.request.Request(  # noqa: S310
            self.manifest_url.format(version=version), method="HEAD"
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310
                return resp.status == 200
        except Exception:  # noqa: BLE001
            return False


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
        self.base_version = strategy.default_version()
        self.known_versions = list(known_versions or [])
        self._lock = threading.Lock()
        self._installing: set[str] = set()
        # which known_versions actually look installable here — probed in the
        # background. None until ready; until then state() shows the full list.
        self._suggest_lock = threading.Lock()
        self._installable: set[str] | None = None
        threading.Thread(target=self._warm_suggestions, daemon=True).start()

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
        # uploaded custom builds live on the same axis (so format/matrix/config
        # treat them as versions) but are surfaced separately so the UI can label
        # them and tell them apart from fetched X.Y.Z releases.
        uploads = [v for v in installed if CUSTOM_RE.match(v)]
        return {
            "versions": installed,
            "default": self.base_version,
            "installing": installing,
            "suggestions": suggestions,
            "uploads": uploads,
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

    def add_upload(self, version_id: str, src: Path) -> tuple[bool, str | None]:
        """Register a user-uploaded prebuilt binary as the custom build
        ``version_id`` (``custom-<slug>``), replacing any build under that id."""
        if not CUSTOM_RE.match(version_id):
            return False, "Invalid custom build id"
        with self._lock:
            if version_id in self._installing:
                return False, "This build is already being installed"
            self._installing.add(version_id)
        try:
            target = self.dir / version_id
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            ok, error = self.strategy.install_upload(src, target)
            if not ok:
                shutil.rmtree(target, ignore_errors=True)
            return ok, error
        finally:
            with self._lock:
                self._installing.discard(version_id)

    def remove_version(self, version: str) -> tuple[bool, str | None]:
        if version == self.base_version:
            return False, "Cannot remove the built-in default version"
        target = self.dir / version
        if self.strategy.installed_binary(target) is None:
            return False, "Version is not installed"
        shutil.rmtree(target, ignore_errors=True)
        return True, None
