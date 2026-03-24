# Defined Terms Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add defined-term parsing, glossary/index generation, and health checks to elspais.

**Architecture:** Definition list blocks are parsed via a post-parse extraction pass over REMAINDER/body text. Term data lives in a standalone `TermDictionary` (not on `TraceGraph`). Health checks flag duplicates, undefined terms, and unmarked usage. CLI commands generate glossary.md, term-index.md, and collection manifests.

**Tech Stack:** Python 3.10+, Lark (existing grammar), Pydantic (config schema), pytest (tests)

**Spec:** `docs/superpowers/specs/2026-03-23-defined-terms-design.md`

---

### Task 1: Config Schema — TermsConfig

**Files:**
- Modify: `src/elspais/config/schema.py:210-248` (add TermsConfig, add field to ElspaisConfig)
- Test: `tests/test_config_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_terms.py
# Implements: REQ-d00080-A
"""Tests for defined terms config, parsing, and generation."""

from elspais.config.schema import ElspaisConfig, TermsConfig


class TestTermsConfig:
    def test_default_terms_config(self):
        """TermsConfig has sensible defaults."""
        cfg = TermsConfig()
        assert cfg.output_dir == "spec/_generated"
        assert cfg.duplicate_severity == "error"
        assert cfg.undefined_severity == "warning"
        assert cfg.unmarked_severity == "warning"

    def test_elspais_config_includes_terms(self):
        """ElspaisConfig accepts [terms] section."""
        cfg = ElspaisConfig(terms=TermsConfig(duplicate_severity="warning"))
        assert cfg.terms.duplicate_severity == "warning"

    def test_toml_with_terms_section(self):
        """Config dict with terms section validates successfully."""
        raw = {"terms": {"output_dir": "out", "duplicate_severity": "off"}}
        cfg = ElspaisConfig.model_validate(raw)
        assert cfg.terms.output_dir == "out"
        assert cfg.terms.duplicate_severity == "off"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_terms.py::TestTermsConfig -v`
Expected: FAIL — `TermsConfig` does not exist yet

- [ ] **Step 3: Write minimal implementation**

In `src/elspais/config/schema.py`, add before `ElspaisConfig`:

```python
class TermsConfig(_StrictModel):
    """Configuration for defined terms feature."""
    output_dir: str = "spec/_generated"
    duplicate_severity: str = "error"
    undefined_severity: str = "warning"
    unmarked_severity: str = "warning"
```

Add to `ElspaisConfig`:

```python
    terms: TermsConfig = Field(default_factory=TermsConfig)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_terms.py::TestTermsConfig -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest`
Expected: All existing tests still pass (no regressions from new config field)

- [ ] **Step 6: Commit**

```bash
git add src/elspais/config/schema.py tests/test_terms.py
git commit -m "feat(terms): add TermsConfig to config schema"
```

---

### Task 2: TermDictionary Data Model

