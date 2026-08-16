"""The vocabulary a reference fault is reported in.

Two vocabularies with different obligations, kept apart here so neither
constrains the other.  The *class* is closed: a project configures a severity
per class, so adding one reopens a decision the project already made.  The
*codes* are open: a diagnosis becomes more specific over releases without
anything having to be reconfigured (REQ-d00271-E).
"""

from __future__ import annotations

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
    WRONG_CASE = "E_WRONG_CASE"
    WRONG_PADDING = "E_WRONG_PADDING"
    WRONG_ASSERTION_SEPARATOR = "E_WRONG_ASSERTION_SEPARATOR"
    WRONG_MULTI_SEPARATOR = "E_WRONG_MULTI_SEPARATOR"
    LABEL_OUT_OF_SERIES = "E_LABEL_OUT_OF_SERIES"
    TRAILING_SEPARATOR = "E_TRAILING_SEPARATOR"
    EMPTY_ITEM = "E_EMPTY_ITEM"
    EMPTY_REFERENCE_LIST = "E_EMPTY_REFERENCE_LIST"
    IDENTIFIER_WITH_TRAILING_TEXT = "E_IDENTIFIER_WITH_TRAILING_TEXT"
    AMBIGUOUS = "E_AMBIGUOUS"
    ORPHAN_REFERENCE = "E_ORPHAN_REFERENCE"


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
