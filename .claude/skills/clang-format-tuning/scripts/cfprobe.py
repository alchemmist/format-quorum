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


def _req(method, path, payload=None, tolerant=False) -> Any:
    """Call the API. On an HTTP error, exit — unless `tolerant`, in which case
    return None (used by the sweep so a config the version rejects just skips)."""
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(FQ_BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            body = r.read().decode()
    except urllib.error.HTTPError as e:
        if tolerant:
            return None
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


DEFAULT_GRID = {
    # "" as a value means "leave the key at its base-config value"
    "AlignAfterOpenBracket": ["", "Align", "DontAlign", "AlwaysBreak", "BlockIndent"],
    "Cpp11BracedListStyle": ["", "true", "false"],
    "BinPackArguments": ["", "true", "false"],
    "AllowAllArgumentsOnNextLine": ["", "true", "false"],
    "InsertTrailingCommas": ["", "None", "Wrapped"],
}


def cmd_sweep(a):
    """Exhaustively try a grid of option combinations and report which ones make
    the TARGET TEST PASS (the only thing that counts as a fix), clean or not.
    This is the guard against claiming a fix that was never verified."""
    import itertools
    t = _target(a.target)
    desired = _norm(t["expected"])
    base = _base_config()
    grid = {}
    for g in a.grid:
        k, vs = g.split("=", 1)
        grid[k] = [v.strip() for v in vs.split(",")]
    if not grid:
        grid = DEFAULT_GRID
    names = list(grid)
    combos = list(itertools.product(*[grid[n] for n in names]))
    if len(combos) > a.max_combos:
        sys.exit(f"{len(combos)} combos exceeds --max-combos={a.max_combos}; "
                 f"narrow the grid (this would be slow and is rarely needed)")
    print(f"[sweep] {len(combos)} combinations of {names} on {t['name']!r} @ {a.version}")

    passing, closest, closest_score = [], None, -1
    for combo in combos:
        ov = {n: v for n, v in zip(names, combo) if v != ""}
        variant = _apply(base, ov)
        resp = _req("POST", "/api/format",
                    {"code": t["input"], "language": "cpp", "clang_version": a.version,
                     "config": variant}, tolerant=True)
        out = resp.get("formatted") if resp else None
        if out is None:
            continue                                  # config the version rejects
        if _norm(out) == desired:
            passing.append(ov)
        else:
            score = sum(1 for x, y in zip(_norm(out).split("\n"), desired.split("\n")) if x == y)
            if score > closest_score:
                closest_score, closest = score, (ov, _norm(out))

    if not passing:
        # No combination makes the target pass — there is NO config fix (clean or
        # destructive). State that, don't claim a breakable fix exists.
        nlines = len(desired.split("\n"))
        print(f"\nNO config in {a.version} makes {t['name']!r} pass — not even one that "
              f"regresses other tests. ({len(combos)} combos tried.)")
        if closest is not None:
            print(f"closest matched {closest_score}/{nlines} lines with {closest[0]}:")
            print(closest[1])
        return

    # Some combos pass — measure regressions to label clean vs destructive.
    _, base_pass, _, _ = _run_suite(a.version)
    scored = []
    for ov in passing:
        _, vp, _, vm = _run_suite(a.version, _apply(base, ov))
        scored.append((ov, sorted(base_pass - vp - vm)))
    scored.sort(key=lambda x: len(x[1]))
    print(f"\n{len(scored)} combo(s) make the target PASS:")
    for ov, regress in scored:
        tag = "CLEAN FIX" if not regress else f"destructive (regresses {len(regress)})"
        print(f"  [{tag}] {ov}")
        if regress:
            print(f"      regressions: {regress}")


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
    s = sub.add_parser("sweep", help="try a grid of combos; report which make the target PASS")
    s.add_argument("--target", required=True); s.add_argument("--version", required=True)
    s.add_argument("--grid", action="append", default=[], metavar="Key=v1,v2,..",
                   help="option grid axis (repeatable); omit to use the default brace/wrap grid")
    s.add_argument("--max-combos", type=int, default=2000)
    s.set_defaults(fn=cmd_sweep)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