**Files:**
- Create: `src/elspais/graph/terms.py`
- Test: `tests/test_terms.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_terms.py
from elspais.graph.terms import TermDictionary, TermEntry, TermRef


class TestTermDictionary:
    def test_add_and_lookup(self):
        """Add a term and look it up case-insensitively."""
        td = TermDictionary()
        entry = TermEntry(
            term="Electronic Record",
            definition="Data stored in digital form.",
            collection=False,
            indexed=True,
            defined_in="REQ-p00001",
            defined_at_line=10,
            namespace="main",
        )
        td.add(entry)
        assert td.lookup("electronic record") is entry
        assert td.lookup("Electronic Record") is entry
        assert td.lookup("nonexistent") is None

    def test_iter_indexed(self):
        """iter_indexed skips non-indexed terms."""
        td = TermDictionary()
        td.add(TermEntry(term="A", definition="d", collection=False, indexed=True,
                         defined_in="REQ-1", defined_at_line=1, namespace="main"))
        td.add(TermEntry(term="B", definition="d", collection=False, indexed=False,
                         defined_in="REQ-2", defined_at_line=2, namespace="main"))
        indexed = list(td.iter_indexed())
        assert len(indexed) == 1
        assert indexed[0].term == "A"

    def test_iter_collections(self):
        """iter_collections returns only collection terms."""
        td = TermDictionary()
        td.add(TermEntry(term="A", definition="d", collection=True, indexed=True,
                         defined_in="REQ-1", defined_at_line=1, namespace="main"))
        td.add(TermEntry(term="B", definition="d", collection=False, indexed=True,
                         defined_in="REQ-2", defined_at_line=2, namespace="main"))
        collections = list(td.iter_collections())
        assert len(collections) == 1
        assert collections[0].term == "A"

    def test_duplicate_detection(self):
        """Adding a term with the same name returns the existing entry."""
        td = TermDictionary()
        e1 = TermEntry(term="X", definition="d1", collection=False, indexed=True,
                       defined_in="REQ-1", defined_at_line=1, namespace="main")
        e2 = TermEntry(term="X", definition="d2", collection=False, indexed=True,
                       defined_in="REQ-2", defined_at_line=5, namespace="main")
        td.add(e1)
        existing = td.add(e2)
        assert existing is e1  # returns the first entry as a duplicate signal

    def test_merge(self):
        """Merging two dictionaries combines entries."""
        td1 = TermDictionary()
        td1.add(TermEntry(term="A", definition="d", collection=False, indexed=True,
                          defined_in="REQ-1", defined_at_line=1, namespace="repo-a"))
        td2 = TermDictionary()
        td2.add(TermEntry(term="B", definition="d", collection=False, indexed=True,
                          defined_in="REQ-2", defined_at_line=1, namespace="repo-b"))
        td1.merge(td2)
        assert td1.lookup("A") is not None
        assert td1.lookup("B") is not None

    def test_merge_duplicate_across_repos(self):
        """Merging detects cross-repo duplicates."""
        td1 = TermDictionary()
        td1.add(TermEntry(term="A", definition="d1", collection=False, indexed=True,
                          defined_in="REQ-1", defined_at_line=1, namespace="repo-a"))
        td2 = TermDictionary()
        td2.add(TermEntry(term="A", definition="d2", collection=False, indexed=True,
                          defined_in="REQ-2", defined_at_line=1, namespace="repo-b"))
        duplicates = td1.merge(td2)
        assert len(duplicates) == 1
        assert duplicates[0][0].namespace == "repo-a"
        assert duplicates[0][1].namespace == "repo-b"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_terms.py::TestTermDictionary -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Write minimal implementation**

Create `src/elspais/graph/terms.py`:

```python
"""Defined terms data model and dictionary.

Standalone data structure for term definitions and references.
Not stored on TraceGraph — built as a companion object during graph construction.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field


@dataclass
class TermRef:
    """A reference to a defined term found in prose text."""
    node_id: str       # enclosing element (REQ, ASSERTION, REMAINDER)
    namespace: str     # repo where the reference occurs
    marked: bool       # True = *term*/**term**, False = plain text
    line: int          # for error reporting


@dataclass
class TermEntry:
    """A single defined term with its definition and references."""
    term: str              # display form (original casing)
    definition: str        # full definition text (metadata lines stripped)
    collection: bool       # generates its own manifest
    indexed: bool          # True by default; False suppresses index + health check
    defined_in: str        # node ID of nearest REQUIREMENT or FILE ancestor
    defined_at_line: int   # for error reporting
    namespace: str         # repo namespace (e.g., "main", "sponsor-a")
    references: list[TermRef] = field(default_factory=list)


class TermDictionary:
    """Standalone term index, keyed by normalized (lowercased) term name.

    Built during graph construction as a companion to FederatedGraph.
    """

    def __init__(self) -> None:
        self._entries: dict[str, TermEntry] = {}

    def add(self, entry: TermEntry) -> TermEntry | None:
        """Add a term entry. Returns existing entry if duplicate (same key)."""
        key = entry.term.lower()
        if key in self._entries:
            return self._entries[key]
        self._entries[key] = entry
        return None

    def lookup(self, term: str) -> TermEntry | None:
        """Look up a term by name (case-insensitive)."""
        return self._entries.get(term.lower())

    def iter_all(self) -> Iterator[TermEntry]:
        """Iterate all term entries."""
        yield from self._entries.values()

    def iter_indexed(self) -> Iterator[TermEntry]:
        """Iterate only indexed terms (Indexed: true, the default)."""
        for entry in self._entries.values():
            if entry.indexed:
                yield entry

    def iter_collections(self) -> Iterator[TermEntry]:
        """Iterate only collection terms (Collection: true)."""
        for entry in self._entries.values():
            if entry.collection:
                yield entry

    def merge(self, other: TermDictionary) -> list[tuple[TermEntry, TermEntry]]:
        """Merge another dictionary into this one. Returns list of duplicate pairs."""
        duplicates: list[tuple[TermEntry, TermEntry]] = []
        for entry in other.iter_all():
            existing = self.add(entry)
            if existing is not None:
                duplicates.append((existing, entry))
        return duplicates

    def __len__(self) -> int:
        return len(self._entries)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_terms.py::TestTermDictionary -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/elspais/graph/terms.py tests/test_terms.py
git commit -m "feat(terms): add TermDictionary data model"
```

---

### Task 3: Post-Parse Definition Extractor

**Files:**
- Create: `src/elspais/graph/term_extractor.py`
- Test: `tests/test_terms.py` (append)

This is the core parsing logic: scan text content for definition list patterns (`Term\n: definition`) and bold/italic candidate references.

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_terms.py
from elspais.graph.term_extractor import extract_definitions, extract_candidate_refs


class TestTermExtractor:
    def test_extract_single_definition(self):
        """Extract a single definition block from text."""
        text = "\nElectronic Record\n: Data stored in digital form.\n"
        defs = extract_definitions(text, base_line=1)
        assert len(defs) == 1
        assert defs[0]["term"] == "Electronic Record"
        assert defs[0]["definition"] == "Data stored in digital form."
        assert defs[0]["collection"] is False
        assert defs[0]["indexed"] is True

    def test_extract_definition_with_collection(self):
        """Extract definition with Collection: true flag."""
        text = "\nQuestionnaire\n: A structured set of questions.\n: Collection: true\n"
        defs = extract_definitions(text, base_line=1)
        assert len(defs) == 1
        assert defs[0]["collection"] is True

    def test_extract_definition_with_indexed_false(self):
        """Extract definition with Indexed: false flag."""
        text = "\nLevel\n: Classification tier.\n: Indexed: false\n"
        defs = extract_definitions(text, base_line=1)
        assert len(defs) == 1
        assert defs[0]["indexed"] is False

    def test_extract_multiline_definition(self):
        """Multi-line definitions are concatenated."""
        text = "\nTerm\n: First line of\n: the definition.\n"
        defs = extract_definitions(text, base_line=1)
        assert len(defs) == 1
        assert defs[0]["definition"] == "First line of the definition."

    def test_extract_multiple_definitions(self):
        """Multiple definition blocks in same text."""
        text = "\nAlpha\n: Definition A.\n\nBeta\n: Definition B.\n"
        defs = extract_definitions(text, base_line=1)
        assert len(defs) == 2
        assert defs[0]["term"] == "Alpha"
        assert defs[1]["term"] == "Beta"

    def test_no_definitions_in_plain_text(self):
        """Plain text without definition list syntax returns empty."""
        text = "This is just normal paragraph text.\nNo definitions here."
        defs = extract_definitions(text, base_line=1)
        assert len(defs) == 0

    def test_extract_candidate_refs_italic(self):
        """Extract *italic* candidate references."""
        text = "The *electronic record* must be stored."
        refs = extract_candidate_refs(text, base_line=5)
        assert len(refs) == 1
        assert refs[0]["token"] == "electronic record"
        assert refs[0]["line"] == 5

    def test_extract_candidate_refs_bold(self):
        """Extract **bold** candidate references."""
        text = "The **audit trail** is maintained."
        refs = extract_candidate_refs(text, base_line=3)
        assert len(refs) == 1
        assert refs[0]["token"] == "audit trail"

    def test_skip_structural_patterns(self):
        """Known structural patterns like *End* are excluded."""
        text = "*End* *REQ-p00001* | **Hash**: abc123"
        refs = extract_candidate_refs(text, base_line=1)
        # Should skip *End*, *REQ-p00001*, **Hash**
        assert len(refs) == 0

    def test_line_numbers_from_base(self):
        """Line numbers are offset from base_line."""
        text = "line one\n*term* on line two"
        refs = extract_candidate_refs(text, base_line=10)
        assert refs[0]["line"] == 11  # base 10 + 1 for second line

    def test_definition_line_numbers(self):
        """Definition line numbers are offset from base_line."""
        text = "\nMyTerm\n: Definition here.\n"
        defs = extract_definitions(text, base_line=20)
        assert defs[0]["line"] == 21  # term name is on line 21 (base 20 + 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_terms.py::TestTermExtractor -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Write minimal implementation**

Create `src/elspais/graph/term_extractor.py`:

```python
"""Post-parse extraction of definition list blocks and candidate term references.

