"""Classification of reference list items."""

import pathlib

import pytest

from elspais.config import load_config
from elspais.graph.reference_faults import FaultClass, FaultCode, ReferenceFault
from elspais.graph.relations import EdgeKind
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
        target_id="REQ-d00001+A-B",
        edge_kind="implements",
        fault_class=FaultClass.MALFORMED,
        codes=(FaultCode.WRONG_ASSERTION_SEPARATOR, FaultCode.WRONG_MULTI_SEPARATOR),
    )
    assert FaultCode.SYNTAX_ERROR in fault.codes
    assert FaultCode.WRONG_ASSERTION_SEPARATOR in fault.codes
    assert FaultCode.WRONG_MULTI_SEPARATOR in fault.codes


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


# Verifies: REQ-d00269-G, REQ-d00269-H, REQ-p00014-T
def test_a_trailing_separator_binds_what_precedes_it(reader):
    """A dangling separator is reported as itself, not as a generic empty
    item -- REQ-d00269-H names it as the separator that introduced nothing.
    """
    items = reader.parse_ref_list("REQ-d00001,")
    assert [i.resolved for i in items if i.resolved] == ["REQ-d00001"]
    trailing = [i for i in items if FaultCode.TRAILING_SEPARATOR in i.codes]
    assert len(trailing) == 1


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


# Verifies: REQ-d00272-C
def test_the_longest_declared_namespace_owns_the_diagnosis():
    """``self._resolvers`` is own-repo-first order; the item must still be
    attributed to whichever declaring member's namespace is the longest
    match, not whichever is scanned first, or a federation whose own
    namespace is a strict prefix of a sibling's (``REQ`` inside ``REQ-ALP``)
    would misattribute every one of the sibling's malformed items to
    itself -- and get no diagnosis at all, since the wrong owner's grammar
    cannot explain a defect that belongs to a different repository's
    identifiers."""
    own_config = {
        "project": {"namespace": "REQ"},
        "levels": {"dev": {"rank": 1, "letter": "d"}},
        "id-patterns": {
            "canonical": "{namespace}-{level.letter}{component}",
            "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
            "assertions": {
                "label_style": "uppercase",
                "max_count": 26,
                "zero_pad": False,
                "multi_separator": "+",
            },
        },
    }
    sibling_config = {
        "project": {"namespace": "REQ-ALP"},
        "levels": {"prd": {"rank": 1, "letter": "p"}},
        "id-patterns": {
            "canonical": "{namespace}-{level.letter}{component}",
            "component": {"style": "numeric", "digits": 3, "leading_zeros": True},
            "assertions": {
                "label_style": "uppercase",
                "max_count": 26,
                "zero_pad": False,
                "multi_separator": "+",
            },
        },
    }
    federated = FederatedIdReader(
        own=build_resolver(own_config), others=[build_resolver(sibling_config)]
    )
    fault_class, codes = federated.classify_unmatched("REQ-ALP-p001+A")
    assert fault_class is FaultClass.MALFORMED
    assert FaultCode.WRONG_ASSERTION_SEPARATOR in codes


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
        "# Implements: REQ-d00001-A\ndef test_f():\n    assert True\n"
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
        "a duplicated target must produce no relationship, even though the target itself exists"
    )
    faults = [f for f in graph.broken_references() if f.target_id == "REQ-d00001"]
    assert len(faults) == 2, f"expected one fault per instance, got {faults}"
    assert all(f.fault_class is FaultClass.FORBIDDEN for f in faults)
    assert all(FaultCode.DUPLICATE_ITEM in f.codes for f in faults)


# ---------------------------------------------------------------------------
# Spec-file and journey reference classification (Task 12): the same
# verdict-threading the code/test path already gets, for a spec's
# Implements/Refines metadata and a journey's Validates line.
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


