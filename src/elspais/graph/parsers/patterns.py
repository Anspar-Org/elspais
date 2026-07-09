# Implements: REQ-d00131-B
"""Shared regex patterns for requirement and journey parsing.

Single source of truth for parser regexes. Modules that need to match
requirement metadata, journey metadata, edge keywords, the changelog
section header, or multi-assertion ID suffixes import from here rather
than inlining their own pattern.
"""
from __future__ import annotations

import re

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


def build_multi_assertion_pattern(
    prefix: str, multi_sep: str | None, separator: str | None = None
) -> re.Pattern[str]:
    """Compile the regex for a REQ-id with optional multi-assertion suffix.

    Both prefix and separators are treated as literal characters (escaped).
    The pattern is case-insensitive. An empty or None ``multi_sep`` is
    treated as the default ``"+"``; callers do not need to dance around
    config defaults.

    ``separator`` is the configured ``[id-patterns.assertions] separator``
    -- the character between the requirement ID/component and the first
    assertion label (e.g. ``"-"`` in ``REQ-x-A``, or ``"/"`` in ``REQ-x/A``).

    When ``separator`` is ``None``/``"-"``/``"_"`` (the legacy default), the
    id/component blob (``[A-Za-z0-9\\-_]+``) already contains those
    characters, so it opportunistically absorbs the separator and first
    label as one unit -- there is no unambiguous boundary between a
    component's own internal hyphens/underscores and the assertion
    separator when they're the same character, so this case is handled as
    it always has been.

    For any other configured separator (e.g. ``"/"``, ``":"``), the id blob
    cannot contain it, so it stops at the true end of the requirement ID --
    an explicit ``separator + label`` group must be appended to avoid
    silently dropping the assertion suffix (CUR-1568 Task 13).
    """
    if not multi_sep:
        multi_sep = "+"
    multi_esc = re.escape(multi_sep)
    label_class = r"[A-Za-z0-9]+"
    id_blob = r"[A-Za-z0-9\-_]+"

    if separator in (None, "-", "_"):
        # Legacy behavior: separator character is folded into the greedy
        # id/component blob (works because "-"/"_" are already members of
        # that character class).
        pattern = rf"{re.escape(prefix)}[-_]{id_blob}(?:{multi_esc}{label_class})*"
    else:
        sep_esc = re.escape(separator)
        suffix = rf"(?:{sep_esc}{label_class}(?:{multi_esc}{label_class})*)?"
        pattern = rf"{re.escape(prefix)}[-_]{id_blob}{suffix}"

    return re.compile(pattern, re.IGNORECASE)
