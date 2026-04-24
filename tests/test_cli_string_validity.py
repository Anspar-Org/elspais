# Verifies: REQ-d00085
"""Cross-check every `elspais <cmd> --<flag>` suggestion in source against
the real tyro dataclasses in `args.py`.

Background:
    Commit c04d237 added `--terms` to the `checks` follow-up hints in
    `_FOLLOWUP_COMMANDS`, but the flag didn't exist on `ChecksArgs` at the
    time. Users who followed the hint hit "Unrecognized options: --terms".
    Nothing caught the drift until it hit the user.

What this test does:
    1. Introspects the `Command` union in `elspais.commands.args` to build
       a map of subcommand (and one level of nested action) -> valid flag
       set, derived from dataclass fields and tyro metadata.
    2. Walks every `.py` file under `src/elspais/`, extracts string
       literals and f-string shells via `ast`, and scans each for the
       pattern `elspais <subcmd> [action] [args...]`.
    3. For each extracted invocation, verifies that every `--flag` /
       `-x` token maps to a real field or alias on the target dataclass.
    4. Reports a precise list of (file, line, subcmd, bad_flag) on
       failure — so fixing future regressions is a direct lookup.

Coverage:
    * Flag existence: every `--foo` / `-x` token must be a real field /
      alias on the target dataclass (or a global flag).
    * Nested action names: `elspais config <X>` requires `<X>` to be
      one of ConfigArgs's registered actions.
    * Literal-typed positionals: e.g. `elspais docs <topic>` requires
      `<topic>` to be one of `DOCS_TOPICS`.

Non-goals:
    * Tracking flag values beyond consuming one token for non-bool flags
      (so we don't misidentify a flag's value as a positional). Literal
      value validity for flags (`--format badformat`) is already caught
      by tyro at parse time.
    * F-string *expressions* — the literal-ness of `{var}` is lost at
      scan time; those are replaced with `{?}` and skipped.
"""

from __future__ import annotations

import ast
import dataclasses
import re
import typing
from pathlib import Path

import pytest

from elspais.commands.args import Command, GlobalArgs

# ---------------------------------------------------------------------------
# Build subcommand -> valid flag set
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class SubcommandSpec:
    """Validation surface for one subcommand (or nested action) variant.

    Token walker uses `flags` to tell which tokens are flags (and which
    consume a following value), `positional_choices` to validate slotted
    Literal positionals, and `nested_actions` to require a valid action
    name at positional slot 0.
    """

    flags: dict[str, bool] = dataclasses.field(default_factory=dict)
    """Flag token → True if it consumes a value, False for bool switches."""

    positional_choices: list[set[str] | None] = dataclasses.field(default_factory=list)
    """Per-slot allowed values. None = unconstrained (free-form path/ID/etc)."""

    nested_actions: set[str] = dataclasses.field(default_factory=set)
    """If non-empty, slot 0 must be one of these (and variant dispatch switches
    to the matching nested-action spec)."""


def _is_positional_field(t: typing.Any) -> bool:
    """True iff the field type is wrapped in `tyro.conf.Positional[...]`.

    We detect this by looking for `_markers.Positional` (or any metadata
    whose repr contains `Positional`) inside the Annotated chain.
    """
    cur = t
    while typing.get_origin(cur) is typing.Annotated:
        for m in typing.get_args(cur)[1:]:
            # tyro marks positionals via a singleton marker (str repr "Positional")
            if repr(m).startswith("Positional") or type(m).__name__.endswith("Positional"):
                return True
        cur = typing.get_args(cur)[0]
    return False


def _literal_choices(t: typing.Any) -> set[str] | None:
    """If `t` is ultimately a `Literal[...]` of string values, return the
    choices; else None. Walks Annotated and Optional wrappers.
    """
    cur = t
    while True:
        origin = typing.get_origin(cur)
        if origin is typing.Annotated:
            cur = typing.get_args(cur)[0]
            continue
        if origin is typing.Union or type(cur).__name__ == "UnionType":
            # Strip None from Optional and see if remaining is a single Literal.
            non_none = [a for a in typing.get_args(cur) if a is not type(None)]
            if len(non_none) == 1:
                cur = non_none[0]
                continue
            return None
        if origin is typing.Literal:
            vals = typing.get_args(cur)
            str_vals = [v for v in vals if isinstance(v, str)]
            if len(str_vals) == len(vals):
                return set(str_vals)
            return None
        return None


