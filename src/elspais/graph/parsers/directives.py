# Implements: REQ-p00002-E+F, REQ-p00017-G
"""The one authority on assertion-level parsing directives.

An *Assertion* whose text opens with a delimiter carries a **directive**: an
instruction to the parser about the *Assertion* itself, rather than an
obligation the *Assertion* states. The directive is what the opening delimiter
and its matching closer enclose, and everything past the closer is the
*Assertion*'s remaining content -- commentary the author wrote about the
directive, which survives parse and render untouched.

Three delimiter pairs open one: ``<>``, ``[]`` and ``{}``. Only ``RETIRED`` is
recognized. A directive the tool does not recognize is never quietly absorbed
into the *Assertion*'s prose (REQ-p00002-F): it is reported, and the
*Assertion* otherwise reads as an ordinary one, so an unrecognized name never
withdraws an obligation by accident.

Case is presentation, not identity. ``<RETIRED>``, ``<Retired>`` and
``<retired>`` name the same directive, exactly as an identifier differing only
in case names the same requirement (REQ-d00212-R); rendering emits the one
canonical spelling. The delimiters are NOT normalized -- the three pairs are
equals, so choosing one for the author would rewrite text that is already
correct.

Whether a retired *Assertion* counts is asked HERE, through
:func:`assertion_is_retired` and :func:`iter_counted_assertions`. Every
coverage and *Traceability* calculation asks through them rather than reading
the field, so retirement is one decision rather than one per surface.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from elspais.graph.GraphNode import GraphNode

# The opening delimiters that introduce a directive, each mapped to the closer
# that ends it. A non-letter opening character outside this table opens
# nothing: an *Assertion* may legitimately begin with a backtick, a quote or an
# emphasis marker, and reading those as directives would report defects in
# prose that is merely formatted.
DIRECTIVE_DELIMITERS: dict[str, str] = {"<": ">", "[": "]", "{": "}"}

# The one recognized directive name, in its canonical spelling.
RETIRED = "RETIRED"

# Every directive the tool recognizes, keyed by the spelling used for matching
# (upper case) and valued by the canonical spelling used for rendering.
RECOGNIZED_DIRECTIVES: dict[str, str] = {RETIRED: RETIRED}

# The node fields a parsed directive is recorded in. Named here so the readers
# below and the builder that writes them cannot drift apart.
FIELD_DIRECTIVE = "directive"
FIELD_RECOGNIZED = "directive_recognized"
FIELD_RETIRED = "retired"


@dataclass(frozen=True)
class AssertionDirective:
    """One directive read off the head of an *Assertion*'s text.

    Attributes:
        name: The directive as written, with surrounding whitespace removed.
            Reported verbatim, because an unrecognized directive is reported
            to its author, who has to recognize what they wrote.
        canonical_name: The one spelling a recognized directive renders in;
            ``None`` when the directive is not recognized, since the tool has
            no canonical spelling to offer for a name it does not know.
        opener: The opening delimiter the author chose.
        closer: Its matching counterpart.
        content: Everything following the closer, VERBATIM -- leading spaces
            included. Preserving it exactly is what lets a retired *Assertion*
            carrying commentary round-trip through a rewrite unchanged.
    """

    name: str
    canonical_name: str | None
    opener: str
    closer: str
    content: str

    @property
    def recognized(self) -> bool:
        """Whether the tool knows this directive."""
        return self.canonical_name is not None

    @property
    def retired(self) -> bool:
        """Whether this directive withdraws the *Assertion* (REQ-p00017-G)."""
        return self.canonical_name == RETIRED

    def render(self) -> str:
        """The *Assertion* text this directive and its content spell.

        A recognized directive renders in its canonical spelling; an
        unrecognized one renders exactly as written, because normalizing a
        name the tool does not know would rewrite an author's text on a guess.
        """
        name = self.canonical_name if self.canonical_name is not None else self.name
        return f"{self.opener}{name}{self.closer}{self.content}"


# Implements: REQ-p00002-E
def read_directive(text: str | None) -> AssertionDirective | None:
    """The directive at the head of *text*, or ``None`` where there is none.

    A directive needs both halves: an opening delimiter this module admits and
    its matching closer somewhere after it. Text opening a pair it never closes
    is ordinary content -- an *Assertion* discussing ``<`` in prose has not
    declared anything.
    """
    if not text:
        return None
    stripped = text.lstrip()
    if not stripped:
        return None
    opener = stripped[0]
    closer = DIRECTIVE_DELIMITERS.get(opener)
    if closer is None:
        return None
    end = stripped.find(closer, 1)
    if end == -1:
        return None
    name = stripped[1:end].strip()
    if not name:
        return None
    return AssertionDirective(
        name=name,
        canonical_name=RECOGNIZED_DIRECTIVES.get(name.upper()),
        opener=opener,
        closer=closer,
        content=stripped[end + 1 :],
    )


# Implements: REQ-p00002-E
def canonical_assertion_text(text: str | None) -> str:
    """*text* with any recognized directive spelled canonically.

    Text carrying no directive, or one the tool does not recognize, is returned
    unchanged: the only spelling this function knows how to correct is one it
    recognizes.
    """
    if text is None:
        return ""
    directive = read_directive(text)
    if directive is None or not directive.recognized:
        return text
    return directive.render()


# Implements: REQ-p00017-G
def assertion_is_retired(node: GraphNode) -> bool:
    """Whether *node* is an *Assertion* withdrawn by the RETIRED directive.

    The ONE question every coverage and *Traceability* calculation asks before
    counting an *Assertion*, so that "does not exist for coverage purposes" is
    decided once rather than per surface.
    """
    return bool(node.get_field(FIELD_RETIRED, False))


# Implements: REQ-p00017-G
def counted_assertions(node: GraphNode, *, structural: bool = False) -> list[GraphNode]:
    """*node*'s *Assertion* children that coverage counts.

    Retired *Assertions* are absent from the result: they are excluded from
    every coverage and *Traceability* calculation (REQ-p00017-G), and a
    calculation that never sees one cannot count it.

    Args:
        node: The REQUIREMENT whose *Assertions* are wanted.
        structural: Restrict the walk to STRUCTURES edges, for callers that
            must not follow the *Traceability* edges a requirement also holds.
    """
    return list(iter_counted_assertions(node, structural=structural))


# Implements: REQ-p00017-G
def iter_counted_assertions(node: GraphNode, *, structural: bool = False) -> Iterator[GraphNode]:
    """Iterate *node*'s *Assertion* children that coverage counts."""
    from elspais.graph.GraphNode import NodeKind

    kinds: Any = None
    if structural:
        from elspais.graph.relations import EdgeKind

        kinds = {EdgeKind.STRUCTURES}
    children = node.iter_children(edge_kinds=kinds) if kinds else node.iter_children()
    for child in children:
        if child.kind == NodeKind.ASSERTION and not assertion_is_retired(child):
            yield child


