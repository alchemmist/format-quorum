#!/usr/bin/env python3
"""Thin CLI/loadable client for the format-quorum backend API.

Base URL comes from $FQ_BASE (default http://localhost:3000). No auth.

Examples:
    FQ_BASE=https://fq.alchemmist.xyz python3 fq.py list
    printf 'int *p;' | python3 fq.py format --lang cpp
    python3 fq.py add --name "X" --lang cpp --mode lock --input-file in.cpp
    python3 fq.py run --lang cpp --version 19.1.7
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("FQ_BASE", "http://localhost:3000").rstrip("/")


def _req(method: str, path: str, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        sys.stderr.write(f"HTTP {exc.code}: {body}\n")
        sys.exit(1)
    return json.loads(body) if body else None


def fmt(code: str, language: str = "cpp", version: str | None = None) -> str:
    payload = {"code": code, "language": language}
    if version:
        payload["clang_version"] = version
    return _req("POST", "/api/format", payload)["formatted"]


def _read(path: str | None) -> str:
    if path in (None, "-"):
        return sys.stdin.read()
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _pp(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


# ── commands ──────────────────────────────────────────────────────────────────
def cmd_list(a):
    rows = _req("GET", "/api/tests")
    if a.json:
        _pp(rows)
        return
    for t in sorted(rows, key=lambda r: (r["language"], r["name"])):
        m = " [muted]" if t.get("muted") else ""
        print(f"{t['id']}  [{t['language']:6}] {t['name']}{m}")
    print(f"\n{len(rows)} tests")


def cmd_get(a):
    # the API has no GET /api/tests/{id}; fetch the list and filter
    rows = _req("GET", "/api/tests")
    match = next((t for t in rows if t["id"] == a.id), None)
    if match is None:
        sys.exit(f"no test with id {a.id}")
    _pp(match)


def cmd_format(a):
    sys.stdout.write(fmt(_read(a.input_file), a.lang, a.version))


def cmd_add(a):
    src = _read(a.input_file)
    if a.mode in ("lock", "guard"):
        expected = fmt(src, a.lang, a.version)
    else:  # want / muted: caller supplies the desired output
        if not (a.expected_file or a.expected):
            sys.exit("want/muted tests need --expected-file or --expected")
        expected = a.expected if a.expected is not None else _read(a.expected_file)
    body = {
        "name": a.name, "language": a.lang, "input": src,
        "expected": expected, "muted": a.muted, "note": a.note or "",
    }
    _pp(_req("POST", "/api/tests", body))


def cmd_update(a):
    patch = {}
    if a.name is not None:
        patch["name"] = a.name
    if a.lang is not None:
        patch["language"] = a.lang
    if a.input_file is not None:
        patch["input"] = _read(a.input_file)
    if a.expected_file is not None:
        patch["expected"] = _read(a.expected_file)
    if a.note is not None:
        patch["note"] = a.note
    if a.muted is not None:
        patch["muted"] = a.muted
    if not patch:
        sys.exit("nothing to update")
    _pp(_req("PUT", f"/api/tests/{a.id}", patch))


def cmd_delete(a):
    _pp(_req("DELETE", f"/api/tests/{a.id}"))


def cmd_run(a):
    payload = {}
    if a.lang:
        payload["language"] = a.lang
    if a.version:
        payload["clang_version"] = a.version
    res = _req("POST", "/api/tests/run", payload)
    print("summary:", res["summary"])
    for r in sorted(res["results"], key=lambda r: (r["language"], r["status"], r["name"])):
        print(f"  {r['status']:7} [{r['language']:6}] {r['name']}")


def cmd_get_config(a):
    sys.stdout.write(_req("GET", f"/api/config/{a.lang}")["content"])


def cmd_put_config(a):
    payload = {"content": _read(a.input_file)}
    if a.author:
        payload["author"] = a.author
    if a.message:
        payload["message"] = a.message
    _pp(_req("PUT", f"/api/config/{a.lang}", payload))


def cmd_config_history(a):
    res = _req("GET", f"/api/config/{a.lang}/history")
    print(f"head: v{res['head']}")
    for v in res["versions"]:
        who = f" by {v['author']}" if v.get("author") else ""
        msg = f" — {v['message']}" if v.get("message") else ""
        print(f"  v{v['seq']:<3} {v.get('ts') or '(base)':<32}{who}{msg}")


def cmd_config_rollback(a):
    payload = {"seq": a.seq}
    if a.author:
        payload["author"] = a.author
    if a.message:
        payload["message"] = a.message
    _pp(_req("POST", f"/api/config/{a.lang}/rollback", payload))


def cmd_versions(a):
    _pp(_req("GET", "/api/clang-versions"))


def _coerce(v):
    """Turn a CLI string into bool/int where it obviously is one (so a YAML
    patch gets `true`/`12`, not `"true"`/`"12"`)."""
    if v in ("true", "false"):
        return v == "true"
    if v.lstrip("-").isdigit():
        return int(v)
    return v


def cmd_whatif(a):
    """Check a 'config patch -> which tests pass/fail' hypothesis."""
    payload = {"language": a.lang}
    if a.version:
        payload["clang_version"] = a.version
    if a.set:
        payload["patch"] = {k: _coerce(v) for k, v in (s.split("=", 1) for s in a.set)}
    if a.config_file:
        payload["config"] = _read(a.config_file)
    if a.target:
        payload["targets"] = a.target
    res = _req("POST", "/api/tests/whatif", payload)
    b, p = res["summary"]["baseline"], res["summary"]["patched"]
    print(f"baseline: {b['passed']} pass / {b['failed']} fail / {b['muted']} muted")
    print(f"patched : {p['passed']} pass / {p['failed']} fail / {p['muted']} muted")
    f = res["flips"]
    print(f"+{len(f['now_pass'])} fixed  -{len(f['now_fail'])} broken  "
          f"{len(f['muted_would_pass'])} muted-would-pass")
    if f["now_pass"]:
        print("  fixes :", ", ".join(f["now_pass"]))
    if f["now_fail"]:
        print("  breaks:", ", ".join(f["now_fail"]))
    if f["muted_would_pass"]:
        print("  muted would pass:", ", ".join(f["muted_would_pass"]))
    for t in res.get("targets", []):
        print(f"  TARGET {t['name']}: {t['baseline_status']} -> {t['patched_status']}"
              f"  (passes: {t['baseline_passed']} -> {t['patched_passed']})")


def main():
    p = argparse.ArgumentParser(description=f"format-quorum API client (base={BASE})")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("list", help="list tests"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_list)
    s = sub.add_parser("get", help="get one test"); s.add_argument("id"); s.set_defaults(fn=cmd_get)

    s = sub.add_parser("format", help="format code from --input-file or stdin")
    s.add_argument("--lang", default="cpp"); s.add_argument("--version")
    s.add_argument("--input-file", "-i", default="-"); s.set_defaults(fn=cmd_format)

    s = sub.add_parser("add", help="create a test")
    s.add_argument("--name", required=True); s.add_argument("--lang", default="cpp")
    s.add_argument("--mode", choices=["lock", "guard", "want"], default="lock")
    s.add_argument("--input-file", "-i", default="-")
    s.add_argument("--expected-file"); s.add_argument("--expected")
    s.add_argument("--muted", action="store_true"); s.add_argument("--note")
    s.add_argument("--version"); s.set_defaults(fn=cmd_add)

    s = sub.add_parser("update", help="patch a test")
    s.add_argument("id"); s.add_argument("--name"); s.add_argument("--lang")
    s.add_argument("--input-file"); s.add_argument("--expected-file"); s.add_argument("--note")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--muted", dest="muted", action="store_true", default=None)
    g.add_argument("--unmuted", dest="muted", action="store_false")
    s.set_defaults(fn=cmd_update)

    s = sub.add_parser("delete", help="delete a test"); s.add_argument("id"); s.set_defaults(fn=cmd_delete)

    s = sub.add_parser("run", help="run tests")
    s.add_argument("--lang"); s.add_argument("--version"); s.set_defaults(fn=cmd_run)

    s = sub.add_parser("get-config", help="print a config"); s.add_argument("lang"); s.set_defaults(fn=cmd_get_config)
    s = sub.add_parser("put-config", help="publish a config from --input-file or stdin (records a version)")
    s.add_argument("lang"); s.add_argument("--input-file", "-i", default="-")
    s.add_argument("--author"); s.add_argument("--message", "-m"); s.set_defaults(fn=cmd_put_config)

    s = sub.add_parser("config-history", help="list a config's version history")
    s.add_argument("lang"); s.set_defaults(fn=cmd_config_history)
    s = sub.add_parser("config-rollback", help="roll a config back to an earlier version")
    s.add_argument("lang"); s.add_argument("seq", type=int)
    s.add_argument("--author"); s.add_argument("--message", "-m"); s.set_defaults(fn=cmd_config_rollback)

    s = sub.add_parser("versions", help="list clang-format versions"); s.set_defaults(fn=cmd_versions)

    s = sub.add_parser("whatif", help="config patch -> which tests flip pass/fail")
    s.add_argument("--lang", default="cpp"); s.add_argument("--version")
    s.add_argument("--set", action="append", default=[], metavar="Key=Value",
                   help="top-level clang-format override on the live config (repeatable)")
    s.add_argument("--config-file", help="try a full config instead of a patch")
    s.add_argument("--target", action="append", default=[], metavar="ID_OR_NAME",
                   help="test id or name substring to call out (repeatable)")
    s.set_defaults(fn=cmd_whatif)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