# Verifies: REQ-d00272-K
@pytest.mark.parametrize(
    "duplicated_field,clean_field,duplicated_kind,clean_kind",
    [
        ("refines", "implements", EdgeKind.REFINES, EdgeKind.IMPLEMENTS),
        ("implements", "refines", EdgeKind.IMPLEMENTS, EdgeKind.REFINES),
    ],
)
def test_a_duplicate_under_one_keyword_leaves_another_keywords_clean_reference_binding(
    tmp_path, repo_root, duplicated_field, clean_field, duplicated_kind, clean_kind
):
    """A verdict answers for the reference it was read from and no other.

    Both metadata lines name REQ-d00001: one repeats it (and so binds
    nothing), the other names it once and cleanly. Judging the clean item by
    the repeated one's verdict loses a relationship its author spelled
    correctly, and loses it silently -- nothing is reported about the
    keyword that was written properly.
    """
    fields = {
        duplicated_field: "REQ-d00001, REQ-d00001",
        clean_field: "REQ-d00001",
    }
    graph = _spec_project(tmp_path, repo_root, **fields)
    node = graph.find_by_id("REQ-d00001")
    assert node is not None

    clean_edges = [e for e in node.iter_edges_by_kind(clean_kind) if e.target.id == "REQ-d00002"]
    assert len(clean_edges) == 1, (
        f"the clean **{clean_field.title()}**: names REQ-d00001 once and must bind; "
        f"got {[(e.kind.value, e.target.id) for e in node.iter_outgoing_edges()]}"
    )

    dup_edges = [e for e in node.iter_edges_by_kind(duplicated_kind) if e.target.id == "REQ-d00002"]
    assert dup_edges == [], "the repeated keyword's items must still bind nothing"

    faults = [f for f in graph.broken_references() if f.target_id == "REQ-d00001"]
    assert len(faults) == 2, f"one report per repeated instance, and no more; got {faults}"
    assert all(f.edge_kind == duplicated_field for f in faults), (
        f"only the repeating keyword is at fault; got {[f.edge_kind for f in faults]}"
    )
    assert all(FaultCode.DUPLICATE_ITEM in f.codes for f in faults)


def _satisfies_project(tmp_path, repo_root, satisfies: str):
    """A project with a template requirement (REQ-d00001) and a second
    requirement (REQ-d00002) whose **Satisfies**: carries the string under
    test."""
    from elspais.config import load_config
    from elspais.graph.factory import build_graph

    (tmp_path / ".elspais.toml").write_text((repo_root / ".elspais.toml").read_text())
    spec = tmp_path / "spec"
    spec.mkdir(exist_ok=True)
    (spec / "r.md").write_text(
        "# REQ-d00001: Thing\n\n"
        "**Level**: dev | **Status**: Active | **Implements**: - | **Template**\n\n"
        "## Assertions\n\n"
        "A. The system SHALL do a thing.\n\n"
        "*End* *Thing* | **Hash**: 00000000\n"
        "---\n"
        "# REQ-d00002: Other\n\n"
        f"**Level**: dev | **Status**: Active | **Implements**: - | **Satisfies**: {satisfies}\n\n"
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


# Verifies: REQ-d00272-A, REQ-d00272-B
def test_a_malformed_satisfies_target_keeps_the_class_reading_reached(tmp_path, repo_root):
    """A ``Satisfies:`` target is resolved across the federation, and the
    missing-associate branch that runs when nobody claims it speaks for a
    later stage of reading than an unread item ever got to. An item holding a
    space was never written as an identifier, so it names no repository --
    declared or undeclared -- and reporting it as one sends its author to
    configure an associate that would not fix anything.
    """
    graph = _satisfies_project(tmp_path, repo_root, "not a reference")
    faults = [
        f
        for f in graph.broken_references()
        if f.edge_kind == EdgeKind.SATISFIES.value and "not a reference" in f.target_id
    ]
    assert len(faults) == 1, f"the refused item is reported once; got {faults}"
    assert faults[0].fault_class is FaultClass.MALFORMED, (
        "stage 0 must not be reported as stage 1; got "
        f"{faults[0].fault_class} with {faults[0].codes}"
    )
    assert FaultCode.NOT_AN_IDENTIFIER in faults[0].codes
    assert faults[0].presumed_foreign is False, (
        "text that is not an identifier belongs to no repository, so it is "
        "not a reference presumed to live in one"
    )


# Verifies: REQ-d00272-K
def test_a_duplicated_satisfies_reference_instantiates_no_template(tmp_path, repo_root):
    """``Satisfies:`` resolves through template instantiation rather than
    pending-link resolution, so it needs its own refusal: an item the reader
    refused names a real template, and looking it up anyway would clone the
    subtree the verdict withheld -- once for a list its author repeated, or
    twice were the repeat collapsed nowhere.
    """
    instantiated = _satisfies_project(tmp_path, repo_root, "REQ-d00001")
    assert instantiated.find_by_id("REQ-d00002::REQ-d00001") is not None, (
        "a clean Satisfies must still instantiate -- otherwise the duplicate "
        "case below proves nothing"
    )

    graph = _satisfies_project(tmp_path, repo_root, "REQ-d00001, REQ-d00001")
    assert graph.find_by_id("REQ-d00002::REQ-d00001") is None, (
        "a repeated target produces no relationship, so no instance exists"
    )
    faults = [
        f
        for f in graph.broken_references()
        if f.target_id == "REQ-d00001" and f.edge_kind == EdgeKind.SATISFIES.value
    ]
    assert len(faults) == 2, (
        "every instance of the repeat is reported -- collapsing them to one "
        f"leaves the others as silent as keeping the first would; got {faults}"
    )
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
        "a duplicated multi-assertion target must produce no relationship, for either label"
    )
    faults = [f for f in graph.broken_references() if "REQ-d00001" in f.target_id]
    assert len(faults) == 2, f"expected one fault per instance, got {faults}"
    assert all(f.fault_class is FaultClass.FORBIDDEN for f in faults)
    assert all(FaultCode.DUPLICATE_ITEM in f.codes for f in faults)