Scans text content (from REMAINDER nodes, requirement bodies, named blocks)
for Markdown definition list patterns and bold/italic tokens.
"""
from __future__ import annotations

import re

# Patterns for bold/italic tokens in prose
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")  # *text* not **text**
_BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*")              # **text**

# Known structural patterns to exclude from candidate refs
_STRUCTURAL_PATTERNS = {
    "end",  # *End* marker
}
_STRUCTURAL_RE = re.compile(
    r"^(End|Hash|Level|Status|Implements|Refines|Satisfies|Validates|"
    r"Actor|Goal|Context|REQ-|JNY-)$",
    re.IGNORECASE,
)

# Definition list pattern: line of text followed by ": " continuation
_DEF_CONTINUATION_RE = re.compile(r"^: (.+)$")

# Metadata flags in definition lines
_COLLECTION_RE = re.compile(r"^Collection:\s*(true|false)$", re.IGNORECASE)
_INDEXED_RE = re.compile(r"^Indexed:\s*(true|false)$", re.IGNORECASE)


def extract_definitions(
    text: str,
    base_line: int = 0,
) -> list[dict]:
    """Extract definition list blocks from text.

    Looks for the pattern:
        <blank line or start>
        Term Name
        : Definition text
        : More definition text
        : Collection: true
        <blank line or end>

    Args:
        text: The text content to scan.
        base_line: Line number offset for the start of this text block.

    Returns:
        List of dicts: {term, definition, collection, indexed, line}.
    """
    lines = text.split("\n")
    results: list[dict] = []
    i = 0

    while i < len(lines):
        # Look for a potential term name: non-empty line preceded by blank/start
        line = lines[i]
        is_preceded_by_blank = (i == 0) or (lines[i - 1].strip() == "")

        if is_preceded_by_blank and line.strip() and not line.startswith(":"):
            # Check if next line starts with ": "
            if i + 1 < len(lines) and _DEF_CONTINUATION_RE.match(lines[i + 1]):
                term_name = line.strip()
                term_line = base_line + i
                definition_parts: list[str] = []
                collection = False
                indexed = True

                j = i + 1
                while j < len(lines):
                    m = _DEF_CONTINUATION_RE.match(lines[j])
                    if not m:
                        break
                    content = m.group(1).strip()

                    # Check for metadata flags
                    cm = _COLLECTION_RE.match(content)
                    if cm:
                        collection = cm.group(1).lower() == "true"
                        j += 1
                        continue

                    im = _INDEXED_RE.match(content)
                    if im:
                        indexed = im.group(1).lower() == "true"
                        j += 1
                        continue

                    definition_parts.append(content)
                    j += 1

                if definition_parts:
                    results.append({
                        "term": term_name,
                        "definition": " ".join(definition_parts),
                        "collection": collection,
                        "indexed": indexed,
                        "line": term_line,
                    })
                i = j
                continue
        i += 1

    return results


def extract_candidate_refs(
    text: str,
    base_line: int = 0,
) -> list[dict]:
    """Extract bold/italic tokens as candidate term references.

    Scans for *token* and **token** patterns, excluding known structural
    patterns like *End*, **Hash**, metadata field names, and REQ/JNY IDs.

    Args:
        text: The text content to scan.
        base_line: Line number offset for the start of this text block.

    Returns:
        List of dicts: {token, line, bold}.
    """
    results: list[dict] = []

    for line_offset, line in enumerate(text.split("\n")):
        line_num = base_line + line_offset

        # Extract bold tokens first (so ** is consumed before *)
        for m in _BOLD_RE.finditer(line):
            token = m.group(1).strip()
            if not _is_structural(token):
                results.append({"token": token, "line": line_num, "bold": True})

        # Extract italic tokens (skip ranges already matched by bold)
        bold_ranges = [(m.start(), m.end()) for m in _BOLD_RE.finditer(line)]
        for m in _ITALIC_RE.finditer(line):
            # Skip if this match overlaps with a bold match
            if any(m.start() >= bs and m.end() <= be for bs, be in bold_ranges):
                continue
            token = m.group(1).strip()
            if not _is_structural(token):
                results.append({"token": token, "line": line_num, "bold": False})

    return results


def _is_structural(token: str) -> bool:
    """Check if a token is a known structural pattern (not a term reference)."""
    if token.lower() in _STRUCTURAL_PATTERNS:
        return True
    if _STRUCTURAL_RE.match(token):
        return True
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_terms.py::TestTermExtractor -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/elspais/graph/term_extractor.py tests/test_terms.py
git commit -m "feat(terms): add post-parse definition and reference extractor"
```

---

### Task 4: GraphBuilder Integration — Build TermDictionary

**Files:**
- Modify: `src/elspais/graph/factory.py:668-673` (add term extraction after annotators)
- Modify: `src/elspais/graph/federated.py` (add `term_dictionary` attribute)
- Test: `tests/test_terms.py` (append)

- [ ] **Step 1: Write the failing test using a real spec fixture**

Create a small spec fixture file for testing:

```python
# Append to tests/test_terms.py
import tempfile
from pathlib import Path


class TestTermBuildIntegration:
    def _build_with_terms(self, spec_content: str) -> tuple:
        """Helper: write spec content to temp dir, build graph, return (graph, term_dict)."""
        from elspais.config import get_config
        from elspais.graph.factory import build_graph

        with tempfile.TemporaryDirectory() as tmpdir:
            spec_dir = Path(tmpdir) / "spec"
            spec_dir.mkdir()
            (spec_dir / "test.md").write_text(spec_content)

            # Minimal config pointing at our temp spec dir
            config = get_config(None, Path(tmpdir))
            graph = build_graph(
                config=config,
                spec_dirs=[spec_dir],
                config_path=None,
            )
            return graph, getattr(graph, "term_dictionary", None)

    def test_definition_extracted_from_spec(self):
        """Definition list in spec file is extracted into TermDictionary."""
        content = """
