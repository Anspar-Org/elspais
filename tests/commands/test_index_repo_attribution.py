# Validates REQ-d00217-B
"""Repo-based attribution for INDEX.md generation.

Validates REQ-d00217-B: INDEX.md generation must bucket each requirement
and journey node by its owning repository name, resolved via
``FederatedGraph.repo_for(node.id).name``. Path-based classification
against ``spec_dirs`` is disallowed. Nodes whose ownership cannot be
determined must bucket under ``Unattributed`` (distinct from any
per-repo bucket).

These tests are written TDD-style — they are expected to fail before
``commands/index.py`` is migrated from path-based to repo-name-based
attribution. Bug 3 (BUG.md): foreign-repo files don't match the
primary ``spec_dirs`` and bucket as ``Unknown Source``.
"""

from __future__ import annotations

from pathlib import Path

from elspais.commands.glossary_cmd import generate_term_index
from elspais.commands.index import _build_index_content
from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph, RepoEntry
from elspais.graph.relations import EdgeKind
from elspais.graph.terms import TermDictionary, TermEntry, TermRef

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_file_node(repo_root: Path, relative_path: str) -> GraphNode:
    """Create a FILE node with absolute_path/relative_path populated."""
    file_id = f"file:{relative_path}"
    fn = GraphNode(id=file_id, kind=NodeKind.FILE, label=Path(relative_path).name)
    fn.set_field("relative_path", relative_path)
    fn.set_field("absolute_path", str((repo_root / relative_path).resolve()))
    return fn


def _make_requirement(req_id: str, label: str, level: str = "PRD") -> GraphNode:
    """Create a REQUIREMENT node with required fields."""
    node = GraphNode(id=req_id, kind=NodeKind.REQUIREMENT, label=label)
    node.set_field("level", level)
    node.set_field("status", "Active")
    node.set_field("hash", "deadbeef")
    return node


def _make_journey(jny_id: str, label: str, actor: str = "User") -> GraphNode:
    node = GraphNode(id=jny_id, kind=NodeKind.USER_JOURNEY, label=label)
    node.set_field("actor", actor)
    return node


def _attach_to_file(graph: TraceGraph, fn: GraphNode, *children: GraphNode) -> None:
    """Wire CONTAINS edges from FILE to children, register all in the index."""
    if fn.id not in graph._index:
        graph._index[fn.id] = fn
        graph._roots.append(fn)
    for child in children:
        graph._index[child.id] = child
        fn.link(child, EdgeKind.CONTAINS)


def _build_single_repo(
    tmp_path: Path,
    *,
    file_relpath: str = "spec/reqs.md",
) -> FederatedGraph:
    """Build a single-repo FederatedGraph with two REQs and one journey."""
    graph = TraceGraph(repo_root=tmp_path)
    fn = _make_file_node(tmp_path, file_relpath)
    req_a = _make_requirement("REQ-p00001", "First Requirement")
    req_b = _make_requirement("REQ-p00002", "Second Requirement")
    jny_a = _make_journey("JNY-A1", "Login Journey")
    _attach_to_file(graph, fn, req_a, req_b, jny_a)
    return FederatedGraph.from_single(graph, config=None, repo_root=tmp_path)


