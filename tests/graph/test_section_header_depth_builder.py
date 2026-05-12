"""Builder violation marking (REQ-d00250-B, REQ-d00250-C)."""

# Verifies: REQ-d00250-B
# Verifies: REQ-d00250-C
from pathlib import Path

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


def _build(tmp_path: Path, spec: str):
    (tmp_path / ".elspais.toml").write_text(_MINIMAL_TOML)
    (tmp_path / "f.md").write_text(spec)
    from elspais.graph.factory import build_graph

    return build_graph(
        config_path=tmp_path / ".elspais.toml",
        spec_dirs=[tmp_path],
        repo_root=tmp_path,
        scan_code=False,
        scan_tests=False,
    )


def _find_req(graph, req_id):
    from elspais.graph import NodeKind

    for n in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if n.id == req_id:
            return n
    return None


@pytest.mark.parametrize(
    "req_d,sec_d,expect_fixable_flag",
    [
        (1, 2, False),
        (1, 3, False),  # legal-but-deeper-than-min
        (1, 1, True),  # same depth as req — too shallow
        (2, 3, False),
        (2, 2, True),  # same depth as req
        (2, 1, True),  # shallower than req
        (3, 4, False),
        (3, 3, True),
    ],
)
def test_assertions_too_shallow_marks_section_header_depth(
    tmp_path, req_d, sec_d, expect_fixable_flag
):
    spec = (
        f"{'#' * req_d} REQ-d00001: T\n\n"
        f"**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        f"{'#' * sec_d} Assertions\n\n"
        f"A. X.\n\n"
        f"*End* *T* | **Hash**: -\n"
    )
    graph = _build(tmp_path, spec)
    node = _find_req(graph, "REQ-d00001")
    reasons = node.get_field("parse_dirty_reasons") or []
    if expect_fixable_flag:
        assert "section_header_depth" in reasons, (
            f"Expected `section_header_depth` in {reasons} " f"for req_d={req_d}, sec_d={sec_d}"
        )
    else:
        assert "section_header_depth" not in reasons, (
            f"Did not expect `section_header_depth` in {reasons} "
            f"for req_d={req_d}, sec_d={sec_d}"
        )


@pytest.mark.parametrize(
    "req_d,sec_d,expect_fixable",
    [
        # SECTION_HDR matches only #{1,2}, so named sections can only be
        # rendered at H1 or H2.  A named section at H2 under a H2 requirement
        # is NOT flagged as too-shallow because promoting it to H3 would put it
        # beyond SECTION_HDR's range, breaking the parse roundtrip.
        (1, 2, False),  # H1 req, H2 named section: valid (min depth = 2)
        (1, 1, True),  # H1 req, H1 named section: too shallow (min depth = 2, fixable to H2)
        (2, 2, False),  # H2 req, H2 named section: NOT flagged (min depth = 3 > SECTION_HDR max)
    ],
)
def test_named_section_too_shallow_marks_section_header_depth(
    tmp_path, req_d, sec_d, expect_fixable
):
    # No assertions block here — test probes the named-section (SECTION_HDR) depth rule.
    # SECTION_HDR only matches #{1,2}, so H3+ named sections without assertions
    # fall to preamble text and are not checkable here.
    spec = (
        f"{'#' * req_d} REQ-d00001: T\n\n"
        f"**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        f"{'#' * sec_d} Notes\n\n"
        f"Some text.\n\n"
        f"*End* *T* | **Hash**: -\n"
    )
    graph = _build(tmp_path, spec)
    node = _find_req(graph, "REQ-d00001")
    reasons = node.get_field("parse_dirty_reasons") or []
    if expect_fixable:
        assert "section_header_depth" in reasons
    else:
        assert "section_header_depth" not in reasons


def test_h6_req_with_assertions_is_unfixable(tmp_path):
    spec = (
        "###### REQ-d00001: T\n\n"
        "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        "###### Assertions\n\n"
        "A. X.\n\n"
        "*End* *T* | **Hash**: -\n"
    )
    graph = _build(tmp_path, spec)
    node = _find_req(graph, "REQ-d00001")
    unfixable = node.get_field("parse_unfixable_reasons") or []
    assert (
        "section_header_depth_unfixable" in unfixable
    ), f"Expected unfixable flag; got parse_unfixable_reasons={unfixable}"
    fixable_reasons = node.get_field("parse_dirty_reasons") or []
    assert (
        "section_header_depth" not in fixable_reasons
    ), f"Unfixable case must NOT also be in fixable reasons; got {fixable_reasons}"


def test_h6_req_without_section_blocks_is_clean(tmp_path):
    """H6 req with no section blocks shouldn't be flagged."""
    spec = (
        "###### REQ-d00001: T\n\n"
        "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        "Description only, no Assertions block.\n\n"
        "*End* *T* | **Hash**: -\n"
    )
    graph = _build(tmp_path, spec)
    node = _find_req(graph, "REQ-d00001")
    unfixable = node.get_field("parse_unfixable_reasons") or []
    assert "section_header_depth_unfixable" not in unfixable
