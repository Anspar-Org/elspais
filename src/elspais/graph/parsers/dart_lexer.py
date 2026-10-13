# Implements: REQ-d00332-A, REQ-d00333-C
"""Dart lexical reading: string literals, comments and brackets.

Two readers need to tell Dart code from Dart comments and strings: the test
prescan, which finds where a ``test(`` call's brackets close, and the
``imports:dart`` dependency source, which reads a file's directives. Both
read through this module, so Dart has one lexical model.

Every function takes the line comment ``marker``. A caller takes it from
:func:`elspais.graph.parsers.patterns.comment_pattern_for_path`, the one
association of a language with its marker. The block form ``/* */`` is Dart
grammar read here only to skip text, never to find a citation in it. Dart
block comments nest, which a single regular expression cannot follow.

The strict readers (:func:`skip_trivia`, :func:`skip_balanced`) raise
:class:`DartLexError` where a comment, string or bracket does not close. The
lenient one (:func:`code_brackets`) ends its walk there instead, because a
prescan reads files that need not compile.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

# The escapes a Dart string literal resolves to one character.  ``\x``,
# ``\u`` and ``\u{...}`` are read separately; any other escaped character
# stands for itself.
_SIMPLE_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v"}
_HEX = re.compile(r"[0-9A-Fa-f]+")
_IDENT_CHAR = re.compile(r"[A-Za-z0-9_$]")
_WHITE = " \t\r\n﻿"
_OPENERS = {"(": ")", "[": "]", "{": "}", "<": ">"}


class DartLexError(ValueError):
    """Text that does not close: a block comment, a string or a bracket.

    ``offset`` is where the unclosed construct opened.
    """

    def __init__(self, why: str, offset: int) -> None:
        super().__init__(why)
        self.why = why
        self.offset = offset


def dart_escape(text: str, i: int) -> tuple[str, int] | None:
    """The character the escape at ``text[i]`` (just past the backslash) stands
    for, and the index after it, or ``None`` for an escape that does not read."""
    if i >= len(text):
        return None
    c = text[i]
    if c in _SIMPLE_ESCAPES:
        return _SIMPLE_ESCAPES[c], i + 1
    if c == "x":
        digits = text[i + 1 : i + 3]
        if len(digits) == 2 and _HEX.fullmatch(digits):
            return chr(int(digits, 16)), i + 3
        return None
    if c == "u":
        if text.startswith("{", i + 1):
            close = text.find("}", i + 2)
            digits = text[i + 2 : close] if close > 0 else ""
            if digits and _HEX.fullmatch(digits) and len(digits) <= 6:
                return chr(int(digits, 16)), close + 1
            return None
        digits = text[i + 1 : i + 5]
        if len(digits) == 4 and _HEX.fullmatch(digits):
            return chr(int(digits, 16)), i + 5
        return None
    return c, i + 1


def opens_string(text: str, i: int) -> bool:
    """Whether a string literal opens at ``text[i]``.

    An ``r`` opens a raw literal only where a quote follows it and it ends no
    identifier, so ``bar'x'`` holds no raw literal.
    """
    if text[i : i + 1] in ("'", '"'):
        return True
    return (
        text[i : i + 1] == "r"
        and text[i + 1 : i + 2] in ("'", '"')
        and (i == 0 or not _IDENT_CHAR.match(text[i - 1]))
    )


def _quote_at(text: str, i: int) -> tuple[bool, str] | None:
    """The literal opening at ``text[i]``: (raw, quote), or ``None`` where none opens."""
    if not opens_string(text, i):
        return None
    raw = text[i] == "r"
    j = i + 1 if raw else i
    quote = text[j : j + 3] if text[j : j + 3] in ("'''", '"""') else text[j : j + 1]
    return raw, quote


def dart_literal(text: str, i: int) -> tuple[str, int] | None:
    """Read one string literal starting at ``text[i]``.

    Returns its value and the index after its closing quote, or ``None`` where
    the literal interpolates a value, does not close, or does not start here.
    """
    opened = _quote_at(text, i)
    if opened is None:
        return None
    raw, quote = opened
    i += len(quote) + (1 if raw else 0)
    if len(quote) == 3:
        # A multi-line literal drops its first line where that line holds
        # nothing but white space.
        line_end = text.find("\n", i)
        if line_end >= 0 and not text[i:line_end].strip(" \t\r"):
            i = line_end + 1
    value: list[str] = []
    while i < len(text):
        if text.startswith(quote, i):
            return "".join(value), i + len(quote)
        c = text[i]
        if c == "\n" and len(quote) == 1:
            return None
        if not raw and c == "\\":
            escaped = dart_escape(text, i + 1)
            if escaped is None:
                return None
            value.append(escaped[0])
            i = escaped[1]
            continue
        if not raw and c == "$":
            return None  # interpolation: the value is decided when the program runs
        value.append(c)
        i += 1
    return None


def dart_string(text: str, i: int) -> tuple[str, int] | None:
    """Read adjacent string literals starting at ``text[i]``, which Dart joins into one.

    Literals may be separated by white space. Returns the joined value and
    the index after the last literal, or ``None`` where no literal starts at
    ``text[i]`` or one of them does not read (see :func:`dart_literal`).
    """
    parts: list[str] = []
    end = i
    while True:
        j = end
        while j < len(text) and text[j] in " \t\r\n":
            j += 1
        if _quote_at(text, j) is None:
            break
        literal = dart_literal(text, j)
        if literal is None:
            return None
        parts.append(literal[0])
        end = literal[1]
    if not parts:
        return None
    return "".join(parts), end


