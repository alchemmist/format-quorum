"""The classic-language formatters (gofmt, rustfmt, prettier, shfmt, taplo, gjf).

Each test skips when its toolchain isn't installed locally — CI and the Docker
image have them all, so coverage is complete there while staying green here.
"""

import pytest

from conftest import binary_present, seed_passing_test

# (formatter id, binary, language, messy input, a token the formatted output must contain)
CASES = [
    ("gofmt", "gofmt", "go", "package main\nfunc main(){x:=1;_=x}\n", "func main()"),
    ("rustfmt", "rustfmt", "rust", "fn main(){let x=1;let _=x;}\n", "let x = 1;"),
    ("prettier-ts", "prettier", "typescript", "const x={a:1,b:2}\n", "const x = { a: 1, b: 2 };"),
    ("prettier-js", "prettier", "javascript", "const x=1\n", "const x = 1;"),
    ("prettier-json", "prettier", "json", '{"a":1,"b":2}\n', '"a": 1'),
    ("prettier-css", "prettier", "css", "a{color:red;margin:0}\n", "color: red;"),
    ("prettier-html", "prettier", "html", "<div>\n<p>hi</p>\n</div>\n", "  <p>hi</p>"),
    ("prettier-md", "prettier", "markdown", "#   Title\n", "# Title"),
    ("prettier-yaml", "prettier", "yaml", "a:   1\nb:  2\n", "a: 1"),
    ("shfmt", "shfmt", "shell", 'if [ "$x" = 1 ];then echo hi;fi\n', "; then"),
    ("taplo", "taplo", "toml", "a={b=1,c=2}\n", "a = { b = 1, c = 2 }"),
    ("google-java-format", "google-java-format", "java",
     "class A{int x=1;}\n", "class A"),
]


@pytest.mark.parametrize("fid,binary,language,src,needle", CASES,
                         ids=[c[0] for c in CASES])
def test_classic_formatter_formats(appctx, fid, binary, language, src, needle):
    if not binary_present(binary):
        pytest.skip(f"{binary} not installed")
    r = appctx.client.post("/api/format", json={"code": src, "formatter": fid})
    assert r.status_code == 200, r.text
    out = r.json()["formatted"]
    assert needle in out
    assert out != src  # it actually reformatted


def test_registry_lists_all_classic_formatters(appctx):
    ids = {f["id"] for f in appctx.client.get("/api/formatters").json()["formatters"]}
    expected = {c[0] for c in CASES}
    assert expected <= ids


def test_each_classic_language_resolves_via_alias(appctx):
    """The legacy `language` param resolves to each language's default formatter."""
    for fid, _bin, language, src, _needle in CASES:
        if not binary_present(_bin):
            continue
        r = appctx.client.post("/api/format", json={"code": src, "language": language})
        assert r.status_code == 200, (language, r.text)


def test_classic_formatter_runs_in_suite(appctx):
    if not binary_present("gofmt"):
        pytest.skip("gofmt not installed")
    rec = seed_passing_test(appctx.client, "go", "package main\nfunc main(){x:=1;_=x}\n")
    out = appctx.client.post(f"/api/tests/{rec['id']}/run", json={}).json()
    assert out["status"] == "pass"
