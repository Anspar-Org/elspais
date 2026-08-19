# Verifies: REQ-d00253-B
"""render_save must not write associate files unless write_associates=True."""

import pathlib

import pytest

from elspais.graph.GraphNode import NodeKind


class FakeFileNode:
    def __init__(self, fid, rel, repo):
        self.id = fid
        self.kind = NodeKind.FILE
        self._fields = {"relative_path": rel, "repo": repo}

    def get_field(self, k):
        return self._fields.get(k)


class _Log:
    def iter_entries(self):
        return iter(())

    def clear(self):
        pass


class FakeGraph:
    repo_root = pathlib.Path("/tmp/primary")
    mutation_log = _Log()

    def __init__(self, nodes):
        self._nodes = nodes

    def find_by_id(self, nid):
        return self._nodes.get(nid)

    def duplicate_req_ids(self):
        return {}

    def nodes_by_kind(self, kind):
        return iter(())

    def repo_for(self, fid):
        raise KeyError(fid)

    def repo_for_node(self, node):
        raise KeyError(node.id)


class _Repo:
    """Minimal repo-like object returned by graph.repo_for().

    Provides the attributes accessed by render_save in both the federation
    write-gate (name) and the write path (repo_root, graph).
    """

    def __init__(self, name: str, repo_root: pathlib.Path) -> None:
        self.name = name
        self.repo_root = repo_root
        self.graph = None  # resolver lookup falls back gracefully on None


class FakeGraphWithOwnership(FakeGraph):
    """FakeGraph variant whose repo_for() resolves via an ownership map.

    Both FILE nodes have ``repo=None`` so the fallback (repo-field) path cannot
    distinguish primary from associate — only the ownership map can.
    """

    root_repo_name = "primary"

    _REPO_ROOTS: dict[str, pathlib.Path] = {
        "primary": pathlib.Path("/tmp/primary"),
        "lib": pathlib.Path("/tmp/lib"),
    }

    def __init__(self, nodes, ownership: dict[str, str]) -> None:
        super().__init__(nodes)
        # ownership maps file_id -> repo name string
        self._ownership = ownership

    def repo_for(self, fid: str) -> _Repo:
        # Raises KeyError for unknown IDs, matching real FederatedGraph behaviour.
        name = self._ownership[fid]
        return _Repo(name, self._REPO_ROOTS[name])

    def repo_for_node(self, node) -> _Repo:
        # The real graph settles this by node identity; these fixtures hold
        # one node per id, so resolving through the id agrees with it.
        return self.repo_for(node.id)


@pytest.mark.parametrize(
    "write_associates, expect_associate_written",
    [
        (False, False),
        (True, True),
    ],
)
def test_render_save_associate_file_filter(monkeypatch, write_associates, expect_associate_written):
    from elspais.graph import render

    written = []

    primary = FakeFileNode("file:spec/a.md", "spec/a.md", None)
    associate = FakeFileNode("file:spec/b.md", "spec/b.md", "lib")
    nodes = {n.id: n for n in (primary, associate)}

    monkeypatch.setattr(render, "_find_dirty_files", lambda g, resolver=None: [primary, associate])
    monkeypatch.setattr(render, "_wire_new_requirements_to_files", lambda g: None)
    monkeypatch.setattr(render, "render_file", lambda node, resolver=None: "body\n")
    monkeypatch.setattr(
        pathlib.Path,
        "write_text",
        lambda self, content, encoding="utf-8": written.append(str(self)),
    )

    g = FakeGraph(nodes)
    result = render.render_save(g, repo_root=g.repo_root, write_associates=write_associates)

    assert any("a.md" in w for w in written), "primary file must always be written"
    assert result["success"] is True

    if expect_associate_written:
        assert any("b.md" in w for w in written), "associate file should be written when enabled"
    else:
        assert not any("b.md" in w for w in written), "associate file must be skipped by default"