# Implements: REQ-p00017-G
def counted_assertion_labels(node: GraphNode, *, structural: bool = False) -> list[str]:
    """The labels of *node*'s counted *Assertions*, unlabelled ones dropped."""
    return [
        label
        for child in iter_counted_assertions(node, structural=structural)
        if (label := child.get_field("label", ""))
    ]


def apply_directive(node: GraphNode, text: str | None) -> str:
    """Record the directive *text* carries on *node* and return its rendering.

    Used wherever an *Assertion*'s text is set after parse, so text arriving
    through a mutation is read for a directive exactly as text arriving from a
    file is. Fields belonging to a directive the new text does NOT carry are
    cleared: an *Assertion* edited out of retirement is no longer retired, and
    a stale flag would keep it out of every denominator it has rejoined.
    """
    fields = directive_fields(text)
    for field in (FIELD_DIRECTIVE, FIELD_RECOGNIZED, FIELD_RETIRED):
        if field in fields:
            node.set_field(field, fields[field])
        elif node.get_field(field, None) is not None:
            node.set_field(field, None)
    return canonical_assertion_text(text)


def directive_fields(text: str | None) -> dict[str, Any]:
    """The node fields recording the directive *text* carries, if any.

    Returned as a mapping so a node-building caller writes what a directive
    determines and nothing else: an *Assertion* without one carries no
    directive fields at all, rather than fields spelling its absence.
    """
    directive = read_directive(text)
    if directive is None:
        return {}
    fields: dict[str, Any] = {
        FIELD_DIRECTIVE: directive.canonical_name or directive.name,
        FIELD_RECOGNIZED: directive.recognized,
    }
    if directive.retired:
        fields[FIELD_RETIRED] = True
    return fields
