"""render_save must not write associate files unless write_associates=True.

Implements: REQ-d00253-B
"""

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

    monkeypatch.setattr(
        render, "_find_dirty_files", lambda g, resolver=None: {"file:spec/a.md", "file:spec/b.md"}
    )
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
