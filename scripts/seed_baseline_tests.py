#!/usr/bin/env python3
"""Seed the baseline formatting test suite.

Re-creates backend/tests/** from a single source of truth grounded in:
  - LOGS-4271  — the config setup ticket (agreed rules)
  - review/13704587 — the config-review PR (inline discussion threads)
  - LOGS-5799  — the follow-up ticket of remaining formatting problems

Test modes:
  lock : expected = what the current config produces. A green regression guard
         that locks an agreed style decision; turns red if the config changes.
  want : expected = an author-written desired output the config does NOT yet
         achieve (a still-open issue). Stays red until fixed.
  guard: like lock, but the input is the *old bad* form — proves the current
         config/clang-format version no longer reproduces it.

Run against a running instance:  python3 scripts/seed_baseline_tests.py
"""

import json
import sys
import urllib.request

BASE = "http://localhost:3000"
LOGS5799 = "https://st.yandex-team.ru/LOGS-5799"
LOGS4271 = "https://st.yandex-team.ru/LOGS-4271"
PR = "https://a.yandex-team.ru/review/13704587"


def _post(path, payload):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))


def fmt(code, language="cpp"):
    return _post("/api/format", {"code": code, "language": language})["formatted"]


def _list():
    return json.load(urllib.request.urlopen(BASE + "/api/tests"))


def _delete(tid):
    req = urllib.request.Request(BASE + f"/api/tests/{tid}", method="DELETE")
    urllib.request.urlopen(req)