def _spec_for_dataclass(cls: type) -> SubcommandSpec:
    """Build a SubcommandSpec from a dataclass's fields + tyro metadata."""
    spec = SubcommandSpec()
    spec.flags["-h"] = False
    spec.flags["--help"] = False
    try:
        hints = typing.get_type_hints(cls, include_extras=True)
    except Exception:
        return spec
    for field in dataclasses.fields(cls):
        if field.name == "action":
            continue  # handled separately via nested_actions
        t = hints.get(field.name, field.type)
        arg_name = field.name.replace("_", "-")
        aliases: tuple[str, ...] = ()
        inner = t
        if typing.get_origin(t) is typing.Annotated:
            inner = typing.get_args(t)[0]
            for m in typing.get_args(t)[1:]:
                if hasattr(m, "name") and m.name:
                    arg_name = m.name
                if hasattr(m, "aliases") and m.aliases:
                    aliases = tuple(m.aliases)
        is_bool = inner is bool
        if _is_positional_field(t):
            spec.positional_choices.append(_literal_choices(t))
            continue
        spec.flags[f"--{arg_name}"] = not is_bool
        if is_bool:
            spec.flags[f"--no-{arg_name}"] = False
        for a in aliases:
            spec.flags[a] = not is_bool
    return spec


def _flags_for_dataclass(cls: type) -> set[str]:
    """Back-compat: return just the flag names as a set."""
    return set(_spec_for_dataclass(cls).flags.keys())


def _subcommand_name_from_meta(meta_tuple: tuple) -> str | None:
    """Pull the subcommand name from a tyro.conf.subcommand(...) annotation."""
    for m in meta_tuple:
        # tyro.conf.subcommand produces an object with a `name` attribute
        if hasattr(m, "name") and isinstance(m.name, str):
            return m.name
    return None


def _nested_actions(cls: type) -> dict[str, type]:
    """If `cls` has an `action` field with one or more Annotated action
    dataclasses (each carrying a `tyro.conf.subcommand(...)` name), return
    {action_name: action_cls}. Empty dict if no nested action.

    Handles two shapes:
      1. Union of `Annotated[X, subcommand("a")]` variants  (e.g. ConfigArgs)
      2. Single `Annotated[X, subcommand("a"), ...]` alias  (e.g. LinkArgs)
    """
    result: dict[str, type] = {}
    try:
        hints = typing.get_type_hints(cls, include_extras=True)
    except Exception:
        return result
    t = hints.get("action")
    if t is None:
        return result

    def _harvest(annotated_t: typing.Any) -> None:
        if typing.get_origin(annotated_t) is not typing.Annotated:
            return
        base, *meta = typing.get_args(annotated_t)
        name = _subcommand_name_from_meta(tuple(meta))
        if name:
            result[name] = base

    # Peel outer Annotated wrappers, keeping track of subcommand metadata
    # on the way in (LinkArgs case: action itself is Annotated[..., subcommand(...)]).
    cur = t
    while typing.get_origin(cur) is typing.Annotated:
        _harvest(cur)
        cur = typing.get_args(cur)[0]

    # After unwrapping, we may have a Union of Annotated variants (ConfigArgs case).
    if typing.get_origin(cur) is typing.Union or type(cur).__name__ == "UnionType":
        for arg in typing.get_args(cur):
            _harvest(arg)
    return result


