"""The one cache of per-file parse results (REQ-d00331).

A graph build spends most of its time reading files through
``FileDispatcher``.  Repeated builds -- a daemon rebuilding after every edit,
a command run twice, a test suite building the same fixture many times --
read the same files under the same grammar again and again.  This module
holds what each such reading produced, so a reading asked for again is
answered without parsing.

It is a pure optimisation.  A result is reused only under a key holding
everything the reading depends on:

- which reading was asked for (``spec``, ``code`` or ``test``);
- the digest of the exact text read;
- the path the text was read from, for the readings that consult it -- the
  path decides the language, its comment marker, whether the Python scanner
  runs, and it is copied into the result as ``source_id``.  ``dispatch_spec``
  never consults its path, so a spec reading is keyed without one;
- the *grammar fingerprint* of the dispatcher (``grammar_fingerprint``):
  the full identifier configuration of every federation member the
  dispatcher's reader alternates, in the reader's order, plus the text of
  the grammar files the parsers are compiled from;
- the argument a reading takes beyond its text: ``dispatch_code``'s
  ``line_context`` and the external pre-scan entry ``dispatch_test`` reads
  for this one file.

Anything that cannot be stated exactly in a key -- a resolver or reader of an
unexpected type, a configuration holding a value that is not plain data, an
argument that does not serialise -- makes the reading uncacheable, and it is
parsed every time.

Results are held pickled, so a stored result is immutable, every hit is a
fresh object graph the caller may mutate freely, and the bytes held are an
exact measure of the memory the cache occupies.  The cache is bounded by
entry count and by bytes, evicting the least recently used entry first, and
every operation on it holds one lock.

``ELSPAIS_PARSE_CACHE`` controls it, read on every reading: unset or ``1``
reuses results; ``0`` reuses nothing and stores nothing; ``verify`` parses
every time and raises ``AssertionError`` naming the file and the reading
wherever a held result differs from the fresh one.
"""

from __future__ import annotations

import dataclasses
import os
import pickle
import threading
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from elspais.utilities.hasher import content_digest

ENV_VAR = "ELSPAIS_PARSE_CACHE"

MODE_ON = "on"
MODE_OFF = "off"
MODE_VERIFY = "verify"

# Bounds of the process's one cache. A pickled reading of a source file is a
# few times the file's size; these hold every file of a large repository and
# its federation many times over without letting a long-lived daemon grow
# without limit.
DEFAULT_MAX_ENTRIES = 20_000
DEFAULT_MAX_BYTES = 256 * 1024 * 1024

_GRAMMARS_DIR = Path(__file__).parent / "lark" / "grammars"


# Implements: REQ-d00331-F+G
def mode() -> str:
    """The mode ``ELSPAIS_PARSE_CACHE`` selects, read now.

    Raises:
        ValueError: The variable holds a value that names no mode, so a
            misspelt request to verify is not silently taken as "on".
    """
    raw = os.environ.get(ENV_VAR)
    if raw is None or raw.strip() in ("", "1"):
        return MODE_ON
    value = raw.strip().lower()
    if value == "0":
        return MODE_OFF
    if value == MODE_VERIFY:
        return MODE_VERIFY
    raise ValueError(f"{ENV_VAR}={raw!r} names no mode; set it to 1 (or unset), 0, or verify")


