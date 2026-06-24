#!/usr/bin/env python3
"""cfprobe — a tuning bench for clang-format options that runs ENTIRELY through
the format-quorum HTTP API ($FQ_BASE, default http://localhost:3000).

It never installs or runs clang-format locally and never overwrites the stored
config: it uses the API's ad-hoc `config` override to format/run the suite
against a candidate config, so the saved config stays exactly as it was.

Everything is pinned to ONE clang-format version — the one you pass with
--version (ask the user; default = the instance's `default`). Do not consider
any other version: a fix that needs a newer clang-format is not a fix here.

Commands:
  versions                            list installed versions + the default
  ensure  --version X.Y.Z             install that version in the instance if missing
  docs    --version X.Y.Z             print the version-matched style-options URL
  baseline --version X.Y.Z            run the cpp suite with the stored config
  show    --target NAME --version ..  print a test's BEFORE / current ACTUAL / DESIRED
  try     --target NAME --version ..  run a variant; report target PASS + regressions
            --set Key=Value (repeat)  top-level key overrides
            --config-file PATH        use a fully hand-built variant (for nested keys)
            --show                    also print the target's actual output

Typical loop:
  FQ_BASE=http://localhost:3000 cfprobe.py ensure --version 18.1.8
  cfprobe.py docs --version 18.1.8            # → WebFetch, grep keywords
  cfprobe.py show --target P5 --version 18.1.8
  cfprobe.py try  --target P5 --version 18.1.8 --set Cpp11BracedListStyle=false --show
"""
from __future__ import annotations
import argparse, json, os, sys, time, urllib.error, urllib.request
from typing import Any

FQ_BASE = os.environ.get("FQ_BASE", "http://localhost:3000").rstrip("/")


def _req(method, path, payload=None) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(FQ_BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            body = r.read().decode()
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} on {method} {path}: {e.read().decode()[:300]}")
    return json.loads(body) if body else None


def docs_url(v):
    return f"https://releases.llvm.org/{v}/tools/clang/docs/ClangFormatStyleOptions.html"


def _norm(s):
    return (s or "").replace("\r\n", "\n").rstrip("\n")


def _tests():
    return _req("GET", "/api/tests")


def _base_config():
    return _req("GET", "/api/config/cpp")["content"]


def _target(name):
    m = [t for t in _tests() if name.lower() in t["name"].lower() and t["language"] == "cpp"]
    if not m:
        sys.exit(f"no cpp test matching {name!r}")
    if len(m) > 1:
        sys.exit("ambiguous target: " + "; ".join(t["name"] for t in m))
    return m[0]


def _apply(base, overrides):
    """Replace or append TOP-LEVEL keys (avoids the duplicate-key error that
    clang-format raises if you just append an existing key)."""
    keys = dict(overrides)
    out = []
    for ln in base.split("\n"):
        s = ln.strip()
        hit = next((k for k in keys if s.startswith(k + ":") and not ln.startswith((" ", "\t"))), None)
        out.append(f"{hit}: {keys.pop(hit)}" if hit else ln)
    out += [f"{k}: {v}" for k, v in keys.items()]
    return "\n".join(out)


def _run_suite(version, config=None):
    body = {"language": "cpp", "clang_version": version}
    if config is not None:
        body["config"] = config
    res = _req("POST", "/api/tests/run", body)
    pass_ = {r["name"] for r in res["results"] if r["status"] == "pass"}
    muted = {r["name"] for r in res["results"] if r["status"] == "muted"}
    fail = {r["name"] for r in res["results"] if r["status"] == "fail"}
    return res["summary"], pass_, fail, muted


def cmd_versions(a):
    print(json.dumps(_req("GET", "/api/clang-versions"), indent=2))


def cmd_ensure(a):
    st = _req("GET", "/api/clang-versions")
    if a.version in st["versions"]:
        print(f"[ensure] {a.version} already installed")
        return
    print(f"[ensure] installing {a.version} in the instance (one-time)…")
    _req("POST", "/api/clang-versions", {"version": a.version})
    for _ in range(120):
        st = _req("GET", "/api/clang-versions")
        if a.version in st["versions"]:
            print(f"[ensure] {a.version} ready"); return
        if a.version not in st.get("installing", []):
            time.sleep(0)  # keep waiting; some backends don't report 'installing'
        time.sleep(2)
    sys.exit(f"[ensure] {a.version} did not become available — check the instance")


def cmd_docs(a):
    print(docs_url(a.version))


def cmd_baseline(a):
    summary, pass_, fail, muted = _run_suite(a.version)
    print(f"cpp: {summary['passed']} pass / {summary['failed']} fail / {summary['muted']} muted")
    if fail:
        print("FAIL:", sorted(fail))


def cmd_show(a):
    t = _target(a.target)
    out = _req("POST", "/api/format",
               {"code": t["input"], "language": "cpp", "clang_version": a.version,
                "config": _base_config()})
    print(f"### {t['name']}\n--- BEFORE ---\n{t['input']}")
    print(f"--- ACTUAL (current config @ {a.version}) ---\n{out.get('formatted', out)}")
    print(f"--- DESIRED ---\n{t['expected']}")


def cmd_try(a):
    t = _target(a.target)
    if a.config_file:
        variant = open(a.config_file, encoding="utf-8").read()
    else:
        variant = _apply(_base_config(), dict(kv.split("=", 1) for kv in a.set))
    _, base_pass, _, _ = _run_suite(a.version)                       # stored config
    summary, var_pass, var_fail, var_muted = _run_suite(a.version, variant)
    out = _req("POST", "/api/format",
               {"code": t["input"], "language": "cpp", "clang_version": a.version,
                "config": variant})
    actual = out.get("formatted")
    ok = actual is not None and _norm(actual) == _norm(t["expected"])
    regress = sorted(base_pass - var_pass - var_muted)
    if a.set:
        print("overrides:", dict(kv.split("=", 1) for kv in a.set))
    if a.config_file:
        print("config-file:", a.config_file)
    print(f"cpp: {summary['passed']} pass / {summary['failed']} fail / {summary['muted']} muted")
    print(f"TARGET {t['name']!r}: {'PASS' if ok else 'still fails'}")
    if regress:
        print(f"REGRESSIONS (were passing, now broken): {regress}")
    else:
        print("no regressions")
    if a.show and actual is not None:
        print("--- target actual ---\n" + actual)


def main():
    p = argparse.ArgumentParser(description=f"clang-format tuning over format-quorum ({FQ_BASE})")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("versions").set_defaults(fn=cmd_versions)
    s = sub.add_parser("ensure"); s.add_argument("--version", required=True); s.set_defaults(fn=cmd_ensure)
    s = sub.add_parser("docs"); s.add_argument("--version", required=True); s.set_defaults(fn=cmd_docs)
    s = sub.add_parser("baseline"); s.add_argument("--version", required=True); s.set_defaults(fn=cmd_baseline)
    s = sub.add_parser("show"); s.add_argument("--target", required=True); s.add_argument("--version", required=True); s.set_defaults(fn=cmd_show)
    s = sub.add_parser("try"); s.add_argument("--target", required=True); s.add_argument("--version", required=True)
    s.add_argument("--set", action="append", default=[], metavar="Key=Value")
    s.add_argument("--config-file"); s.add_argument("--show", action="store_true")
    s.set_defaults(fn=cmd_try)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