@pytest.mark.parametrize(
    "write_associates, expect_associate_written",
    [
        (False, False),
        (True, True),
    ],
)
# Verifies: REQ-d00253-B
def test_render_save_ownership_map_path(monkeypatch, write_associates, expect_associate_written):
    """Gate uses repo_for() ownership map as primary signal, not the repo field.

    Both FILE nodes have ``repo=None``.  The fallback (repo-field) path therefore
    cannot distinguish primary from associate, so if the gate ever reverts to
    using the repo field this test will fail (the associate would not be filtered
    and would be written even with write_associates=False).
    """
    from elspais.graph import render

    written = []

    # repo=None on BOTH nodes — fallback path cannot detect the associate.
    primary = FakeFileNode("file:spec/a.md", "spec/a.md", None)
    associate = FakeFileNode("file:lib/b.md", "lib/b.md", None)
    nodes = {n.id: n for n in (primary, associate)}

    # Ownership map: primary file is owned by "primary", associate by "lib".
    ownership = {
        "file:spec/a.md": "primary",
        "file:lib/b.md": "lib",
    }

    monkeypatch.setattr(render, "_find_dirty_files", lambda g, resolver=None: [primary, associate])
    monkeypatch.setattr(render, "_wire_new_requirements_to_files", lambda g: None)
    monkeypatch.setattr(render, "render_file", lambda node, resolver=None: "body\n")
    monkeypatch.setattr(
        pathlib.Path,
        "write_text",
        lambda self, content, encoding="utf-8": written.append(str(self)),
    )

    g = FakeGraphWithOwnership(nodes, ownership)
    result = render.render_save(g, repo_root=g.repo_root, write_associates=write_associates)

    assert any("a.md" in w for w in written), "primary file must always be written"
    assert result["success"] is True

    if expect_associate_written:
        assert any("b.md" in w for w in written), "associate file should be written when enabled"
    else:
        assert not any("b.md" in w for w in written), (
            "associate must be skipped (ownership-map path)"
        )


class TestRenderSaveRealFederationSamePath:
    """Validates REQ-d00253-B: the write gate answers for the repo actually edited.

    Both members of this federation hold `spec/reqs.md`, so the ownership map
    keyed by structural id resolves both to a single member.  Only resolution
    by node identity routes the associate's edit to the associate's file and
    leaves the primary's same-named file alone.
    """

    @staticmethod
    def _federation(tmp_path):
        """Build a real primary + associate federation sharing `spec/reqs.md`."""
        from elspais.config import load_config
        from elspais.graph.factory import build_graph
        from tests.federation_repos import make_repo, namespace_for

        associate = make_repo(tmp_path, "lib")
        primary = make_repo(tmp_path, "core", associates={"lib": str(associate)})

        config_path = primary / ".elspais.toml"
        graph = build_graph(
            config=load_config(config_path),
            config_path=config_path,
            repo_root=primary,
            scan_code=False,
            scan_tests=False,
        )
        associate_req = f"{namespace_for('lib')}-d00001"
        assert graph.find_by_id(associate_req) is not None, "associate requirement must load"
        return graph, primary, associate, associate_req

    # Verifies: REQ-d00253-B
    def test_d00253_B_associate_edit_lands_in_associate_repo(self, tmp_path):
        from elspais.graph.render import render_save

        graph, primary, associate, associate_req = self._federation(tmp_path)
        primary_spec = primary / "spec" / "reqs.md"
        associate_spec = associate / "spec" / "reqs.md"
        primary_before = primary_spec.read_bytes()

        new_title = "Retitled in the associate"
        graph.update_title(associate_req, new_title)

        result = render_save(graph, repo_root=primary, write_associates=True)

        assert result["success"] is True, result["errors"]
        # 1. The associate's own file carries the edit.
        assert new_title in associate_spec.read_text(encoding="utf-8"), (
            "the associate's file must receive the edit made to its requirement; "
            f"files_modified={result['files_modified']}"
        )
        # 2. The primary's same-path file must not have been rewritten.
        assert primary_spec.read_bytes() == primary_before, (
            "the primary repo's same-named file must be untouched by an associate-owned edit"
        )

    # Verifies: REQ-d00253-B
    def test_d00253_B_associate_edit_refused_by_default(self, tmp_path):
        from elspais.graph.render import render_save

        graph, primary, associate, associate_req = self._federation(tmp_path)
        primary_spec = primary / "spec" / "reqs.md"
        associate_spec = associate / "spec" / "reqs.md"
        primary_before = primary_spec.read_bytes()
        associate_before = associate_spec.read_bytes()

        graph.update_title(associate_req, "Retitled without permission")

        # 3. Default write_associates=False refuses the write entirely.
        render_save(graph, repo_root=primary)

        assert associate_spec.read_bytes() == associate_before, (
            "an associate-owned edit must not be written with write_associates=False"
        )
        assert primary_spec.read_bytes() == primary_before, (
            "refusing the associate write must not divert it into the primary repo"
        )