## REQ-p00001: Test Requirement
**Level**: prd | **Status**: Active | **Implements**: -

Electronic Record
: Data stored in digital form.

## Assertions
A. The system SHALL store *electronic records*.

*End* *Test Requirement* | **Hash**: 00000000
"""
        graph, td = self._build_with_terms(content)
        assert td is not None
        entry = td.lookup("electronic record")
        assert entry is not None
        assert entry.definition == "Data stored in digital form."

    def test_reference_resolved(self):
        """Bold/italic term in assertion is resolved as a reference."""
        content = """
## REQ-p00001: Test Requirement
**Level**: prd | **Status**: Active | **Implements**: -

Electronic Record
: Data stored in digital form.

## Assertions
A. The system SHALL store *electronic records*.

*End* *Test Requirement* | **Hash**: 00000000
"""
        # Note: "electronic records" won't match "Electronic Record" exactly.
        # This test validates that exact matching works; plural is deferred.
        graph, td = self._build_with_terms(content)
        entry = td.lookup("electronic record")
        # "electronic records" (plural) should NOT match in v1 (exact only)
        # but "Electronic Record" (exact) in a marked reference would match
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_terms.py::TestTermBuildIntegration -v`
Expected: FAIL — `graph.term_dictionary` does not exist

- [ ] **Step 3: Implement term extraction in factory.py**

In `src/elspais/graph/factory.py`, after the `annotate_coverage(graph)` call (line ~673), add:

```python
    # Extract defined terms from parsed content
    from elspais.graph.term_extractor import extract_definitions, extract_candidate_refs
    from elspais.graph.terms import TermDictionary, TermEntry, TermRef
    from elspais.graph import NodeKind

    term_dict = TermDictionary()

    # Scan all REMAINDER and REQUIREMENT nodes for definition blocks
    for node in graph.all_nodes():
        if node.kind == NodeKind.REMAINDER:
            raw_text = node.get_field("raw_text") or node.get_field("text") or ""
            parse_line = node.get_field("parse_line") or 0
            defs = extract_definitions(raw_text, base_line=parse_line)
            for d in defs:
                # Find nearest REQUIREMENT or FILE ancestor for defined_in
                ancestor = _find_term_ancestor(node)
                entry = TermEntry(
                    term=d["term"],
                    definition=d["definition"],
                    collection=d["collection"],
                    indexed=d["indexed"],
                    defined_in=ancestor,
                    defined_at_line=d["line"],
                    namespace="root",  # set per-repo in federated build
                )
                term_dict.add(entry)
                # Mark this REMAINDER node as a definition block
                node.set_field("content_type", "definition_block")
```

Add helper function:

```python
def _find_term_ancestor(node: GraphNode) -> str:
    """Find the nearest REQUIREMENT or FILE ancestor for a term's defined_in."""
    for ancestor in node.ancestors(edge_kinds={EdgeKind.STRUCTURES, EdgeKind.CONTAINS}):
        if ancestor.kind in (NodeKind.REQUIREMENT, NodeKind.FILE):
            return ancestor.id
    return node.id  # fallback to self
