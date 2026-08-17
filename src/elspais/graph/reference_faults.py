"""The vocabulary a reference fault is reported in.

Two vocabularies with different obligations, kept apart here so neither
constrains the other.  The *class* is closed: a project configures a severity
per class, so adding one reopens a decision the project already made.  The
*codes* are open: a diagnosis becomes more specific over releases without
anything having to be reconfigured (REQ-d00271-E).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class FaultClass(Enum):
    """How far reading a reference got before it failed.

    The order is the reading order, and it is what makes "no later class than
    the one the reference reached" checkable (REQ-p00014-R, REQ-d00272-A).
    """

    # Implements: REQ-p00014-R, REQ-d00272-A
    MALFORMED = ("malformed", 0)
    UNKNOWN_NAMESPACE = ("unknown_namespace", 1)
    UNKNOWN_REQUIREMENT = ("unknown_requirement", 2)
    UNKNOWN_ASSERTION = ("unknown_assertion", 3)
    FORBIDDEN = ("forbidden", 4)

    def __init__(self, label: str, stage: int) -> None:
        self.label = label
        self.stage = stage


class FaultCode:
    """What is wrong with an item, named only where the input determines it.

    Codes are not disjoint: an item defective in several independent respects
    carries a code for each (REQ-d00271-B).  ``SYNTAX_ERROR`` is carried by
    every fault, and carried *alone* it is the report that nothing more
    specific is known -- not the absence of a diagnosis (REQ-d00271-C).
    """

    # Implements: REQ-d00271-A, REQ-d00271-E
    SYNTAX_ERROR = "E_SYNTAX_ERROR"
    NOT_AN_IDENTIFIER = "E_NOT_AN_IDENTIFIER"
    WRONG_ASSERTION_SEPARATOR = "E_WRONG_ASSERTION_SEPARATOR"
    WRONG_MULTI_SEPARATOR = "E_WRONG_MULTI_SEPARATOR"
    LABEL_OUT_OF_SERIES = "E_LABEL_OUT_OF_SERIES"
    TRAILING_SEPARATOR = "E_TRAILING_SEPARATOR"
    EMPTY_ITEM = "E_EMPTY_ITEM"
    EMPTY_REFERENCE_LIST = "E_EMPTY_REFERENCE_LIST"
    IDENTIFIER_WITH_TRAILING_TEXT = "E_IDENTIFIER_WITH_TRAILING_TEXT"
    # A numeric component's VALUE exceeds what the configuration admits
    # (REQ-d00212-T).  Distinct from a padding defect: re-padding cannot make
    # an out-of-range value fit, so nothing about the spelling would answer
    # it -- the number itself is one this repository cannot name.
    COMPONENT_OUT_OF_RANGE = "E_COMPONENT_OUT_OF_RANGE"
    # Implements: REQ-d00272-K
    DUPLICATE_ITEM = "E_DUPLICATE_ITEM"
    # An identifier is spelled in a form the configuration admits but is not
    # the canonical one -- the finding never costs the relationship the
    # reference names (REQ-d00272-N).  ``NON_CANONICAL_SPELLING`` is carried
    # by every such finding and, carried alone, is the report that the
    # spelling differs in no respect the tool has a name for.
    NON_CANONICAL_SPELLING = "E_NON_CANONICAL_SPELLING"
    WRONG_CASE = "E_WRONG_CASE"
    WRONG_PADDING = "E_WRONG_PADDING"
    # A keyword's form is non-canonical -- the finding never costs the edge
    # its keyword introduces (REQ-d00272-G).
    KEYWORD_WRONG_CASE = "E_KEYWORD_WRONG_CASE"
    KEYWORD_NO_MARKER_SPACE = "E_KEYWORD_NO_MARKER_SPACE"
    KEYWORD_MARKDOWN_EMPHASIS_OFF_MARKDOWN = "E_KEYWORD_MARKDOWN_EMPHASIS_OFF_MARKDOWN"


@dataclass(frozen=True)
class ReferenceFault:
    """A declared reference that produced no relationship.

    Attributes:
        source_id: ID of the node holding the reference.
        target_id: The item as written, verbatim -- reporting it is the point.
        edge_kind: The relationship the keyword would have produced.
        fault_class: How far reading got.  Never later than it reached.
        codes: What is wrong, where the input determines it.
        item_index: Which item of the list, 0-based; -1 when the whole
            content is at fault rather than one item of it.
        presumed_foreign: Retained for the clone-assistance path, which
            reports a target belonging to a repository that is declared but
            absent, and is a different question from this fault's class.
        diagnostic: Free text from the validation matrix, surfaced verbatim
            (REQ-p00014-F).
        line: The line the reference was written on, when the fault is
            anchored to a node (a FILE, say) that carries no ``parse_line``
            of its own -- an empty reference list or a trailing separator
            has nowhere else to put it, so it rides on the fault
            (REQ-d00252-K).
    """

    source_id: str
    target_id: str
    edge_kind: str
    fault_class: FaultClass = FaultClass.UNKNOWN_REQUIREMENT
    # Implements: REQ-d00271-B
    codes: tuple[str, ...] = ()
    item_index: int = -1
    presumed_foreign: bool = False
    diagnostic: str = ""
    line: int | None = None

    # Implements: REQ-d00271-C
    def __post_init__(self) -> None:
        if FaultCode.SYNTAX_ERROR not in self.codes:
            object.__setattr__(self, "codes", (FaultCode.SYNTAX_ERROR, *self.codes))

    def __str__(self) -> str:
        foreign = " [foreign]" if self.presumed_foreign else ""
        return (
            f"{self.source_id} --[{self.edge_kind}]--> {self.target_id} "
            f"({self.fault_class.label}{foreign})"
        )


# Implements: REQ-d00269-G
@dataclass(frozen=True)
class RefItem:
    """One item of a reference list, and what became of it.

    Exactly one of ``resolved`` and ``fault_class`` is set.  A list is judged
    item by item, so an item that read produces its relationship whatever its
    neighbours did (REQ-d00269-G).

    Attributes:
        raw: The item as the author wrote it, stripped of surrounding space.
        resolved: The normalized reference, or None if the item did not read.
        index: Position in the list, 0-based.
        fault_class: How far reading this item got, or None if it read.
        codes: What is wrong with it, where the input determines that.
    """

    raw: str
    index: int
    resolved: str | None = None
    fault_class: FaultClass | None = None
    codes: tuple[str, ...] = ()


# Implements: REQ-d00269-G, REQ-d00272-K
def refs_and_verdicts(
    items: list[RefItem],
) -> tuple[list[str], dict[str, tuple[FaultClass, tuple[str, ...]]]]:
    """Split a ``parse_ref_list`` result into the shape every caller needs.

    ``refs`` keeps one entry per item -- resolved where an item read, raw
    where it did not, so a faulted item survives to be reported instead of
    vanishing.  ``verdicts`` is keyed by raw text (the form that reaches the
    builder as a pending link's target) and carries every item's class and
    codes, INCLUDING a resolved item's -- an item that read cleanly but was
    later found to repeat a target it shares with a sibling has its
    ``resolved`` cleared and its verdict set to ``FORBIDDEN``/
    ``DUPLICATE_ITEM`` by ``parse_ref_list`` itself, and that verdict must
    still reach the builder alongside its raw text. One reading, so every
    surface that divides a reference list -- code/test annotations, spec
    metadata, journey ``Validates:`` -- hands its builder the identical
    shape rather than three near-identical transforms of the same list.
    """
    refs = [i.resolved or i.raw for i in items if i.raw]
    verdicts = {i.raw: (i.fault_class, i.codes) for i in items if i.fault_class is not None}
    return refs, verdicts


# Implements: REQ-d00272-G
@dataclass(frozen=True)
class StyleFinding:
    """A keyword written in a non-canonical form.

    Never withholds the edge its keyword introduces -- it is a fact about
    how the file is written, not about whether the reference resolved, so it
    is reported through its own rule rather than joining a bucket that
    counts references that failed to bind.

    Attributes:
        source_id: ID of the node the finding is anchored to (a FILE node,
            when no more specific node exists for the line).
        code: One of the keyword-form codes (``E_KEYWORD_*``).
        line: The line the keyword was written on.
    """

    source_id: str
    code: str
    line: int | None = None


# Implements: REQ-d00272-N
@dataclass(frozen=True)
class IdentifierFormFinding:
    """A reference spelled in a form the configuration admits, but not the
    canonical one.

    The referent counterpart of :class:`StyleFinding`, and it says the same
    thing about the identifier that that says about the keyword: a spelling
    the configuration admits produces the relationship it names, and that it
    is not the canonical spelling is a fact about the file worth reporting
    rather than a reason to withhold an edge.

    Attributes:
        source_id: ID of the node the finding is anchored to.
        text: The reference as the author wrote it.
        codes: ``NON_CANONICAL_SPELLING`` always, plus whichever of
            ``WRONG_CASE``/``WRONG_PADDING`` the input determines.
        line: The line the reference was written on.
    """

    source_id: str
    text: str
    codes: tuple[str, ...] = ()
    line: int | None = None

    def __post_init__(self) -> None:
        if FaultCode.NON_CANONICAL_SPELLING not in self.codes:
            object.__setattr__(self, "codes", (FaultCode.NON_CANONICAL_SPELLING, *self.codes))


# Zeros that open a digit run -- the padding a component style adds, as
# opposed to a zero that is part of the number.
_LEADING_ZEROS = re.compile(r"(?<!\d)0+(\d)")


def _unpadded(text: str) -> str:
    """*text* with the padding zeros stripped from every component."""
    return _LEADING_ZEROS.sub(r"\1", text)


# Implements: REQ-d00272-N, REQ-d00271-D
def identifier_form_defects(raw: str, resolved: str | None) -> tuple[str, ...]:
    """How *raw*'s spelling differs from the canonical *resolved* one.

    Empty where the item did not resolve (a reference that produced no
    relationship is a fault, and its spelling is not the story) or where it
    was already written canonically.  Otherwise the generic code, plus
    whichever of case and padding the two spellings determine -- and only
    those: a difference in neither is reported as the generic code alone
    rather than guessed at (REQ-d00271-D).
    """
    if not resolved or raw == resolved:
        return ()
    codes: list[str] = []
    if _unpadded(raw).lower() == _unpadded(resolved).lower():
        if raw.lower() != resolved.lower():
            codes.append(FaultCode.WRONG_PADDING)
        if _unpadded(raw) != _unpadded(resolved):
            codes.append(FaultCode.WRONG_CASE)
    return (FaultCode.NON_CANONICAL_SPELLING, *sorted(codes))


# Implements: REQ-d00272-O
@dataclass(frozen=True)
class UndeclaredRelationship:
    """An identifier opening a comment that no *Traceability* keyword introduces.

    Opening a comment with an identifier and then explaining, in prose, why
    the code below answers to it is a natural way to write, and an author
    doing it means the relationship -- they have simply not spelled it in
    the form the tool reads.  Nothing about the line is malformed, so it is
    not a reference fault; and reading intent as a declaration is the
    failure this whole vocabulary exists to prevent, so it produces no
    relationship.  It is reported on its own, at its own severity, with a
    message that leads the author to write the keyword.

    Two comments are excluded, and neither is a citation: one a keyword
    introduces is already a declaration, and one continuing a list is an
    item of that list.  Both are consumed before this is reached.

    Attributes:
        source_id: ID of the node the finding is anchored to -- the FILE
            node, since no CODE/TEST node exists for a line that declared
            nothing.
        text: The comment as written, verbatim.
        line: The line the comment was written on.
    """

    source_id: str
    text: str
    line: int | None = None
