"""Classification of reference list items."""

import pathlib

import pytest

from elspais.config import load_config
from elspais.graph.reference_faults import FaultClass, FaultCode, ReferenceFault
from elspais.utilities.patterns import FederatedIdReader, build_resolver


# Verifies: REQ-p00014-R
def test_fault_classes_are_ordered_by_how_far_reading_got():
    """A later class means reading got further, so the order is meaningful."""
    order = list(FaultClass)
    assert order == [
        FaultClass.MALFORMED,
        FaultClass.UNKNOWN_NAMESPACE,
        FaultClass.UNKNOWN_REQUIREMENT,
        FaultClass.UNKNOWN_ASSERTION,
        FaultClass.FORBIDDEN,
    ]
    assert FaultClass.MALFORMED.stage < FaultClass.UNKNOWN_NAMESPACE.stage
    assert FaultClass.UNKNOWN_ASSERTION.stage < FaultClass.FORBIDDEN.stage


# Verifies: REQ-d00271-C
def test_a_fault_always_carries_the_generic_code():
    fault = ReferenceFault(
        source_id="code:/x.py",
        target_id="not a reference",
        edge_kind="implements",
        fault_class=FaultClass.MALFORMED,
    )
    assert FaultCode.SYNTAX_ERROR in fault.codes


# Verifies: REQ-d00271-B
def test_a_fault_may_carry_several_specific_codes():
    fault = ReferenceFault(
        source_id="code:/x.py",
        target_id="req-d1",
        edge_kind="implements",
        fault_class=FaultClass.MALFORMED,
        codes=(FaultCode.WRONG_CASE, FaultCode.WRONG_PADDING),
    )
    assert FaultCode.SYNTAX_ERROR in fault.codes
    assert FaultCode.WRONG_CASE in fault.codes
    assert FaultCode.WRONG_PADDING in fault.codes


@pytest.fixture(scope="module")
def repo_root():
    return pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def reader(repo_root):
    """A reader over this repository's own grammar (REQ namespace, 5 digits)."""
    resolver = build_resolver(load_config(repo_root / ".elspais.toml"))
    return FederatedIdReader(own=resolver)


# Verifies: REQ-d00269-G
def test_every_item_gets_its_own_verdict(reader):
    items = reader.parse_ref_list("REQ-d00001, not a reference, REQ-d00002")
    assert [i.index for i in items] == [0, 1, 2]
    assert items[0].resolved == "REQ-d00001"
    assert items[2].resolved == "REQ-d00002"
    assert items[1].resolved is None
    assert items[1].raw == "not a reference"


# Verifies: REQ-d00269-G
def test_an_item_that_read_carries_no_fault(reader):
    items = reader.parse_ref_list("REQ-d00001")
    assert items[0].fault_class is None
    assert items[0].codes == ()


# Verifies: REQ-d00271-A
def test_empty_content_yields_no_items(reader):
    assert reader.parse_ref_list("") == []
    assert reader.parse_ref_list("   ") == []


# Verifies: REQ-d00269-G
def test_a_repeated_unmatched_item_collapses_to_one(reader):
    """A duplicate item collapses to one entry whether or not it resolved --
    the divider deduped uniformly before this task and must go on doing so,
    since a caller that keeps an unmatched item relies on that collapse to
    avoid reporting and wiring the same typo twice."""
    items = reader.parse_ref_list("BADREF, BADREF")
    assert len(items) == 1
    assert items[0].raw == "BADREF"
    assert items[0].resolved is None
    assert items[0].fault_class is not None


# Verifies: REQ-d00269-G
def test_a_defect_costs_one_reference_not_the_line(reader):
    items = reader.parse_ref_list("REQ-d00001, REQ-d0000X, REQ-d00002")
    bound = [i.resolved for i in items if i.resolved]
    assert bound == ["REQ-d00001", "REQ-d00002"]
    failed = [i for i in items if i.fault_class is not None]
    assert len(failed) == 1
    assert failed[0].raw == "REQ-d0000X"


# Verifies: REQ-d00269-G, REQ-p00014-T
def test_a_trailing_separator_binds_what_precedes_it(reader):
    items = reader.parse_ref_list("REQ-d00001,")
    assert [i.resolved for i in items if i.resolved] == ["REQ-d00001"]
    empties = [i for i in items if FaultCode.EMPTY_ITEM in i.codes]
    assert len(empties) == 1


# Verifies: REQ-d00269-G
def test_an_item_is_matched_whole_never_searched_inside(reader):
    """XREQ-d00001 must not bind REQ-d00001 -- an edge nobody declared."""
    items = reader.parse_ref_list("XREQ-d00001")
    assert items[0].resolved is None
    assert items[0].fault_class is not None


# Verifies: REQ-d00269-G
def test_a_code_file_binds_the_good_items_of_a_mixed_line(tmp_path, repo_root):
    """The whole pipeline: a line with one bad item still binds the others."""
    from elspais.config import load_config
    from elspais.graph.factory import build_graph

    (tmp_path / ".elspais.toml").write_text((repo_root / ".elspais.toml").read_text())
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "r.md").write_text(
        "# REQ-d00001: Thing\n\n"
        "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        "## Assertions\n\n"
        "A. The system SHALL do a thing.\n\n"
        "*End* *Thing* | **Hash**: 00000000\n"
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "m.py").write_text("# Implements: REQ-d00001-A, REQ-d0000X\ndef f():\n    return 1\n")
    config_path = tmp_path / ".elspais.toml"
    graph = build_graph(
        load_config(config_path),
        config_path=config_path,
        repo_root=tmp_path,
        scan_code=True,
        scan_tests=False,
    )
    targets = {f.target_id for f in graph.broken_references()}
    assert "REQ-d0000X" in targets
    assert "REQ-d00001-A" not in targets  # the good item bound


# Verifies: REQ-d00269-G
def test_an_underscore_notation_item_binds_in_a_reference_list(reader):
    """A list item spelled in underscore notation -- the same grammar a
    Python test function name renders (``IdResolver.grammar(separator="_")``)
    -- is matched whole and resolves, not left as a string no member's
    canonical, dash-separated form claims."""
    items = reader.parse_ref_list("REQ_d00001_A")
    assert items[0].resolved == "REQ-d00001-A"
    assert items[0].fault_class is None
