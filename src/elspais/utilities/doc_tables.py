# Implements: REQ-d00286-E
"""The documentation tables the program renders from its own definitions.

A set the program defines and the documentation presents is presented from
that definition, so the two cannot disagree (REQ-d00286-E). A hand-written
table of what the tool offers -- its comment patterns, its checks, its result
reporters, its commands -- is correct on the day it is written and wrong on
the day the tool gains one more entry, and nothing announces the difference.
The tables below are rendered from the definitions themselves and spliced into
the shipped topics between named markers, so the answer a reader gets is the
answer the program holds.

This lives beside `docs_loader`, which READS those topics: the reader and the
writer of the same files are one concern, kept in one place.

Only the fragment between a pair of markers is written. Everything else in the
topic -- the narrative that surrounds a table, and the guidance that no set can
hold -- is prose, and prose is left exactly as its author wrote it.

Regenerate with::

    python -m elspais.utilities.doc_tables

A marker naming a fragment this module cannot render is an error, and so is a
fragment this module renders that no topic presents: either way a set and its
presentation have parted company, which is the condition this module exists to
remove.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from elspais.graph.parsers.patterns import (
    COMMENT_PATTERN_BY_EXTENSION,
    COMMENT_PATTERN_BY_NAME,
    CommentPattern,
)
from elspais.graph.parsers.results.registry import REPORTER_REGISTRY
from elspais.utilities.docs_loader import find_docs_dir
from elspais.utilities.findings import NO_KNOWN_REMEDY, REGISTRY

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

BEGIN = "<!-- generated: {name} -->"
END = "<!-- /generated: {name} -->"

# The one line every fragment opens with, so a reader who meets a table in the
# file rather than through `elspais docs` knows why editing it is futile.
_PREAMBLE = (
    "<!-- Rendered from the program's own definitions; edits here are "
    "overwritten. Regenerate: python -m elspais.utilities.doc_tables -->"
)


# --- table primitives ------------------------------------------------------ #


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [_row(headers), _row(["---"] * len(headers))]
    lines.extend(_row(r) for r in rows)
    return "\n".join(lines)


def _code(text: str) -> str:
    return f"`{text}`"


# --- comment patterns ------------------------------------------------------ #


def render_comment_patterns() -> str:
    """The named set of comment patterns, and the file types each covers."""
    by_pattern: dict[CommentPattern, list[str]] = {p: [] for p in CommentPattern}
    for extension, pattern in COMMENT_PATTERN_BY_EXTENSION.items():
        by_pattern[pattern].append(extension)
    names: dict[CommentPattern, list[str]] = {p: [] for p in CommentPattern}
    for file_name, pattern in COMMENT_PATTERN_BY_NAME.items():
        names[pattern].append(file_name)

    rows = []
    for pattern in CommentPattern:
        extensions = " ".join(_code(e) for e in sorted(by_pattern[pattern])) or "--"
        whole = " ".join(_code(n) for n in sorted(names[pattern])) or "--"
        rows.append([_code(pattern.label), _code(pattern.marker), extensions, whole])

    return "\n".join(
        [
            _table(["Name", "Marker", "Extensions", "Whole file names"], rows),
            "",
            "A whole file name is matched without regard to case: `Dockerfile`,",
            "`dockerfile` and `DOCKERFILE` are one file type.",
        ]
    )


# --- health checks --------------------------------------------------------- #


def check_categories() -> list[str]:
    """Every category a registered check reports under, in a stable order."""
    return sorted({rule.category for rule in REGISTRY.values()})


def _configured_by(path: tuple[str, ...]) -> str:
    """The one configuration setting a check reads, as a reader would write it."""
    table = "[" + ".".join(path[:-1]) + "]"
    if path[:2] == ("rules", "severity"):
        return _code(table)
    return _code(f"{table} {path[-1]}")


def render_check_catalog(category: str) -> str:
    """The catalog of checks reporting under one category."""
    rows = []
    for rule in REGISTRY.values():
        if rule.category != category:
            continue
        remedy = rule.remedy if rule.remedy == NO_KNOWN_REMEDY else _code(rule.remedy)
        rows.append(
            [
                _code(rule.name),
                rule.description,
                rule.default,
                _configured_by(rule.path),
                remedy,
            ]
        )
    if not rows:
        raise ValueError(
            f"No registered check reports under the category {category!r}. "
            f"A marker presents a category the registry does not hold."
        )
    return _table(["Check", "Description", "Default severity", "Configured by", "Remedy"], rows)


# --- result reporters ------------------------------------------------------ #


def render_reporters() -> str:
    """The built-in result and coverage reporters."""
    rows = []
    for name in sorted(REPORTER_REGISTRY):
        spec = REPORTER_REGISTRY[name]
        if not spec.description:
            raise ValueError(
                f"The reporter {name!r} is registered without a description, so the "
                f"published table would present it as an empty cell. Give its "
                f"`ReporterSpec` a `description`."
            )
        rows.append([_code(name), spec.channel, spec.kind, spec.description])

    return "\n".join(
        [
            _table(["Reporter", "Channel", "Kind", "Description"], rows),
            "",
            "These are the reporters the tool is built with. `register_reporter()` admits",
            "further formats at run time, so a project that registers one has a reporter",
            "this table does not name.",
        ]
    )


# --- command index --------------------------------------------------------- #


def command_entries() -> list[tuple[str, str, str]]:
    """Every command the CLI exposes, as (name, group, description).

    Read from the `Command` union and the group table in `commands.args`, which
    are what the CLI itself dispatches on -- the index cannot then name a
    command the tool does not have, or miss one it does.
    """
    import typing

    # Imported here rather than at module scope: `utilities` is beneath
    # `commands` in this package's layering, and only this function looks up.
    from elspais.commands.args import COMMAND_GROUPS, Command

    described: dict[str, str] = {}
    for arg in typing.get_args(Command):
        if typing.get_origin(arg) is not typing.Annotated:
            continue
        base_type, *metadata = typing.get_args(arg)
        name = None
        for m in metadata:
            if hasattr(m, "name"):
                name = m.name
        if name is None:
            continue
        doc = (base_type.__doc__ or "").strip().split("\n")[0].strip()
        described[name] = doc.rstrip(".")

    unknown = sorted(set(described) - set(COMMAND_GROUPS))
    if unknown:
        raise ValueError(
            f"These commands are in no group: {', '.join(unknown)}. "
            f"Add them to COMMAND_GROUPS in elspais/commands/args.py."
        )

    group_order = list(dict.fromkeys(COMMAND_GROUPS.values()))
    entries: list[tuple[str, str, str]] = []
    for group in group_order:
        for name, command_group in COMMAND_GROUPS.items():
            if command_group == group and name in described:
                entries.append((name, group, described[name]))
    return entries


def render_command_index() -> str:
    """The index of commands: what each one is, and which group it belongs to."""
    rows = [[_code(name), group, description] for name, group, description in command_entries()]
    return "\n".join(
        [
            _table(["Command", "Group", "What it does"], rows),
            "",
            "Each command's own section below says how to use it. `elspais <command>",
            "--help` says the same from the installed program.",
        ]
    )


# --- fragments and splicing ------------------------------------------------ #


def renderers() -> dict[str, Callable[[], str]]:
    """Every fragment this module can render, by the name a marker gives it."""
    table: dict[str, Callable[[], str]] = {
        "comment-patterns": render_comment_patterns,
        "reporters": render_reporters,
        "command-index": render_command_index,
    }
    for category in check_categories():
        table[f"check-catalog:{category}"] = _catalog_renderer(category)
    return table


def _catalog_renderer(category: str) -> Callable[[], str]:
    def render() -> str:
        return render_check_catalog(category)

    return render


def marker_names(text: str) -> list[str]:
    """The fragments a document presents, in the order it presents them."""
    found = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("<!-- generated: ") and stripped.endswith(" -->"):
            found.append(stripped[len("<!-- generated: ") : -len(" -->")])
    return found


def splice(text: str, name: str, body: str) -> str:
    """Replace the fragment named *name*, leaving everything else untouched."""
    begin = BEGIN.format(name=name)
    end = END.format(name=name)
    if text.count(begin) != 1 or text.count(end) != 1:
        raise ValueError(
            f"The marker pair for {name!r} must appear exactly once "
            f"(found {text.count(begin)} opening and {text.count(end)} closing)."
        )
    head, _, rest = text.partition(begin)
    _, _, tail = rest.partition(end)
    return f"{head}{begin}\n{_PREAMBLE}\n\n{body.rstrip()}\n{end}{tail}"


@dataclass(frozen=True)
class Document:
    """One documentation file, and the fragments it presents."""

    path: Path
    names: list[str]


def documents() -> list[Document]:
    """Every documentation file holding at least one generated fragment."""
    found: list[Document] = []
    for path in _candidate_files():
        text = path.read_text(encoding="utf-8")
        names = marker_names(text)
        if names:
            found.append(Document(path, names))
    return found


def _candidate_files() -> Iterator[Path]:
    docs_dir = find_docs_dir()
    if docs_dir is not None:
        yield from sorted(docs_dir.glob("*.md"))
    repo_doc = repository_root() / "docs" / "configuration.md"
    if repo_doc.is_file():
        yield repo_doc


def repository_root() -> Path:
    """The checkout this module was loaded from, where one exists."""
    return Path(__file__).resolve().parents[3]


def regenerate() -> list[tuple[Path, bool]]:
    """Render every fragment into every document that presents one.

    Returns:
        One (path, changed) pair per document, in the order they were written.

    Raises:
        ValueError: If a document presents a fragment this module cannot
            render, or if a fragment this module renders is presented nowhere.
    """
    available = renderers()
    presented: set[str] = set()
    results: list[tuple[Path, bool]] = []

    for document in documents():
        original = document.path.read_text(encoding="utf-8")
        text = original
        for name in document.names:
            if name not in available:
                raise ValueError(
                    f"{document.path} presents a fragment named {name!r}, which this "
                    f"module cannot render. Known fragments: {', '.join(sorted(available))}."
                )
            presented.add(name)
            text = splice(text, name, available[name]())
        if text != original:
            document.path.write_text(text, encoding="utf-8")
        results.append((document.path, text != original))

    unpresented = sorted(set(available) - presented)
    if unpresented:
        raise ValueError(
            f"These fragments are rendered by nothing the documentation presents: "
            f"{', '.join(unpresented)}. Add the marker pair to the topic that should "
            f"present each, or stop rendering it."
        )
    return results


def main(argv: list[str] | None = None) -> int:
    """Regenerate every documentation fragment in place."""
    if argv:
        print(
            "usage: python -m elspais.utilities.doc_tables\n"
            "Regenerates every generated documentation fragment in place.",
            file=sys.stderr,
        )
        return 2
    try:
        results = regenerate()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not results:
        print("error: no documentation file presents a generated fragment.", file=sys.stderr)
        return 1
    for path, changed in results:
        print(f"{'updated' if changed else 'unchanged'}  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
