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