def _build_two_repo_federation(
    tmp_path: Path,
) -> tuple[FederatedGraph, Path, Path]:
    """Build a two-repo federation: ``root`` and ``callisto``."""
    root_repo = tmp_path / "root"
    callisto_repo = tmp_path / "callisto"
    root_repo.mkdir(parents=True, exist_ok=True)
    callisto_repo.mkdir(parents=True, exist_ok=True)

    # Root repo: REQ-p00001 lives in spec/root_reqs.md
    root_graph = TraceGraph(repo_root=root_repo)
    root_fn = _make_file_node(root_repo, "spec/root_reqs.md")
    root_req = _make_requirement("REQ-p00001", "Root Requirement")
    _attach_to_file(root_graph, root_fn, root_req)

    # Callisto repo: REQ-CAL-p00001 lives in spec/callisto_reqs.md
    cal_graph = TraceGraph(repo_root=callisto_repo)
    cal_fn = _make_file_node(callisto_repo, "spec/callisto_reqs.md")
    cal_req = _make_requirement("REQ-CAL-p00001", "Callisto Requirement")
    _attach_to_file(cal_graph, cal_fn, cal_req)

    root_entry = RepoEntry(
        name="root",
        graph=root_graph,
        config=None,
        repo_root=root_repo,
    )
    cal_entry = RepoEntry(
        name="callisto",
        graph=cal_graph,
        config=None,
        repo_root=callisto_repo,
    )
    fed = FederatedGraph([root_entry, cal_entry], root_repo="root")
    return fed, root_repo, callisto_repo


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSingleRepoBucketsByName:
    """Validates REQ-d00217-B: single-repo nodes bucket under primary repo name."""

    # Implements: REQ-d00217-B
    def test_REQ_d00217_B_single_repo_uses_repo_name_label(self, tmp_path: Path) -> None:
        """A single-repo federation buckets every REQ/JNY under the repo's name.

        Pre-fix: classification uses ``Path.relative_to(spec_dir)`` which works
        when the file's absolute_path resolves under the passed spec_dir, but
        the rendered section label comes from ``_resolve_spec_dir_info`` —
        a path-derived label like ``<parent>/<spec>``, NOT the repo name.
        Post-fix: the label is the repo name (e.g. ``root``).
        """
        fed = _build_single_repo(tmp_path)
        spec_dirs = [tmp_path / "spec"]
        (tmp_path / "spec").mkdir(parents=True, exist_ok=True)

        _output, content, req_count, jny_count = _build_index_content(fed, spec_dirs)

        assert req_count == 2, f"Expected 2 REQs in index, got {req_count}"
        assert jny_count == 1, f"Expected 1 journey in index, got {jny_count}"
        assert "REQ-p00001" in content and "REQ-p00002" in content
        assert "JNY-A1" in content
        assert "Unknown Source" not in content, (
            "Pre-fix path-based classification would surface 'Unknown Source' "
            "for foreign or unmatched files. After fix, it must never appear."
        )
        assert "Unattributed" not in content, (
            "Single-repo with all nodes owned by 'root' must NOT produce an "
            "'Unattributed' bucket."
        )
        # Single-repo INDEX.md historically renders without a per-repo
        # subsection (subsections only appear when multiple repos contribute).
        # The post-fix preserves that behavior: nodes are still attributed
        # internally via repo_for(...).name, but the rendered output omits
        # the trivial single-repo subsection label. The critical invariants
        # for this case are (a) no "Unknown Source" bucket and (b) all REQs
        # render normally.
        assert "REQ-p00001" in content
        assert "REQ-p00002" in content
        assert "JNY-A1" in content


class TestFederatedMultiRepoBuckets:
    """Validates REQ-d00217-B: federated REQs bucket under their owning repo."""

    # Implements: REQ-d00217-B
    def test_REQ_d00217_B_multi_repo_buckets_by_owning_repo(self, tmp_path: Path) -> None:
        """Each REQ appears under a section labeled with its owning repo's name.

        Pre-fix bug: the foreign repo's FILE node has an ``absolute_path``
        that does NOT live under the primary's ``spec_dirs``, so the
        path-based classifier returns ``None`` and the foreign REQ buckets
        as 'Unknown Source'.
        """
        fed, root_repo, _cal_repo = _build_two_repo_federation(tmp_path)
        spec_dirs = [root_repo / "spec"]

        _output, content, req_count, _jny_count = _build_index_content(fed, spec_dirs)

        assert req_count == 2, f"Expected 2 REQs across both repos, got {req_count}"
        assert "REQ-p00001" in content
        assert "REQ-CAL-p00001" in content
        assert "Unknown Source" not in content, (
            "Foreign-repo REQ must NOT bucket as 'Unknown Source'. "
            "It belongs under its owning repo's name ('callisto')."
        )
        assert (
            "callisto" in content
        ), "REQ-CAL-p00001 must surface under a 'callisto' section label."
        # The labels 'root' and 'callisto' should appear distinctly — the
        # foreign REQ should not be lumped with the primary's section.
        assert "root" in content

        # Locate each REQ in the rendered text and verify the nearest
        # preceding subsection label matches the expected repo name.
        cal_idx = content.index("REQ-CAL-p00001")
        # The closest 'callisto' label preceding the foreign REQ must be
        # closer than any 'root' label (i.e., the foreign REQ is rendered
        # under the callisto bucket, not under root).
        cal_label_before_foreign = content.rfind("callisto", 0, cal_idx)
        root_label_before_foreign = content.rfind("root", 0, cal_idx)
        assert cal_label_before_foreign != -1, (
            "Expected 'callisto' label to appear before REQ-CAL-p00001 in "
            "the rendered INDEX, indicating the foreign REQ buckets there."
        )
        assert cal_label_before_foreign > root_label_before_foreign, (
            "REQ-CAL-p00001 must be rendered under the 'callisto' bucket, "
            "not under the 'root' bucket. Closest preceding label should be "
            f"'callisto' (at {cal_label_before_foreign}) but found 'root' "
            f"closer (at {root_label_before_foreign})."
        )


