#!/usr/bin/env python3
"""cfprobe — an isolated bench for tuning clang-format options against the
format-quorum test suite, without touching the live config.

It pulls the test cases + current config from a running format-quorum instance
($FQ_BASE, default http://localhost:3000), installs the EXACT clang-format
version into a throw-away venv (cached under ~/.cache/cfprobe/<version>), and
lets you try config overrides while watching one target test and the whole
suite for regressions. The real config is never modified.

Commands:
  setup   --version X.Y.Z            install the binary + snapshot tests/config
  docs    --version X.Y.Z            print the matching style-options doc URL
  baseline                           run the suite with the snapshot config
  show    --target NAME              print a test's BEFORE / current ACTUAL / DESIRED
  try     --target NAME --set K=V .. build a variant, run target + suite, list regressions
                         [--show]    also print the target's actual output

Typical loop:
  FQ_BASE=http://localhost:3000 cfprobe.py setup --version 18.1.8
  cfprobe.py docs --version 18.1.8      # → WebFetch this, grep keywords
  cfprobe.py show --target P5
  cfprobe.py try  --target P5 --set Cpp11BracedListStyle=false --show
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, urllib.request
from pathlib import Path

FQ_BASE = os.environ.get("FQ_BASE", "http://localhost:3000").rstrip("/")
CACHE = Path(os.environ.get("CFPROBE_CACHE", Path.home() / ".cache" / "cfprobe"))


def _verdir(version: str) -> Path:
    return CACHE / version


def _binary(version: str) -> Path:
    return _verdir(version) / "venv" / "bin" / "clang-format"


def docs_url(version: str) -> str:
    return f"https://releases.llvm.org/{version}/tools/clang/docs/ClangFormatStyleOptions.html"


def _get(path: str):
    return json.load(urllib.request.urlopen(FQ_BASE + path))


def cmd_setup(a):
    d = _verdir(a.version)
    d.mkdir(parents=True, exist_ok=True)
    binp = _binary(a.version)
    if not binp.exists():
        print(f"[setup] installing clang-format=={a.version} (one-time)…")
        import venv
        venv.EnvBuilder(with_pip=True).create(d / "venv")
        pip = d / "venv" / "bin" / "pip"
        r = subprocess.run([str(pip), "install", "--no-cache-dir", f"clang-format=={a.version}"],
                           capture_output=True, text=True)
        if r.returncode != 0 or not binp.exists():
            sys.exit(f"[setup] pip install failed:\n{r.stderr}")
    # snapshot tests + config from the running instance
    tests = _get("/api/tests")
    (d / "tests.json").write_text(json.dumps(tests))
    cfg = _get("/api/config/cpp")["content"]
    (d / "base.clang-format").write_text(cfg)
    ver = subprocess.run([str(binp), "--version"], capture_output=True, text=True).stdout.strip()
    print(f"[setup] {ver}")
    print(f"[setup] {sum(1 for t in tests if t['language']=='cpp')} cpp / "
          f"{sum(1 for t in tests if t['language']=='python')} python tests cached at {d}")
    print(f"[setup] docs: {docs_url(a.version)}")


def cmd_docs(a):
    print(docs_url(a.version))


def _load(version: str):
    d = _verdir(version)
    if not _binary(version).exists() or not (d / "tests.json").exists():
        sys.exit(f"run `setup --version {version}` first")
    return (str(_binary(version)),
            json.loads((d / "tests.json").read_text()),
            (d / "base.clang-format").read_text())


def _norm(s: str) -> str:
    return s.replace("\r\n", "\n").rstrip("\n")


def _fmt(binp: str, cfg_path: str, code: str):
    p = subprocess.run([binp, "--Wno-error=unknown", "--assume-filename=input.cpp",
                        f"--style=file:{cfg_path}"], input=code, capture_output=True, text=True)
    return (p.stdout, None) if p.returncode == 0 else (None, p.stderr.strip())


def _make(base: str, overrides: dict) -> str:
    """Replace or append TOP-LEVEL keys. (Nested keys like BraceWrapping.X must
    be edited in the base config by hand.)"""
    keys = dict(overrides)
    out = []
    for ln in base.split("\n"):
        s = ln.strip()
        hit = next((k for k in keys if s.startswith(k + ":") and not ln.startswith((" ", "\t"))), None)
        out.append(f"{hit}: {keys.pop(hit)}" if hit else ln)
    out += [f"{k}: {v}" for k, v in keys.items()]
    return "\n".join(out)


def _suite(binp: str, tests: list, cfg_path: str):
    res = {"pass": set(), "fail": set(), "muted": set(), "error": []}
    for t in tests:
        if t["language"] != "cpp":
            continue
        out, err = _fmt(binp, cfg_path, t["input"])
        if err is not None:
            res["error"].append((t["name"], err))
        elif t["muted"]:
            res["muted"].add(t["name"])
        elif _norm(out) == _norm(t["expected"]):
            res["pass"].add(t["name"])
        else:
            res["fail"].add(t["name"])
    return res


def _target(tests, name):
    m = [t for t in tests if name.lower() in t["name"].lower()]
    if not m:
        sys.exit(f"no test matching {name!r}")
    if len(m) > 1:
        sys.exit("ambiguous target: " + ", ".join(t["name"] for t in m))
    return m[0]


def cmd_show(a):
    binp, tests, base = _load(a.version)
    t = _target(tests, a.target)
    tmp = _verdir(a.version) / "_cur.cfg"
    tmp.write_text(base)
    out, err = _fmt(binp, str(tmp), t["input"])
    print(f"### {t['name']}\n--- BEFORE ---\n{t['input']}")
    print(f"--- ACTUAL (current config) ---\n{err or out}")
    print(f"--- DESIRED ---\n{t['expected']}")


def cmd_try(a):
    binp, tests, base = _load(a.version)
    t = _target(tests, a.target)
    overrides = dict(kv.split("=", 1) for kv in a.set)
    # baseline (snapshot config) — what passes before our change
    bcfg = _verdir(a.version) / "_base.cfg"; bcfg.write_text(base)
    base_pass = _suite(binp, tests, str(bcfg))["pass"]
    # variant
    vcfg = _verdir(a.version) / "_variant.cfg"; vcfg.write_text(_make(base, overrides))
    r = _suite(binp, tests, str(vcfg))
    out, err = _fmt(binp, str(vcfg), t["input"])
    ok = err is None and _norm(out) == _norm(t["expected"])
    regress = sorted(base_pass - r["pass"] - r["muted"])
    print(f"overrides: {overrides}")
    print(f"cpp: {len(r['pass'])} pass / {len(r['fail'])} fail / {len(r['muted'])} muted"
          + (f" / {len(r['error'])} error" if r["error"] else ""))
    print(f"TARGET {t['name']!r}: {'PASS ✅' if ok else 'still fails ❌'}" + (f"  (error: {err})" if err else ""))
    if regress:
        print(f"⚠ REGRESSIONS (were passing, now broken): {regress}")
    else:
        print("no regressions")
    if r["error"]:
        print("config errors:", r["error"])
    if a.show and out:
        print("--- target actual ---\n" + out)


def main():
    p = argparse.ArgumentParser(description="clang-format tuning bench over format-quorum")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup"); s.add_argument("--version", required=True); s.set_defaults(fn=cmd_setup)
    s = sub.add_parser("docs"); s.add_argument("--version", required=True); s.set_defaults(fn=cmd_docs)
    s = sub.add_parser("baseline"); s.add_argument("--version", required=True); s.set_defaults(fn=_baseline)
    s = sub.add_parser("show"); s.add_argument("--version", required=True); s.add_argument("--target", required=True); s.set_defaults(fn=cmd_show)
    s = sub.add_parser("try"); s.add_argument("--version", required=True); s.add_argument("--target", required=True)
    s.add_argument("--set", action="append", default=[], metavar="Key=Value"); s.add_argument("--show", action="store_true")
    s.set_defaults(fn=cmd_try)
    a = p.parse_args(); a.fn(a)


def _baseline(a):
    binp, tests, base = _load(a.version)
    cfg = _verdir(a.version) / "_base.cfg"; cfg.write_text(base)
    r = _suite(binp, tests, str(cfg))
    print(f"cpp: {len(r['pass'])} pass / {len(r['fail'])} fail / {len(r['muted'])} muted")
    if r["fail"]:
        print("FAIL:", sorted(r["fail"]))


if __name__ == "__main__":
    main()
