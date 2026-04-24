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

Non-goals:
    * Markdown docs — scoped out for V1; they have more placeholders and
      variable syntax. If we need that later, extend this module.
    * Positional argument validation — we only check flag tokens.
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


def _flags_for_dataclass(cls: type) -> set[str]:
    """Derive --foo / -x flags from dataclass fields + tyro metadata.

    Includes --no-<flag> for bool fields (tyro generates these automatically).
    """
    flags: set[str] = {"-h", "--help"}
    try:
        hints = typing.get_type_hints(cls, include_extras=True)
    except Exception:
        return flags
    for field in dataclasses.fields(cls):
        t = hints.get(field.name, field.type)
        arg_name = field.name.replace("_", "-")
        aliases: tuple[str, ...] = ()
        is_bool = False
        inner = t
        if typing.get_origin(t) is typing.Annotated:
            inner = typing.get_args(t)[0]
            for m in typing.get_args(t)[1:]:
                if hasattr(m, "name") and m.name:
                    arg_name = m.name
                if hasattr(m, "aliases") and m.aliases:
                    aliases = tuple(m.aliases)
        if inner is bool:
            is_bool = True
        flags.add(f"--{arg_name}")
        if is_bool:
            flags.add(f"--no-{arg_name}")
        flags.update(aliases)
    return flags


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
def valid_flags_by_subcommand() -> dict[str, set[str]]:
    """Map "subcmd" and "subcmd action" -> set of valid flag tokens.

    Every variant includes `GlobalArgs` flags (--verbose, -v, -C, etc.)
    since those are accepted on any subcommand.
    """
    global_flags = _flags_for_dataclass(GlobalArgs)
    # Common value-holders that tyro allows as CLI tokens but aren't fields
    # (format literal choices, status values, etc.) — not relevant here.
    result: dict[str, set[str]] = {}
    for arg in typing.get_args(Command):
        if typing.get_origin(arg) is not typing.Annotated:
            continue
        base, *meta = typing.get_args(arg)
        name = _subcommand_name_from_meta(tuple(meta))
        if not name:
            continue
        result[name] = _flags_for_dataclass(base) | global_flags
        for action_name, action_cls in _nested_actions(base).items():
            result[f"{name} {action_name}"] = _flags_for_dataclass(action_cls) | global_flags
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
_TERMINATORS = set("`\"'|\n")

# A real CLI flag looks like `-<letter>` or `--<letter>...`.
# This explicitly rejects `-->` (HTML comment close), `--` (argparse
# separator), `-123` (a negative number), and bare `-`.
_FLAG_RE = re.compile(r"^--?[a-zA-Z][a-zA-Z0-9-]*$")

# If `elspais` is preceded (on the same line) by one of these tokens, the
# occurrence is not an elspais CLI invocation. `pipx runpip elspais install
# -e <path>` is the canonical case: pipx takes `elspais` as the package
# name to install into, not as a command.
_NOT_A_CLI_PREFIXES = {"runpip", "pip", "pipx", "python", "python3", "which"}

# Regex to locate the anchor. We don't capture args here — we tokenize
# manually below so we can walk past global flags before the subcommand.
_ELSPAIS_RE = re.compile(r"\belspais\b(?!-)")

# Field placeholders that show up in templated examples — skip these.
_PLACEHOLDER_RE = re.compile(r"[{<]")


def _tokenize_command(text: str) -> list[str]:
    """Split the command-line fragment into tokens up to a terminator.

    Stops at the first quote / backtick / pipe / newline so we don't spill
    from code into surrounding prose.
    """
    tokens: list[str] = []
    buf: list[str] = []
    for ch in text:
        if ch in _TERMINATORS:
            break
        if ch.isspace():
            if buf:
                tokens.append("".join(buf))
                buf = []
            continue
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
class BadFlag:
    file: str
    line: int
    subcommand: str
    flag: str
    context: str


# Literal strings that should not be scanned (declare allowlist here,
# keyed by substring match — keeps the guard honest).
_ALLOWLIST: set[str] = set()


