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
ASSERTION_LINE_PATTERN = re.compile(r"^\s*([A-Z0-9]+)\.\s+(.+)$", re.MULTILINE)

# --- Journey IDs ----------------------------------------------------------- #

JNY_ID_PATTERN = re.compile(r"JNY-[A-Za-z0-9-]+", re.IGNORECASE)
JNY_ID_LINE_PATTERN = re.compile(r"^#*[ \t]*(?P<id>JNY-[A-Za-z0-9-]+):[ \t]*(?P<title>.+)$")
JNY_END_PATTERN = re.compile(r"^\*End\*\s+\*JNY-[^*]+\*", re.MULTILINE)
# Captures the slug between "JNY-" and the trailing "-<digits>" counter.
JNY_DESCRIPTOR_PATTERN = re.compile(r"^JNY-(.+)-\d+$")

# --- Journey metadata ------------------------------------------------------ #

ACTOR_PATTERN = re.compile(r"\*\*Actor\*\*:[ \t]*(?P<actor>.+?)(?:\n|$)")
GOAL_PATTERN = re.compile(r"\*\*Goal\*\*:[ \t]*(?P<goal>.+?)(?:\n|$)")
VALIDATES_PATTERN = re.compile(r"^Validates:[ \t]*(?P<validates>.+?)$", re.MULTILINE)

# --- Edge-keyword classifier ---------------------------------------------- #
#
# Covers all five documented keywords. Previous inlined regexes missed
# `validates` and `satisfies` -- this is the canonical form.
KEYWORD_PATTERN = re.compile(r"(?:implements|verifies|refines|validates|satisfies)", re.IGNORECASE)

# --- Changelog section header --------------------------------------------- #
#
# Depth-2 ATX. MULTILINE is baked in so callers can simply `.search(text)`.
CHANGELOG_HEADER_PATTERN = re.compile(r"^## Changelog\s*$", re.MULTILINE)


def build_multi_assertion_pattern(prefix: str, multi_sep: str) -> re.Pattern[str]:
    """Compile the regex for a REQ-id with optional multi-assertion suffix.

    Both prefix and separator are treated as literal characters (escaped).
    The pattern is case-insensitive.
    """
    return re.compile(
        rf"{re.escape(prefix)}[-_][A-Za-z0-9\-_]+" rf"(?:{re.escape(multi_sep)}[A-Za-z0-9]+)*",
        re.IGNORECASE,
    )
