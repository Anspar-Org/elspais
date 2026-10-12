"""A small evaluator for the GitHub Actions expressions the workflows use.

Enough of the expression language to evaluate `if:` conditions and expression
values as GitHub would: string literals, context names, `==`/`!=`, `!`, `&&`,
`||` (which yield an operand, not a boolean), parentheses and `fromJSON`. A name
the context does not supply raises, so a condition reading something a test did
not anticipate fails loudly rather than evaluating to nothing.
"""

from __future__ import annotations

import json
import re

_TOKEN = re.compile(
    r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<op>==|!=|&&|\|\||!|\(|\)|,)"
    r"|(?P<name>[A-Za-z_][A-Za-z0-9_.\-]*))"
)
_LITERALS = {"true": True, "false": False, "null": None}
_FUNCTIONS = {"fromJSON": json.loads}


def _tokens(text: str) -> list[tuple[str, str]]:
    text = text.strip()
    found, pos = [], 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise ValueError(f"cannot read expression at {text[pos:]!r}")
        kind = m.lastgroup
        found.append((kind, m.group(kind)))
        pos = m.end()
    return found


def _equal(a, b) -> bool:
    if isinstance(a, str) and isinstance(b, str):
        return a.lower() == b.lower()  # GitHub compares strings ignoring case
    return a == b


class _Expression:
    def __init__(self, text: str, context: dict):
        self.toks = _tokens(text)
        self.pos = 0
        self.context = context

    def _peek(self):
        return self.toks[self.pos] if self.pos < len(self.toks) else (None, None)

    def _take(self, value=None):
        tok = self._peek()
        if value is not None and tok[1] != value:
            raise ValueError(f"expected {value!r}, found {tok[1]!r}")
        self.pos += 1
        return tok

    def evaluate(self):
        value = self._or()
        if self.pos != len(self.toks):
            raise ValueError(f"trailing tokens: {self.toks[self.pos :]!r}")
        return value

    def _or(self):
        value = self._and()
        while self._peek() == ("op", "||"):
            self._take()
            right = self._and()
            value = value if value else right
        return value

    def _and(self):
        value = self._cmp()
        while self._peek() == ("op", "&&"):
            self._take()
            right = self._cmp()
            value = right if value else value
        return value

    def _cmp(self):
        value = self._unary()
        if self._peek() in (("op", "=="), ("op", "!=")):
            op = self._take()[1]
            right = self._unary()
            value = _equal(value, right) if op == "==" else not _equal(value, right)
        return value

    def _unary(self):
        if self._peek() == ("op", "!"):
            self._take()
            return not self._unary()
        return self._primary()

    def _primary(self):
        kind, value = self._take()
        if kind == "str":
            return value[1:-1].replace("''", "'")
        if (kind, value) == ("op", "("):
            inner = self._or()
            self._take(")")
            return inner
        if kind != "name":
            raise ValueError(f"unexpected token {value!r}")
        if self._peek() == ("op", "("):
            self._take()
            args = [self._or()]
            while self._peek() == ("op", ","):
                self._take()
                args.append(self._or())
            self._take(")")
            return _FUNCTIONS[value](*args)
        if value in _LITERALS:
            return _LITERALS[value]
        return self.context[value]


def evaluate(expression, context: dict):
    """Evaluate a workflow expression (`${{ ... }}`, or a bare `if:`)."""
    if isinstance(expression, bool):
        return expression
    text = expression.strip()
    if text.startswith("${{"):
        assert text.endswith("}}"), f"unterminated expression {text!r}"
        text = text[3:-2]
    return _Expression(text, context).evaluate()


def runs(item: dict, context: dict) -> bool:
    """Whether a job or step with this `if:` runs (no `if:` means it runs)."""
    return bool(evaluate(item.get("if", True), context))
