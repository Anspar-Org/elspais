# Implements: REQ-d00131-B
"""Shared regex patterns for requirement and journey parsing.

Single source of truth for parser regexes. Modules that need to match
requirement metadata, journey metadata, edge keywords, the changelog
section header, or multi-assertion ID suffixes import from here rather
than inlining their own pattern.

It is also the one home of the named set of comment patterns and of the
file-type-to-pattern association built on it (REQ-d00236-H): which marker
opens a comment is a parser-level fact shared across modules, and every
surface that needs one -- the reference grammar, the transformer that reads
a keyword, the reader that ends a reference at a comment, and the term
scanner -- reads it from here.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# --- Requirement metadata -------------------------------------------------- #

ALT_STATUS_PATTERN = re.compile(r"\*\*Status\*\*:\s*(?P<status>\w+)")
IMPLEMENTS_PATTERN = re.compile(r"\*\*Implements\*\*:\s*(?P<implements>[^|\n]+)")
REFINES_PATTERN = re.compile(r"\*\*Refines\*\*:\s*(?P<refines>[^|\n]+)")
# Implements: REQ-p00014-E
TEMPLATE_PATTERN = re.compile(r"\*\*Template\*\*(?:\s*\|\s*|\s*$)")
ASSERTION_LINE_PATTERN = re.compile(r"^\s*([A-Z0-9]+)\.\s+(.+)$", re.MULTILINE)

# --- Journey IDs ----------------------------------------------------------- #
#
# Journey IDs have the form ``JNY-<descriptor>-<number>``. The canonical
# pattern is anchored, captures both parts, and serves both roles:
#   - "is this string a valid journey ID?"           -> .fullmatch()
#   - "extract the descriptor slug from a journey ID" -> .match().group("descriptor")

JNY_ID_PATTERN = re.compile(
    r"^JNY-(?P<descriptor>[A-Za-z0-9][A-Za-z0-9-]*)-(?P<number>\d+)$",
    re.IGNORECASE,
)
JNY_ID_LINE_PATTERN = re.compile(r"^#*[ \t]*(?P<id>JNY-[A-Za-z0-9-]+):[ \t]*(?P<title>.+)$")
JNY_END_PATTERN = re.compile(r"^\*End\*\s+\*JNY-[^*]+\*", re.MULTILINE)

# A ``Verifies:`` target may name a whole journey or an addressable step.
# Matches ``JNY-<descriptor>-<number>`` optionally followed by ``/<number>``
# (the step suffix, mirroring the ``<requirement>/A`` assertion form).
# No capturing groups -- ``re.findall`` returns full-string matches.
JOURNEY_REF_PATTERN = re.compile(
    r"JNY-[A-Za-z0-9][A-Za-z0-9-]*-\d+(?:/\d+)?",
    re.IGNORECASE,
)

# --- Journey metadata ------------------------------------------------------ #

ACTOR_PATTERN = re.compile(r"\*\*Actor\*\*:[ \t]*(?P<actor>.+?)(?:\n|$)")
GOAL_PATTERN = re.compile(r"\*\*Goal\*\*:[ \t]*(?P<goal>.+?)(?:\n|$)")
VALIDATES_PATTERN = re.compile(r"^Validates:[ \t]*(?P<validates>.+?)$", re.MULTILINE)

# --- Edge-keyword classifier ---------------------------------------------- #
#
# Covers all five documented keywords. Previous inlined regexes missed
# `validates` and `satisfies` -- this is the canonical form.
KEYWORD_PATTERN = re.compile(
    r"(?:implements|verifies|refines|validates|satisfies|integrates)", re.IGNORECASE
)

# --- Changelog section header --------------------------------------------- #
#
# Depth-2 ATX. MULTILINE is baked in so callers can simply `.search(text)`.
CHANGELOG_HEADER_PATTERN = re.compile(r"^## Changelog\s*$", re.MULTILINE)


# --- Comment patterns ------------------------------------------------------ #
#
# Implements: REQ-d00236-H, REQ-d00269-K
#
# The named set. Six patterns, each one marker, each with a name a person can
# say out loud -- so a file type is associated with a *name*, not with a
# respelled regex, and the association is stated once.
#
# This is a property of the LANGUAGE a file is written in, and nothing else.
# It decides where a *Traceability* keyword may be written; it does NOT vary
# what a reference may say. One set of acceptance rules applies in every
# context that accepts a reference (REQ-p00014-T) -- the identifier grammar is
# the same in a Python comment, a SQL comment and a spec metadata line. There
# are no per-file reference overrides.
#
# Block comments (`/* */`, `<!-- -->`) are deliberately absent: a
# *Traceability* keyword inside one is never read, so a language whose only
# comment form is a block has no reference form at all (REQ-d00082-H).


class CommentPattern(Enum):
    """A comment marker, under the name file types are associated by."""

    C_LIKE = "//"
    SHELL_LIKE = "#"
    FUNCTION_LIKE = "--"
    LISP_LIKE = ";"
    MATH_LIKE = "%"
    BASIC_LIKE = "'"

    @property
    def marker(self) -> str:
        """The characters that open a comment in this pattern."""
        return self.value

    # Implements: REQ-d00236-J
    @property
    def label(self) -> str:
        """The name this pattern is published and documented under.

        The set is published as a table under ``elspais docs linking``, which
        names every pattern by this label beside its marker and the languages
        it covers. A name a user cannot look up is not a named set, so the
        label and the published table are one obligation, not two.
        """
        return self.name.lower().replace("_", "-")


# Implements: REQ-d00236-H
# One extension, one pattern. An extension absent here has no comment pattern,
# and so no place a *Traceability* keyword may be written -- see
# ``comment_pattern_for_path``.
COMMENT_PATTERN_BY_EXTENSION: dict[str, CommentPattern] = {
    # --- c-like: // ---
    **dict.fromkeys(
        (
            ".c",
            ".cc",
            ".cjs",
            ".cpp",
            ".cs",
            ".cxx",
            ".dart",
            ".go",
            ".h",
            ".hpp",
            ".j2",
            ".java",
            ".js",
            ".jsx",
            ".kt",
            ".kts",
            ".less",
            ".mjs",
            ".php",
            ".proto",
            ".rs",
            ".scala",
            ".scss",
            ".swift",
            ".ts",
            ".tsx",
            ".zig",
        ),
        CommentPattern.C_LIKE,
    ),
    # --- shell-like: # ---
    **dict.fromkeys(
        (
            ".bash",
            ".cmake",
            ".dockerfile",
            ".ex",
            ".exs",
            ".hcl",
            ".jl",
            ".ksh",
            ".mk",
            ".nix",
            ".pl",
            ".pm",
            ".ps1",
            ".py",
            ".r",
            ".rb",
            ".sh",
            ".tf",
            ".tfvars",
            ".toml",
            ".yaml",
            ".yml",
            ".zsh",
        ),
        CommentPattern.SHELL_LIKE,
    ),
    # --- function-like: -- ---
    **dict.fromkeys(
        (
            ".ada",
            ".adb",
            ".ads",
            ".elm",
            ".hs",
            ".lua",
            ".sql",
            ".vhd",
            ".vhdl",
        ),
        CommentPattern.FUNCTION_LIKE,
    ),
    # --- lisp-like: ; ---
    **dict.fromkeys(
        (
            ".clj",
            ".cljc",
            ".cljs",
            ".edn",
            ".el",
            ".lisp",
            ".lsp",
            ".rkt",
            ".scm",
            ".ss",
        ),
        CommentPattern.LISP_LIKE,
    ),
    # --- math-like: % ---
    **dict.fromkeys(
        (
            ".cls",
            ".erl",
            ".hrl",
            ".sty",
            ".tex",
        ),
        CommentPattern.MATH_LIKE,
    ),
    # --- basic-like: ' ---
    **dict.fromkeys(
        (
            ".bas",
            ".frm",
            ".vb",
            ".vbs",
        ),
        CommentPattern.BASIC_LIKE,
    ),
}

# Extensions deliberately left out of the map above, so that leaving them out
# reads as a decision rather than an oversight:
#
#   .css, .html, .xml, .svg -- their only comment form is a block, which never
#       carries a citation (REQ-d00082-H).
#   .m -- MATLAB writes `%` and Objective-C writes `//`. A file type is
#       associated with exactly ONE pattern (REQ-d00236-H), and this extension
#       cannot say which, so it is associated with none.
#   .s -- assembler dialects disagree (`#`, `;`, `//`) for the same reason.

# `.j2` is c-like, and is decided by being a template rather than by whatever
# it renders to: `viewer.js.j2`, `page.css.j2` and a hypothetical `conf.yml.j2`
# all annotate with `//`. Reading the suffix beneath the template suffix
# instead would make one scannable file type carry several patterns, which is
# the thing REQ-d00236-H forbids -- and it would silence the annotations in
# every template rendering to a block-comment language, which are real code
# implementing real requirements.


# Implements: REQ-d00236-H
# A few scannable file types name their language in the whole file name rather
# than in an extension. They are associated the same way every other type is --
# one type, one pattern -- and they are listed here rather than in the
# extension map because there is no extension to key them by.
COMMENT_PATTERN_BY_NAME: dict[str, CommentPattern] = {
    "containerfile": CommentPattern.SHELL_LIKE,
    "dockerfile": CommentPattern.SHELL_LIKE,
}


# Implements: REQ-d00269-K
def comment_pattern_for_path(path: str) -> CommentPattern | None:
    """The one comment pattern the language of *path* is associated with.

    ``None`` where the extension names no language this tool has a pattern
    for. That answer is deliberately the restrictive one: a keyword written
    in such a file is read nowhere, because no marker can be shown to open a
    comment there. Guessing a marker would bind references off the strength
    of a shape, which is the failure this association exists to remove.
    """
    name = path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    named = COMMENT_PATTERN_BY_NAME.get(name)
    if named is not None:
        return named
    _, dot, extension = name.rpartition(".")
    if not dot:
        return None
    return COMMENT_PATTERN_BY_EXTENSION.get("." + extension)


def comment_markers_for_path(path: str) -> tuple[str, ...]:
    """The markers that open a comment in the language of *path*.

    Empty where the language is not one of the associated set -- the caller
    then reads a keyword nowhere in that file.
    """
    pattern = comment_pattern_for_path(path)
    return () if pattern is None else (pattern.marker,)


# Implements: REQ-p00014-T
# The markers to assume where a file's language names none: a spec or journey
# metadata line is a markdown field rather than source, and a file type the
# map does not name has no marker at all.
#
# These say where a keyword may BEGIN. Where a reference list ENDS needs no
# marker -- a list is identifiers, separators and whitespace, so it ends at
# the first content that is none of those (REQ-d00287-B).
#
# Named from the set above rather than respelled, and deliberately not an
# exception to REQ-d00269-K, which governs where a keyword may be read: for a
# metadata line that is decided by the field itself.
METADATA_COMMENT_MARKERS: tuple[str, ...] = (
    CommentPattern.SHELL_LIKE.marker,
    CommentPattern.C_LIKE.marker,
    CommentPattern.FUNCTION_LIKE.marker,
)


def comment_style_fragment(markers: Sequence[str]) -> str:
    """A regex alternation matching any of *markers*, for a Lark terminal.

    An empty *markers* yields a pattern that can never match. It must NOT
    yield an empty alternation: ``(?:)`` matches the empty string, which
    would let a bare ``Implements:`` outside any comment bind a reference --
    the widest possible reading of the narrowest possible input.

    Forward slashes are escaped beyond what ``re.escape`` does, because the
    fragment is substituted into a ``/.../``-delimited Lark terminal.
    """
    if not markers:
        return "(?!)"
    return "|".join(re.escape(marker).replace("/", r"\/") for marker in markers)
