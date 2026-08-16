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
def test_a_repeated_unmatched_item_is_reported_at_every_position(reader):
    """An item that never resolved names no target, so it is not the
    "repeated target" REQ-d00272-K speaks of -- but REQ-d00269-G still
    judges each position of the list on its own, so it is not collapsed
    away either. Both positions are reported."""
    items = reader.parse_ref_list("BADREF, BADREF")
    assert len(items) == 2
    assert [i.raw for i in items] == ["BADREF", "BADREF"]
    assert all(i.resolved is None for i in items)
    assert all(i.fault_class is not None for i in items)
    assert all(FaultCode.DUPLICATE_ITEM not in i.codes for i in items)


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


# Verifies: REQ-d00272-B
@pytest.mark.parametrize(
    "item",
    ["not a reference at all", "see REQ-d00001", "REQ-d00001 (A, C, F)"],
)
def test_an_item_holding_a_space_is_not_an_identifier(reader, item):
    cls, _codes = reader.classify_unmatched(item)
    assert cls is FaultClass.MALFORMED


# Verifies: REQ-d00272-B
def test_a_spaced_item_is_never_called_a_repository(reader):
    cls, _ = reader.classify_unmatched("not a reference at all")
    assert cls is not FaultClass.UNKNOWN_NAMESPACE


# Verifies: REQ-d00272-C
def test_an_item_opening_with_a_declared_namespace_is_ours(reader):
    """REQ is this repository's namespace, so REQ-d0000X is ours, written wrongly."""
    cls, _ = reader.classify_unmatched("REQ-d0000X")
    assert cls is FaultClass.MALFORMED


# Verifies: REQ-d00272-C
def test_an_item_opening_with_no_declared_namespace_is_foreign(reader):
    cls, codes = reader.classify_unmatched("WIDGET-42")
    assert cls is FaultClass.UNKNOWN_NAMESPACE
    assert codes == ()


def _project(tmp_path, repo_root, code: str):
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
        "B. The system SHALL do another.\n\n"
        "*End* *Thing* | **Hash**: 00000000\n"
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "m.py").write_text(code)
    config_path = tmp_path / ".elspais.toml"
    return build_graph(
        load_config(config_path),
        config_path=config_path,
        repo_root=tmp_path,
        scan_code=True,
        scan_tests=False,
    )


# Verifies: REQ-p00014-R
def test_an_absent_requirement_is_unknown_requirement(tmp_path, repo_root):
    graph = _project(tmp_path, repo_root, "# Implements: REQ-d00099\ndef f():\n    return 1\n")
    fault = next(f for f in graph.broken_references() if f.target_id == "REQ-d00099")
    assert fault.fault_class is FaultClass.UNKNOWN_REQUIREMENT


# Verifies: REQ-p00014-R
def test_an_absent_label_on_a_present_requirement_is_unknown_assertion(tmp_path, repo_root):
    graph = _project(tmp_path, repo_root, "# Implements: REQ-d00001-Z\ndef f():\n    return 1\n")
    fault = next(f for f in graph.broken_references() if f.target_id == "REQ-d00001-Z")
    assert fault.fault_class is FaultClass.UNKNOWN_ASSERTION


# Verifies: REQ-d00269-G
def test_a_multi_assertion_item_binds_the_labels_that_exist(tmp_path, repo_root):
    """A+Z: A binds, Z is reported. Salvage applies inside the expansion too."""
    graph = _project(tmp_path, repo_root, "# Implements: REQ-d00001-A+Z\ndef f():\n    return 1\n")
    targets = {f.target_id for f in graph.broken_references()}
    assert any("Z" in t for t in targets)
    assert not any(t.endswith("-A") for t in targets)