# Verifies: REQ-d00212-R
@pytest.mark.parametrize("item", ["req-d00001", "REQ-d1", "REQ-D00001"])
def test_case_and_padding_resolve_rather_than_faulting(reader, item):
    """Neither reaches diagnose_item: the matcher already admits both."""
    items = reader.parse_ref_list(item)
    assert items[0].resolved == "REQ-d00001"
    assert items[0].fault_class is None


# Verifies: REQ-d00272-D
def test_a_single_relaxation_is_named(reader):
    codes = reader.own.diagnose_item("REQ-d00001+A")
    assert FaultCode.WRONG_ASSERTION_SEPARATOR in codes


# Verifies: REQ-d00272-D
def test_a_wrong_multi_separator_is_named(reader):
    """Two labels joined by the assertion separator instead of the
    multi-*Assertion* separator name the other dimension."""
    codes = reader.own.diagnose_item("REQ-d00001-A-B")
    assert FaultCode.WRONG_MULTI_SEPARATOR in codes


# Verifies: REQ-d00271-D
def test_an_item_no_relaxation_explains_is_named_no_further(reader):
    assert reader.own.diagnose_item("WIDGET-42") == ()


# Verifies: REQ-d00272-E
def test_an_identifier_followed_by_other_text_names_both(reader):
    codes = reader.own.diagnose_item("REQ-d00001 (A")
    assert FaultCode.IDENTIFIER_WITH_TRAILING_TEXT in codes


# Verifies: REQ-d00272-D
@pytest.mark.parametrize("item", ["REQ-d00001", "REQ-d00001-A", "REQ-d00001-A+B+C"])
def test_an_already_acceptable_item_names_no_relaxation(reader, item):
    """Each relaxation is a no-op on a string its own wrong shape does not
    match, so applying one to an already-acceptable item trivially
    fullmatches too -- without a guard for that, every size would report a
    combo that succeeded for a reason unrelated to any defect, and two
    single-relaxation combos succeeding the same trivial way would read as
    AMBIGUOUS for an item that is not malformed at all."""
    assert reader.own.diagnose_item(item) == ()


# Verifies: REQ-d00271-A
def test_a_label_outside_the_configured_series_is_named_through_classify_unmatched(reader):
    """A bare identifier followed by the real assertion separator and a
    character the label alphabet does not admit is a defect in the label,
    not generic trailing content -- ``classify_unmatched`` names it more
    specifically than ``IDENTIFIER_WITH_TRAILING_TEXT``."""
    fault_class, codes = reader.classify_unmatched("REQ-d00001-9")
    assert fault_class is FaultClass.MALFORMED
    assert codes == (FaultCode.LABEL_OUT_OF_SERIES,)


