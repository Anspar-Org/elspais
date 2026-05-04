# Implements: REQ-d00246-A
"""Markdown emphasis normalization utility.

Single canonical helper for stripping balanced markdown emphasis wrappers
from user-text captured during spec parsing. Used by lark transformers at
every site that captures emphasis-decorated text from spec source (term
names, journey actor/goal/context fields, reference-term parsing).

See `docs/superpowers/specs/2026-05-04-markdown-render-hygiene-design.md`.
"""

from __future__ import annotations


def strip_emphasis(s: str) -> str:
    """Strip balanced markdown emphasis wrappers from `s`.

    Trims outer whitespace first, then peels matching pairs of `*` or `_`
    from the start and end of `s` when the boundary character runs are equal
    in length and the same marker character. Unbalanced wrappers (different
    marker types or unequal widths) leave the string intact. Idempotent.

    Examples:
        strip_emphasis('**Foo**')        -> 'Foo'
        strip_emphasis('****Foo****')    -> 'Foo'
        strip_emphasis('__Foo__')        -> 'Foo'
        strip_emphasis('**__Foo__**')    -> 'Foo'
        strip_emphasis('Foo')            -> 'Foo'
        strip_emphasis('*Foo_')          -> '*Foo_'   # different markers
        strip_emphasis('*Foo**')         -> '*Foo**'  # unequal widths
        strip_emphasis('   **Foo**   ')  -> 'Foo'
    """
    s = s.strip()
    while s and s[0] in "*_" and s[0] == s[-1]:
        marker = s[0]
        left_run = 0
        for c in s:
            if c == marker:
                left_run += 1
            else:
                break
        right_run = 0
        for c in reversed(s):
            if c == marker:
                right_run += 1
            else:
                break
        if left_run != right_run:
            break
        if left_run * 2 >= len(s):
            s = ""
        else:
            s = s[left_run:-left_run]
    return s