# Verifies: REQ-d00272-J
def test_a_keyword_a_code_file_may_not_use_is_refused_not_passed_over(tmp_path, repo_root):
    """Refines: is requirement-to-requirement only; a code file may not use it."""
    graph = _project(tmp_path, repo_root, "# Refines: REQ-d00001-A\ndef f():\n    return 1\n")
    fault = next(f for f in graph.broken_references() if f.target_id == "REQ-d00001-A")
    assert fault.fault_class is FaultClass.FORBIDDEN
    assert "refines" in fault.diagnostic.lower()
    assert "code" in fault.diagnostic.lower()
    # The refusal produced no relationship.
    node = graph.find_by_id("REQ-d00001-A")
    from elspais.graph.relations import EdgeKind

    assert not any(node.iter_edges_by_kind(EdgeKind.REFINES))


# Verifies: REQ-d00272-J
def test_a_keyword_a_test_file_may_not_use_is_refused_not_passed_over(tmp_path, repo_root):
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
    from elspais.config import load_config
    from elspais.graph.factory import build_graph

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_m.py").write_text(
        "# Implements: REQ-d00001-A\n" "def test_f():\n" "    assert True\n"
    )
    config_path = tmp_path / ".elspais.toml"
    graph = build_graph(
        load_config(config_path),
        config_path=config_path,
        repo_root=tmp_path,
        scan_code=False,
        scan_tests=True,
    )
    fault = next(f for f in graph.broken_references() if f.target_id == "REQ-d00001-A")
    assert fault.fault_class is FaultClass.FORBIDDEN
    assert "implements" in fault.diagnostic.lower()
    assert "test" in fault.diagnostic.lower()


# Verifies: REQ-d00272-K
def test_every_instance_of_a_repeated_target_is_reported_and_none_resolves(reader):
    items = reader.parse_ref_list("REQ-d00001, REQ-d00001")
    assert [i.resolved for i in items] == [None, None]
    assert all(FaultCode.DUPLICATE_ITEM in i.codes for i in items)


# Verifies: REQ-d00272-K
def test_a_target_named_once_still_resolves(reader):
    items = reader.parse_ref_list("REQ-d00001, REQ-d00002")
    assert [i.resolved for i in items] == ["REQ-d00001", "REQ-d00002"]


# Verifies: REQ-d00212-R
def test_two_spellings_of_one_identifier_count_as_a_repeat(reader):
    """Detection is on the normalized target: case is not a way to name a
    target twice without it being noticed."""
    items = reader.parse_ref_list("REQ-d00001, req-d00001")
    assert [i.resolved for i in items] == [None, None]
    assert all(FaultCode.DUPLICATE_ITEM in i.codes for i in items)


# Verifies: REQ-d00272-K
def test_a_duplicated_existing_target_binds_nothing_and_reports_twice(tmp_path, repo_root):
    """End-to-end through build_graph(): the reader's verdict is not enough
    on its own. A downstream consumer that falls back to raw text when an
    item's ``resolved`` is None -- the same fallback that lets a genuinely
    unmatched item survive to be reported -- must not let a duplicate's raw
    text (which may spell a real, existing node) reach the builder as a
    bindable target. REQ-d00001 exists in the fixture graph, so this is the
    case that actually exercises the bug: an ordinary unmatched item never
    coincides with a real id, a duplicate of an existing one always does.
    """
    graph = _project(
        tmp_path,
        repo_root,
        "# Implements: REQ-d00001, REQ-d00001\ndef f():\n    return 1\n",
    )
    node = graph.find_by_id("REQ-d00001")
    assert node is not None
    from elspais.graph.relations import EdgeKind

    assert not any(node.iter_edges_by_kind(EdgeKind.IMPLEMENTS)), (
        "a duplicated target must produce no relationship, even though the " "target itself exists"
    )
    faults = [f for f in graph.broken_references() if f.target_id == "REQ-d00001"]
    assert len(faults) == 2, f"expected one fault per instance, got {faults}"
    assert all(f.fault_class is FaultClass.FORBIDDEN for f in faults)
    assert all(FaultCode.DUPLICATE_ITEM in f.codes for f in faults)


