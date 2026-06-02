# Federation Write/Generation Scope Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `elspais fix` and MCP mutations primary-repo-only by default, with two opt-in `[federation]` config flags, so associates affect only read/validation surfaces.

**Architecture:** Add a `[federation]` config table (`write_associates`, `index_associates`, both default `false`). Gate the single write surface (`render_save`) and the two generate surfaces (`INDEX.md` via `_build_index_content`, term-index via `_fix_terms`) on these flags. Add an MCP guard that rejects mutations targeting associate-owned nodes when writes are disabled.

**Tech Stack:** Python 3.10+, pydantic v2 (config schema), pytest (unit + e2e markers), tomlkit.

**Reference spec:** `docs/superpowers/specs/2026-06-01-federation-write-scope-design.md`

---

## Background facts the implementer needs

- `build_graph()` returns a `FederatedGraph` (primary repo + associates). It is correct that reads federate; only writes/generation must not.
- A FILE node carries a `repo` field: `None` for the primary (root) repo, the associate name for associates (`factory.py:1209` sets `repo=None if repo_name == self._root_repo else repo_name`). **Use `file_node.get_field("repo") is None` as the "is primary FILE" test.**
- For non-FILE nodes (REQUIREMENT, etc.), ownership is `graph.repo_for(node_id).name`; the primary is `graph.root_repo_name`. `repo_for` raises `KeyError` for unknown/structural ids.
- `load_config()` returns a `dict[str, Any]` (pydantic `model_dump(by_alias=True)`). Nested access: `config.get("federation", {}).get("write_associates", False)`. New fields with defaults need **no** version migration.
- The single write surface is `render_save()` in `src/elspais/graph/render.py:734`. Both `fix` and MCP `save_mutations` call it.
- `_build_index_content()` (`src/elspais/commands/index.py:316`) iterates `graph.nodes_by_kind(NodeKind.REQUIREMENT)` / `USER_JOURNEY` across all repos.
- `_fix_terms()` (`src/elspais/commands/fix_cmd.py:759`) uses `graph.terms` (merged across repos).
- MCP mutate tool wrappers live inside `create_server()` (`src/elspais/mcp/server.py`, ~5340-5530); each delegates to a private `_mutate_*(graph, ...)`. `_state["config"]` (a dict) and `_state["graph"]` are in closure scope at the wrapper.

**Run tests with:** `pytest <path> -v` (unit tier, ~26s). E2E tests use `@pytest.mark.e2e` and run with `pytest -m e2e`.

---

## Task 1: Add `[federation]` config schema

**Files:**
- Modify: `src/elspais/config/schema.py` (add `FederationConfig`, add field to `ElspaisConfig`)
- Test: `tests/config/test_federation_config.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/config/test_federation_config.py`:

```python
"""Tests for the [federation] config table.

Implements: REQ-d00231-A
"""
from elspais.config.schema import ElspaisConfig, FederationConfig


def test_federation_defaults_are_false():
    cfg = ElspaisConfig()
    assert cfg.federation.write_associates is False
    assert cfg.federation.index_associates is False


def test_federation_parses_from_dict():
    cfg = ElspaisConfig.model_validate(
        {"federation": {"write_associates": True, "index_associates": True}}
    )
    assert cfg.federation.write_associates is True
    assert cfg.federation.index_associates is True


def test_federation_dump_uses_plain_keys():
    dumped = ElspaisConfig().model_dump(by_alias=True)
    assert dumped["federation"] == {
        "write_associates": False,
        "index_associates": False,
    }


def test_federation_rejects_unknown_field():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FederationConfig(bogus=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/config/test_federation_config.py -v`
Expected: FAIL — `ImportError: cannot import name 'FederationConfig'`.

- [ ] **Step 3: Implement the schema**

In `src/elspais/config/schema.py`, add the sub-model just before `class ElspaisConfig` (near line 407):

```python
class FederationConfig(_StrictModel):
    """Controls how associate repos affect write/generate surfaces.

    Reads (checks/summary/cross-repo resolution) always federate; these flags
    govern only the write and generation surfaces.
    """

    write_associates: bool = False
    index_associates: bool = False
```

Then add the field to `ElspaisConfig` (alongside `associates`, after line 433):