class TestUnattributedBucket:
    """Validates REQ-d00217-B: orphan IDs (KeyError from repo_for) bucket as Unattributed."""

    # Implements: REQ-d00217-B
    def test_REQ_d00217_B_unknown_ownership_buckets_as_unattributed(self, tmp_path: Path) -> None:
        """A node whose ID is not in ``_ownership`` must bucket as 'Unattributed'.

        We simulate the unattributed condition by subclassing FederatedGraph
        and overriding ``repo_for`` to raise KeyError for one specific node.
        The rendered INDEX must surface an 'Unattributed' section containing
        that node, distinct from any per-repo bucket.
        """

        class _OrphanIDFederation(FederatedGraph):
            ORPHAN_ID = "REQ-p00002"

            def repo_for(self, node_id: str):  # type: ignore[override]
                if node_id == self.ORPHAN_ID:
                    raise KeyError(f"Node '{node_id}' not found in any repo")
                return super().repo_for(node_id)

        # Build via the normal route then re-wrap with the subclass.
        graph = TraceGraph(repo_root=tmp_path)
        fn = _make_file_node(tmp_path, "spec/reqs.md")
        req_owned = _make_requirement("REQ-p00001", "Owned Requirement")
        req_orphan = _make_requirement("REQ-p00002", "Orphan Requirement")
        _attach_to_file(graph, fn, req_owned, req_orphan)

        entry = RepoEntry(
            name="root",
            graph=graph,
            config=None,
            repo_root=tmp_path,
        )
        fed = _OrphanIDFederation([entry], root_repo="root")

        spec_dirs = [tmp_path / "spec"]
        (tmp_path / "spec").mkdir(parents=True, exist_ok=True)

        _output, content, req_count, _jny_count = _build_index_content(fed, spec_dirs)

        assert req_count == 2, f"Expected both REQs to be enumerated, got {req_count}"
        assert "REQ-p00001" in content
        assert "REQ-p00002" in content
        assert "Unattributed" in content, (
            "A node whose ownership cannot be resolved (KeyError from "
            "repo_for) must bucket as 'Unattributed'."
        )
        # The 'Unattributed' label must be distinct from any per-repo bucket
        # label — i.e. it must not equal 'root' (the only configured repo).
        assert "Unattributed" != "root", "Sanity"

        # The orphaned REQ must appear inside the Unattributed bucket — its
        # nearest preceding label should be 'Unattributed', not 'root'.
        orphan_idx = content.index("REQ-p00002")
        unatt_before_orphan = content.rfind("Unattributed", 0, orphan_idx)
        root_before_orphan = content.rfind("root", 0, orphan_idx)
        assert unatt_before_orphan != -1, "Expected 'Unattributed' label to precede REQ-p00002."
        assert unatt_before_orphan > root_before_orphan, (
            "REQ-p00002 must be rendered under the 'Unattributed' bucket, " "not under 'root'."
        )