# ---------------------------------------------------------------------------
# Spec-file and journey reference classification (Task 12): the same
# verdict-threading the code/test path already gets, for **Implements**:,
# **Refines**: and a journey's Validates:.
# ---------------------------------------------------------------------------


def _spec_project(tmp_path, repo_root, implements: str = "-", refines: str = "-"):
    """A project with a target requirement (REQ-d00001) and a second
    requirement (REQ-d00002) whose **Implements**:/**Refines**: carries the
    string under test."""
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
        "B. The system SHALL do another.\n\n"
        "*End* *Thing* | **Hash**: 00000000\n"
        "---\n"
        f"# REQ-d00002: Other\n\n"
        f"**Level**: dev | **Status**: Active | **Implements**: {implements} | "
        f"**Refines**: {refines}\n\n"
        "## Assertions\n\n"
        "A. The system SHALL do a third thing.\n\n"
        "*End* *Other* | **Hash**: 00000000\n"
    )
    config_path = tmp_path / ".elspais.toml"
    return build_graph(
        load_config(config_path),
        config_path=config_path,
        repo_root=tmp_path,
        scan_code=False,
        scan_tests=False,
    )


def _journey_project(tmp_path, repo_root, validates: str):
    """A project with a target requirement (REQ-d00001) and a journey whose
    Validates: line carries the string under test."""
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
        "B. The system SHALL do another.\n\n"
        "*End* *Thing* | **Hash**: 00000000\n"
    )
    (spec / "journeys.md").write_text(
        "## JNY-o-01: A Journey\n\n"
        "**Actor**: User\n"
        "**Goal**: Do a thing\n"
        f"Validates: {validates}\n\n"
        "### Steps\n\n"
        "1. Do the thing\n\n"
        "*End* *JNY-o-01*\n"
    )
    config_path = tmp_path / ".elspais.toml"
    return build_graph(
        load_config(config_path),
        config_path=config_path,
        repo_root=tmp_path,
        scan_code=False,
        scan_tests=False,
    )


# Verifies: REQ-d00272-A, REQ-d00272-C
def test_a_malformed_spec_reference_is_not_reported_as_a_missing_requirement(tmp_path, repo_root):
    """Stage 0 must not be reported as stage 2."""
    graph = _spec_project(tmp_path, repo_root, implements="not a reference")
    fault = next(f for f in graph.broken_references() if "not a reference" in f.target_id)
    assert fault.fault_class is FaultClass.MALFORMED


# Verifies: REQ-d00272-C
def test_a_foreign_spec_reference_is_not_reported_as_a_missing_requirement(tmp_path, repo_root):
    graph = _spec_project(tmp_path, repo_root, implements="WIDGET-42")
    fault = next(f for f in graph.broken_references() if f.target_id == "WIDGET-42")
    assert fault.fault_class is FaultClass.UNKNOWN_NAMESPACE


# Verifies: REQ-d00272-K
def test_a_duplicated_spec_reference_binds_nothing_and_reports_twice(tmp_path, repo_root):
    """The code/test path already refuses this; the spec path must too."""
    from elspais.graph.relations import EdgeKind

    graph = _spec_project(tmp_path, repo_root, implements="REQ-d00001, REQ-d00001")
    node = graph.find_by_id("REQ-d00001")
    assert node is not None
    edges = [e for e in node.iter_edges_by_kind(EdgeKind.IMPLEMENTS) if e.source.id == "REQ-d00002"]
    assert edges == []
    faults = [f for f in graph.broken_references() if f.target_id == "REQ-d00001"]
    assert len(faults) == 2
    assert all(FaultCode.DUPLICATE_ITEM in f.codes for f in faults)