def _scan_string(
    s: str,
    lineno: int,
    file: str,
    flag_map: dict[str, set[str]],
) -> list[BadFlag]:
    findings: list[BadFlag] = []
    for m in _ELSPAIS_RE.finditer(s):
        if s in _ALLOWLIST:
            continue
        if _preceded_by_non_cli_token(s, m.start()):
            continue
        after = s[m.end() :]
        # Cut to the first terminator so we don't leak into prose.
        tokens = _tokenize_command(after.lstrip())
        # Strip leading global flags (so we find the actual subcommand).
        global_flags = flag_map.get("__globals__") or set()
        i = 0
        # Rebuild a set of globals by pulling the union across every entry.
        if not global_flags:
            for fs in flag_map.values():
                global_flags = global_flags | fs
                break  # They're all supersets of globals; one sample is fine.
        while i < len(tokens):
            t = tokens[i]
            if t.startswith("-") and t.split("=", 1)[0] in _flags_for_dataclass(GlobalArgs):
                # Global flag; consume it (and its value if non-bool). We
                # don't need precise value-counting; just advance.
                i += 1
                continue
            break
        if i >= len(tokens):
            continue
        subcmd = tokens[i]
        if _PLACEHOLDER_RE.search(subcmd):
            continue
        if subcmd not in flag_map:
            # Not a real elspais subcommand — maybe future/unrelated word.
            # We *could* fail here but that generates noise for prose like
            # "the elspais tool". Only flag if the token is surrounded by
            # clear command context (preceded by a quote-backtick pair).
            continue
        # Pick the longest-matching variant (with nested action).
        variant = subcmd
        if i + 1 < len(tokens):
            two = f"{subcmd} {tokens[i + 1]}"
            if two in flag_map:
                variant = two
                i += 1
        valid = flag_map[variant]
        # Walk remaining tokens and validate any --flag / -x tokens.
        j = i + 1
        while j < len(tokens):
            tok = tokens[j]
            # Strip =value from --foo=bar forms.
            key = tok.split("=", 1)[0]
            if _FLAG_RE.match(key) and not _PLACEHOLDER_RE.search(key):
                if key not in valid:
                    findings.append(
                        BadFlag(
                            file=file,
                            line=lineno,
                            subcommand=variant,
                            flag=key,
                            context=s[max(0, m.start() - 10) : m.end() + 60].strip(),
                        )
                    )
            j += 1
    return findings


# ---------------------------------------------------------------------------
# The actual test
# ---------------------------------------------------------------------------


SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "elspais"


def test_all_elspais_strings_in_python_source_use_real_flags(
    valid_flags_by_subcommand: dict[str, set[str]],
) -> None:
    """Every `elspais <cmd> --<flag>` literal in src/elspais/**/*.py must
    reference a real flag on the target subcommand's Args dataclass.
    """
    assert SRC_ROOT.is_dir(), f"Source root missing: {SRC_ROOT}"

    all_findings: list[BadFlag] = []
    for py_file in SRC_ROOT.rglob("*.py"):
        # Skip args.py itself — it *defines* the dataclasses; any help-
        # string examples inside are presumed self-consistent and noisy.
        if py_file.name == "args.py":
            continue
        rel = py_file.relative_to(SRC_ROOT.parent.parent)
        for lineno, s in _iter_source_strings(py_file):
            if "elspais" not in s:
                continue
            findings = _scan_string(s, lineno, str(rel), valid_flags_by_subcommand)
            all_findings.extend(findings)

    if all_findings:
        msg_lines = [
            "Found `elspais <cmd> --<flag>` references to flags that don't exist.",
            "Either add the flag to the subcommand's Args dataclass, or fix the string:",
            "",
        ]
        for f in all_findings:
            msg_lines.append(
                f"  {f.file}:{f.line}  `elspais {f.subcommand} ... {f.flag}`  "
                f"(context: {f.context!r})"
            )
        pytest.fail("\n".join(msg_lines))


DOCS_ROOT = SRC_ROOT / "docs"


def test_all_elspais_strings_in_markdown_docs_use_real_flags(
    valid_flags_by_subcommand: dict[str, set[str]],
) -> None:
    """Every `elspais <cmd> --<flag>` example in docs/**/*.md must reference
    a real flag. User-facing docs were the source of the original
    `--global` vs `--global-scope` drift.
    """
    assert DOCS_ROOT.is_dir(), f"Docs root missing: {DOCS_ROOT}"

    all_findings: list[BadFlag] = []
    for md_file in DOCS_ROOT.rglob("*.md"):
        rel = md_file.relative_to(SRC_ROOT.parent.parent)
        text = md_file.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.split("\n"), 1):
            if "elspais" not in line:
                continue
            findings = _scan_string(line, lineno, str(rel), valid_flags_by_subcommand)
            all_findings.extend(findings)

    if all_findings:
        msg_lines = [
            "Found `elspais <cmd> --<flag>` references in docs pointing at",
            "flags that don't exist. Either add the flag or fix the doc:",
            "",
        ]
        for f in all_findings:
            msg_lines.append(
                f"  {f.file}:{f.line}  `elspais {f.subcommand} ... {f.flag}`  "
                f"(context: {f.context!r})"
            )
        pytest.fail("\n".join(msg_lines))