@pytest.fixture(scope="module")
def subcommand_specs() -> dict[str, SubcommandSpec]:
    """Map "subcmd" and "subcmd action" -> SubcommandSpec.

    Every variant's `flags` dict is pre-merged with GlobalArgs flags so
    the scanner doesn't need to special-case globals.
    """
    global_spec = _spec_for_dataclass(GlobalArgs)

    def _merged(sub_spec: SubcommandSpec) -> SubcommandSpec:
        merged = SubcommandSpec(
            flags={**sub_spec.flags, **global_spec.flags},
            positional_choices=list(sub_spec.positional_choices),
            nested_actions=set(sub_spec.nested_actions),
        )
        return merged

    result: dict[str, SubcommandSpec] = {}
    for arg in typing.get_args(Command):
        if typing.get_origin(arg) is not typing.Annotated:
            continue
        base, *meta = typing.get_args(arg)
        name = _subcommand_name_from_meta(tuple(meta))
        if not name:
            continue
        base_spec = _spec_for_dataclass(base)
        actions = _nested_actions(base)
        base_spec.nested_actions = set(actions.keys())
        result[name] = _merged(base_spec)
        for action_name, action_cls in actions.items():
            result[f"{name} {action_name}"] = _merged(_spec_for_dataclass(action_cls))
    return result


# ---------------------------------------------------------------------------
# Extract `elspais <cmd> ...` strings from source
# ---------------------------------------------------------------------------


# Tokens that terminate a command line when embedded in prose/markdown.
# Quotes are terminators — we don't try to track quote nesting, which means
# we stop scanning at the first ' or ". For validation purposes this is
# exactly what we want: the closing quote of a quoted example (the common
# case) ends the command, and `-m 'msg'` style arguments are the rare case
# where we'd stop slightly early, which doesn't harm flag validation.
# `#` terminates shell comments in code-block examples (e.g. `$ elspais X
# # Short description`).
_TERMINATORS = set("`\"'|\n#")

# A real CLI flag looks like `-<letter>` or `--<letter>...`.
# This explicitly rejects `-->` (HTML comment close), `--` (argparse
# separator), `-123` (a negative number), and bare `-`.
_FLAG_RE = re.compile(r"^--?[a-zA-Z][a-zA-Z0-9-]*$")

# If `elspais` is preceded (on the same line) by one of these tokens, the
# occurrence is not an elspais CLI invocation. Two categories:
#   * Package-name contexts — `pipx runpip elspais install -e <path>`
#     (pipx treats `elspais` as the target package, not a command).
#   * Prose determiners — "the elspais CLI", "an elspais project". These
#     are English noun phrases, not commands. In real CLI hints, `elspais`
#     is preceded by a shell prompt, a quote, a backtick, or nothing (line
#     start), never by an article/possessive.
_NOT_A_CLI_PREFIXES = {
    "runpip",
    "pip",
    "pipx",
    "python",
    "python3",
    "which",
    "the",
    "a",
    "an",
    "your",
    "our",
    "my",
    "this",
    "that",
    "into",
    "from",
    "of",
}

# Regex to locate the anchor. We don't capture args here — we tokenize
# manually below so we can walk past global flags before the subcommand.
_ELSPAIS_RE = re.compile(r"\belspais\b(?!-)")

# Field placeholders that show up in templated examples — skip these.
_PLACEHOLDER_RE = re.compile(r"[{<]")


def _tokenize_command(text: str) -> list[str]:
    """Split the command-line fragment into tokens up to a terminator.

    Stops at: the first quote / backtick / pipe / newline / shell-comment
    `#`, OR a run of 3+ consecutive spaces (used for column-alignment in
    help-text tables like `elspais example --full        Display …`).
    """
    tokens: list[str] = []
    buf: list[str] = []
    space_run = 0
    for ch in text:
        if ch in _TERMINATORS:
            break
        if ch == " ":
            space_run += 1
            if space_run >= 3:
                break
            if buf:
                tokens.append("".join(buf))
                buf = []
            continue
        if ch.isspace():
            # tab / other whitespace: treat as single-space separator
            if buf:
                tokens.append("".join(buf))
                buf = []
            space_run = 0
            continue
        space_run = 0
        buf.append(ch)
    if buf:
        tokens.append("".join(buf))
    return tokens


def _preceded_by_non_cli_token(s: str, pos: int) -> bool:
    """Return True if the word immediately before `s[pos]` is something
    like `runpip` or `pipx` — signalling this `elspais` is a package
    name, not a command.
    """
    # Look back past whitespace; grab the previous word.
    i = pos - 1
    while i >= 0 and s[i].isspace():
        i -= 1
    end = i + 1
    while i >= 0 and not s[i].isspace() and s[i] not in _TERMINATORS:
        i -= 1
    prev = s[i + 1 : end]
    return prev in _NOT_A_CLI_PREFIXES


