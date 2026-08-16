# Verifies: REQ-p00014-T, REQ-d00269-G
"""Dividing a list of references into its items.

A *Traceability* keyword introduces a list and nothing else, and the one
place that list is divided is ``FederatedIdReader.parse_ref_list``. It
judges every item on its own and returns a verdict for each -- resolved, or
faulted -- regardless of ``on_unmatched``. What becomes of a faulted item on
behalf of the whole line is the caller's policy, not the divider's:

``reject``
    A scanned annotation is found in the wild. A line the grammar can only
    partly account for is a line read wrongly, so the caller discards the
    whole line rather than keeping whichever items parsed.
``keep``
    A reference authored in a spec file is data. A wrong one has to survive
    being read in order to be reported as a broken reference; a caller that
    dropped the line would retire the diagnostic along with the typo.

These pin the difference, so a later unification on one policy has to face
the surface it would silence.
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
def test_a_reference_no_grammar_claims_survives_the_keep_policy():
    """The unreadable item is carried through as its own item, verbatim, so
    a caller applying the spec-file policy can still report it."""
    items = _reader().parse_ref_list(f"{_GOOD}, {_TYPO}", on_unmatched="keep")

    assert len(items) == 2, f"every item gets its own verdict; got {items}"
    typo_item = items[1]
    assert typo_item.raw == _TYPO, (
        "the item no grammar accounts for must reach the caller verbatim -- "
        f"dropping it retires the broken-reference report; got {typo_item}"
    )
    assert typo_item.resolved is None
    assert typo_item.fault_class is not None
    good_item = items[0]
    assert good_item.resolved is not None and good_item.resolved.startswith(
        "REQ-p00001"
    ), f"the readable reference must survive alongside it; got {items}"


# Verifies: REQ-p00014-T, REQ-d00269-G
@pytest.mark.parametrize("policy", ["keep", "reject"])
def test_on_unmatched_does_not_change_what_parse_ref_list_returns(policy):
    """``on_unmatched`` is the caller's policy for the whole line -- the
    divider classifies each item the same way regardless of it."""
    items = _reader().parse_ref_list(f"{_GOOD}, {_TYPO}", on_unmatched=policy)

    assert len(items) == 2
    assert items[0].resolved is not None
    assert items[1].raw == _TYPO
    assert items[1].fault_class is not None


# Verifies: REQ-p00014-T
@pytest.mark.parametrize("policy", ["keep", "reject"])
def test_a_wholly_readable_list_reads_the_same_under_either_policy(policy):
    """The policies differ only over the item that cannot be read."""
    items = _reader().parse_ref_list(f"{_GOOD}, REQ-p00002", on_unmatched=policy)

    refs = [i.resolved for i in items if i.resolved]
    assert "REQ-p00002" in refs
    assert _TYPO not in refs


# Verifies: REQ-p00014-T
def test_an_unrecognised_policy_is_refused():
    """There are two policies, and the caller names one of them."""
    with pytest.raises(ValueError, match="on_unmatched"):
        _reader().parse_ref_list(_GOOD, on_unmatched="ignore")


# Verifies: REQ-d00269-G
def test_a_repeated_unmatched_item_reaches_the_caller_once():
    """A typo written twice in the same list must not double the diagnostic
    -- the divider deduped every branch uniformly before per-item verdicts
    existed, and a caller that keeps unmatched items (a spec file's
    ``Implements:``) must still see one entry, not two."""
    items = _reader().parse_ref_list(f"{_TYPO}, {_TYPO}", on_unmatched="keep")
    refs = [i.resolved if i.resolved else i.raw for i in items if i.raw]

    assert refs == [_TYPO], (
        "a duplicate unmatched item must collapse to one caller-visible "
        f"entry, exactly as the original divider collapsed it; got {refs}"
    )


_SPEC_CONFIG = """\
version = 3

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

    broken = [br for br in graph.broken_references() if br.source_id == "REQ-d00001"]
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