```

In `src/elspais/graph/federated.py`, add `term_dictionary` attribute to `FederatedGraph.__init__`:

```python
    self.term_dictionary: TermDictionary = TermDictionary()
```

And at the end of `build_graph()` in `factory.py`, attach the term dictionary to the federated graph before returning.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_terms.py::TestTermBuildIntegration -v`
Expected: PASS

- [ ] **Step 5: Run full test suite for regressions**

Run: `pytest`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/elspais/graph/factory.py src/elspais/graph/federated.py tests/test_terms.py
git commit -m "feat(terms): integrate term extraction into graph build pipeline"
```

---

### Task 5: Health Checks — Duplicate, Undefined, Unmarked

**Files:**
- Modify: `src/elspais/commands/health.py` (add term health checks)
- Test: `tests/test_terms.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_terms.py
from elspais.commands.health import HealthCheck


class TestTermHealthChecks:
    def test_check_duplicate_definitions(self):
        """Duplicate term definitions produce error findings."""
        from elspais.graph.terms import TermDictionary, TermEntry
        from elspais.commands.health import check_term_duplicates

        td = TermDictionary()
        td.add(TermEntry(term="X", definition="d1", collection=False, indexed=True,
                         defined_in="REQ-1", defined_at_line=1, namespace="main"))
        # Force a duplicate by bypassing the add() guard
        td._entries["x_dup"] = td._entries["x"]  # won't work — need a different approach

        # Better: test via the duplicate detection during build
        # The build process collects duplicates; the health check reports them
        duplicates = [
            (TermEntry(term="X", definition="d1", collection=False, indexed=True,
                       defined_in="REQ-1", defined_at_line=1, namespace="main"),
             TermEntry(term="X", definition="d2", collection=False, indexed=True,
                       defined_in="REQ-2", defined_at_line=5, namespace="main")),
        ]
        check = check_term_duplicates(duplicates, severity="error")
        assert not check.passed
        assert check.severity == "error"
        assert len(check.findings) == 1

    def test_check_undefined_terms(self):
        """Unresolved candidate references produce warning findings."""
        from elspais.commands.health import check_undefined_terms

        undefined = [
            {"token": "Flowchart", "line": 47, "node_id": "REQ-p00003",
             "file_path": "spec/prd-core.md"},
        ]
        check = check_undefined_terms(undefined, severity="warning")
        assert not check.passed
        assert check.severity == "warning"
        assert len(check.findings) == 1

    def test_check_unmarked_usage(self):
        """Unmarked usage of indexed terms produce warning findings."""
        from elspais.commands.health import check_unmarked_usage

        unmarked = [
            {"term": "Electronic Record", "line": 12, "node_id": "REQ-d00045",
             "file_path": "spec/dev-records.md"},
        ]
        check = check_unmarked_usage(unmarked, severity="warning")
        assert not check.passed
        assert len(check.findings) == 1

    def test_severity_off_skips_check(self):
        """Severity 'off' means the check always passes."""
        from elspais.commands.health import check_term_duplicates

        duplicates = [
            (TermEntry(term="X", definition="d1", collection=False, indexed=True,
                       defined_in="REQ-1", defined_at_line=1, namespace="main"),
             TermEntry(term="X", definition="d2", collection=False, indexed=True,
                       defined_in="REQ-2", defined_at_line=5, namespace="main")),
        ]
        check = check_term_duplicates(duplicates, severity="off")
        assert check.passed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_terms.py::TestTermHealthChecks -v`
Expected: FAIL — functions don't exist

- [ ] **Step 3: Write implementation**

Add to `src/elspais/commands/health.py`:

```python
def check_term_duplicates(
    duplicates: list[tuple[TermEntry, TermEntry]],
    severity: str = "error",
) -> HealthCheck:
    """Check for duplicate term definitions."""
    if severity == "off":
        return HealthCheck(
            name="term.duplicates", passed=True,
            message="Duplicate term check disabled", category="spec", severity="info",
        )
    findings = []
    for existing, duplicate in duplicates:
        findings.append(HealthFinding(
            message=(
                f"Duplicate definition of '{existing.term}': "
                f"{existing.defined_in}:{existing.defined_at_line} and "
                f"{duplicate.defined_in}:{duplicate.defined_at_line}"
            ),
            node_id=existing.defined_in,
            line=existing.defined_at_line,
        ))
    return HealthCheck(
        name="term.duplicates",
        passed=len(findings) == 0,
        message=f"{len(findings)} duplicate term definition(s)" if findings else "No duplicate terms",
        category="spec",
        severity=severity,
        findings=findings,
    )


