# Overview PDF Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `--overview` and `--max-depth` flags to `elspais pdf` that produce a PRD-only stakeholder document.

**Architecture:** Filter at the assembler level — `MarkdownAssembler` gains two params (`overview`, `max_depth`) that restrict which level buckets are emitted and which files pass the depth gate. No graph/parser/config changes. Associated repo nodes detected using `PatternValidator.parse()` from `utilities/patterns.py` — if `parsed.associated` is not None, the node is from an associated repo. All filtering uses graph metadata only (node IDs, levels, graph depth); file reads happen only during rendering.

**Tech Stack:** Python 3.10+, argparse, existing `MarkdownAssembler`, pytest.

---

### Task 1: Add overview filtering to MarkdownAssembler

**Files:**
- Modify: `src/elspais/pdf/assembler.py:42-96`
- Test: `tests/test_pdf_assembler.py`

**Step 1: Write the failing tests**

Add to `tests/test_pdf_assembler.py`. These tests need an expanded `_make_graph` that includes an associated-repo PRD node (with ID pattern `REQ-CAL-p00001`).

First, add a new fixture markdown and an OPS node to the helper:

```python
_OPS_DEPLOY_MD = """\
# OPS Deployment

---

# REQ-o00001: Deployment Pipeline

**Level**: OPS | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The system SHALL deploy via CI.

*End* *Deployment Pipeline* | **Hash**: ddd44444

---
"""

_ASSOC_PRD_MD = """\
# Associated Product

---

# REQ-CAL-p00001: Callisto Auth

**Level**: PRD | **Status**: Active | **Implements**: -

## Assertions

A. The associated system SHALL authenticate.

*End* *Callisto Auth* | **Hash**: eee55555

---
"""
```

Add a helper that builds an extended graph with all four levels (core PRD, OPS, DEV, associated PRD):

```python
def _make_overview_graph(base_dir: Path | None = None) -> TraceGraph:
    """Build a test graph with PRD, OPS, DEV, and associated-repo PRD."""
    graph = _make_graph(base_dir)

    if base_dir is not None:
        spec_dir = base_dir / "spec"
        (spec_dir / "ops-deploy.md").write_text(_OPS_DEPLOY_MD, encoding="utf-8")
        (spec_dir / "assoc-prd.md").write_text(_ASSOC_PRD_MD, encoding="utf-8")

    # OPS requirement (depth 1, child of PRD root)
    ops = GraphNode(
        id="REQ-o00001",
        kind=NodeKind.REQUIREMENT,
        label="Deployment Pipeline",
        source=SourceLocation(path="spec/ops-deploy.md", line=5),
    )
    ops._content = {"level": "OPS", "status": "Active", "hash": "ddd44444"}
    graph._index["REQ-o00001"] = ops
    prd = graph.find_by_id("REQ-p00001")
    prd.add_child(ops)

    # Associated-repo PRD (root, depth 0) — detected by ID pattern REQ-CAL-xxx
    assoc = GraphNode(
        id="REQ-CAL-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Callisto Auth",
        source=SourceLocation(path="spec/assoc-prd.md", line=5),
    )
    assoc._content = {"level": "PRD", "status": "Active", "hash": "eee55555"}
    graph._index["REQ-CAL-p00001"] = assoc
    graph._roots.append(assoc)

    return graph
```

Then add the test class:

```python
class TestOverviewMode:
    """Validates overview PDF filtering (PRD-only, depth-limited)."""

    def test_overview_excludes_ops_and_dev(self, tmp_path):
        """Overview mode only includes PRD-level sections."""
        graph = _make_overview_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(graph, overview=True)
        output = asm.assemble()
        assert "# Product Requirements" in output
        assert "# Operational Requirements" not in output
        assert "# Development Requirements" not in output

    def test_overview_includes_associated_prd(self, tmp_path):
        """Overview mode includes PRD from associated repos."""
        graph = _make_overview_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(graph, overview=True)
        output = asm.assemble()
        assert "Callisto Auth" in output

    def test_overview_max_depth_filters_core(self, tmp_path):
        """max_depth limits core PRD files by graph depth."""
        graph = _make_overview_graph(base_dir=tmp_path)
        # Add a depth-1 core PRD to test filtering
        prd2 = GraphNode(
            id="REQ-p00002",
            kind=NodeKind.REQUIREMENT,
            label="Child PRD",
            source=SourceLocation(path="spec/prd-auth.md", line=50),
        )
        prd2._content = {"level": "PRD", "status": "Active"}
        graph._index["REQ-p00002"] = prd2
        prd = graph.find_by_id("REQ-p00001")
        prd.add_child(prd2)

        # max_depth=1 means only depth 0
        asm = MarkdownAssembler(graph, overview=True, max_depth=1)
        output = asm.assemble()
        # Root PRD (depth 0) included
        assert "Authentication" in output
        # Associated PRD included (no depth limit on associates)
        assert "Callisto Auth" in output

    def test_overview_default_title(self, tmp_path):
        """Overview mode uses 'Product Requirements Overview' as default title."""
        graph = _make_overview_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(graph, overview=True)
        output = asm.assemble()
        assert 'title: "Product Requirements Overview"' in output

    def test_overview_custom_title_overrides(self, tmp_path):
        """Explicit title overrides the overview default."""
        graph = _make_overview_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(graph, title="My Custom", overview=True)
        output = asm.assemble()
        assert 'title: "My Custom"' in output

    def test_non_overview_unchanged(self, tmp_path):
        """Without overview flag, all levels still appear."""
        graph = _make_overview_graph(base_dir=tmp_path)
        asm = MarkdownAssembler(graph)
        output = asm.assemble()
        assert "# Product Requirements" in output
        assert "# Operational Requirements" in output
        assert "# Development Requirements" in output
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pdf_assembler.py::TestOverviewMode -v`
Expected: FAIL — `MarkdownAssembler` doesn't accept `overview` or `max_depth` params yet.