# Verifies: REQ-d00272-K
def test_a_duplicated_refines_reference_binds_nothing_and_reports_twice(tmp_path, repo_root):
    from elspais.graph.relations import EdgeKind

    graph = _spec_project(tmp_path, repo_root, refines="REQ-d00001, REQ-d00001")
    node = graph.find_by_id("REQ-d00001")
    assert node is not None
    edges = [e for e in node.iter_edges_by_kind(EdgeKind.REFINES) if e.source.id == "REQ-d00002"]
    assert edges == []
    faults = [f for f in graph.broken_references() if f.target_id == "REQ-d00001"]
    assert len(faults) == 2
    assert all(FaultCode.DUPLICATE_ITEM in f.codes for f in faults)


# Verifies: REQ-d00272-A, REQ-d00272-C
def test_a_malformed_journey_validates_reference_is_not_reported_as_a_missing_requirement(
    tmp_path, repo_root
):
    graph = _journey_project(tmp_path, repo_root, validates="not a reference")
    fault = next(f for f in graph.broken_references() if "not a reference" in f.target_id)
    assert fault.fault_class is FaultClass.MALFORMED


# Verifies: REQ-d00272-C
def test_a_foreign_journey_validates_reference_is_not_reported_as_a_missing_requirement(
    tmp_path, repo_root
):
    graph = _journey_project(tmp_path, repo_root, validates="WIDGET-42")
    fault = next(f for f in graph.broken_references() if f.target_id == "WIDGET-42")
    assert fault.fault_class is FaultClass.UNKNOWN_NAMESPACE


# Verifies: REQ-d00272-K
def test_a_duplicated_journey_validates_reference_binds_nothing_and_reports_twice(
    tmp_path, repo_root
):
    from elspais.graph.relations import EdgeKind

    graph = _journey_project(tmp_path, repo_root, validates="REQ-d00001, REQ-d00001")
    node = graph.find_by_id("REQ-d00001")
    assert node is not None
    jny = graph.find_by_id("JNY-o-01")
    assert jny is not None
    edges = [e for e in node.iter_outgoing_edges() if e.kind == EdgeKind.VALIDATES]
    assert edges == []
    faults = [f for f in graph.broken_references() if f.target_id == "REQ-d00001"]
    assert len(faults) == 2
    assert all(FaultCode.DUPLICATE_ITEM in f.codes for f in faults)


# Verifies: REQ-d00272-K
def test_a_duplicated_multi_assertion_reference_binds_nothing_and_reports_each_instance(
    tmp_path, repo_root
):
    """A multi-assertion item that repeats another whole item verbatim must
    not escape REQ-d00272-K by parsing as valid multi-assertion syntax: the
    duplicate's raw text is by definition a valid spelling (that's what
    makes it a duplicate rather than a typo), so ``_resolver.parse()``
    succeeds on it. If the builder expanded a verdicted item before
    checking its verdict, the per-label expansion ``REQ-d00001-A``/
    ``REQ-d00001-B`` would no longer match the raw-text verdict key
    ``"REQ-d00001-A+B"``, and both labels would fall through to ordinary
    node lookup and bind -- silently reopening exactly the bug the
    single-target version of this test (above) already closed."""
    from elspais.graph.relations import EdgeKind

    graph = _project(
        tmp_path,
        repo_root,
        "# Implements: REQ-d00001-A+B, REQ-d00001-A+B\ndef f():\n    return 1\n",
    )
    node = graph.find_by_id("REQ-d00001")
    assert node is not None
    assert not any(node.iter_edges_by_kind(EdgeKind.IMPLEMENTS)), (
        "a duplicated multi-assertion target must produce no relationship, " "for either label"
    )
    faults = [f for f in graph.broken_references() if "REQ-d00001" in f.target_id]
    assert len(faults) == 2, f"expected one fault per instance, got {faults}"
    assert all(f.fault_class is FaultClass.FORBIDDEN for f in faults)
    assert all(FaultCode.DUPLICATE_ITEM in f.codes for f in faults)