def _block_comment_end(text: str, i: int) -> int | None:
    """The index past the block comment opening at ``text[i]``, nesting; ``None`` if unclosed."""
    depth = 0
    n = len(text)
    while i < n:
        if text.startswith("/*", i):
            depth += 1
            i += 2
        elif text.startswith("*/", i):
            depth -= 1
            i += 2
            if depth == 0:
                return i
        else:
            i += 1
    return None


def _comment_end(text: str, i: int, marker: str, *, strict: bool) -> int | None:
    """The index past the comment opening at ``text[i]``, or ``None`` where none opens.

    A line comment ends with its line. A block comment that does not close
    raises where the reading is strict, and ends the text where it is lenient.
    """
    if text.startswith(marker, i):
        line_end = text.find("\n", i)
        return len(text) if line_end < 0 else line_end + 1
    if not text.startswith("/*", i):
        return None
    end = _block_comment_end(text, i)
    if end is not None:
        return end
    if strict:
        raise DartLexError("a block comment does not close", i)
    return len(text)


def skip_trivia(text: str, i: int, marker: str) -> int:
    """The index of the first character at or after ``text[i]`` that is not
    white space or a comment.

    Raises:
        DartLexError: A block comment does not close.
    """
    n = len(text)
    while i < n:
        if text[i] in _WHITE:
            i += 1
            continue
        end = _comment_end(text, i, marker, strict=True)
        if end is None:
            return i
        i = end
    return i


def _string_end(text: str, i: int, marker: str, *, strict: bool) -> int:
    """The index past the string literal opening at ``text[i]``.

    An interpolation ``${...}`` is skipped as code. Where the literal does not
    close, a strict reading raises; a lenient one ends a single-line literal
    at its line and any other at the end of the text.
    """
    opened = _quote_at(text, i)
    assert opened is not None
    raw, quote = opened
    start = i
    i += len(quote) + (1 if raw else 0)
    n = len(text)
    stops = _string_stops(quote[0], raw)
    while i < n:
        found = stops.search(text, i)
        if found is None:
            break
        i = found.start()
        if text.startswith(quote, i):
            return i + len(quote)
        c = text[i]
        if c == "\n" and len(quote) == 1:
            if strict:
                raise DartLexError("a string does not close on its line", start)
            return i
        if not raw and c == "\\":
            i += 2
            continue
        if not raw and text.startswith("${", i):
            i = _balanced_end(text, i + 1, marker, strict=strict)
            continue
        i += 1
    if strict:
        raise DartLexError("a string does not close", start)
    return n


_STRING_STOPS: dict[tuple[str, bool], re.Pattern[str]] = {}


def _string_stops(quote: str, raw: bool) -> re.Pattern[str]:
    """The characters at which a string literal can close, escape, interpolate or end its line."""
    if (quote, raw) not in _STRING_STOPS:
        chars = re.escape(quote) + "\\n" + ("" if raw else "\\\\$")
        _STRING_STOPS[(quote, raw)] = re.compile(f"[{chars}]")
    return _STRING_STOPS[(quote, raw)]


def _balanced_end(text: str, i: int, marker: str, *, strict: bool) -> int:
    """The index past the bracket closing the one at ``text[i]``.

    Strings and comments between are skipped. An angle bracket counts only
    angle brackets; any other counts the three kinds of bracket together.
    """
    opener = text[i]
    angle = opener == "<"
    depth = 0
    start = i
    n = len(text)
    while i < n:
        c = text[i]
        if c in _WHITE:
            i += 1
            continue
        end = _comment_end(text, i, marker, strict=strict)
        if end is not None:
            i = end
            continue
        if opens_string(text, i):
            i = _string_end(text, i, marker, strict=strict)
            continue
        if (angle and c == "<") or (not angle and c in "([{"):
            depth += 1
        elif (angle and c == ">") or (not angle and c in ")]}"):
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    if strict:
        raise DartLexError(f"a {opener!r} does not close", start)
    return n


def skip_balanced(text: str, i: int, marker: str) -> int:
    """The index past the bracket that closes the one at ``text[i]``.

    ``text[i]`` is ``(``, ``[``, ``{`` or ``<``. Strings, with their
    interpolations, and comments are skipped.

    Raises:
        DartLexError: A bracket, string or comment does not close.
    """
    if text[i : i + 1] not in _OPENERS:
        raise DartLexError("no bracket opens here", i)
    return _balanced_end(text, i, marker, strict=True)


def code_brackets(text: str, start: int, marker: str) -> Iterator[tuple[int, str]]:
    """Each bracket character of ``text`` from ``start`` that is code, with its offset.

    Brackets inside comments and strings are not code; an interpolation
    ``${...}`` inside a string is skipped whole. A single-line string that does
    not close ends at its line, and a block comment or multi-line string that
    does not close ends the walk.
    """
    stops = _code_stops(marker)
    i = start
    n = len(text)
    while i < n:
        found = stops.search(text, i)
        if found is None:
            return
        i = found.start()
        c = text[i]
        end = _comment_end(text, i, marker, strict=False)
        if end is not None:
            i = end
            continue
        if opens_string(text, i):
            i = _string_end(text, i, marker, strict=False)
            continue
        if c in "([{)]}":
            yield i, c
        i += 1


_STOPS: dict[str, re.Pattern[str]] = {}


def _code_stops(marker: str) -> re.Pattern[str]:
    """The characters at which code can open a comment, a string or a bracket."""
    if marker not in _STOPS:
        _STOPS[marker] = re.compile("[()\\[\\]{}'\"/" + re.escape(marker[0]) + "]|r['\"]")
    return _STOPS[marker]


__all__ = [
    "DartLexError",
    "code_brackets",
    "dart_escape",
    "dart_literal",
    "dart_string",
    "opens_string",
    "skip_balanced",
    "skip_trivia",
]
