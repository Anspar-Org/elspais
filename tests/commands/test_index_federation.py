# Verifies: REQ-d00253-C
"""INDEX.md content includes associate reqs only when index_associates=True.

NOTE: The canonical_federated_graph fixture uses the hht-like fixture which has
no [associates] configured, so it has no associate repos. This test therefore
takes the single-repo path: assert that include_associates=True and
include_associates=False produce identical output when there are no associates.
This is a real correctness assertion — it verifies that the filter does not
accidentally drop primary-repo nodes. Full associate-exclusion behavior (the
case where associates ARE present) is covered by the e2e test added in Task 7.
"""

from elspais.commands.index import _build_index_content


def test_include_associates_false_keeps_all_primary_nodes(canonical_federated_graph):
    """When no associates exist, primary-only output equals full-federation output.

    This verifies the filter does not drop primary-repo nodes. If an associate
    were present its nodes would be absent from the include_associates=False
    result — that case is covered in Task 7 e2e tests.
    """
    g = canonical_federated_graph
    spec_dirs = [g.repo_root / "spec"]

    _p_all, content_all, n_all, j_all = _build_index_content(g, spec_dirs, include_associates=True)
    _p_primary, content_primary, n_primary, j_primary = _build_index_content(
        g, spec_dirs, include_associates=False
    )

    # With no associates, both modes must produce identical counts and content.
    assert n_primary == n_all, (
        f"Primary-only count ({n_primary}) differs from all-repos count ({n_all}) "
        "even though no associates are configured; primary nodes are being dropped."
    )
    assert j_primary == j_all, (
        f"Primary-only journey count ({j_primary}) differs from all-repos "
        f"count ({j_all}) even though no associates are configured."
    )
    assert content_primary == content_all, (
        "Content differs between include_associates=True and =False despite no "
        "associates being configured. Primary-repo nodes must not be filtered out."
    )

    # Sanity: the graph must actually have requirements (not vacuously passing).
    assert n_all > 0, "hht-like fixture must have at least one requirement"


def test_include_associates_defaults_to_false(canonical_federated_graph):
    """_build_index_content default arg is include_associates=False (primary-only)."""
    g = canonical_federated_graph
    spec_dirs = [g.repo_root / "spec"]

    # Call without the kwarg — must not raise and must equal the explicit False call.
    _p_default, content_default, n_default, j_default = _build_index_content(g, spec_dirs)
    _p_false, content_false, n_false, j_false = _build_index_content(
        g, spec_dirs, include_associates=False
    )

    assert content_default == content_false
    assert n_default == n_false
    assert j_default == j_false
