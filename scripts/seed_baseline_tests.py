#!/usr/bin/env python3
"""Seed the baseline formatting test suite.

Re-creates backend/tests/** from a single source of truth grounded in:
  - LOGS-4271  — the config setup ticket (agreed rules)
  - review/13704587 — the config-review PR (description problems + threads)
  - LOGS-5799  — the follow-up ticket of remaining formatting problems

Every problem case is an **anonymised reconstruction**: the issue was looked up
in the ticket/PR, then rebuilt with the same structural context (namespace /
class / method nesting, nested calls) that drives clang-format's column-based
wrapping — but with generic names and no real source code (NDA). Only the
essence is kept.

Test modes:
  lock : expected = what the current config produces. A green regression guard
         that locks an agreed style decision; turns red if the config changes.
  want : expected = an author-written desired output the config does NOT yet
         achieve (a still-open issue). Stays red until fixed.
  guard: like lock, but the input is the *old bad* form — proves the current
         config/clang-format version no longer reproduces it.
  muted tests (muted=True) show yellow regardless — accepted compromises.

Run against a running instance:  python3 scripts/seed_baseline_tests.py
"""

import json
import sys
import urllib.request

import os

# Target instance. Defaults to the local dev server; point at prod with
#   FQ_BASE=https://fq.alchemmist.xyz python3 scripts/seed_baseline_tests.py
BASE = os.environ.get("FQ_BASE", "http://localhost:3000").rstrip("/")
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
 ("Style: short function is not collapsed onto one line", "cpp", "lock",
  "struct T {\n    int Get() { return X; }\n    int X;\n};", None, False,
  f"AllowShortFunctionsOnASingleLine: false. {PR}"),
 ("Style: short enum is not collapsed onto one line", "cpp", "lock",
  "enum class EKind { First, Second, Third };", None, False,
  f"AllowShortEnumsOnASingleLine: false. {PR}"),
 ("Style: blank line between function definitions", "cpp", "lock",
  "int A() {\n    return 1;\n}\nint B() {\n    return 2;\n}", None, False,
  f"SeparateDefinitionBlocks: Always. {PR}"),
 ("Style: ternary breaks before the operator", "cpp", "lock",
  "const auto value = someConditionThatIsFairlyLong ? theFirstAlternativeValue : theSecondAlternativeValue;",
  None, False, f"BreakBeforeTernaryOperators: true. {PR}"),
 ("Style: function opening brace stays on the signature line", "cpp", "lock",
  "int Add(int a, int b)\n{\n    return a + b;\n}", None, False,
  f"BraceWrapping.AfterFunction: false. {LOGS4271}"),
 ("Style: template declaration breaks before the function", "cpp", "lock",
  "template <typename T> T Identity(T value);", None, False,
  f"AlwaysBreakTemplateDeclarations: Yes. {PR}"),
 ("Style: long template parameter list — one per line", "cpp", "lock",
  "template <typename TRow, typename TOutput, typename TKeyRequest, typename TStateProxy, bool SimpleKeyRequest = false>\nclass TProcessor {};",
  None, False, f"Long template decl wraps each parameter. {PR}"),
 ("Style: long function arguments — one per line (no bin-packing)", "cpp", "lock",
  "void Configure(const TOptions& options, const TContext& context, int retryCount, bool verboseLogging);",
  None, False, f"BinPackArguments: false. {PR}"),
 ("Style: constructor initializer list — leading comma, one per line", "cpp", "lock",
  "struct TFoo {\n    TFoo(int a, int b, int c) : A_(a), B_(b), C_(c) {}\n    int A_, B_, C_;\n};",
  None, False, f"BreakConstructorInitializers: BeforeComma, PackConstructorInitializers: Never. {PR}"),
 ("Style: inheritance list breaks before the comma", "cpp", "lock",
  "class TDerived : public TBaseOne, public TBaseTwo, public TBaseThree, public TBaseFour {};",
  None, False, f"BreakInheritanceList: BeforeComma. {PR}"),
 ("Style: concept declaration breaks before the concept", "cpp", "lock",
  "template <typename T>\nconcept TScorable = requires(T t) { { t.Score() } -> std::convertible_to<double>; };",
  None, False, f"BreakBeforeConceptDeclarations. {PR}"),
 ("Style: chained method calls indentation", "cpp", "lock",
  "const auto result = builder.WithFirstOption(1).WithSecondOption(2).WithThirdOption(3).Build();",
  None, False, f"Locks current chained-call behaviour (PR thread #8). {PR}"),

 # ─── LOGS-5799 problem 1 (fixed) — class opening brace, in a namespace ───────
 ("P1: class opening brace stays on the header line", "cpp", "lock",
  "namespace app {\nclass TWidget : public IWidget {\npublic:\nint Value;\n};\n}",
  None, False,
  f"LOGS-5799 problem 1 (fixed). Anonymised reconstruction. {LOGS5799}"),

 # ─── problem 2 (fixed) — return type stays with the name, args wrap ──────────
 ("P2: return type stays on the function-name line", "cpp", "lock",
  "namespace app {\nclass TSessionStore {\npublic:\n"
  "TVector<TReducedSession> ComputeReducedSessionsForRequest(const TRequest& request, int limitValue, bool flag);\n};\n}",
  None, False,
  f"LOGS-5799 problem 2 (fixed): wrap after '(' by args. Anonymised. {LOGS5799}"),

 # ─── problem 4 (fixed) — closing brackets in a nested call ───────────────────
 ("P4: consistent closing-bracket indentation", "cpp", "lock",
  "namespace app {\nvoid TWidget::Process() {\n"
  "RunPipeline(WrapHandler([&] {\nDoStep();\nFinalize();\n}), MakeOptions(optionAlpha, optionBeta, optionGamma, optionDelta));\n}\n}",
  None, False,
  f"LOGS-5799 problem 4 (fixed): no ragged closing-bracket staircase. Anonymised. {LOGS5799}"),

 # ─── problem 7 (open) — empty () splits when the line overflows ──────────────
 ("P7: empty () splits onto two lines when the line overflows", "cpp", "want",
  "namespace app {\nvoid TWidget::Finish(TResponse& response) {\n"
  "NDomain::NProto::TUndoVerdictResult& undoVerdictResult = *response.MutableUndoVerdictResultMsg();\n}\n}",
  "namespace app {\nvoid TWidget::Finish(TResponse& response) {\n"
  "    NDomain::NProto::TUndoVerdictResult& undoVerdictResult =\n"
  "        *response.MutableUndoVerdictResultMsg();\n}\n} // namespace app",
  False,
  f"LOGS-5799 problem 7 (open): when the declaration exceeds the 100-col limit, the "
  f"empty () is the only break point — '(' stays at the end of the line and ');' dangles "
  f"on its own. Wanted: break after '=' and keep () together. The length matters: a "
  f"shorter line fits and never reproduces it. Anonymised reconstruction. {LOGS5799}"),

 # ─── problem 3 (unfixable, muted) — break after '=' in a parenthesised expr ──
 ("P3: no line break after '=' in an assignment (muted)", "cpp", "want",
  "namespace app {\nclass TWidget {\nvoid Process(const TMessage& message) {\n"
  "auto parseLag = (TInstant::Now() - TInstant::Seconds(message.GetProfileTimestamps().GetStageWallTime()));\n}\n};\n}",
  "namespace app {\nclass TWidget {\n    void Process(const TMessage& message) {\n"
  "        auto parseLag = (TInstant::Now() -\n"
  "            TInstant::Seconds(message.GetProfileTimestamps().GetStageWallTime()));\n"
  "    }\n};\n} // namespace app",
  True,
  f"LOGS-5799 problem 3 (🙈): the right-hand side block-indents with the closing ')' "
  f"dangling on its own line (staircase). AlignAfterOpenBracket: DontAlign produces the "
  f"clean wrapped form (this desired) but is global and regresses agreed styles, so it's a "
  f"muted compromise. Anonymised reconstruction. {LOGS5799}"),

 # ─── problem 5 (open) — nested designated initializers indentation ──────────
 ("P5: nested designated initializers indentation", "cpp", "want",
  "namespace app {\nvoid TWidget::Configure() {\n"
  "TModelConfig config = {.Buckets = {{.Lo = 1000, .Hi = 2000}, {.Lo = 3000, .Hi = 4000}, {.Lo = 5000, .Hi = 6000}, {.Lo = 7000, .Hi = 8000}}, .Limit = 9};\n}\n}",
  "namespace app {\nvoid TWidget::Configure() {\n    TModelConfig config = {\n"
  "        .Buckets =\n            {\n                {.Lo = 1000, .Hi = 2000},\n"
  "                {.Lo = 3000, .Hi = 4000},\n                {.Lo = 5000, .Hi = 6000},\n"
  "                {.Lo = 7000, .Hi = 8000},\n            },\n        .Limit = 9,\n    };\n}\n} // namespace app",
  True,
  f"LOGS-5799 problem 5 (🙈): the block-indented inner list is unreachable — no option "
  f"combination produces it; AlignAfterOpenBracket/Cpp11BracedListStyle only regress "
  f"other styles. Anonymised reconstruction. {LOGS5799}"),

 # ─── problem 6 (fixed) — lambda argument bodies indent correctly ────────────
 ("P6: lambda argument bodies indent correctly (fixed)", "cpp", "lock",
  "namespace app {\nvoid TWidget::Handle(const TVariant& value) {\n"
  "std::visit(TOverloaded{[](const TFirst& f) { return f.Value; }, [](const TSecond& s) { return s.Other; }}, value);\n}\n}",
  None,
  False,
  f"LOGS-5799 problem 6 (fixed): a lambda passed as an argument (std::visit / "
  f"TOverloaded) now indents its body under the lambda declaration instead of drifting "
  f"to a wrong level. Anonymised reconstruction. {LOGS5799}"),

 # ─── problem 8 (open) — nested template/call argument indentation ───────────
 ("P8: nested template/call arguments indentation", "cpp", "want",
  "namespace app {\nvoid TWidget::Open() {\n"
  "Reader_ = new NLib::TTableReader<NProto::TMessage>(new NLib::TProtoReader(client->CreateRawReader(paths.at(currentIndex), NLib::TFormat::Protobuf({prototype->GetDescriptor()}, false))));\n}\n}",
  "namespace app {\nvoid TWidget::Open() {\n    Reader_ = new NLib::TTableReader<NProto::TMessage>(\n"
  "        new NLib::TProtoReader(\n            client->CreateRawReader(\n"
  "                paths.at(currentIndex),\n                NLib::TFormat::Protobuf({prototype->GetDescriptor()}, false))));\n}\n} // namespace app",
  True,
  f"LOGS-5799 problem 8 (🙈): progressive indentation of nested calls is unreachable — "
  f"no option combination produces it. Anonymised reconstruction. {LOGS5799}"),

 # ─── PR review/13704587 — still-open threads (want) ─────────────────────────
 ("PR: multiline if wraps the brace onto its own line (option в2)", "cpp", "lock",
  "namespace app {\nvoid TWidget::Process(TState* state) {\n"
  "if (!pendingMessages->empty() && pendingMessages->begin()->WriteTimestamp <= notificationWriteTimestamp) {\nHandle(state);\n}\n}\n}",
  None,
  False,
  f"PR problem 7, option в2 (adopted): when an if condition wraps across lines the "
  f"opening '{{' moves to its own line while the operator stays trailing and ')' stays "
  f"attached. comment-18341038 wanted ') {{' de-indented — this is that result. "
  f"Anonymised reconstruction. {PR}/details#comment-18341038"),
 ("PR: blank line after namespace open and before close (muted)", "cpp", "want",
  "namespace app {\nint Foo();\nint Bar();\n}",
  "namespace app {\n\nint Foo();\nint Bar();\n\n} // namespace app",
  True,
  f"comment-18341258: a reviewer wanted one blank line right after '{{' and before '}}' "
  f"of a namespace; clang-format cannot insert a literal blank line (the only offered "
  f"alternative was wrapping the brace). Unfixable, muted. {PR}/details#comment-18341258"),

 # ─── PR review/13704587 — accepted compromises (muted, 🙈 unfixable) ─────────
 ("PR3: arrow operator stays attached to the closing )", "cpp", "want",
  "namespace app {\nvoid TWidget::Run() {\n"
  "auto result = sessionBuilder.MakeReducedSessionProcessor(firstArgument, secondArgument, thirdArgument)->Run();\n}\n}",
  "namespace app {\nvoid TWidget::Run() {\n    auto result =\n"
  "        sessionBuilder.MakeReducedSessionProcessor(firstArgument, secondArgument, thirdArgument)->Run();\n}\n} // namespace app",
  True,
  f"PR description problem 3 (🙈) + comment-18183104: '`)->Run()`' becomes "
  f"'`)` newline `->Run()`'. Anonymised reconstruction. {PR}/details#comment-18183104"),
 ("PR: template closing > on its own line (like a wrapped ) )", "cpp", "want",
  "namespace app {\ntemplate <typename TStateRequestMessage, typename TStateDiffMessage, typename TOutputStateMessage, typename TValidatorContext>\nclass TStateValidator {};\n}",
  "namespace app {\ntemplate <\n    typename TStateRequestMessage,\n    typename TStateDiffMessage,\n"
  "    typename TOutputStateMessage,\n    typename TValidatorContext\n>\nclass TStateValidator { };\n} // namespace app",
  True,
  f"comment-18340323: wanted the closing '>' of a wrapped template on its own line, "
  f"analogous to '()'. Anonymised reconstruction. {PR}/details#comment-18340323"),
 ("PR: opening { on next line for ctors with an initializer list", "cpp", "want",
  "namespace app {\nclass TWidget {\npublic:\n"
  "TWidget(int firstValue, int secondValue) : First_(firstValue), Second_(secondValue) {\nInitialize();\n}\n\nprivate:\nint First_, Second_;\n};\n}",
  "namespace app {\nclass TWidget {\npublic:\n    TWidget(int firstValue, int secondValue)\n"
  "        : First_(firstValue)\n        , Second_(secondValue)\n    {\n        Initialize();\n    }\n\n"
  "private:\n    int First_, Second_;\n};\n} // namespace app",
  True,
  f"comment-18340933: wanted '{{' on the next line for constructors with an initializer "
  f"list. Anonymised reconstruction. {PR}/details#comment-18340933"),
 ("PR: compound requirement stays on one line ({ expr } -> Type)", "cpp", "want",
  "namespace app {\ntemplate <typename TMessage>\nconcept CMessage = requires(TMessage msg) {\n"
  "requires CProtoMessage<TMessage>;\n{ msg.GetSign() } -> std::same_as<NProto::int64>;\n"
  "{ msg.GetTimestamp() } -> std::same_as<NProto::uint64>;\n};\n}",
  "namespace app {\ntemplate <typename TMessage>\nconcept CMessage = requires (TMessage msg) {\n"
  "    requires CProtoMessage<TMessage>;\n    { msg.GetSign() } -> std::same_as<NProto::int64>;\n"
  "    { msg.GetTimestamp() } -> std::same_as<NProto::uint64>;\n};\n} // namespace app",
  True,
  f"comment-18195479 (PR problem 7, requires example): clang-format 18 breaks "
  f"'{{ expr }} -> Type' across lines even with AllowShortCompoundRequirementOnASingleLine "
  f"(effective only in 19+). Anonymised reconstruction. {PR}/details#comment-18195479"),

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
 # P9 (open) — Python boolean operator wrap, in a real-ish dict() context
 ("P9: Python boolean operator wrap inside dict() (muted)", "python", "want",
  "def build_config():\n    return dict(RedirBuilderSendNonBaobabClicks=is_images_click_log or is_video_click_log or is_baobab_click_log, Other=1)",
  "def build_config():\n    return dict(\n        RedirBuilderSendNonBaobabClicks=(\n"
  "            is_images_click_log or is_video_click_log or is_baobab_click_log\n"
  "        ),\n        Other=1,\n    )",
  True,
  f"LOGS-5799 problem 9 (unfixable, 🙈): 'or'/'and' land at the start of the next line "
  f"at the same level as the dict keys — inside dict(...) it reads like a separate key. "
  f"ruff won't reindent (Black issue 4123). Desired shows the manual workaround: wrap "
  f"the value in parens. Anonymised reconstruction. {LOGS5799}"),
]


def main():
    for t in _list():
        _delete(t["id"])

    warnings = []
    for name, lang, mode, src, desired, muted, note in CASES:
        expected = fmt(src, lang) if mode in ("lock", "guard") else desired
        _post("/api/tests", {
            "name": name, "language": lang, "input": src,
            "expected": expected, "muted": muted, "note": note,
        })
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
