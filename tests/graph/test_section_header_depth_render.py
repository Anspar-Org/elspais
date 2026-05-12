"""Render canonicalization tests (REQ-d00250-D)."""

# Verifies: REQ-d00250-D
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
    from elspais.graph import NodeKind

    for n in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if n.id == req_id:
            return n
    return None


def _render(node):
    """Render a REQUIREMENT node to its text form."""
    from elspais.graph.render import _render_requirement

    return _render_requirement(node)


@pytest.mark.parametrize(
    "req_d,stored_d,expected_d",
    [
        (1, 2, 2),  # canonical
        (1, 3, 3),  # deeper-than-min preserved
        (1, 1, 2),  # too shallow -> bumped to req+1
        (2, 2, 3),  # H2 req with H2 Assertions -> bumped to H3
        (2, 3, 3),  # canonical
        (2, 4, 4),  # deeper preserved
        (3, 4, 4),  # canonical
        (3, 3, 4),  # too shallow
        (6, 6, 6),  # H6 ceiling clamp (builder flags unfixable, render emits H6)
    ],
)
def test_assertions_render_depth(tmp_path, req_d, stored_d, expected_d):
    spec = (
        f"{'#' * req_d} REQ-d00001: T\n\n"
        f"**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        f"{'#' * stored_d} Assertions\n\n"
        f"A. The system shall do X.\n\n"
        f"*End* *T* | **Hash**: -\n"
    )
    graph = _build(tmp_path, spec)
    node = _find_req(graph, "REQ-d00001")
    rendered = _render(node)
    expected_header = "#" * expected_d + " Assertions"
    assert expected_header in rendered, (
        f"Expected header `{expected_header}` not found in rendered output.\n" f"Got:\n{rendered}"
    )


@pytest.mark.parametrize(
    "req_d,stored_d,expected_d",
    [
        (1, 2, 2),
        (1, 1, 2),
        # H2 req with H2 named section: SECTION_HDR only supports #{1,2},
        # so named sections are capped at H2 to preserve parse-roundtrip.
        # The section stays at H2 (not promoted to H3).
        (2, 2, 2),
        (2, 3, 3),
        (3, 5, 5),
    ],
)
def test_named_section_render_depth(tmp_path, req_d, stored_d, expected_d):
    spec = (
        f"{'#' * req_d} REQ-d00001: T\n\n"
        f"**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        f"## Assertions\n\n"
        f"A. X.\n\n"
        f"{'#' * stored_d} Notes\n\n"
        f"Some notes.\n\n"
        f"*End* *T* | **Hash**: -\n"
    )
    graph = _build(tmp_path, spec)
    node = _find_req(graph, "REQ-d00001")
    rendered = _render(node)
    expected_header = "#" * expected_d + " Notes"
    assert expected_header in rendered, f"Expected `{expected_header}` not in:\n{rendered}"


def test_hash_sub_heading_renders_against_effective_parent(tmp_path):
    """Sub-heading depth is computed against the effective (canonicalized) parent depth.

    H2 req: assertions stored H2 -> effective H3. Sub-heading stored H3 ->
    effective H4 (assertions_eff+1 = 4). Note: sub-headings at H1/H2 match
    SECTION_HDR (priority 7) rather than ASSERT_SUB_HASH_HDR (priority 6),
    so sub-headings must be H3+ for the hash branch to apply.
    """
    spec = (
        "## REQ-d00001: T\n\n"  # H2 req
        "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        "## Assertions\n\n"  # stored H2 -> effective H3 (req+1)
        "### Core\n\n"  # stored H3 -> effective H4 (assertions_eff+1)
        "A. X.\n\n"
        "*End* *T* | **Hash**: -\n"
    )
    graph = _build(tmp_path, spec)
    node = _find_req(graph, "REQ-d00001")
    rendered = _render(node)
    assert "### Assertions" in rendered, f"Expected `### Assertions` (H2+1=H3) in:\n{rendered}"
    assert (
        "#### Core" in rendered
    ), f"Expected `#### Core` (effective-assertions+1=H4) in:\n{rendered}"


def test_h1_req_h2_assertions_unchanged(tmp_path):
    """Regression: existing H1-req / H2-Assertions files render identically."""
    spec = (
        "# REQ-d00001: T\n\n"
        "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        "## Assertions\n\n"
        "A. X.\n\n"
        "## Notes\n\n"
        "Some notes.\n\n"
        "*End* *T* | **Hash**: -\n"
    )
    graph = _build(tmp_path, spec)
    node = _find_req(graph, "REQ-d00001")
    rendered = _render(node)
    assert "## Assertions" in rendered
    assert "## Notes" in rendered
    assert "### Assertions" not in rendered
    assert "### Notes" not in rendered