```python
    federation: FederationConfig = Field(default_factory=FederationConfig)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/config/test_federation_config.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Verify existing config tests still pass**

Run: `pytest tests/config/ -v`
Expected: PASS (no regressions; existing configs without `[federation]` still validate via the default).

- [ ] **Step 6: Commit**

```bash
# bump patch version per project rule
python - <<'PY'
import re, pathlib
p = pathlib.Path("pyproject.toml"); t = p.read_text()
t = re.sub(r'(version = "0\.117\.)(\d+)(")', lambda m: f'{m.group(1)}{int(m.group(2))+1}{m.group(3)}', t, count=1)
p.write_text(t)
PY
git add src/elspais/config/schema.py tests/config/test_federation_config.py pyproject.toml
git commit -m "[CUR-1419] feat(config): add [federation] write_associates/index_associates flags

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Author governing spec requirements

Tests must reference real REQs (project rule). Author them now so later tasks can cite them.

**Files:**
- Spec files under `spec/` (use the elspais MCP / spec authoring; exact file chosen by inspection)
- Generated: `spec/INDEX.md`, `spec/_generated/*` (regenerated by `elspais fix`)

- [ ] **Step 1: Find the right home for the requirements**

Use the elspais MCP to locate the existing federation/fix requirements:

```
mcp__elspais__search(query="federation associate", field="all")
mcp__elspais__search(query="fix render_save generate INDEX", field="all")
```

Identify the DEV-level requirement family that owns federation behavior (the spec uses `REQ-d00200`/`REQ-d00230` series for federation). Pick the next free DEV id in that area — referred to below as **`REQ-d00231`** (adjust if taken).

- [ ] **Step 2: Author the requirement with assertions**

Add a new requirement (via spec file edit in the appropriate `spec/*.md`, matching surrounding format) titled e.g. "Federation write/generation scope", with these assertions:

- **-A**: The `[federation]` config table SHALL expose `write_associates` and `index_associates`, both defaulting to false.
- **-B**: `elspais fix` SHALL write spec files only in the primary (root) repo unless `federation.write_associates` is true; with it false, primary-repo output SHALL be byte-identical whether or not an associate is configured.
- **-C**: Generated `INDEX.md` and `term-index.md` SHALL contain only primary-repo requirements/terms unless `federation.index_associates` is true.
- **-D**: MCP mutation tools SHALL reject mutations targeting associate-owned nodes when `federation.write_associates` is false, returning a read-only error and applying no in-memory change.

- [ ] **Step 3: Regenerate and validate**