# (name, language, mode, input, desired_or_None, muted, note)
CASES = [
 # ─────────────────────────── C++ style locks (config = PR outcome) ──────────
 ("Style: pointer binds to the type (T* p)", "cpp", "lock",
  "int *p = nullptr;", None, False, f"PointerAlignment: Left. {PR}"),
 ("Style: reference binds to the type (T& r)", "cpp", "lock",
  "int x = 0;\nint &r = x;", None, False, f"PointerAlignment: Left. {PR}"),
 ("Style: namespace gets a closing comment", "cpp", "lock",
  "namespace NFoo {\nint X;\n}", None, False, f"FixNamespaceComments: true. {PR}"),
 ("Style: space before paren in control statements", "cpp", "lock",
  "if (x) {\n    F();\n}", None, False, f"SpaceBeforeParens: ControlStatements. {PR}"),
 ("Style: braces auto-inserted into a brace-less if", "cpp", "lock",
  "if (x)\n    DoIt();", None, False,
  f"InsertBraces: true — agreed instead of a separate clang-tidy pass. {LOGS4271}"),
 ("Style: braces auto-inserted into a brace-less for", "cpp", "lock",
  "for (int i = 0; i < n; ++i)\n    Step(i);", None, False,
  f"InsertBraces: true. {LOGS4271}"),
 ("Style: 4-space indentation", "cpp", "lock",
  "int main() {\nreturn 0;\n}", None, False, f"IndentWidth: 4. {PR}"),
 ("Style: access modifier sits at -4 (AccessModifierOffset)", "cpp", "lock",
  "class TFoo {\npublic:\n    int X;\n\nprivate:\n    int Y;\n};", None, False,
  f"AccessModifierOffset: -4. {PR}"),
 ("Style: case labels are indented", "cpp", "lock",
  "switch (x) {\ncase 1:\nA();\nbreak;\ndefault:\nB();\n}", None, False,
  f"IndentCaseLabels: true. {PR}"),
 ("Style: empty block keeps a space {}", "cpp", "lock",
  "void F() {}", None, False, f"SpaceInEmptyBlock: true. {PR}"),
 ("Style: class opening brace stays on the header line", "cpp", "lock",
  "class TFoo\n{\npublic:\n    int X;\n};", None, False,
  f"BraceWrapping.AfterClass: false — opening brace on the same line. {LOGS4271}"),
 ("Style: function opening brace stays on the signature line", "cpp", "lock",
  "int Add(int a, int b)\n{\n    return a + b;\n}", None, False,
  f"BraceWrapping.AfterFunction: false. {LOGS4271}"),
 ("Style: short function is not collapsed onto one line", "cpp", "lock",
  "struct T {\n    int Get() { return X; }\n    int X;\n};", None, False,
  f"AllowShortFunctionsOnASingleLine: false. {PR}"),
 ("Style: short enum is not collapsed onto one line", "cpp", "lock",
  "enum class EKind { First, Second, Third };", None, False,
  f"AllowShortEnumsOnASingleLine: false. {PR}"),
 ("Style: blank line between function definitions", "cpp", "lock",
  "int A() {\n    return 1;\n}\nint B() {\n    return 2;\n}", None, False,
  f"SeparateDefinitionBlocks: Always. {PR}"),
 ("Style: template declaration breaks before the function", "cpp", "lock",
  "template <typename T> T Identity(T value);", None, False,
  f"AlwaysBreakTemplateDeclarations: Yes — template on its own line. PR thread: "
  f"'template и class должны быть на разных строках'. {PR}"),
 ("Style: long template parameter list — one per line", "cpp", "lock",
  "template <typename TRow, typename TOutput, typename TKeyRequest, typename TStateProxy, bool SimpleKeyRequest = false>\nclass TProcessor {};",
  None, False,
  f"Long template decl wraps each parameter. PR thread #32. {PR}"),
 ("Style: long function arguments — one per line (no bin-packing)", "cpp", "lock",
  "void Configure(const TOptions& options, const TContext& context, int retryCount, bool verboseLogging);",
  None, False, f"BinPackArguments: false, AllowAllArgumentsOnNextLine: false. {PR}"),
 ("Style: constructor initializer list — leading comma, one per line", "cpp", "lock",
  "struct TFoo {\n    TFoo(int a, int b, int c) : A_(a), B_(b), C_(c) {}\n    int A_, B_, C_;\n};",
  None, False,
  f"BreakConstructorInitializers: BeforeComma, PackConstructorInitializers: Never. {PR}"),
 ("Style: inheritance list breaks before the comma", "cpp", "lock",
  "class TDerived : public TBaseOne, public TBaseTwo, public TBaseThree, public TBaseFour {};",
  None, False, f"BreakInheritanceList: BeforeComma. {PR}"),
 ("Style: ternary breaks before the operator", "cpp", "lock",
  "const auto value = someConditionThatIsFairlyLong ? theFirstAlternativeValue : theSecondAlternativeValue;",
  None, False, f"BreakBeforeTernaryOperators: true. {PR}"),
 ("Style: concept declaration breaks before the concept", "cpp", "lock",
  "template <typename T>\nconcept TScorable = requires(T t) { { t.Score() } -> std::convertible_to<double>; };",
  None, False, f"BreakBeforeConceptDeclarations: true. {PR}"),
 ("Style: chained method calls indentation", "cpp", "lock",
  "const auto result = builder.WithFirstOption(1).WithSecondOption(2).WithThirdOption(3).Build();",
  None, False,
  f"PR thread #8: ')->Run()' breaking was discussed. Locks current behaviour. {PR}"),

 # ─────────────────────────── LOGS-5799 fixed problems (lock) ────────────────
 ("P1: class opening brace stays on the header line", "cpp", "lock",
  "class TFoo\n{\npublic:\n    int X;\n};", None, False,
  f"LOGS-5799 problem 1 (fixed). {LOGS5799}"),
 ("P2: return type stays on the function-name line", "cpp", "lock",
  "std::vector<TString> ComputeReducedSessionsForRequest(const TRequest& request, int limitValue, bool flag);",
  None, False, f"LOGS-5799 problem 2 (fixed): wrap after '(' by args. {LOGS5799}"),
 ("P4: consistent closing-bracket indentation", "cpp", "lock",
  "DoCall(Wrap([&] {\nProcess();\nFinish();\n}), MakeOptions(optionAlpha, optionBeta, optionGamma, optionDelta));",
  None, False, f"LOGS-5799 problem 4 (fixed): no ragged closing-bracket staircase. {LOGS5799}"),
 ("P7: empty () call is not split onto two lines", "cpp", "guard",
  "NAntifraud::NProto::TUndoChEventVerdict& undoCheventVerdict = *res.MutableUndoCheventVerdictMsg(\n);",
  None, False,
  f"LOGS-5799 problem 7: empty () used to split; clang-format 22 keeps it on one line. {LOGS5799}"),

 # ─────────────────────────── LOGS-5799 open problems (want) ─────────────────
 ("P3: no line break after '=' in an assignment (muted)", "cpp", "want",
  "const auto verdict = response.MutableProfileData()->CalculateSomethingWithLongName(argumentOne, argumentTwo);",
  "const auto verdict = response.MutableProfileData()->CalculateSomethingWithLongName(\n"
  "    argumentOne, argumentTwo);",
  True, f"LOGS-5799 problem 3 (unfixable): only AlignAfterOpenBracket: DontAlign removes it, "
  f"which breaks other places. Muted compromise. {LOGS5799}"),
 ("P5: nested designated initializers indentation", "cpp", "want",
  "TSomeLongConfigName cfg = {.FieldNumberOne = {{.A = 1, .B = 2}, {.A = 3, .B = 4}}, .FieldNumberTwo = {{.A = 5}}};",
  "TSomeLongConfigName cfg = {\n    .FieldNumberOne =\n        {\n            {.A = 1, .B = 2},\n"
  "            {.A = 3, .B = 4},\n        },\n    .FieldNumberTwo = {{.A = 5}},\n};",
  False, f"LOGS-5799 problem 5 (open). {LOGS5799}"),
 ("P6: lambda arguments keep a readable indentation", "cpp", "want",
  "std::visit(TOverloaded{[](const TFirst& f) { return f.Value; }, [](const TSecond& s) { return s.Other; }}, variant);",
  "std::visit(\n    TOverloaded{\n        [](const TFirst& f) { return f.Value; },\n"
  "        [](const TSecond& s) { return s.Other; },\n    },\n    variant);",
  False, f"LOGS-5799 problem 6: ticket marks it fixed, but this config still aligns lambda args "
  f"to the brace. Also PR threads #37 #38. {LOGS5799}"),
 ("P8: nested template/call arguments indentation", "cpp", "want",
  "TableReader_ = new NYT::TTableReader<NProtoBuf::Message>(new NYT::TLenvalProtoTableReader(Client_->CreateRawReader(TablePaths_.at(CurrentTableIdx_), NYT::TFormat::Protobuf({ProtoMessagePrototype_->GetDescriptor()}, false))));",
  "TableReader_ = new NYT::TTableReader<NProtoBuf::Message>(\n    new NYT::TLenvalProtoTableReader(\n"
  "        Client_->CreateRawReader(\n            TablePaths_.at(CurrentTableIdx_),\n"
  "            NYT::TFormat::Protobuf({ProtoMessagePrototype_->GetDescriptor()}, false))));",
  False, f"LOGS-5799 problem 8 (open). {LOGS5799}"),

 # ─────────────────────────── PR review/13704587 open threads (want) ─────────
 ("PR: multiline if — operator at line start, ) { de-indented", "cpp", "want",
  "void F() {\n    if (!signMessages->empty() && signMessages->begin()->WriteTimestamp <= notificationWriteTimestamp) {\n        G();\n    }\n}",
  "void F() {\n    if (\n        !signMessages->empty()\n"
  "        && signMessages->begin()->WriteTimestamp <= notificationWriteTimestamp\n    ) {\n        G();\n    }\n}",
  False, f"PR thread #31: preferred multiline-if style (operator leading, ')' de-indented). {PR}"),
 ("PR: blank line after namespace open and before close", "cpp", "want",
  "namespace NFoo {\nint Foo();\nint Bar();\n}",
  "namespace NFoo {\n\nint Foo();\nint Bar();\n\n} // namespace NFoo",
  False, f"PR thread #35: wanted one blank line after '{{' and before '}}' of a namespace — "
  f"not configurable in clang-format. {PR}"),

 # ─────────────────────────── Python: single quotes ─────────────────────────
 ("Py quotes: double string becomes single", "python", "lock",
  'x = "hello"', None, False, "ruff quote-style = single."),
 ("Py quotes: single string stays single", "python", "lock",
  "x = 'hello'", None, False, "ruff quote-style = single."),
 ("Py quotes: string with an apostrophe keeps double quotes", "python", "lock",
  'msg = "it\'s fine"', None, False,
  "ruff keeps double quotes to avoid escaping the apostrophe."),
 ("Py quotes: f-string becomes single-quoted", "python", "lock",
  'name = f"value {x}"', None, False, "ruff quote-style = single."),
 ("Py quotes: dict keys and values become single-quoted", "python", "lock",
  'd = {"a": "b", "c": "d"}', None, False, "ruff quote-style = single."),
 ("Py quotes: bytes literal becomes single-quoted", "python", "lock",
  'data = b"payload"', None, False, "ruff quote-style = single."),
 ("Py quotes: docstring stays triple double-quoted", "python", "lock",
  'def f():\n    "single-line docstring"\n    return 1', None, False,
  "ruff normalises docstrings to double quotes."),
 ("Py quotes: mixed quotes normalised to single", "python", "lock",
  "row = dict(name=\"Bob\", city='NY', tag=\"vip\")", None, False,
  "ruff quote-style = single."),

 # ─────────────────────────── Python: formatting ────────────────────────────
 ("Py: dict and operator spacing", "python", "lock",
  "x={1:2,3:4}\ny=1+2*3", None, False, "ruff format spacing."),
 ("Py: blank lines between top-level defs", "python", "lock",
  "def a():\n    return 1\ndef b():\n    return 2", None, False,
  "ruff inserts two blank lines between top-level defs."),
 ("Py: magic trailing comma keeps the call expanded", "python", "lock",
  "f(\n    alpha,\n    beta,\n)", None, False,
  "skip-magic-trailing-comma = false → trailing comma keeps it multiline."),
 ("Py: long call wraps at the configured line length", "python", "lock",
  "result = compute_something(first_argument, second_argument, third_argument, fourth_one)",
  None, False, "ruff line-length from ruff.toml."),
 ("P9: Python boolean operator wrap inside dict()", "python", "want",
  "config = dict(RedirBuilderSendNonBaobabClicks=is_images_click_log or is_video_click_log or is_baobab_click_log, Other=1)",
  "config = dict(\n    RedirBuilderSendNonBaobabClicks=is_images_click_log\n"
  "        or is_video_click_log\n        or is_baobab_click_log,\n    Other=1,\n)",
  False, f"LOGS-5799 problem 9 (open): 'or' lands at the start of the next line. {LOGS5799}"),
]


def main():
    # wipe existing tests
    for t in _list():
        _delete(t["id"])

    warnings = []
    for name, lang, mode, src, desired, muted, note in CASES:
        if mode in ("lock", "guard"):
            expected = fmt(src, lang)
        else:
            expected = desired
        _post("/api/tests", {
            "name": name, "language": lang, "input": src,
            "expected": expected, "muted": muted, "note": note,
        })
        # sanity: a want test that already matches is mislabelled
        if mode == "want" and not muted and fmt(src, lang).rstrip("\n") == (expected or "").rstrip("\n"):
            warnings.append(name)

    run = _post("/api/tests/run", {})
    print("summary:", run["summary"])
    for r in sorted(run["results"], key=lambda r: (r["language"], r["status"], r["name"])):
        print(f"  {r['status']:7} [{r['language']:6}] {r['name']}")
    if warnings:
        print("\n!! WANT tests that unexpectedly pass (fix their desired):", file=sys.stderr)
        for w in warnings:
            print("   -", w, file=sys.stderr)


if __name__ == "__main__":
    main()