class ParseCache:
    """A bounded, thread-safe, least-recently-used store of pickled readings."""

    # Implements: REQ-d00331-D
    def __init__(
        self,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self._entries: OrderedDict[tuple, bytes] = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.verified = 0
        # (reading, file) of every verification that failed. The failure is
        # raised as well; this survives a caller that reports what it caught
        # instead of propagating it (a serving process's rebuild does).
        self.mismatches: list[tuple[str, str]] = []

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    @property
    def size_bytes(self) -> int:
        """The bytes of every held reading."""
        with self._lock:
            return self._bytes

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._bytes = 0

    def get(self, key: tuple) -> bytes | None:
        """The held reading under *key*, marking it most recently used."""
        with self._lock:
            blob = self._entries.get(key)
            if blob is None:
                self.misses += 1
                return None
            self._entries.move_to_end(key)
            self.hits += 1
            return blob

    # Implements: REQ-d00331-D
    def put(self, key: tuple, blob: bytes) -> None:
        """Hold *blob* under *key*, evicting the least recently used to fit.

        A reading larger than the whole byte bound is not held at all.
        """
        size = len(blob)
        if size > self.max_bytes or self.max_entries <= 0:
            return
        with self._lock:
            previous = self._entries.pop(key, None)
            if previous is not None:
                self._bytes -= len(previous)
            self._entries[key] = blob
            self._bytes += size
            while len(self._entries) > self.max_entries or self._bytes > self.max_bytes:
                _, evicted = self._entries.popitem(last=False)
                self._bytes -= len(evicted)
                self.evictions += 1


# The process's one cache: the viewer and the MCP server share a process, and
# so share it.
_CACHE = ParseCache()


def cache() -> ParseCache:
    """The process's parse cache."""
    return _CACHE


# ----------------------------------------------------------------------
# Key derivation
# ----------------------------------------------------------------------


def _is_plain(value: Any) -> bool:
    """Whether *value* is plain data whose ``repr`` states it exactly.

    Types are matched exactly: a subclass of ``str`` or ``dict`` may carry
    state its ``repr`` does not show.
    """
    kind = type(value)
    if value is None or kind in (bool, int, float, str):
        return True
    if kind in (list, tuple):
        return all(_is_plain(v) for v in value)
    if kind is dict:
        return all(type(k) in (str, int) and _is_plain(v) for k, v in value.items())
    return False


_GRAMMAR_TEXT_DIGEST: str | None = None


def _grammar_text_digest() -> str:
    """Digest of the grammar files every parser is compiled from.

    They are package data, fixed for the life of the process like the code
    that reads them (an installation change renews the serving process,
    REQ-o00077-D), so they are read once.
    """
    global _GRAMMAR_TEXT_DIGEST
    if _GRAMMAR_TEXT_DIGEST is None:
        parts = [
            f"{path.name}\0{path.read_text(encoding='utf-8')}"
            for path in sorted(_GRAMMARS_DIR.glob("*.lark"))
        ]
        _GRAMMAR_TEXT_DIGEST = content_digest("\0\0".join(parts))
    return _GRAMMAR_TEXT_DIGEST


# Implements: REQ-d00331-B
def grammar_fingerprint(reader: Any) -> str | None:
    """Everything a dispatcher's grammars and transformers read, as one string.

    A ``FileDispatcher`` holds its own resolver and a ``FederatedIdReader``
    over it and the other members; ``GrammarFactory`` and both transformers
    read only those (``grammar()``, the reader's alternated fragments,
    ``resolve_level``, ``parse_ref_list`` and the rest), and an
    ``IdResolver`` is a function of its ``IdPatternConfig`` alone -- every
    attribute it holds is derived from that in its constructor.  So the
    configuration of every resolver the reader holds, in the reader's order
    (which decides alternation and which member claims a reference), states
    the whole grammar.

    Returns ``None`` -- uncacheable -- where that argument does not hold: a
    reader or resolver of another type, which may read something else, or a
    configuration holding a value that is not plain data.
    """
    from elspais.utilities.patterns import FederatedIdReader, IdPatternConfig, IdResolver

    if type(reader) is not FederatedIdReader:
        return None
    configs = []
    for resolver in reader.resolvers:
        if type(resolver) is not IdResolver or type(resolver.config) is not IdPatternConfig:
            return None
        as_data = dataclasses.asdict(resolver.config)
        if not _is_plain(as_data):
            return None
        configs.append(as_data)
    return content_digest(repr((_grammar_text_digest(), configs)))


def _argument_fingerprint(argument: Any) -> str | None:
    """A reading's extra argument stated exactly, or ``None`` if it cannot be."""
    if argument is None:
        return ""
    if not _is_plain(argument):
        return None
    return repr(argument)


# ----------------------------------------------------------------------
# The one entry point
# ----------------------------------------------------------------------


# Implements: REQ-d00331-A+B+C+E+F
def cached_reading(
    reading: str,
    fingerprint: str | None,
    content: str,
    file_path: str | None,
    argument: Any,
    parse: Callable[[], list],
    *,
    reported_path: str = "",
) -> list:
    """Answer a reading from the cache, or by calling *parse* and holding it.

    Args:
        reading: Which reading this is (``spec``, ``code`` or ``test``).
        fingerprint: The dispatcher's ``grammar_fingerprint``; ``None``
            parses without caching.
        content: The exact text the reading is of.
        file_path: The path the reading consults, or ``None`` where it
            consults none.
        argument: The reading's extra argument, or ``None``.
        parse: Produces the reading.
        reported_path: The file named by a verification failure.
    """
    selected = mode()
    if selected == MODE_OFF or fingerprint is None:
        return parse()
    argument_key = _argument_fingerprint(argument)
    if argument_key is None:
        return parse()
    key = (reading, fingerprint, file_path, content_digest(content), argument_key)

    held = _CACHE.get(key)
    if held is not None and selected == MODE_ON:
        return pickle.loads(held)

    result = parse()
    try:
        blob = pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:  # noqa: BLE001 - an unpicklable reading is simply not held
        return result

    if held is not None:
        # Verify mode: the held reading must be the fresh one.
        _CACHE.verified += 1
        if blob != held and pickle.loads(held) != result:
            named = reported_path or file_path or "<unnamed>"
            _CACHE.mismatches.append((reading, named))
            raise AssertionError(
                f"parse cache mismatch: dispatch_{reading} of {named} produced a "
                f"result that differs from the one held under the same key"
            )
        return result
    _CACHE.put(key, blob)
    return result


__all__ = [
    "ENV_VAR",
    "MODE_OFF",
    "MODE_ON",
    "MODE_VERIFY",
    "ParseCache",
    "cache",
    "cached_reading",
    "grammar_fingerprint",
    "mode",
]