def _iter_source_strings(py_path: Path) -> list[tuple[int, str]]:
    """Yield (lineno, literal_text) for every string-ish AST node.

    For f-strings, replace each `{expr}` with a neutral `{?}` token so
    that the static parts can still be scanned without tripping the
    regex on raw Python code.
    """
    results: list[tuple[int, str]] = []
    try:
        tree = ast.parse(py_path.read_text(encoding="utf-8"))
    except SyntaxError:
        return results
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            results.append((node.lineno, node.value))
        elif isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    parts.append(v.value)
                else:
                    parts.append("{?}")
            results.append((node.lineno, "".join(parts)))
    return results


@dataclasses.dataclass(frozen=True)
class Finding:
    file: str
    line: int
    subcommand: str
    kind: str  # "flag" | "action" | "positional"
    token: str
    context: str

    def format(self) -> str:
        head = f"{self.file}:{self.line}"
        if self.kind == "flag":
            body = f"`elspais {self.subcommand} ... {self.token}`  — unknown flag"
        elif self.kind == "action":
            body = (
                f"`elspais {self.subcommand} {self.token} ...`  — "
                f"unknown action for `{self.subcommand}`"
            )
        else:
            body = (
                f"`elspais {self.subcommand} ... {self.token}`  — "
                f"positional not in allowed choices"
            )
        return f"  {head}  {body}  (context: {self.context!r})"


# Back-compat alias kept so older direct callers of `_scan_string` keep
# working — tests in this module import `BadFlag` by name.
BadFlag = Finding


# Literal strings that should not be scanned (declare allowlist here,
# keyed by substring match — keeps the guard honest).
_ALLOWLIST: set[str] = set()


def _consume_flag_and_value(
    tokens: list[str], i: int, spec: SubcommandSpec
) -> tuple[int, str | None]:
    """If tokens[i] is a valid flag for `spec`, advance past it (and its
    value if it takes one). Returns (new_i, None) on success, or (i+1, flag)
    if the token looked like a flag but wasn't in the spec.
    """
    tok = tokens[i]
    key, _, inline_value = tok.partition("=")
    takes_value = spec.flags.get(key)
    if takes_value is None:
        return i + 1, key  # unknown flag
    if takes_value and not inline_value:
        # Consume the next token as the flag's value.
        return i + 2, None
    return i + 1, None


def _scan_string(
    s: str,
    lineno: int,
    file: str,
    specs: dict[str, SubcommandSpec],
) -> list[Finding]:
    findings: list[Finding] = []
    for m in _ELSPAIS_RE.finditer(s):
        if s in _ALLOWLIST:
            continue
        if _preceded_by_non_cli_token(s, m.start()):
            continue
        after = s[m.end() :]
        tokens = _tokenize_command(after.lstrip())
        context = s[max(0, m.start() - 10) : m.end() + 60].strip()

        # Walk past global flags (any -flag valid on GlobalArgs) before the
        # subcommand. Global flags may consume a value, so use the merged
        # spec of any entry (they all share the same global-flag subset).
        global_spec = _spec_for_dataclass(GlobalArgs)
        i = 0
        while i < len(tokens):
            t = tokens[i]
            if _FLAG_RE.match(t.split("=", 1)[0]) and t.split("=", 1)[0] in global_spec.flags:
                i, _ = _consume_flag_and_value(tokens, i, global_spec)
                continue
            break
        if i >= len(tokens):
            continue

        subcmd = tokens[i]
        if _PLACEHOLDER_RE.search(subcmd):
            continue
        if subcmd not in specs:
            continue  # not an elspais CLI invocation (prose "elspais tool")
        i += 1

        # If subcmd has nested actions, the next positional must be an
        # action name — switch to the nested spec for the remainder.
        spec = specs[subcmd]
        variant = subcmd
        if spec.nested_actions:
            # Skip any leading flags before the action (rare, but valid).
            j = i
            while j < len(tokens) and _FLAG_RE.match(tokens[j].split("=", 1)[0]):
                j, _ = _consume_flag_and_value(tokens, j, spec)
            if j < len(tokens):
                action_tok = tokens[j]
                if _PLACEHOLDER_RE.search(action_tok) or action_tok == "{?}":
                    # Templated action name — can't validate, skip the
                    # rest of this invocation.
                    continue
                if action_tok not in spec.nested_actions:
                    findings.append(
                        Finding(
                            file=file,
                            line=lineno,
                            subcommand=subcmd,
                            kind="action",
                            token=action_tok,
                            context=context,
                        )
                    )
                    continue
                variant = f"{subcmd} {action_tok}"
                spec = specs[variant]
                i = j + 1

        # Now walk the remaining tokens: flags (with their values) and
        # positionals. Validate each.
        positional_slot = 0
        while i < len(tokens):
            tok = tokens[i]
            if _PLACEHOLDER_RE.search(tok) or tok == "{?}":
                # Placeholder — advances one slot (most placeholders stand
                # in for a single positional, e.g. <req-id>).
                positional_slot += 1
                i += 1
                continue
            key = tok.split("=", 1)[0]
            if _FLAG_RE.match(key):
                if key in spec.flags:
                    i, _ = _consume_flag_and_value(tokens, i, spec)
                else:
                    findings.append(
                        Finding(
                            file=file,
                            line=lineno,
                            subcommand=variant,
                            kind="flag",
                            token=key,
                            context=context,
                        )
                    )
                    i += 1
                continue
            # Positional slot.
            if positional_slot < len(spec.positional_choices):
                choices = spec.positional_choices[positional_slot]
                if choices is not None and tok not in choices:
                    findings.append(
                        Finding(
                            file=file,
                            line=lineno,
                            subcommand=variant,
                            kind="positional",
                            token=tok,
                            context=context,
                        )
                    )
            positional_slot += 1
            i += 1
    return findings