**Step 3: Implement the assembler changes**

In `src/elspais/pdf/assembler.py`:

Add import for `PatternValidator` and `PatternConfig` (at top, with other imports):

```python
from elspais.utilities.patterns import PatternConfig, PatternValidator
```

Update `__init__` (line 50-52):

```python
def __init__(
    self,
    graph: TraceGraph,
    title: str | None = None,
    overview: bool = False,
    max_depth: int | None = None,
    pattern_config: PatternConfig | None = None,
) -> None:
    self._graph = graph
    self._overview = overview
    self._max_depth = max_depth
    if title:
        self._title = title
    elif overview:
        self._title = "Product Requirements Overview"
    else:
        self._title = "Requirements Specification"
    # PatternValidator for detecting associated-repo nodes by ID
    if pattern_config is None:
        pattern_config = PatternConfig.from_dict({})
    self._pattern_validator = PatternValidator(pattern_config)
```

**Note:** This changes the `title` param from `str` default to `str | None` default. Callers currently pass `title="Requirements Specification"` explicitly from `pdf_cmd.py`, which still works. `PatternConfig.from_dict({})` gives sensible defaults.

Update `assemble()` (line 54-96) — replace the level iteration loop:

```python
# Emit each level group
if self._overview:
    levels_to_emit = ("PRD",)
else:
    levels_to_emit = ("PRD", "OPS", "DEV")

for level in levels_to_emit:
    files = level_buckets.get(level, [])
    if not files:
        continue

    # Apply max_depth filter for core files in overview mode
    if self._overview and self._max_depth is not None:
        files = self._filter_by_depth(files, file_groups)

    if not files:
        continue

    heading = _LEVEL_HEADINGS.get(level, level)
    parts.append(f"# {heading}")
    parts.append("")

    sorted_files = self._sort_files_by_depth(files, file_groups)

    for file_path in sorted_files:
        parts.extend(self._render_file(file_path))
```

Add a new helper method `_is_associated_node` and `_filter_by_depth` method after `_sort_files_by_depth` (around line 371):

```python
def _is_associated_node(self, node: GraphNode) -> bool:
    """Check if a node belongs to an associated repository.

    Uses PatternValidator.parse() to detect associated-repo IDs
    (e.g., REQ-CAL-p00001 has parsed.associated == "CAL").
    """
    parsed = self._pattern_validator.parse(node.id)
    return parsed is not None and parsed.associated is not None

def _filter_by_depth(
    self,
    file_paths: list[str],
    file_groups: dict[str, list[GraphNode]],
) -> list[str]:
    """Filter files by max depth, excluding associated-repo files from filtering.

    Associated-repo files (detected via PatternValidator) are always included.
    Core files are included only if their minimum depth < max_depth.
    All checks use graph metadata only — no file reads.
    """
    result: list[str] = []
    for path in file_paths:
        nodes = file_groups.get(path, [])
        # If any node in the file is from an associated repo, always include
        if any(self._is_associated_node(n) for n in nodes):
            result.append(path)
            continue
        # Core file: check depth
        min_depth = min(
            (self._node_depth(n) for n in nodes),
            default=999,
        )
        if min_depth < self._max_depth:
            result.append(path)
    return result
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pdf_assembler.py -v`
Expected: ALL PASS (both old and new tests).

**Step 5: Commit**

```bash
git add src/elspais/pdf/assembler.py tests/test_pdf_assembler.py
git commit -m "feat: Add overview mode to MarkdownAssembler for PRD-only PDFs"
```

---

### Task 2: Wire CLI flags and pdf_cmd

**Files:**
- Modify: `src/elspais/cli.py:771-778`
- Modify: `src/elspais/commands/pdf_cmd.py:21-76`
- Test: `tests/test_pdf_cmd.py`

**Step 1: Write the failing tests**

Add to `tests/test_pdf_cmd.py`:

```python
class TestOverviewArgs:
    """Validates --overview and --max-depth CLI argument registration."""

    def test_overview_flag_registered(self):
        """The --overview flag is available on the pdf parser."""
        from elspais.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["pdf", "--overview"])
        assert args.overview is True

    def test_overview_default_false(self):
        """The --overview flag defaults to False."""
        from elspais.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["pdf"])
        assert args.overview is False

    def test_max_depth_registered(self):
        """The --max-depth flag is available on the pdf parser."""
        from elspais.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["pdf", "--max-depth", "2"])
        assert args.max_depth == 2

    def test_max_depth_default_none(self):
        """The --max-depth flag defaults to None."""
        from elspais.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["pdf"])
        assert args.max_depth is None
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pdf_cmd.py::TestOverviewArgs -v`
Expected: FAIL — `--overview` and `--max-depth` not registered yet.

**Step 3: Implement CLI changes**

In `src/elspais/cli.py`, after the `--cover` argument (after line 777), add:

```python
    pdf_parser.add_argument(
        "--overview",
        action="store_true",
        default=False,
        help="Generate stakeholder overview (PRD requirements only, no OPS/DEV)",
    )
    pdf_parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Max graph depth for core PRDs in overview mode (0=roots only, 1=+children, ...)",
        metavar="N",
    )
```

Update the epilog examples (lines 733-739) to add overview examples:

```
Examples:
  elspais pdf                                # Generate spec-output.pdf
  elspais pdf --output review.pdf            # Custom output path
  elspais pdf --title "My Project Specs"     # Custom title
  elspais pdf --template custom.latex        # Custom LaTeX template
  elspais pdf --engine lualatex              # Use lualatex instead of xelatex
  elspais pdf --cover cover.md               # Custom cover page from Markdown file
  elspais pdf --overview                     # PRD-only stakeholder overview
  elspais pdf --overview --max-depth 2       # Overview with depth limit
```

In `src/elspais/commands/pdf_cmd.py`, update the assembler instantiation (lines 59-62).
The config dict is already loaded by `build_graph` internally, but we need it for `PatternConfig`.
Load config explicitly and pass pattern_config through:

```python
    from elspais.config import get_config
    from elspais.utilities.patterns import PatternConfig

    config = get_config(config_path, repo_root)
    pattern_config = PatternConfig.from_dict(config.get("patterns", {}))

    title = getattr(args, "title", None)
    cover = getattr(args, "cover", None)
    overview = getattr(args, "overview", False)
    max_depth = getattr(args, "max_depth", None)
    assembler = MarkdownAssembler(
        graph, title=title, overview=overview, max_depth=max_depth,
        pattern_config=pattern_config,
    )
    markdown_content = assembler.assemble()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pdf_cmd.py tests/test_pdf_assembler.py -v`
Expected: ALL PASS.

**Step 5: Commit**

```bash
git add src/elspais/cli.py src/elspais/commands/pdf_cmd.py tests/test_pdf_cmd.py
git commit -m "feat: Wire --overview and --max-depth flags to elspais pdf command"
```

---

### Task 3: Update CLI documentation

**Files:**
- Modify: `docs/cli/commands.md`

**Step 1: Add pdf section to commands.md**

After the `## changed` section (line 125) or at the end before `## index`, add:

```markdown
## pdf

Compile spec files into a PDF document.

  $ elspais pdf                              # Generate spec-output.pdf
  $ elspais pdf --output review.pdf          # Custom output path
  $ elspais pdf --title "My Project Specs"   # Custom title
  $ elspais pdf --overview                   # PRD-only stakeholder overview
  $ elspais pdf --overview --max-depth 2     # Overview with depth limit

**Options:**

  `--output PATH`       Output PDF file path (default: spec-output.pdf)
  `--engine ENGINE`     PDF engine: xelatex (default), lualatex, pdflatex
  `--template PATH`     Custom pandoc LaTeX template
  `--title TITLE`       Document title
  `--cover PATH`        Markdown file for custom cover page
  `--overview`          Generate stakeholder overview (PRD only, no OPS/DEV)
  `--max-depth N`       Max graph depth for core PRDs in overview mode

**Prerequisites:**

  pandoc:   https://pandoc.org/installing.html
  xelatex:  Install TeX Live, MiKTeX, or MacTeX

**Overview Mode:**

  Generates a lighter document for stakeholders:
  - Only PRD-level requirements from all repos
  - No OPS or DEV requirements
  - Default title: "Product Requirements Overview"
  - `--max-depth` limits core PRD depth (associates always fully included)
```

**Step 2: Commit**

```bash
git add docs/cli/commands.md
git commit -m "docs: Add pdf command with overview flags to CLI reference"
```

---

### Task 4: Run full test suite

**Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: ALL PASS — no regressions.

**Step 2: Verify no import errors with overview mode**

Run: `python -c "from elspais.pdf.assembler import MarkdownAssembler; print('OK')"`
Expected: `OK`