# --------------------------------------------------------------------------- #
# A cause is named by a code, a location, and that code's documented meaning
# --------------------------------------------------------------------------- #


# Verifies: REQ-d00252-K, REQ-d00272-A
@pytest.mark.parametrize(
    "annotation,expected_class",
    [
        ("# Implements: REQ-d09999\n", FaultClass.UNKNOWN_REQUIREMENT),
        ("# Implements: REQ-d00001-Z\n", FaultClass.UNKNOWN_ASSERTION),
    ],
)
def test_a_reference_that_parsed_and_is_absent_carries_no_prose(
    tmp_path, repo_root, annotation, expected_class
):
    """An item spelled exactly as this repository's grammar admits, naming
    something the graph does not hold, has nothing wrong with its spelling.
    Prose blaming the assertion separator would name a cause the input does
    not determine -- and, because a health finding renders the diagnostic in
    place of the check's description, it would replace the one true sentence
    about the fault with a false one."""
    graph = _project(tmp_path, repo_root, annotation + "def f():\n    return 1\n")
    faults = [f for f in graph.broken_references() if f.source_id.startswith("code:")]
    assert len(faults) == 1, f"expected one fault, got {faults}"
    assert faults[0].fault_class is expected_class
    assert faults[0].diagnostic == "", (
        "the code, the file and the line name the cause; a fourth naming "
        f"guessing at a separator is not one the input determines: {faults[0].diagnostic!r}"
    )


# Verifies: REQ-d00252-K, REQ-d00272-A
def test_a_malformed_own_namespace_reference_names_its_cause_by_code_and_location(
    tmp_path, repo_root
):
    """What names the cause is the code together with where the reference was
    written, and both reach the surface that reports it."""
    from elspais.commands.health import _fault_location

    graph = _project(tmp_path, repo_root, "# Implements: REQ-d00001+A\ndef f():\n    return 1\n")
    faults = [f for f in graph.broken_references() if f.source_id.startswith("code:")]
    assert len(faults) == 1, f"expected one fault, got {faults}"
    fault = faults[0]
    assert fault.fault_class is FaultClass.MALFORMED
    assert FaultCode.WRONG_ASSERTION_SEPARATOR in fault.codes
    file_path, line = _fault_location(graph, fault.source_id, fault.line)
    assert file_path and file_path.endswith("m.py")
    assert line == 1
    assert fault.diagnostic == ""


# --------------------------------------------------------------------------- #
# A keyword the file may not use refuses only what actually read
# --------------------------------------------------------------------------- #


# Verifies: REQ-d00272-A, REQ-d00272-J
def test_an_item_that_never_read_is_not_reported_as_refused(tmp_path, repo_root):
    """`Refines:` is not a keyword a code file may use, but the refusal is a
    verdict on a relationship the item named -- and this item named none. Its
    own, earlier verdict is what is reported."""
    graph = _project(tmp_path, repo_root, "# Refines: not a reference\ndef f():\n    return 1\n")
    faults = [f for f in graph.broken_references() if f.source_id.startswith("code:")]
    assert len(faults) == 1, f"expected one fault, got {faults}"
    assert faults[0].fault_class is FaultClass.MALFORMED
    assert faults[0].fault_class is not FaultClass.FORBIDDEN
    assert faults[0].diagnostic == "", (
        "the refusal prose says the reference resolves and the relationship "
        "is refused, which is false of an item that never read"
    )


# Verifies: REQ-d00272-A, REQ-d00272-J
def test_a_mixed_forbidden_line_reports_each_item_at_the_stage_it_reached(tmp_path, repo_root):
    """One list, two items, two different stages: the item that read reaches
    the keyword's refusal, the item that did not stops where it stopped."""
    graph = _project(
        tmp_path,
        repo_root,
        "# Refines: not a reference, REQ-d00001-A\ndef f():\n    return 1\n",
    )
    faults = {f.target_id: f for f in graph.broken_references() if f.source_id.startswith("code:")}
    assert set(faults) == {"not a reference", "REQ-d00001-A"}, faults
    assert faults["not a reference"].fault_class is FaultClass.MALFORMED
    assert faults["REQ-d00001-A"].fault_class is FaultClass.FORBIDDEN
    assert "not a valid keyword" in faults["REQ-d00001-A"].diagnostic


