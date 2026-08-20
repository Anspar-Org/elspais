"""Continuing a reference list onto the lines below it.

ONE reading of REQ-d00269-H, wherever a reference list is written. A list is
divided by the reader and only by the reader; what a continuation adds is
which text the reader is given, and that question has the same answer in a
comment block, in requirement metadata, and in whatever holds a reference
list next. Deriving it per surface is how two surfaces come to disagree about
a rule neither of them states.

The caller supplies how to read a candidate line, because that IS the part
that differs -- content after a comment marker, the text of a metadata block's
line -- and nothing else about continuation does.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

from elspais.graph.parsers.patterns import KEYWORD_PATTERN
from elspais.utilities.patterns import REF_LIST_SEPARATOR

T = TypeVar("T")


# Implements: REQ-d00269-H, REQ-d00269-E
def opens_with_keyword(text: str) -> bool:
    """Whether *text*'s own first content is a *Traceability* keyword.

    Read positionally and without regard to case (REQ-d00269-E): the keyword
    is the line's first content and the separator that ends it abuts it.
    """
    stripped = text.lstrip("*_ \t")
    match = KEYWORD_PATTERN.match(stripped)
    if match is None:
        return False
    return stripped[match.end() :].lstrip("*_")[:1] in (":", "=")


# Implements: REQ-d00269-H
def fold_continuation(
    opener_text: str,
    opener_line: int,
    candidates: Sequence[T],
    *,
    line_of: Callable[[T], int],
    content_of: Callable[[T], str | None],
) -> tuple[str, list[T], int]:
    """Join *opener_text* with the lines that continue it.

    Returns the joined text, the candidates it was taken from, and the line
    the list now ends on. When nothing continues the list the text is returned
    unchanged, no candidate is consumed, and the caller reports the separator
    that introduced nothing -- H's third sentence.

    *candidates* are the lines following the opener, in order. ``content_of``
    returns a candidate's reference content, or None where the candidate is
    not a line that may hold any -- which is where a caller expresses what its
    own surface makes unavailable, such as a quoted line being displayed text
    rather than a declaration (REQ-d00269-E).

    H's two exclusions are applied HERE rather than by each caller: a line
    holding no content does not continue a list, and neither does one whose
    own first content is a *Traceability* keyword. A surface where the grammar
    already makes an exclusion structural pays nothing for it being checked
    again, and no surface can omit one by forgetting it.
    """
    joined = opener_text.rstrip()
    consumed: list[T] = []
    last_line = opener_line

    for candidate in candidates:
        if not joined.endswith(REF_LIST_SEPARATOR):
            break
        if line_of(candidate) != last_line + 1:
            break
        content = content_of(candidate)
        if content is None:
            break
        body = content.strip()
        if not body or opens_with_keyword(body):
            break
        joined = f"{joined} {body}"
        consumed.append(candidate)
        last_line = line_of(candidate)

    return joined, consumed, last_line
