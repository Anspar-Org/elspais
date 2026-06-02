"""term-index generation uses primary terms only unless index_associates=True.

Implements: REQ-d00253-C
"""

from elspais.commands.fix_cmd import _select_terms_dictionary


def test_select_terms_federated_returns_merged(canonical_federated_graph):
    g = canonical_federated_graph
    federated = _select_terms_dictionary(g, include_associates=True)
    assert federated is g.terms


def test_select_terms_primary_only_returns_root_not_merged(canonical_federated_graph):
    """False branch must return the root repo's own TraceGraph._terms, not the merged dict.

    Identity semantics (both properties return a stable cached object):
      - FederatedGraph.terms   -> self._terms  (merged TermDictionary, a distinct object)
      - TraceGraph.terms       -> self._terms  (the per-repo TermDictionary)
      - FederatedGraph._merge_terms() always constructs a NEW TermDictionary, so
        g.terms is never the same object as any single repo's entry.graph._terms.

    Assertions:
      1. primary is NOT the merged federated dict     -- fails if False branch returns g.terms
      2. primary IS the root repo's own TraceGraph._terms -- fails if False branch returns
         anything other than the root repo's terms
      3. len(primary) <= len(federated)               -- sanity: subset relationship
    """
    g = canonical_federated_graph
    primary = _select_terms_dictionary(g, include_associates=False)
    federated = _select_terms_dictionary(g, include_associates=True)

    # Locate the root repo's TraceGraph.
    root_entry = next(e for e in g.iter_repos() if e.name == g.root_repo_name)
    root_terms = root_entry.graph.terms  # stable object: TraceGraph._terms

    # 1. Must NOT be the merged dict (would fail if False branch returns g.terms).
    assert primary is not g.terms, (
        "_select_terms_dictionary(False) must return the root repo's own terms, "
        "not the federated merged TermDictionary"
    )

    # 2. Must be exactly the root repo's own stable _terms object.
    assert primary is root_terms, (
        "_select_terms_dictionary(False) must return root_entry.graph.terms "
        f"(id={id(root_terms):#x}), got id={id(primary):#x}"
    )

    # 3. Sanity: primary is a subset of the federated merged dict.
    assert len(primary) <= len(federated)