Run: `elspais fix`
Expected: "Validated N requirements"; the new REQ appears in `spec/INDEX.md`. (Note: this repo has no associate configured, so the new filters don't change its output.)

- [ ] **Step 4: Commit**

```bash
git add spec/
git commit -m "[CUR-1419] spec: requirements for federation write/generation scope

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

(No version bump needed for a spec-only changelog if the project's pre-commit `elspais fix` is satisfied; if pre-commit complains, bump patch as in Task 1 Step 6.)

---

## Task 3: Gate the write surface in `render_save`

**Files:**
- Modify: `src/elspais/graph/render.py` (`render_save` signature + filter)
- Modify: `src/elspais/commands/fix_cmd.py` (2 call sites: lines ~494, ~640)
- Modify: `src/elspais/mcp/server.py` (`save_mutations`, ~5746)
- Test: `tests/graph/test_render_save_federation.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/graph/test_render_save_federation.py`:

```python
"""render_save must not write associate files unless write_associates=True.

Implements: REQ-d00231-B
"""
from elspais.graph.GraphNode import GraphNode, NodeKind


def _make_file_node(graph_obj, file_id, rel_path, repo):
    """Find or fabricate a minimal dirty FILE node for the test."""
    node = graph_obj.find_by_id(file_id)
    return node


def test_associate_file_excluded_when_write_disabled(monkeypatch):
    """A dirty FILE node owned by an associate (repo field set) is filtered
    out of the write set when write_associates=False."""
    from elspais.graph import render

    written = []

    class FakeFileNode:
        kind = NodeKind.FILE

        def __init__(self, fid, rel, repo):
            self.id = fid
            self._fields = {"relative_path": rel, "repo": repo}

        def get_field(self, k):
            return self._fields.get(k)

    primary = FakeFileNode("file:spec/a.md", "spec/a.md", None)
    associate = FakeFileNode("file:spec/b.md", "spec/b.md", "lib")
    nodes = {n.id: n for n in (primary, associate)}

    class FakeGraph:
        repo_root = __import__("pathlib").Path("/tmp/primary")

        def find_by_id(self, nid):
            return nodes.get(nid)

        def duplicate_req_ids(self):
            return {}

        class _Log:
            def iter_entries(self):
                return iter(())

            def clear(self):
                pass

        mutation_log = _Log()

        def nodes_by_kind(self, kind):
            return iter(())

    monkeypatch.setattr(
        render, "_find_dirty_files", lambda g, resolver=None: {"file:spec/a.md", "file:spec/b.md"}
    )
    monkeypatch.setattr(render, "_wire_new_requirements_to_files", lambda g: None)
    monkeypatch.setattr(render, "render_file", lambda node, resolver=None: "body\n")
    monkeypatch.setattr(
        FakeFileNode, "kind", NodeKind.FILE, raising=False
    )

    def fake_write(self, content, encoding="utf-8"):
        written.append(str(self))

    monkeypatch.setattr("pathlib.Path.write_text", fake_write)

    g = FakeGraph()
    result = render.render_save(g, repo_root=g.repo_root, write_associates=False)

    assert any("a.md" in w for w in written)
    assert not any("b.md" in w for w in written)
    assert result["success"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/graph/test_render_save_federation.py -v`
Expected: FAIL — `render_save() got an unexpected keyword argument 'write_associates'`.

- [ ] **Step 3: Add the parameter and filter**

In `src/elspais/graph/render.py`, change the `render_save` signature (line 734) to add the parameter:

```python
def render_save(
    graph: FederatedGraph,
    repo_root: Path | None = None,
    consistency_check: bool = False,
    rebuild_fn: Any | None = None,
    resolver: Any | None = None,
    write_associates: bool = False,
) -> dict[str, Any]:
```

Then, immediately after `dirty_file_ids = _find_dirty_files(graph, resolver=resolver)` (line 780) and before the `if not dirty_file_ids:` check, insert the primary-repo filter:

```python
    # Federation: by default, fix/save writes only primary-repo files. An
    # associate FILE node carries a non-None `repo` field; the primary's is
    # None. Implements: REQ-d00231-B
    if not write_associates:
        primary_only: set[str] = set()
        for file_id in dirty_file_ids:
            fnode = graph.find_by_id(file_id)
            if fnode is not None and fnode.get_field("repo") is not None:
                continue  # owned by an associate — never written by default
            primary_only.add(file_id)
        dirty_file_ids = primary_only
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/graph/test_render_save_federation.py -v`
Expected: PASS.

- [ ] **Step 5: Plumb the flag from `fix` call sites**

In `src/elspais/commands/fix_cmd.py`, both call sites have `config` already loaded (line 378 in `_fix_parse_dirty`, line 525 in the single-node fix). Change line ~494:

```python
    result = render_save(
        graph,
        repo_root=repo_root,
        write_associates=config.get("federation", {}).get("write_associates", False),
    )
```

And the call near line ~640 (same change — `config` is in scope there):

```python
    result = render_save(
        graph,
        repo_root=repo_root,
        write_associates=config.get("federation", {}).get("write_associates", False),
    )
```

- [ ] **Step 6: Plumb the flag from MCP `save_mutations`**

In `src/elspais/mcp/server.py`, the `save_mutations` body calls `render_save(graph, _state["working_dir"], resolver=...)` near line 5746. Change it to pass the flag from `_state["config"]`:

```python
        result = render_save(
            graph,
            _state["working_dir"],
            resolver=_build_resolver_for_save(config),
            write_associates=(
                config.get("federation", {}).get("write_associates", False)
                if isinstance(config, dict)
                else False
            ),
        )
```

(`config = _state.get("config", {})` is already bound earlier in `save_mutations`.)

- [ ] **Step 7: Run the surrounding suites**

Run: `pytest tests/graph/ tests/commands/ -v -k "render or fix or save"`
Expected: PASS (no regressions).

- [ ] **Step 8: Commit**

```bash
python - <<'PY'
import re, pathlib
p = pathlib.Path("pyproject.toml"); t = p.read_text()
t = re.sub(r'(version = "0\.117\.)(\d+)(")', lambda m: f'{m.group(1)}{int(m.group(2))+1}{m.group(3)}', t, count=1)
p.write_text(t)
PY
git add src/elspais/graph/render.py src/elspais/commands/fix_cmd.py src/elspais/mcp/server.py tests/graph/test_render_save_federation.py pyproject.toml
git commit -m "[CUR-1419] fix(federation): render_save writes primary-repo files only by default

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Gate `INDEX.md` generation

**Files:**
- Modify: `src/elspais/commands/index.py` (`_build_index_content` signature + filter; pass-through in `_regenerate_index`)
- Modify: `src/elspais/commands/fix_cmd.py` (`_fix_index` ~745 passes the flag)
- Test: `tests/commands/test_index_federation.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/commands/test_index_federation.py`:

```python
"""INDEX.md content includes associate reqs only when index_associates=True.

Implements: REQ-d00231-C
"""
import pytest

from elspais.commands.index import _build_index_content
from elspais.graph.GraphNode import NodeKind


@pytest.fixture
def two_repo_graph(canonical_federated_graph):
    """A federated graph with at least one associate repo."""
    return canonical_federated_graph


def _ids_in_content(content):
    import re
    return set(re.findall(r"REQ-\w+|[A-Z]+-\w+", content))


def test_primary_only_excludes_associate_reqs(two_repo_graph, tmp_path):
    spec_dirs = [two_repo_graph.repo_root / "spec"]
    _path, content_all, n_all, _j1 = _build_index_content(
        two_repo_graph, spec_dirs, include_associates=True
    )
    _path, content_primary, n_primary, _j2 = _build_index_content(
        two_repo_graph, spec_dirs, include_associates=False
    )
    # Primary-only must have <= federated count, and strictly fewer if the
    # fixture actually has associate reqs.
    assert n_primary <= n_all
    root = two_repo_graph.root_repo_name
    # Every requirement counted in primary-only is owned by the root repo.
    for node in two_repo_graph.nodes_by_kind(NodeKind.REQUIREMENT):
        owner = None
        try:
            owner = two_repo_graph.repo_for(node.id).name
        except KeyError:
            pass
        if owner is not None and owner != root:
            assert node.id not in content_primary
```

> Note: confirm `canonical_federated_graph` includes an associate. If it does not, build a minimal two-repo graph in the test using the same helper the `test_e2e_associated` fixture uses, or skip with a clear reason and rely on the e2e test in Task 7.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/commands/test_index_federation.py -v`
Expected: FAIL — `_build_index_content() got an unexpected keyword argument 'include_associates'`.

- [ ] **Step 3: Add the parameter and filter**

In `src/elspais/commands/index.py`, change `_build_index_content` (line 316):

```python
def _build_index_content(
    graph: FederatedGraph, spec_dirs: list[Path], include_associates: bool = False
) -> tuple[Path, str, int, int]:
```

Inside, replace the two iteration loops (lines 349-352) with filtered versions:

```python
    root_repo = graph.root_repo_name

    def _is_included(node: object) -> bool:
        if include_associates:
            return True
        name = _repo_name_for(graph, node.id)
        # Unattributed (name is None) defaults to primary inclusion.
        return name is None or name == root_repo

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if not _is_included(node):
            continue
        reqs_by_bucket[_bucket_for(node)].append(node)
    for node in graph.nodes_by_kind(NodeKind.USER_JOURNEY):
        if not _is_included(node):
            continue
        jnys_by_bucket[_bucket_for(node)].append(node)
```

- [ ] **Step 4: Thread the flag through `_regenerate_index`**

In `src/elspais/commands/index.py`, change `_regenerate_index` (line 492) to accept and forward the flag:

```python
def _regenerate_index(
    graph: FederatedGraph,
    spec_dirs: list[Path],
    args: argparse.Namespace,
    include_associates: bool = False,
) -> int:
    """Regenerate INDEX.md from graph requirements."""
    repo_root = getattr(args, "git_root", None)
    if repo_root is None:
        print("Cannot generate INDEX.md: not in a git repository.", file=sys.stderr)
        return 1

    output_path, content, req_count, jny_count = _build_index_content(
        graph, spec_dirs, include_associates=include_associates
    )
```

(rest of `_regenerate_index` unchanged.)

- [ ] **Step 5: Pass the flag from `_fix_index`**

In `src/elspais/commands/fix_cmd.py`, `_fix_index` loads `config` at line 727. Change the two `_build_index_content` / `_regenerate_index` calls (lines ~745, ~755):

```python
    include_assoc = config.get("federation", {}).get("index_associates", False)
    output_path, expected, _req_count, _jny_count = _build_index_content(
        graph, all_spec_dirs, include_associates=include_assoc
    )
    if output_path.exists():
        current = output_path.read_text(encoding="utf-8")
        if current == expected:
            return

    if dry_run:
        print("Would regenerate INDEX.md")
        return

    _regenerate_index(graph, all_spec_dirs, args, include_associates=include_assoc)
```

- [ ] **Step 6: Find and update any other `_build_index_content` / `_regenerate_index` callers**

Run: `grep -rn "_build_index_content\|_regenerate_index" src/`
Expected: only the sites above. If the `index` CLI command (`elspais index`) calls `_regenerate_index` directly, pass `include_associates` from its config the same way. Update each to read the flag from its loaded config.

- [ ] **Step 7: Run tests**

Run: `pytest tests/commands/test_index_federation.py tests/commands/ -v -k index`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
python - <<'PY'
import re, pathlib
p = pathlib.Path("pyproject.toml"); t = p.read_text()
t = re.sub(r'(version = "0\.117\.)(\d+)(")', lambda m: f'{m.group(1)}{int(m.group(2))+1}{m.group(3)}', t, count=1)
p.write_text(t)
PY
git add src/elspais/commands/index.py src/elspais/commands/fix_cmd.py tests/commands/test_index_federation.py pyproject.toml
git commit -m "[CUR-1419] fix(federation): INDEX.md primary-repo-only unless index_associates

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Gate term-index / glossary generation

**Files:**
- Modify: `src/elspais/commands/fix_cmd.py` (`_fix_terms`, lines ~759-802)
- Test: `tests/commands/test_terms_federation.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/commands/test_terms_federation.py`:

```python
"""term-index generation uses primary terms only unless index_associates=True.

Implements: REQ-d00231-C
"""
from elspais.commands.fix_cmd import _select_terms_dictionary


def test_select_terms_primary_only(canonical_federated_graph):
    g = canonical_federated_graph
    primary = _select_terms_dictionary(g, include_associates=False)
    federated = _select_terms_dictionary(g, include_associates=True)
    # Primary terms are a subset of federated terms.
    assert len(primary) <= len(federated)


def test_select_terms_federated(canonical_federated_graph):
    g = canonical_federated_graph
    federated = _select_terms_dictionary(g, include_associates=True)
    assert federated is g.terms
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/commands/test_terms_federation.py -v`
Expected: FAIL — `cannot import name '_select_terms_dictionary'`.

- [ ] **Step 3: Extract a term-selection helper and gate it**

In `src/elspais/commands/fix_cmd.py`, add a helper near `_fix_terms`:

```python
def _select_terms_dictionary(graph, include_associates: bool):
    """Return the TermDictionary to render.

    Primary-only (default) returns the root repo's own terms; federated
    returns the merged dictionary. Implements: REQ-d00231-C
    """
    if include_associates:
        return graph.terms if hasattr(graph, "terms") else None
    # Primary-only: the root repo's own TraceGraph terms.
    root = getattr(graph, "root_repo_name", None)
    if root is not None:
        for entry in graph.iter_repos():
            if entry.name == root and entry.graph is not None:
                return getattr(entry.graph, "terms", None)
    # Non-federated graph fallback.
    return getattr(graph, "terms", None)
```

Then replace the term-selection block in `_fix_terms` (lines 780-789) with:

```python
    config = get_config(config_path)
    include_assoc = config.get("federation", {}).get("index_associates", False)
    td = _select_terms_dictionary(graph, include_associates=include_assoc)
```

(Remove the old `if hasattr(graph, "terms"): ... else: for entry in graph._repos.values(): ...` block. `config`/`get_config` are already imported at the top of `_fix_terms`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/commands/test_terms_federation.py -v`
Expected: PASS.

- [ ] **Step 5: Run terms/glossary suites**

Run: `pytest tests/ -v -k "term or glossary"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
python - <<'PY'
import re, pathlib
p = pathlib.Path("pyproject.toml"); t = p.read_text()
t = re.sub(r'(version = "0\.117\.)(\d+)(")', lambda m: f'{m.group(1)}{int(m.group(2))+1}{m.group(3)}', t, count=1)
p.write_text(t)
PY
git add src/elspais/commands/fix_cmd.py tests/commands/test_terms_federation.py pyproject.toml
git commit -m "[CUR-1419] fix(federation): term-index primary-repo-only unless index_associates

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: MCP read-only guard for associate mutations

**Files:**
- Modify: `src/elspais/mcp/server.py` (add `_guard_associate_write`; apply in mutate wrappers; surface flags in `_get_workspace_info`)
- Test: `tests/mcp/test_associate_guard.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/mcp/test_associate_guard.py`:

```python
"""MCP mutations targeting associate nodes are rejected when writes disabled.

Implements: REQ-d00231-D
"""
from elspais.mcp.server import _guard_associate_write


class _Repo:
    def __init__(self, name):
        self.name = name


class _Graph:
    root_repo_name = "primary"

    def __init__(self, ownership):
        self._ownership = ownership

    def repo_for(self, node_id):
        if node_id not in self._ownership:
            raise KeyError(node_id)
        return _Repo(self._ownership[node_id])


def test_guard_blocks_associate_node_when_disabled():
    g = _Graph({"LIB-d00001": "lib"})
    cfg = {"federation": {"write_associates": False}}
    result = _guard_associate_write(g, cfg, "LIB-d00001")
    assert result is not None
    assert result["success"] is False
    assert "read-only" in result["error"].lower()
    assert "lib" in result["error"].lower()


def test_guard_allows_primary_node():
    g = _Graph({"REQ-d00001": "primary"})
    cfg = {"federation": {"write_associates": False}}
    assert _guard_associate_write(g, cfg, "REQ-d00001") is None


def test_guard_allows_when_enabled():
    g = _Graph({"LIB-d00001": "lib"})
    cfg = {"federation": {"write_associates": True}}
    assert _guard_associate_write(g, cfg, "LIB-d00001") is None


def test_guard_ignores_unknown_node():
    g = _Graph({})
    cfg = {"federation": {"write_associates": False}}
    assert _guard_associate_write(g, cfg, "REQ-dNEW") is None


def test_guard_checks_all_ids():
    g = _Graph({"REQ-d00001": "primary", "LIB-d00001": "lib"})
    cfg = {"federation": {"write_associates": False}}
    # Edge with one associate endpoint is blocked.
    assert _guard_associate_write(g, cfg, "REQ-d00001", "LIB-d00001") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/mcp/test_associate_guard.py -v`
Expected: FAIL — `cannot import name '_guard_associate_write'`.

- [ ] **Step 3: Implement the guard helper**

In `src/elspais/mcp/server.py`, add at module level (near the other `_mutate_*` helpers, before `create_server`):

```python
def _guard_associate_write(graph, config, *node_ids: str) -> dict | None:
    """Return a read-only error dict if any node_id is associate-owned and
    associate writes are disabled; otherwise None.

    Implements: REQ-d00231-D
    """
    fed = config.get("federation", {}) if isinstance(config, dict) else {}
    if fed.get("write_associates", False):
        return None
    root = getattr(graph, "root_repo_name", None)
    for nid in node_ids:
        if not nid:
            continue
        try:
            owner = graph.repo_for(nid).name
        except (KeyError, AttributeError):
            continue  # unknown/new/structural node — not an associate
        if root is not None and owner != root:
            return {
                "success": False,
                "error": (
                    f"Associate '{owner}' is read-only "
                    f"(set federation.write_associates=true to enable mutations)"
                ),
            }
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/mcp/test_associate_guard.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Apply the guard in every mutate wrapper**

In `src/elspais/mcp/server.py`, inside `create_server`, add a guard call at the top of each `@mcp.tool()` mutate wrapper (lines ~5340-5530). Guard on the **existing target node id(s)**; for edges guard **both** endpoints. Pattern:

```python
    @mcp.tool()
    def mutate_rename_node(old_id: str, new_id: str) -> dict[str, Any]:
        """Rename a requirement's ID (e.g., REQ-d00001 -> REQ-d00010). Updates all references."""
        guard = _guard_associate_write(_state["graph"], _state["config"], old_id)
        if guard:
            return guard
        return _mutate_rename_node(_state["graph"], old_id, new_id)
```

Apply, with the indicated id(s):

| Wrapper | Guard id(s) |
|---|---|
| `mutate_rename_node` | `old_id` |
| `mutate_update_title` | `node_id` |
| `mutate_change_status` | `node_id` |
| `mutate_add_requirement` | `parent_id` (only when set) |
| `mutate_delete_requirement` | `node_id` |
| `mutate_add_assertion` | `req_id` |
| `mutate_update_assertion` | `assertion_id` |
| `mutate_delete_assertion` | `assertion_id` |
| `mutate_rename_assertion` | `old_id` |
| `mutate_add_edge` | `source_id`, `target_id` |
| `mutate_change_edge_kind` | `source_id`, `target_id` |
| `mutate_delete_edge` | `source_id`, `target_id` |
| `mutate_fix_broken_reference` | `source_id` |
| `mutate_change_edge_targets` | `source_id`, `target_id` |
| `mutate_move_node_to_file` | `node_id`, `target_file_id` |
| `mutate_rename_file` | `file_id` |

For `mutate_add_requirement`, guard conditionally (new ids won't resolve, so guarding `parent_id` is the meaningful check):

```python
        guard = _guard_associate_write(_state["graph"], _state["config"], parent_id) if parent_id else None
        if guard:
            return guard
```

- [ ] **Step 6: Surface flag state in `get_workspace_info`**

Open `_get_workspace_info` (`src/elspais/mcp/server.py:1980`). Find where it assembles the federation/associates section and add the flag state. Locate the dict it returns (search within the function for `"associates"`), and add a `federation` block read from `config`:

```python
    fed_cfg = config.get("federation", {}) if isinstance(config, dict) else {}
    # ... within the returned/assembled info dict, add:
    #   "federation": {
    #       "write_associates": fed_cfg.get("write_associates", False),
    #       "index_associates": fed_cfg.get("index_associates", False),
    #   }
```

Add the `"federation"` key to the info dict that `_get_workspace_info` returns (place it next to the existing associates info). Keep it present in the `default` and `all` detail profiles.

- [ ] **Step 7: Run MCP suites**

Run: `pytest tests/mcp/ -v -k "guard or mutate or workspace"`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
python - <<'PY'
import re, pathlib
p = pathlib.Path("pyproject.toml"); t = p.read_text()
t = re.sub(r'(version = "0\.117\.)(\d+)(")', lambda m: f'{m.group(1)}{int(m.group(2))+1}{m.group(3)}', t, count=1)
p.write_text(t)
PY
git add src/elspais/mcp/server.py tests/mcp/test_associate_guard.py pyproject.toml
git commit -m "[CUR-1419] feat(mcp): read-only guard for associate mutations + workspace flag state

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: E2E regression tests in `test_e2e_associated`

**Files:**
- Modify: `tests/<path>/test_e2e_associated.py` (locate via grep; add tests to the existing fixture)

These are the bug's acceptance assertions (associate untouched; primary INDEX count unchanged) plus the opt-in path. **ALWAYS use a sub-agent to write these tests.**

- [ ] **Step 1: Locate the fixture file and its structure**

Run: `grep -rln "test_e2e_associated\|associates" tests/ | grep e2e`
Read the file to learn its project layout (primary repo + FDA associate), how it runs `elspais` (subprocess helper), and where mutation tests are ordered (they go last).

- [ ] **Step 2: Write the regression tests (via sub-agent)**

Add these `@pytest.mark.e2e` tests, each referencing the REQs from Task 2:

```python
# Implements: REQ-d00231-B
def test_fix_does_not_mutate_associate_repo(associated_project):
    """elspais fix from the primary leaves the associate repo working tree clean."""
    # 1. ensure both repos clean
    # 2. run `elspais fix` from primary root
    # 3. assert `git -C <associate> status --porcelain` is empty
    ...

# Implements: REQ-d00231-B, REQ-d00231-C
def test_fix_index_count_unchanged_by_associate(associated_project):
    """Primary INDEX.md req count with associate configured (flags default off)
    equals the count produced with no associate configured."""
    # 1. run fix with associate configured; count REQ rows in spec/INDEX.md
    # 2. remove/disable [associates] in .elspais.toml; run fix; count again
    # 3. assert counts equal AND no associate-namespace rows in the federated run
    ...

# Implements: REQ-d00231-C
def test_index_associates_opt_in(associated_project):
    """With federation.index_associates=true, INDEX.md includes associate rows."""
    ...

# Implements: REQ-d00231-B
def test_write_associates_opt_in(associated_project):
    """With federation.write_associates=true, fix may rewrite associate spec files."""
    ...
```

The sub-agent must fill these in concretely using the fixture's existing subprocess/run helpers and assert real porcelain output and parsed row counts — no placeholders.

- [ ] **Step 3: Run the e2e tests**

Run: `pytest tests/<path>/test_e2e_associated.py -m e2e -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
python - <<'PY'
import re, pathlib
p = pathlib.Path("pyproject.toml"); t = p.read_text()
t = re.sub(r'(version = "0\.117\.)(\d+)(")', lambda m: f'{m.group(1)}{int(m.group(2))+1}{m.group(3)}', t, count=1)
p.write_text(t)
PY
git add tests/ pyproject.toml
git commit -m "[CUR-1419] test(e2e): associate read-only + primary-only INDEX regression tests

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: User-facing surfaces (mandatory per CLAUDE.md)

**Files:**
- Modify: `docs/configuration.md`
- Modify: `docs/cli/fix.md` (and `docs/cli/index.md` if present)
- Modify: `src/elspais/commands/init.py` (generated `.elspais.toml` template)
- Modify: shell completion source (locate via grep)

- [ ] **Step 1: Document the `[federation]` table in `docs/configuration.md`**

Add a section:

```markdown
## `[federation]`

Controls how associate repos affect write/generation surfaces. Reads
(`checks`, `summary`, cross-repo `Integrates:` resolution) always federate;
these flags govern only writes and generated artifacts.

| Key | Default | Effect |
|-----|---------|--------|
| `write_associates` | `false` | When false, `elspais fix` and MCP `save_mutations` write only primary-repo files; mutations targeting associate nodes are rejected read-only. |
| `index_associates` | `false` | When false, generated `INDEX.md` and `term-index.md` contain only primary-repo requirements/terms. |

With defaults, `elspais fix` produces byte-identical primary-repo files whether
or not an associate is configured.
```

- [ ] **Step 2: Note the default in `docs/cli/fix.md`**

Add a short paragraph: by default `fix` never modifies associate repos or folds their requirements into the primary `INDEX.md`/`term-index.md`; opt in via `[federation]`.

- [ ] **Step 3: Add to the init template**

In `src/elspais/commands/init.py`, find the generated `.elspais.toml` template string and add a commented `[federation]` block:

```toml
# [federation]
# write_associates = false   # allow fix/MCP to write associate repo files
# index_associates = false   # include associate reqs in INDEX.md / term-index.md
```

- [ ] **Step 4: Update shell completion**

Run: `grep -rln "associates\|cli_ttl\|completion" src/elspais/ | grep -i complet`
If a completion source lists config keys/sections, add `federation`, `write_associates`, `index_associates`.

- [ ] **Step 5: Verify docs render / no broken references**

Run: `pytest tests/ -v -k "docs or config or init"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
python - <<'PY'
import re, pathlib
p = pathlib.Path("pyproject.toml"); t = p.read_text()
t = re.sub(r'(version = "0\.117\.)(\d+)(")', lambda m: f'{m.group(1)}{int(m.group(2))+1}{m.group(3)}', t, count=1)
p.write_text(t)
PY
git add docs/ src/elspais/commands/init.py pyproject.toml
git commit -m "[CUR-1419] docs: document [federation] flags; init template + completion

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: Full verification

- [ ] **Step 1: Run the complete suite**

Run: `pytest -m ""`
Expected: all pass (unit + e2e + browser). Per project rule, run before push.

- [ ] **Step 2: Manual reproduction check (optional but recommended)**

If a two-repo sandbox is available, reproduce the original bug scenario:
- Configure an associate, ensure both repos clean, run `elspais fix` from primary.
- Confirm `git -C <associate> status` is empty and `spec/INDEX.md` count matches a no-associate run.

- [ ] **Step 3: Final state confirmation**

Run: `git log --oneline origin/main..HEAD`
Expected: one commit per task, all `[CUR-1419]`-prefixed.

---

## Self-review notes

- **Spec coverage:** -A → Task 1; -B → Tasks 3, 7; -C → Tasks 4, 5, 7; -D → Task 6. All four assertions have implementing tasks.
- **Type consistency:** new param names are consistent — `write_associates` (render_save + guard + config key), `include_associates` (`_build_index_content`, `_regenerate_index`, `_select_terms_dictionary`), `index_associates` (config key). Guard helper `_guard_associate_write(graph, config, *node_ids)`.
- **Open items the implementer must verify during execution (not placeholders — verification steps):** (1) the exact free DEV requirement id in Task 2 (`REQ-d00231` is a suggestion); (2) whether `canonical_federated_graph` actually contains an associate for the Task 4/5 unit tests — if not, fall back to the e2e coverage in Task 7; (3) exact location of the `elspais index` CLI caller of `_regenerate_index` (Task 4 Step 6); (4) the shell-completion source file (Task 8 Step 4).