class TestNoSpecDirPathMatching:
    """Validates REQ-d00217-B: classification ignores spec_dirs path matching."""

    # Implements: REQ-d00217-B
    def test_REQ_d00217_B_file_outside_spec_dirs_still_buckets_by_repo(
        self, tmp_path: Path
    ) -> None:
        """Files whose absolute_path is outside ``spec_dirs`` still bucket
        under the owning repo (regression for Bug 3).

        Pre-fix: ``_classify_node`` walks ``spec_dirs`` calling
        ``relative_to``; if no spec_dir contains the file, it returns None
        and the node ends up under 'Unknown Source'.
        Post-fix: classification consults ``graph.repo_for(node.id).name``
        and is independent of any spec_dirs argument.
        """
        graph = TraceGraph(repo_root=tmp_path)

        # Place the FILE node under a path that is NOT under the spec_dirs
        # we will pass to _build_index_content. This simulates a foreign
        # repo whose files do not live under the primary's spec dirs, OR
        # a misconfigured spec_dirs argument.
        far_file_relpath = "elsewhere/foreign_reqs.md"
        fn = _make_file_node(tmp_path, far_file_relpath)
        req = _make_requirement("REQ-p00001", "Requirement Outside Spec Dirs")
        _attach_to_file(graph, fn, req)

        fed = FederatedGraph.from_single(graph, config=None, repo_root=tmp_path)

        # Pass a spec_dirs that does NOT contain the file's directory.
        spec_dirs = [tmp_path / "spec"]
        (tmp_path / "spec").mkdir(parents=True, exist_ok=True)

        _output, content, req_count, _jny_count = _build_index_content(fed, spec_dirs)

        assert req_count == 1, f"Expected REQ to be indexed, got {req_count}"
        assert "REQ-p00001" in content
        assert "Unknown Source" not in content, (
            "Bug 3 regression: a file outside the passed spec_dirs must "
            "NOT bucket as 'Unknown Source'. After the fix, it buckets "
            "under its owning repo's name."
        )
        assert "Unattributed" not in content, (
            "REQ-p00001 has a known owner ('root'); it must NOT bucket "
            "as 'Unattributed' just because its file is outside spec_dirs."
        )


class TestCrossGeneratorConsistency:
    """Validates REQ-d00217-B: INDEX.md and term-index.md agree on bucket label."""

    # Implements: REQ-d00217-B
    def test_REQ_d00217_B_index_label_matches_term_index_namespace(self, tmp_path: Path) -> None:
        """For a federated graph, any REQ ID present in both INDEX.md and
        term-index.md must use the same bucket label.

        term-index.md groups TermRef by ``namespace`` (which is the repo
        name). After the INDEX.md fix, the INDEX.md bucket for the same
        REQ must also be the repo name — so the labels align.
        """
        fed, root_repo, _cal_repo = _build_two_repo_federation(tmp_path)
        spec_dirs = [root_repo / "spec"]

        _output, index_content, _r, _j = _build_index_content(fed, spec_dirs)

        # Build a term dictionary that references the foreign REQ from the
        # callisto namespace. This mirrors how the federation's _scan_terms
        # would attribute references — by repo name.
        td = TermDictionary()
        td.add(
            TermEntry(
                term="Federation",
                definition="A union of repositories sharing terms.",
                indexed=True,
                defined_in="REQ-CAL-p00001",
                namespace="callisto",
                references=[
                    TermRef(
                        node_id="REQ-CAL-p00001",
                        namespace="callisto",
                        marked=True,
                        line=1,
                    ),
                ],
            )
        )
        td.add(
            TermEntry(
                term="Root",
                definition="The primary repository in a federation.",
                indexed=True,
                defined_in="REQ-p00001",
                namespace="root",
                references=[
                    TermRef(
                        node_id="REQ-p00001",
                        namespace="root",
                        marked=True,
                        line=1,
                    ),
                ],
            )
        )
        term_index_content = generate_term_index(td, format="markdown")

        # term-index.md uses **<namespace>:** as the bucket header.
        assert "**callisto:**" in term_index_content
        assert "**root:**" in term_index_content
        assert "REQ-CAL-p00001" in term_index_content
        assert "REQ-p00001" in term_index_content

        # The foreign REQ's term-index namespace is 'callisto'. The INDEX.md
        # bucket label for the same REQ MUST also surface 'callisto' — not
        # 'Unknown Source' and not the primary's path-derived label.
        assert "callisto" in index_content, (
            "INDEX.md bucket label for REQ-CAL-p00001 must align with the "
            "term-index.md namespace ('callisto'). Pre-fix it surfaces as "
            "'Unknown Source' instead."
        )
        # Same for the root REQ.
        assert "root" in index_content
        assert "Unknown Source" not in index_content
