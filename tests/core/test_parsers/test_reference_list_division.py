# Verifies: REQ-p00014-T, REQ-d00269-G
"""Dividing a list of references into its items.

A *Traceability* keyword introduces a list and nothing else, and the one
place that list is divided is ``FederatedIdReader.parse_ref_list``. It
judges every item on its own and returns a verdict for each -- resolved, or
faulted. There is no caller-selectable policy: a faulted item always stays
in the returned list, carrying the class it reached, so every caller reports
it rather than losing it. What a caller does with that verdict -- report the
faulted item as broken, drop it from a scanned annotation's edges, keep it
verbatim in a spec file's metadata -- is the caller's own business, decided
by what it does with ``.resolved``/``.fault_class`` on each item; it is no
longer a parameter of the divider itself (REQ-d00269-G).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.config.schema import ElspaisConfig
from elspais.utilities.patterns import FederatedIdReader, build_resolver

_GOOD = "REQ-p00001/A&B"
_TYPO = "TYPO-999"


def _reader() -> FederatedIdReader:
    """A reader for a repository that separates a label with "/" and joins
    several with "&"."""
    config = {
        "project": {"namespace": "REQ"},
        "levels": {
            "prd": {"rank": 1, "letter": "p", "implements": ["prd"]},
            "dev": {"rank": 2, "letter": "d", "implements": ["dev", "prd"]},
        },
        "id-patterns": {
            "canonical": "{namespace}-{level.letter}{component}",
            "component": {"style": "numeric", "digits": 5},
            "assertions": {
                "label_style": "uppercase",
                "separator": "/",
                "multi_separator": "&",
            },
        },
    }
    ElspaisConfig.model_validate(config)
    return FederatedIdReader(build_resolver(config))


# Verifies: REQ-p00014-T, REQ-d00269-G
def test_an_unreadable_item_survives_alongside_a_readable_one():
    """The unreadable item is carried through as its own item, verbatim, and
    the readable item beside it still resolves -- a defect in one item is
    evidence about that item, not the list."""
    items = _reader().parse_ref_list(f"{_GOOD}, {_TYPO}")

    assert len(items) == 2, f"every item gets its own verdict; got {items}"
    typo_item = items[1]
    assert typo_item.raw == _TYPO, (
        "the item no grammar accounts for must reach the caller verbatim -- "
        f"dropping it retires the broken-reference report; got {typo_item}"
    )
    assert typo_item.resolved is None
    assert typo_item.fault_class is not None
    good_item = items[0]
    assert good_item.resolved is not None and good_item.resolved.startswith("REQ-p00001"), (
        f"the readable reference must survive alongside it; got {items}"
    )


# Verifies: REQ-p00014-T
def test_a_wholly_readable_list_reads_cleanly():
    """A list with no defect carries no fault for any item."""
    items = _reader().parse_ref_list(f"{_GOOD}, REQ-p00002")

    refs = [i.resolved for i in items if i.resolved]
    assert "REQ-p00002" in refs
    assert _TYPO not in refs


# Verifies: REQ-d00269-G
def test_a_repeated_unmatched_item_reaches_the_caller_at_each_position():
    """A typo written twice in the same list is judged at each position of
    the list on its own (REQ-d00269-G): an item that never resolved names
    no target, so it is not the "repeated target" REQ-d00272-K collapses --
    a caller that keeps unmatched items (a spec file's ``Implements:``) sees
    both."""
    items = _reader().parse_ref_list(f"{_TYPO}, {_TYPO}")
    refs = [i.resolved if i.resolved else i.raw for i in items if i.raw]

    assert refs == [_TYPO, _TYPO]


_SPEC_CONFIG = """\
version = 5

[project]
name = "keeptypo"
namespace = "REQ"

[id-patterns.assertions]
label_style = "uppercase"
separator = "/"
multi_separator = "&"

[levels.prd]
rank = 1
letter = "p"
implements = []

[levels.dev]
rank = 2
letter = "d"
implements = ["dev", "prd"]
"""

_SPEC_FILES = """\
# REQ-p00001: Widget

The system provides widgets.

## Assertions

A. The system SHALL frob.

B. The system SHALL twiddle.

*End* *Widget*

# REQ-d00001: Widget implementation

**Implements**: REQ-p00001/A&B, TYPO-999

The widget detail.

## Assertions

A. The system SHALL flush.

*End* *Widget implementation*
"""


# Verifies: REQ-p00014-T
def test_a_typo_in_a_spec_metadata_line_is_reported_not_dropped(tmp_path: Path):
    """End to end: the unreadable item reaches the broken-reference report,
    and the readable ones still wire their edges."""
    from elspais.graph.factory import build_graph

    project = tmp_path / "keeptypo"
    (project / "spec").mkdir(parents=True)
    (project / ".elspais.toml").write_text(_SPEC_CONFIG, encoding="utf-8")
    (project / "spec" / "spec.md").write_text(_SPEC_FILES, encoding="utf-8")

    graph = build_graph(config_path=project / ".elspais.toml", repo_root=project, scan_code=False)

    broken = [br for br in graph.unresolved_references() if br.source_id == "REQ-d00001"]
    assert [br.target_id for br in broken] == [_TYPO], (
        "the reference no grammar accounts for must be reported, not silently "
        f"dropped along with the line; got {broken}"
    )

    parent = graph.find_by_id("REQ-p00001")
    assert parent is not None
    targets = sorted(
        label
        for edge in parent.iter_outgoing_edges()
        if edge.target.id == "REQ-d00001"
        for label in edge.assertion_targets
    )
    assert targets == [
        "A",
        "B",
    ], f"the readable references on the same line must still wire; got {targets}"


# ---------------------------------------------------------------------------
# Placeholders: a target its author declared as not yet chosen.
#
# REQ-d00287-B widened what a reference list is composed of -- identifiers,
# PLACEHOLDERS, separators and whitespace -- and REQ-d00287-H fixes the
# spelling: a form no identifier can take. Everything below is asked of the
# reader configured above, whose separators are "/" and "&" rather than the
# shipped defaults, so nothing here can be passing because of a separator.
# ---------------------------------------------------------------------------


# Verifies: REQ-d00287-B, REQ-d00287-H
@pytest.mark.parametrize(
    "written",
    ["<TBD>", "[TODO]", "<TBD, see the ticket>", "[the requirement for step 3]"],
)
def test_a_target_declared_as_not_yet_chosen_reads_as_one_placeholder(written: str):
    """An item wholly enclosed is one item, and it is a placeholder rather
    than a reading that failed. ``<TBD, see the ticket>`` is the case that
    matters most: the separator inside the enclosure must not shred it into
    two items, which would report one deliberate blank as two broken
    references."""
    items = _reader().parse_ref_list(written)

    assert len(items) == 1, f"an enclosure is one item however it is spelled inside; got {items}"
    item = items[0]
    assert item.raw == written
    assert item.placeholder is True
    assert item.resolved is None, "a placeholder names nothing, so it binds nothing"
    assert item.fault_class is None, (
        "nothing went wrong reading a placeholder -- carrying a fault class "
        f"would report a deliberate blank as a defect; got {item}"
    )


# Verifies: REQ-d00287-H
@pytest.mark.parametrize("written", ["TBD", "TODO", "a <b> c", "<TBD", "TBD>", "REQ-p00001<A>"])
def test_a_target_not_wholly_enclosed_is_not_excused_as_a_placeholder(written: str):
    """The enclosure is what puts a placeholder out of the identifier
    grammar's reach, so it must be the whole item. A bare word and a partial
    enclosure are references that did not read, and each keeps the class it
    reached -- otherwise a mistyped identifier could be excused as a blank
    its author left on purpose."""
    items = _reader().parse_ref_list(written)

    assert len(items) == 1
    item = items[0]
    assert item.placeholder is False, f"{written!r} must not read as a placeholder; got {item}"
    assert item.resolved is None
    assert item.fault_class is not None, (
        f"{written!r} is a reference that did not read and must carry its class; got {item}"
    )


# Verifies: REQ-d00287-B
def test_a_placeholder_beside_a_reference_costs_the_reference_nothing():
    """Each item is judged on its own, so a blank left on purpose in one
    position leaves the real reference beside it resolving."""
    items = _reader().parse_ref_list(f"<TBD>, {_GOOD}")

    assert [i.placeholder for i in items] == [True, False]
    assert items[1].resolved is not None and items[1].resolved.startswith("REQ-p00001"), (
        f"the reference beside a placeholder must still resolve; got {items}"
    )


# Verifies: REQ-d00287-H, REQ-d00287-I
def test_a_placeholder_produces_no_reference_and_no_verdict():
    """``refs_and_verdicts`` is what a caller wires edges and reports faults
    from. A placeholder must reach neither: passing it through as a
    reference would have the builder bind a blank, and as a verdict would
    report one as a citation that broke. ``placeholders_of`` is where it
    does surface, as written."""
    from elspais.graph.reference_faults import placeholders_of, refs_and_verdicts

    items = _reader().parse_ref_list(f"<TBD>, {_GOOD}")
    refs, verdicts = refs_and_verdicts(items, "implements")

    assert "<TBD>" not in refs
    assert not any("<TBD>" in str(key) for key in verdicts)
    assert len(refs) == 1, f"only the real reference contributes a target; got {refs}"
    assert placeholders_of(items) == ["<TBD>"]


# Verifies: REQ-d00287-B
def test_the_separator_divides_a_list_only_outside_an_enclosure():
    """The division is the mirror of the composition rule: enclosures are
    recognised before the separator is honoured, so a list mixing the two
    yields one item per author-intended target."""
    from elspais.utilities.patterns import split_ref_list

    assert split_ref_list("<TBD, see the ticket>, REQ-p00001, [later]") == [
        "<TBD, see the ticket>",
        " REQ-p00001",
        " [later]",
    ]
