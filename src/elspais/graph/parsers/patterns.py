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
