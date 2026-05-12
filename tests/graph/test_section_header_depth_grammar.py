"""Grammar acceptance tests for section header depth (REQ-d00250-A)."""

# Verifies: REQ-d00250-A
import pytest

_MINIMAL_TOML = """\
version = 4
[project]
namespace = "REQ"
[id-patterns]
canonical = "{namespace}-{level.letter}{component}"
[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true
[levels.prd]
rank = 1
letter = "p"
display_name = "PRD"
implements = ["prd"]
[levels.ops]
rank = 2
letter = "o"
display_name = "OPS"
implements = ["ops", "prd"]
[levels.dev]
rank = 3
letter = "d"
display_name = "DEV"
implements = ["dev", "ops", "prd"]
"""


def _build(tmp_path, spec_text):
    """Build a graph from a single spec file in tmp_path."""
    (tmp_path / ".elspais.toml").write_text(_MINIMAL_TOML)
    (tmp_path / "test.md").write_text(spec_text)
    from elspais.graph.factory import build_graph

    return build_graph(
        config_path=tmp_path / ".elspais.toml",
        spec_dirs=[tmp_path],
        repo_root=tmp_path,
        scan_code=False,
        scan_tests=False,
    )


def _find_req(graph, req_id):
    """Find a REQUIREMENT node by ID across federated repos if needed."""
    from elspais.graph import NodeKind

    for n in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if n.id == req_id:
            return n
    return None


SECTION_HEADER_CASES = [
    # (req_depth, section_depth)
    (1, 2),
    (1, 3),
    (1, 1),  # recognized; illegality is detected by builder (later task)
    (2, 3),
    (2, 2),  # recognized; illegality is detected by builder
    (3, 4),
    (6, 6),
]


@pytest.mark.parametrize("req_d,sec_d", SECTION_HEADER_CASES)
def test_assertions_header_recognized_at_any_depth(req_d, sec_d, tmp_path):
    """ASSERTIONS_HDR lexes correctly at any 1<=d<=6 depth."""
    spec = (
        f"{'#' * req_d} REQ-d00001: Test\n\n"
        f"**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        f"{'#' * sec_d} Assertions\n\n"
        f"A. The system shall do X.\n\n"
        f"*End* *Test* | **Hash**: -\n"
    )
    graph = _build(tmp_path, spec)
    node = _find_req(graph, "REQ-d00001")
    assert node is not None
    from elspais.graph import EdgeKind, NodeKind

    assertions = [
        c
        for c in node.iter_children(edge_kinds={EdgeKind.STRUCTURES})
        if c.kind == NodeKind.ASSERTION
    ]
    assert len(assertions) == 1, (
        f"Expected 1 ASSERTION child but got {len(assertions)}. "
        f"Likely the `{'#' * sec_d} Assertions` header was not recognized "
        f"as ASSERTIONS_HDR and fell through to remainder."
    )


@pytest.mark.parametrize("req_d,sec_d", SECTION_HEADER_CASES)
def test_changelog_header_recognized_at_any_depth(req_d, sec_d, tmp_path):
    """CHANGELOG_HDR lexes correctly at any 1<=d<=6 depth."""
    spec = (
        f"{'#' * req_d} REQ-d00001: Test\n\n"
        f"**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        f"## Assertions\n\n"
        f"A. The system shall do X.\n\n"
        f"{'#' * sec_d} Changelog\n\n"
        f"- 2026-05-11 | abc12345 | - | Dev (d@ex.com) | seed\n\n"
        f"*End* *Test* | **Hash**: -\n"
    )
    graph = _build(tmp_path, spec)
    node = _find_req(graph, "REQ-d00001")
    assert node is not None
    changelog = node.get_field("changelog") or []
    assert len(changelog) == 1, (
        f"Expected 1 changelog entry but got {len(changelog)}. "
        f"Likely the `{'#' * sec_d} Changelog` header was not recognized "
        f"as CHANGELOG_HDR and fell through to remainder."
    )


@pytest.mark.parametrize("req_d,sec_d", SECTION_HEADER_CASES)
def test_named_section_header_recognized_at_any_depth(req_d, sec_d, tmp_path):
    """SECTION_HDR lexes correctly at any 1<=d<=6 depth."""
    spec = (
        f"{'#' * req_d} REQ-d00001: Test\n\n"
        f"**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        f"## Assertions\n\n"
        f"A. The system shall do X.\n\n"
        f"{'#' * sec_d} Notes\n\n"
        f"Some notes.\n\n"
        f"*End* *Test* | **Hash**: -\n"
    )
    graph = _build(tmp_path, spec)
    node = _find_req(graph, "REQ-d00001")
    assert node is not None
    from elspais.graph import EdgeKind, NodeKind

    notes = [
        c
        for c in node.iter_children(edge_kinds={EdgeKind.STRUCTURES})
        if c.kind == NodeKind.REMAINDER and c.get_field("heading") == "Notes"
    ]
    assert len(notes) == 1, (
        f"Expected 1 'Notes' REMAINDER child but got {len(notes)}. "
        f"Likely the `{'#' * sec_d} Notes` header was not recognized "
        f"as SECTION_HDR and fell through to remainder text."
    )


SUB_HEADING_CASES = [
    # (assertions_depth, sub_depth)
    (2, 3),
    (2, 4),
    (2, 1),
    (2, 2),
    (3, 4),
    (3, 3),
    (1, 1),
    (1, 6),
]


@pytest.mark.parametrize("ass_d,sub_d", SUB_HEADING_CASES)
def test_hash_sub_heading_recognized_at_any_depth(ass_d, sub_d, tmp_path):
    """ASSERT_SUB_HASH_HDR lexes correctly at any 1<=d<=6 depth."""
    spec = (
        f"# REQ-d00001: Test\n\n"
        f"**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        f"{'#' * ass_d} Assertions\n\n"
        f"{'#' * sub_d} Core\n\n"
        f"A. The system shall do X.\n\n"
        f"*End* *Test* | **Hash**: -\n"
    )
    graph = _build(tmp_path, spec)
    node = _find_req(graph, "REQ-d00001")
    assert node is not None
    from elspais.graph import EdgeKind, NodeKind

    sub_heads = [
        c
        for c in node.iter_children(edge_kinds={EdgeKind.STRUCTURES})
        if c.kind == NodeKind.REMAINDER and c.get_field("heading") == "Core"
    ]
    assert len(sub_heads) == 1, (
        f"Expected 1 'Core' sub-heading REMAINDER but got {len(sub_heads)}. "
        f"`{'#' * sub_d} Core` was not recognized as ASSERT_SUB_HASH_HDR."
    )