# ---------------------------------------------------------------------------
# The actual test
# ---------------------------------------------------------------------------


SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "elspais"
DOCS_ROOT = SRC_ROOT / "docs"


def _format_failure(findings: list[Finding], header: str) -> str:
    return "\n".join([header, ""] + [f.format() for f in findings])


def test_all_elspais_strings_in_python_source_use_real_flags(
    subcommand_specs: dict[str, SubcommandSpec],
) -> None:
    """Every `elspais <cmd> [action] [--flag ...] [positional ...]` literal
    in `src/elspais/**/*.py` must use real flags, real action names, and
    positional tokens that fall within Literal choices (when applicable).
    """
    assert SRC_ROOT.is_dir(), f"Source root missing: {SRC_ROOT}"

    all_findings: list[Finding] = []
    for py_file in SRC_ROOT.rglob("*.py"):
        # Skip args.py itself — it *defines* the dataclasses; help-string
        # examples inside are presumed self-consistent and noisy.
        if py_file.name == "args.py":
            continue
        rel = py_file.relative_to(SRC_ROOT.parent.parent)
        for lineno, s in _iter_source_strings(py_file):
            if "elspais" not in s:
                continue
            all_findings.extend(_scan_string(s, lineno, str(rel), subcommand_specs))

    if all_findings:
        pytest.fail(
            _format_failure(
                all_findings,
                "Found invalid `elspais <cmd> ...` references in Python source.\n"
                "Fix the string, or add the flag/action/choice to args.py:",
            )
        )


def test_all_elspais_strings_in_markdown_docs_use_real_flags(
    subcommand_specs: dict[str, SubcommandSpec],
) -> None:
    """Every `elspais <cmd> ...` example in docs/**/*.md must use real
    flags, real action names, and valid Literal positional choices.
    """
    assert DOCS_ROOT.is_dir(), f"Docs root missing: {DOCS_ROOT}"

    all_findings: list[Finding] = []
    for md_file in DOCS_ROOT.rglob("*.md"):
        rel = md_file.relative_to(SRC_ROOT.parent.parent)
        text = md_file.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.split("\n"), 1):
            if "elspais" not in line:
                continue
            all_findings.extend(_scan_string(line, lineno, str(rel), subcommand_specs))

    if all_findings:
        pytest.fail(
            _format_failure(
                all_findings,
                "Found invalid `elspais <cmd> ...` references in docs.\n"
                "Fix the doc, or add the flag/action/choice to args.py:",
            )
        )