# --------------------------------------------------------------------------- #
# Padding decides nothing; an out-of-range value is its own defect
# --------------------------------------------------------------------------- #


# Verifies: REQ-d00212-R
@pytest.mark.parametrize(
    "item,canonical",
    [
        ("REQ-d1", "REQ-d00001"),
        ("REQ-d001", "REQ-d00001"),
        ("REQ-d000001", "REQ-d00001"),
        ("REQ-d00001", "REQ-d00001"),
        ("REQ-d012345", "REQ-d12345"),
        ("REQ-d0", "REQ-d00000"),
        ("REQ-d00000", "REQ-d00000"),
    ],
)
def test_leading_zeros_never_decide_whether_an_identifier_resolves(reader, item, canonical):
    """The configured digit count bounds the component's VALUE. Every
    spelling below the bound reads, however many zeros precede it, and each
    renders in the one form the configuration names."""
    items = reader.parse_ref_list(item)
    assert items[0].resolved == canonical
    assert items[0].fault_class is None


# Verifies: REQ-d00212-T
@pytest.mark.parametrize("item", ["REQ-d123456", "REQ-d0123456"])
def test_a_component_value_beyond_the_configured_bound_resolves_to_nothing(reader, item):
    """No repadding makes 123456 fit five digits, so this is not a padding
    defect: the value itself is one the configuration cannot name, and the
    code says so rather than blaming trailing text."""
    items = reader.parse_ref_list(item)
    assert items[0].resolved is None
    assert items[0].fault_class is FaultClass.MALFORMED
    fault_class, codes = reader.classify_unmatched(item)
    assert fault_class is FaultClass.MALFORMED
    assert codes == (FaultCode.COMPONENT_OUT_OF_RANGE,)


# --------------------------------------------------------------------------- #
# A character no configuration can admit
# --------------------------------------------------------------------------- #


# Verifies: REQ-d00272-M
@pytest.mark.parametrize("item", ["REQ-d00001:A", ":", "file:REQ:spec/r.md"])
def test_an_item_holding_a_reserved_character_is_not_an_identifier(reader, item):
    """`:` separates the parts of a node identifier, so configuration
    validation refuses any pattern element able to produce one. An item
    carrying one therefore cannot be any repository's identifier, and
    describing it as a name from a repository nobody configured is the
    misattribution the space test exists to prevent."""
    fault_class, codes = reader.classify_unmatched(item)
    assert fault_class is FaultClass.MALFORMED
    assert fault_class is not FaultClass.UNKNOWN_NAMESPACE
    assert codes == (FaultCode.NOT_AN_IDENTIFIER,)


# Verifies: REQ-d00272-M, REQ-d00269-G
def test_repeated_colons_after_a_keyword_bind_nothing(tmp_path, repo_root):
    """The keyword's own colon is one character. Removing every colon an
    author typed would let `# Implements:::: REQ-d00001` bind as though it
    were written correctly -- a silent repair, and exactly the shape of the
    defect the bounded emphasis strip beside it avoids."""
    from elspais.graph.relations import EdgeKind

    graph = _project(tmp_path, repo_root, "# Implements:::: REQ-d00001-A\ndef f():\n    return 1\n")
    node = graph.find_by_id("REQ-d00001")
    assert node is not None
    assert not any(node.iter_edges_by_kind(EdgeKind.IMPLEMENTS)), (
        "an annotation with three colons the keyword did not write is not the "
        "annotation the author meant, and must not bind as though it were"
    )
    faults = [f for f in graph.broken_references() if f.source_id.startswith("code:")]
    assert len(faults) == 1, f"expected one fault, got {faults}"
    assert faults[0].fault_class is FaultClass.MALFORMED
    assert FaultCode.NOT_AN_IDENTIFIER in faults[0].codes