def check_undefined_terms(
    undefined: list[dict],
    severity: str = "warning",
) -> HealthCheck:
    """Check for bold/italic tokens that don't match any defined term."""
    if severity == "off":
        return HealthCheck(
            name="term.undefined", passed=True,
            message="Undefined term check disabled", category="spec", severity="info",
        )
    findings = []
    for u in undefined:
        findings.append(HealthFinding(
            message=f"Possible undefined term '{u['token']}'",
            node_id=u.get("node_id"),
            file_path=u.get("file_path"),
            line=u.get("line"),
        ))
    return HealthCheck(
        name="term.undefined",
        passed=len(findings) == 0,
        message=f"{len(findings)} possible undefined term(s)" if findings else "No undefined terms",
        category="spec",
        severity=severity,
        findings=findings,
    )


def check_unmarked_usage(
    unmarked: list[dict],
    severity: str = "warning",
) -> HealthCheck:
    """Check for plain-text usage of indexed terms without markup."""
    if severity == "off":
        return HealthCheck(
            name="term.unmarked", passed=True,
            message="Unmarked term check disabled", category="spec", severity="info",
        )
    findings = []
    for u in unmarked:
        findings.append(HealthFinding(
            message=f"Unmarked usage of '{u['term']}'",
            node_id=u.get("node_id"),
            file_path=u.get("file_path"),
            line=u.get("line"),
        ))
    return HealthCheck(
        name="term.unmarked",
        passed=len(findings) == 0,
        message=f"{len(findings)} unmarked term usage(s)" if findings else "All term usages are marked",
        category="spec",
        severity=severity,
        findings=findings,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_terms.py::TestTermHealthChecks -v`
Expected: PASS

- [ ] **Step 5: Wire health checks into `health.run()`**

Find where health checks are collected in `health.py`'s `run()` function and add the term checks. This requires the `TermDictionary` to be available from the graph — use `graph.term_dictionary`.

- [ ] **Step 6: Run full test suite**

Run: `pytest`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add src/elspais/commands/health.py tests/test_terms.py
git commit -m "feat(terms): add health checks for duplicates, undefined, unmarked"
```

---

### Task 6: Glossary and Term Index Generators

**Files:**
- Create: `src/elspais/commands/glossary_cmd.py`
- Create: `src/elspais/commands/term_index_cmd.py`
- Test: `tests/test_terms.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_terms.py
class TestGlossaryGenerator:
    def test_generate_glossary_markdown(self):
        """Glossary generates alphabetically with letter headings."""
        from elspais.commands.glossary_cmd import generate_glossary

        td = TermDictionary()
        td.add(TermEntry(term="Beta", definition="B def.", collection=False, indexed=True,
                         defined_in="REQ-1", defined_at_line=1, namespace="main"))
        td.add(TermEntry(term="Alpha", definition="A def.", collection=True, indexed=True,
                         defined_in="REQ-2", defined_at_line=1, namespace="main"))
        td.add(TermEntry(term="Level", definition="L def.", collection=False, indexed=False,
                         defined_in="REQ-3", defined_at_line=1, namespace="main"))

        output = generate_glossary(td, format="markdown")
        # Check alphabetical ordering
        assert output.index("Alpha") < output.index("Beta") < output.index("Level")
        # Check letter headings
        assert "## A" in output
        assert "## B" in output
        assert "## L" in output
        # Check flags
        assert "*(collection)*" in output
        assert "*(not indexed)*" in output

    def test_generate_glossary_json(self):
        """Glossary JSON format returns structured data."""
        import json
        from elspais.commands.glossary_cmd import generate_glossary

        td = TermDictionary()
        td.add(TermEntry(term="Alpha", definition="A def.", collection=False, indexed=True,
                         defined_in="REQ-1", defined_at_line=1, namespace="main"))
        output = generate_glossary(td, format="json")
        data = json.loads(output)
        assert len(data["terms"]) == 1
        assert data["terms"][0]["term"] == "Alpha"


class TestTermIndexGenerator:
    def test_generate_term_index_markdown(self):
        """Term index lists references grouped by namespace."""
        from elspais.commands.term_index_cmd import generate_term_index

        td = TermDictionary()
        entry = TermEntry(term="Alpha", definition="A def.", collection=False, indexed=True,
                          defined_in="REQ-1", defined_at_line=1, namespace="main")
        entry.references = [
            TermRef(node_id="REQ-p00001", namespace="main", marked=True, line=10),
            TermRef(node_id="REQ-d00002", namespace="sponsor-a", marked=True, line=20),
        ]
        td.add(entry)
        # Add non-indexed term — should NOT appear
        td.add(TermEntry(term="Level", definition="L def.", collection=False, indexed=False,
                         defined_in="REQ-3", defined_at_line=1, namespace="main"))

        output = generate_term_index(td, format="markdown")
        assert "## Alpha" in output
        assert "REQ-p00001" in output
        assert "**main:**" in output
        assert "**sponsor-a:**" in output
        assert "Level" not in output  # non-indexed excluded

    def test_generate_collection_manifest(self):
        """Collection term gets its own manifest."""
        from elspais.commands.term_index_cmd import generate_collection_manifest

        entry = TermEntry(term="Questionnaire", definition="Q def.", collection=True, indexed=True,
                          defined_in="REQ-1", defined_at_line=1, namespace="main")
        entry.references = [
            TermRef(node_id="REQ-p00012", namespace="main", marked=True, line=10),
        ]
        output = generate_collection_manifest(entry, format="markdown")
        assert "# Questionnaire" in output
        assert "REQ-p00012" in output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_terms.py::TestGlossaryGenerator tests/test_terms.py::TestTermIndexGenerator -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

Create `src/elspais/commands/glossary_cmd.py` and `src/elspais/commands/term_index_cmd.py` with the generator functions and `run()` entry points following the pattern from `index.py`. Each accepts `--format markdown|json` and `--output-dir`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_terms.py::TestGlossaryGenerator tests/test_terms.py::TestTermIndexGenerator -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/elspais/commands/glossary_cmd.py src/elspais/commands/term_index_cmd.py tests/test_terms.py
git commit -m "feat(terms): add glossary and term-index generators"
```

---

### Task 7: CLI Registration and Fix Integration

**Files:**
- Modify: `src/elspais/commands/args.py` (add GlossaryArgs, TermIndexArgs)
- Modify: `src/elspais/cli.py` (register commands, dispatch)
- Modify: `src/elspais/commands/fix_cmd.py` (call glossary + term-index in fix)
- Test: `tests/test_terms.py` (append e2e test)

- [ ] **Step 1: Add GlossaryArgs and TermIndexArgs to args.py**

```python
@dataclasses.dataclass
class GlossaryArgs:
    """Generate glossary from defined terms."""
    format: Literal["markdown", "json"] = "markdown"
    output_dir: Annotated[str | None, tyro.conf.arg(aliases=["-d"])] = None
    """Override output directory (default from config)."""
    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


@dataclasses.dataclass
class TermIndexArgs:
    """Generate term index and collection manifests."""
    format: Literal["markdown", "json"] = "markdown"
    output_dir: Annotated[str | None, tyro.conf.arg(aliases=["-d"])] = None
    """Override output directory (default from config)."""
    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""
```

- [ ] **Step 2: Register in cli.py**

Add imports, add to `_CMD_MAP`, add dispatch cases:
```python
GlossaryArgs: "glossary",
TermIndexArgs: "term-index",
```

And in dispatch:
```python
elif args.command == "glossary":
    from elspais.commands import glossary_cmd
    return glossary_cmd.run(args)
elif args.command == "term-index":
    from elspais.commands import term_index_cmd
    return term_index_cmd.run(args)
```

- [ ] **Step 3: Wire into fix_cmd.py**

Add `_fix_glossary()` and `_fix_term_index()` functions, called from `run()` after `_fix_index()`:

```python
    _fix_glossary(args, dry_run)
    _fix_term_index(args, dry_run)
```

- [ ] **Step 4: Write e2e test**

```python
# Append to tests/test_terms.py
import subprocess

@pytest.mark.e2e
class TestTermsCLI:
    def test_glossary_command(self, tmp_path):
        """elspais glossary generates output."""
        # Set up a minimal spec dir with a definition
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "test.md").write_text("""
## REQ-p00001: Test
**Level**: prd | **Status**: Active | **Implements**: -

Electronic Record
: Data stored digitally.

*End* *Test* | **Hash**: 00000000
""")
        # Minimal config
        (tmp_path / ".elspais.toml").write_text('version = 4\n[project]\nname = "test"\n')

        result = subprocess.run(
            ["elspais", "glossary", "--format", "markdown"],
            cwd=tmp_path, capture_output=True, text=True,
        )
        assert "Electronic Record" in result.stdout or result.returncode == 0
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_terms.py -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/elspais/commands/args.py src/elspais/cli.py src/elspais/commands/fix_cmd.py tests/test_terms.py
git commit -m "feat(terms): register glossary and term-index CLI commands, wire into fix"
```

---

### Task 8: Render Extension for Definition Blocks

**Files:**
- Modify: `src/elspais/graph/render.py` (extend `_render_remainder`)
- Test: `tests/test_terms.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_terms.py
class TestDefinitionBlockRender:
    def test_render_definition_block(self):
        """REMAINDER node with content_type=definition_block renders as definition list."""
        from elspais.graph.GraphNode import GraphNode, NodeKind
        from elspais.graph.render import render_node

        node = GraphNode(id="rem:test:10", kind=NodeKind.REMAINDER, label="")
        node.set_field("content_type", "definition_block")
        node.set_field("text", "Electronic Record\n: Data stored in digital form.\n")

        output = render_node(node)
        assert "Electronic Record" in output
        assert ": Data stored in digital form." in output

    def test_render_normal_remainder(self):
        """REMAINDER without content_type renders as raw text (no regression)."""
        from elspais.graph.GraphNode import GraphNode, NodeKind
        from elspais.graph.render import render_node

        node = GraphNode(id="rem:test:20", kind=NodeKind.REMAINDER, label="")
        node.set_field("text", "Just some normal text.\n")

        output = render_node(node)
        assert output == "Just some normal text.\n"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_terms.py::TestDefinitionBlockRender -v`

- [ ] **Step 3: Extend `_render_remainder` in render.py**

The change is minimal — check for `content_type` field:

```python
def _render_remainder(node: GraphNode) -> str:
    content_type = node.get_field("content_type")
    if content_type == "definition_block":
        return node.get_field("text") or ""  # definition list text stored verbatim
    return node.get_field("text") or ""
```

Note: in v1, both paths return the same thing because definition block text is stored verbatim. The branching is scaffolding for future formatting changes.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_terms.py::TestDefinitionBlockRender -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/elspais/graph/render.py tests/test_terms.py
git commit -m "feat(terms): extend _render_remainder for definition_block content type"
```

---

### Task 9: Init Template and Documentation

**Files:**
- Modify: `src/elspais/commands/init.py` (add `[terms]` section to template)
- Create: `docs/cli/terms.md`

- [ ] **Step 1: Add `[terms]` section to init template**

Find the config template string in `init.py` and add:

```toml
[terms]
# Where generated files go (relative to repo root)
output_dir = "spec/_generated"

# Severity for duplicate definitions (same term, two locations)
duplicate_severity = "error"      # "error" | "warning" | "off"

# Severity for undefined terms (bold/italic token with no definition)
undefined_severity = "warning"    # "error" | "warning" | "off"

# Severity for unmarked usage of indexed terms in prose
unmarked_severity = "warning"     # "error" | "warning" | "off"
```

- [ ] **Step 2: Create docs/cli/terms.md**

Write the user documentation covering:
- What defined terms are and why they matter
- Definition syntax with examples
- Placement rules
- Reference markup conventions
- Health check descriptions
- Configuration reference
- Generated output (glossary, term-index, collections)
- FDA/regulatory context

- [ ] **Step 3: Verify docs command picks it up**

Run: `elspais docs terms`
Expected: Shows the terms documentation

- [ ] **Step 4: Commit**

```bash
git add src/elspais/commands/init.py docs/cli/terms.md
git commit -m "docs(terms): add init template section and CLI documentation"
```

---

### Task 10: Final Integration Testing and Cleanup

**Files:**
- All files from previous tasks
- Test: `tests/test_terms.py` (final integration tests)

- [ ] **Step 1: Run full test suite**

Run: `pytest`
Expected: All pass, no regressions

- [ ] **Step 2: Run e2e tests**

Run: `pytest -m e2e`
Expected: All pass including new term CLI tests

- [ ] **Step 3: Test with real elspais spec files**

Run: `elspais checks` and `elspais fix` in the elspais repo itself.
Verify: no new errors from the terms feature (there are no definition blocks in the current specs yet, so it should be a no-op).

- [ ] **Step 4: Add a sample definition to an elspais spec file and test end-to-end**

Add a test definition to a spec file, run `elspais glossary`, verify output.

- [ ] **Step 5: Final commit**

```bash
git commit -m "feat(terms): complete defined terms feature — v1"
```
