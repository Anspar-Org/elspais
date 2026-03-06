# Multi-Assertion Reference Expansion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make multi-assertion reference expansion configurable, formally specified, and working across all parser types.

**Architecture:** Add `multi_assertion_separator` to `[references.defaults]` config (default `"+"`). Move expansion logic from RequirementParser into GraphBuilder.build() so all parsers benefit. The separator MUST differ from ID separators — config validation enforces this.

**Tech Stack:** Python 3.10+, tomlkit, pytest

---

### Task 1: Add Formal Requirement Spec

**Files:**
- Create: `spec/dev-multi-assertion.md`
- Modify: `spec/INDEX.md`

**Step 1: Write the spec file**

Create `spec/dev-multi-assertion.md`:

```markdown
# Multi-Assertion Reference Expansion

## REQ-d00081: Multi-Assertion Reference Expansion

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00001

Multi-assertion references allow compact notation for referencing multiple assertions
of the same requirement. A dedicated separator character (distinct from ID separators)
joins assertion labels after the first: `REQ-p00001-A+B+C` expands to individual
assertion references `REQ-p00001-A`, `REQ-p00001-B`, `REQ-p00001-C`.

## Assertions

A. The `multi_assertion_separator` key SHALL be available in `[references.defaults]` configuration.

B. The default value of `multi_assertion_separator` SHALL be `"+"`.

C. Config validation SHALL reject configurations where the multi-assertion separator character appears in the `separators` list.

D. Expansion SHALL occur in the graph builder's link resolution, applying uniformly to all parser types (requirement, code, test, result).

E. The expansion pattern SHALL derive from the configured assertion label pattern and multi-assertion separator.

F. When `multi_assertion_separator` is empty or `false`, expansion SHALL be disabled.

G. A reference containing no multi-assertion separator character SHALL pass through unchanged.

## Rationale

The previous implementation hardcoded expansion in RequirementParser only, using a
regex that assumed uppercase letter labels and hyphen separators. This created silent
failures when code comments (`# Implements: REQ-x-A-B-C`) and test names
(`test_REQ_x_A_B_C`) were not expanded. A dedicated separator character eliminates
ambiguity regardless of the configured assertion label style (uppercase, numeric,
alphanumeric).

*End* *REQ-d00081* <!-- hash:00000000 -->
```

**Step 2: Add to INDEX.md**

Add the row to the index table:

```
| REQ-d00081 | Multi-Assertion Reference Expansion           | dev-multi-assertion.md   | 00000000 |
```

**Step 3: Regenerate hash**

Run: `cd /home/metagamer/anspar-org/elspais-worktrees/exemplar && python -m elspais validate --mode core`

Check output — it will report the correct hash. Update the hash in both files.

**Step 4: Commit**

```bash
git add spec/dev-multi-assertion.md spec/INDEX.md
git commit -m "feat: add REQ-d00081 multi-assertion expansion spec"
```

---

### Task 2: Add Config Default and ReferenceConfig Field

**Files:**
- Modify: `src/elspais/config/__init__.py:62-74`
- Modify: `src/elspais/utilities/reference_config.py:27-51`
- Test: `tests/core/test_parsers/test_reference_config.py`

**Step 1: Write the failing test**

Add to `tests/core/test_parsers/test_reference_config.py`:

```python
class TestMultiAssertionSeparator:
    """Tests for REQ-d00081-A+B multi-assertion separator config."""

    def test_REQ_d00081_A_default_separator_is_plus(self):
        """Default multi_assertion_separator should be '+'."""
        rc = ReferenceConfig()
        assert rc.multi_assertion_separator == "+"

    def test_REQ_d00081_B_from_dict_reads_separator(self):
        """from_dict should read multi_assertion_separator."""
        rc = ReferenceConfig.from_dict({"multi_assertion_separator": "&"})
        assert rc.multi_assertion_separator == "&"

    def test_REQ_d00081_F_empty_string_disables(self):
        """Empty string disables expansion."""
        rc = ReferenceConfig.from_dict({"multi_assertion_separator": ""})
        assert rc.multi_assertion_separator == ""

    def test_REQ_d00081_F_false_disables(self):
        """False value disables expansion."""
        rc = ReferenceConfig.from_dict({"multi_assertion_separator": False})
        assert rc.multi_assertion_separator == ""
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_parsers/test_reference_config.py::TestMultiAssertionSeparator -v`
Expected: FAIL — `ReferenceConfig` has no `multi_assertion_separator` attribute

**Step 3: Implement config changes**

In `src/elspais/config/__init__.py`, add to `DEFAULT_CONFIG["references"]["defaults"]` (line ~64):

```python
"references": {
    "defaults": {
        "separators": ["-", "_"],
        "case_sensitive": False,
        "prefix_optional": False,
        "comment_styles": ["#", "//", "--"],
        "multi_assertion_separator": "+",
        "keywords": {
            ...
        },
    },
    "overrides": [],
},
```

In `src/elspais/utilities/reference_config.py`, add field to `ReferenceConfig` dataclass (after line 51):

```python
multi_assertion_separator: str = "+"
```

In `ReferenceConfig.from_dict()`, add parsing:

```python
mas = data.get("multi_assertion_separator", "+")
if mas is False or mas is None:
    mas = ""
kwargs["multi_assertion_separator"] = str(mas)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_parsers/test_reference_config.py::TestMultiAssertionSeparator -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/elspais/config/__init__.py src/elspais/utilities/reference_config.py tests/core/test_parsers/test_reference_config.py
git commit -m "feat(REQ-d00081-A+B): add multi_assertion_separator config field"
```

---

### Task 3: Add Config Validation (Separator Conflict)

**Files:**
- Modify: `src/elspais/utilities/reference_config.py`
- Test: `tests/core/test_parsers/test_reference_config.py`

**Step 1: Write the failing test**

```python
class TestMultiAssertionValidation:
    """Tests for REQ-d00081-C separator conflict validation."""

    def test_REQ_d00081_C_rejects_separator_overlap(self):
        """Should raise ValueError when multi_assertion_separator is in separators."""
        with pytest.raises(ValueError, match="conflicts with"):
            ReferenceConfig.from_dict({
                "separators": ["-", "_", "+"],
                "multi_assertion_separator": "+",
            })

    def test_REQ_d00081_C_accepts_non_overlapping(self):
        """Should accept when separator doesn't overlap."""
        rc = ReferenceConfig.from_dict({
                "separators": ["-", "_"],
                "multi_assertion_separator": "+",
        })
        assert rc.multi_assertion_separator == "+"

    def test_REQ_d00081_C_skips_validation_when_disabled(self):
        """No conflict check when expansion is disabled."""
        rc = ReferenceConfig.from_dict({
            "separators": ["-", "_"],
            "multi_assertion_separator": "",
        })
        assert rc.multi_assertion_separator == ""
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_parsers/test_reference_config.py::TestMultiAssertionValidation -v`
Expected: FAIL — no ValueError raised

**Step 3: Implement validation**

In `ReferenceConfig.from_dict()`, after setting `multi_assertion_separator`, add:

```python
if kwargs.get("multi_assertion_separator"):
    seps = kwargs.get("separators", cls.separators) if "separators" in data else ["-", "_"]
    if kwargs["multi_assertion_separator"] in seps:
        raise ValueError(
            f"multi_assertion_separator {kwargs['multi_assertion_separator']!r} "
            f"conflicts with configured separators {seps}. "
            f"The multi-assertion separator must be distinct from ID separators."
        )
```

Note: check the actual structure of `from_dict` to place this after both `separators` and `multi_assertion_separator` are resolved.

**Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_parsers/test_reference_config.py::TestMultiAssertionValidation -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/elspais/utilities/reference_config.py tests/core/test_parsers/test_reference_config.py
git commit -m "feat(REQ-d00081-C): validate multi-assertion separator conflicts"
```

---

### Task 4: Implement Expansion in GraphBuilder

**Files:**
- Modify: `src/elspais/graph/builder.py:1602-1627,1931-1980`
- Modify: `src/elspais/graph/factory.py:200-202`
- Test: `tests/core/test_builder.py`

**Step 1: Write the failing test**

Add to `tests/core/test_builder.py`:

```python
class TestMultiAssertionExpansion:
    """Tests for REQ-d00081-D+E+G multi-assertion expansion in builder."""

    def test_REQ_d00081_D_expands_code_ref_multi_assertion(self):
        """Code refs with + separator should expand to individual assertion links."""
        builder = GraphBuilder(multi_assertion_separator="+")

        # Add a requirement with assertions A, B, C
        builder.add_parsed_content(ParsedContent(
            parser_type="requirement",
            source_id="spec/test.md",
            start_line=1,
            parsed_data={
                "id": "REQ-p00001",
                "title": "Test Req",
                "level": "prd",
                "status": "Active",
                "body": "Body",
                "implements": [],
                "refines": [],
                "assertions": [
                    {"label": "A", "text": "Assertion A", "line": 5},
                    {"label": "B", "text": "Assertion B", "line": 6},
                    {"label": "C", "text": "Assertion C", "line": 7},
                ],
            },
        ))
        # Add a code ref that uses multi-assertion syntax
        builder.add_parsed_content(ParsedContent(
            parser_type="code_ref",
            source_id="src/foo.py",
            start_line=1,
            parsed_data={
                "implements": ["REQ-p00001-A+B+C"],
                "validates": [],
            },
        ))

        graph = builder.build()
        req_node = graph.find_by_id("REQ-p00001")
        assert req_node is not None
        # The code node should be linked to the requirement
        code_children = [c for c in req_node.iter_children() if c.kind == NodeKind.CODE]
        assert len(code_children) == 1

    def test_REQ_d00081_G_single_assertion_passthrough(self):
        """Single assertion ref (no + separator) passes through unchanged."""
        builder = GraphBuilder(multi_assertion_separator="+")

        builder.add_parsed_content(ParsedContent(
            parser_type="requirement",
            source_id="spec/test.md",
            start_line=1,
            parsed_data={
                "id": "REQ-p00001",
                "title": "Test Req",
                "level": "prd",
                "status": "Active",
                "body": "Body",
                "implements": [],
                "refines": [],
                "assertions": [
                    {"label": "A", "text": "Assertion A", "line": 5},
                ],
            },
        ))
        builder.add_parsed_content(ParsedContent(
            parser_type="code_ref",
            source_id="src/foo.py",
            start_line=1,
            parsed_data={
                "implements": ["REQ-p00001-A"],
                "validates": [],
            },
        ))

        graph = builder.build()
        # Should resolve without broken refs
        assert len(graph.broken_references) == 0

    def test_REQ_d00081_E_uses_configured_separator(self):
        """Expansion uses the configured separator, not hardcoded."""
        builder = GraphBuilder(multi_assertion_separator="&")

        builder.add_parsed_content(ParsedContent(
            parser_type="requirement",
            source_id="spec/test.md",
            start_line=1,
            parsed_data={
                "id": "REQ-p00001",
                "title": "Test Req",
                "level": "prd",
                "status": "Active",
                "body": "Body",
                "implements": [],
                "refines": [],
                "assertions": [
                    {"label": "A", "text": "Assertion A", "line": 5},
                    {"label": "B", "text": "Assertion B", "line": 6},
                ],
            },
        ))
        builder.add_parsed_content(ParsedContent(
            parser_type="code_ref",
            source_id="src/foo.py",
            start_line=1,
            parsed_data={
                "implements": ["REQ-p00001-A&B"],
                "validates": [],
            },
        ))

        graph = builder.build()
        assert len(graph.broken_references) == 0

    def test_REQ_d00081_F_disabled_when_empty(self):
        """No expansion when multi_assertion_separator is empty."""
        builder = GraphBuilder(multi_assertion_separator="")

        builder.add_parsed_content(ParsedContent(
            parser_type="requirement",
            source_id="spec/test.md",
            start_line=1,
            parsed_data={
                "id": "REQ-p00001",
                "title": "Test Req",
                "level": "prd",
                "status": "Active",
                "body": "Body",
                "implements": [],
                "refines": [],
                "assertions": [
                    {"label": "A", "text": "Assertion A", "line": 5},
                    {"label": "B", "text": "Assertion B", "line": 6},
                ],
            },
        ))
        builder.add_parsed_content(ParsedContent(
            parser_type="code_ref",
            source_id="src/foo.py",
            start_line=1,
            parsed_data={
                "implements": ["REQ-p00001-A+B"],
                "validates": [],
            },
        ))

        graph = builder.build()
        # Should NOT expand — "REQ-p00001-A+B" treated as literal (broken ref)
        assert len(graph.broken_references) == 1
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_builder.py::TestMultiAssertionExpansion -v`
Expected: FAIL — `GraphBuilder` doesn't accept `multi_assertion_separator`

**Step 3: Implement expansion in builder**

In `src/elspais/graph/builder.py`, modify `GraphBuilder.__init__` (line ~1602):

```python
def __init__(
    self,
    repo_root: Path | None = None,
    hash_mode: str = "normalized-text",
    satellite_kinds: list[str] | None = None,
    multi_assertion_separator: str = "+",
) -> None:
```

Add to `__init__` body:

```python
self._multi_assertion_separator = multi_assertion_separator
```

Add expansion method to `GraphBuilder`:

```python
def _expand_multi_assertion(self, target_id: str) -> list[str]:
    """Expand multi-assertion reference using configured separator.

    REQ-p00001-A+B+C -> [REQ-p00001-A, REQ-p00001-B, REQ-p00001-C]

    The first assertion label is part of the base ID (normal separator).
    Additional labels follow the multi-assertion separator.
    """
    sep = self._multi_assertion_separator
    if not sep or sep not in target_id:
        return [target_id]

    # Split on the multi-assertion separator
    parts = target_id.split(sep)
    # First part is the base ID including first assertion label
    base = parts[0]
    if not parts[1:]:
        return [target_id]

    # Extract the base requirement ID (everything before the last separator + label)
    # e.g., "REQ-p00001-A" -> base_req = "REQ-p00001", first_label = "A"
    # Find the last ID separator (- or _) to split off the first assertion label
    last_sep_idx = max(base.rfind("-"), base.rfind("_"))
    if last_sep_idx < 0:
        return [target_id]

    base_req = base[:last_sep_idx]
    id_sep = base[last_sep_idx]  # the separator character used
    first_label = base[last_sep_idx + 1:]

    result = [f"{base_req}{id_sep}{first_label}"]
    for label in parts[1:]:
        if label:
            result.append(f"{base_req}{id_sep}{label}")

    return result
```

Modify `build()` method (line ~1941) to expand before resolving:

```python
# Resolve pending links
expanded_links: list[tuple[str, str, EdgeKind]] = []
for source_id, target_id, edge_kind in self._pending_links:
    for resolved_target in self._expand_multi_assertion(target_id):
        expanded_links.append((source_id, resolved_target, edge_kind))

for source_id, target_id, edge_kind in expanded_links:
    source = self._nodes.get(source_id)
    target = self._nodes.get(target_id)
    # ... rest of existing logic unchanged ...
```

In `src/elspais/graph/factory.py` (line ~200), pass config to builder:

```python
ref_defaults = config.get("references", {}).get("defaults", {})
mas = ref_defaults.get("multi_assertion_separator", "+")
if mas is False or mas is None:
    mas = ""
builder = GraphBuilder(
    repo_root=repo_root,
    hash_mode=hash_mode,
    satellite_kinds=satellite_kinds,
    multi_assertion_separator=str(mas),
)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_builder.py::TestMultiAssertionExpansion -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: All pass (no regressions)

**Step 6: Commit**

```bash
git add src/elspais/graph/builder.py src/elspais/graph/factory.py tests/core/test_builder.py
git commit -m "feat(REQ-d00081-D+E+F+G): implement multi-assertion expansion in builder"
```

---

### Task 5: Remove Old Expansion from RequirementParser

**Files:**
- Modify: `src/elspais/graph/parsers/requirement.py:220-222,264-283`
- Modify: `tests/core/test_parsers/test_requirement_parser.py:199-215`

**Step 1: Update the existing requirement parser test**

The test at `test_requirement_parser.py:199` currently verifies expansion happens in the parser. Update it to verify the parser passes through multi-assertion syntax unchanged (builder now handles expansion):

```python
def test_passes_through_multi_assertion_syntax(self, parser):
    """Multi-assertion expansion now happens in builder, not parser."""
    lines = [
        (1, "## REQ-o00001: Multi-Assertion"),
        (2, "**Implements**: REQ-p00001-A+B+C | **Status**: Active"),
        (3, "Body."),
        (4, "*End* *REQ-o00001*"),
    ]
    ctx = ParseContext(file_path="spec/ops.md")

    results = list(parser.claim_and_parse(lines, ctx))

    assert len(results) == 1
    implements = results[0].parsed_data["implements"]
    # Parser should pass through as-is — builder expands later
    assert "REQ-p00001-A+B+C" in implements
```

**Step 2: Remove expansion from RequirementParser**

In `src/elspais/graph/parsers/requirement.py`:

- Remove lines 220-222 (the `_expand_multi_assertion` calls)
- Remove the `_expand_multi_assertion` method (lines 264-283)

**Step 3: Run tests**

Run: `pytest tests/core/test_parsers/test_requirement_parser.py -v && pytest tests/core/test_builder.py::TestMultiAssertionExpansion -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add src/elspais/graph/parsers/requirement.py tests/core/test_parsers/test_requirement_parser.py
git commit -m "refactor(REQ-d00081-D): remove expansion from RequirementParser"
```

---

### Task 6: Update Init Template

**Files:**
- Modify: `src/elspais/commands/init.py:258-267`

**Step 1: Add multi_assertion_separator to the generated template**

In `src/elspais/commands/init.py`, find the `[references.defaults]` section of the template (or if absent, add it). The init template currently doesn't include `[references]` at all. Add before the `[ignore]` section (before line 258):

```toml
[references.defaults]
# Separator characters accepted between ID components
separators = ["-", "_"]
# Character joining multiple assertion labels: REQ-p00001-A+B+C
multi_assertion_separator = "+"
```

**Step 2: Verify by running init in a temp dir**

Run: `cd /tmp && mkdir test-init && cd test-init && git init && python -m elspais init && grep multi_assertion .elspais.toml`
Expected: Shows `multi_assertion_separator = "+"`

**Step 3: Commit**

```bash
git add src/elspais/commands/init.py
git commit -m "feat(REQ-d00081-A+B): add multi_assertion_separator to init template"
```

---

### Task 7: Update Documentation

**Files:**
- Modify: `docs/configuration.md:388-405`
- Modify: `docs/cli/linking.md:116-132`
- Modify: `CLAUDE.md`
- Modify: `src/elspais/mcp/server.py:1088-1112`

**Step 1: Update `docs/configuration.md`**

In the `[references.defaults]` section (after line 390), add:

```markdown
# Character for joining multiple assertion labels in compact syntax
# REQ-p00001-A+B+C expands to REQ-p00001-A, REQ-p00001-B, REQ-p00001-C
# Must NOT appear in the separators list. Set to "" to disable.
multi_assertion_separator = "+"
```

**Step 2: Update `docs/cli/linking.md`**

Replace the multi-assertion section (lines 116-132) to use `+` syntax:

```markdown
## Multi-Assertion Syntax

Reference multiple assertions of the same requirement with a compact syntax
using the `+` separator (configurable via `multi_assertion_separator`):

```python
# Implements: REQ-d00001-A+B+C
```

This expands to three separate references:
  `REQ-d00001-A`, `REQ-d00001-B`, `REQ-d00001-C`

Works in all contexts: `Implements:`, `Refines:`, `Tests:`, and test function names.

```python
def test_REQ_d00001_A+B+C_full_auth():
    ...
```

The separator character is configured in `.elspais.toml`:

```toml
[references.defaults]
multi_assertion_separator = "+"  # Must differ from ID separators
```
```

**Step 3: Update CLAUDE.md**

Change the multi-assertion line to:

```
**Multi-Assertion Syntax**: `Implements: REQ-p00001-A+B+C` expands to individual assertion references (`REQ-p00001-A`, `REQ-p00001-B`, `REQ-p00001-C`). Same for `Refines:`. The separator (`+` by default) is configured via `multi_assertion_separator` in `[references.defaults]`.
```

**Step 4: Update MCP server assertion format helper**

In `src/elspais/mcp/server.py`, update `_build_assertion_format()` (line ~1108) to read the configured separator and use it in the example:

```python
ref_defaults = config.get("references", {}).get("defaults", {})
mas = ref_defaults.get("multi_assertion_separator", "+")

return {
    "label_style": assertions.get("label_style", "uppercase"),
    "max_count": assertions.get("max_count", 26),
    "example": f"{prefix}-{first_type_id}{example_num}-A",
    "multi_assertion_syntax": (
        f"{prefix}-{first_type_id}{example_num}-A{mas}B{mas}C expands to "
        f"{prefix}-{first_type_id}{example_num}-A, "
        f"{prefix}-{first_type_id}{example_num}-B, "
        f"{prefix}-{first_type_id}{example_num}-C"
    ) if mas else "disabled",
}
```

**Step 5: Commit**

```bash
git add docs/configuration.md docs/cli/linking.md CLAUDE.md src/elspais/mcp/server.py
git commit -m "docs(REQ-d00081): update multi-assertion syntax documentation"
```

---

### Task 8: Update Project Config and Migrate Existing References

**Files:**
- Modify: `.elspais.toml`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/pr-validation.yml`

**Step 1: Add to project config**

Add `multi_assertion_separator = "+"` to `.elspais.toml` in the `[references.defaults]` section (create section if absent).

**Step 2: Update CI workflow references**

In `.github/workflows/ci.yml`, change:
- `REQ-o00066-A-B-C-D-E` -> `REQ-o00066-A+B+C+D+E`

In `.github/workflows/pr-validation.yml`, change:
- `REQ-o00066-F-G` -> `REQ-o00066-F+G`

**Step 3: Update spec file references**

Search for any `Implements:` or `Refines:` lines in `spec/` that use the old multi-assertion syntax (multiple single-letter labels separated by `-` after a requirement ID). These should now use `+`.

Run: `grep -rn 'Implements.*REQ-[a-z][0-9]*-[A-Z]-[A-Z]' spec/`

Update any matches.

**Step 4: Verify**

Run: `python -m elspais validate --mode core`
Expected: No broken references from multi-assertion syntax

**Step 5: Commit**

```bash
git add .elspais.toml .github/workflows/ci.yml .github/workflows/pr-validation.yml
git commit -m "migrate(REQ-d00081): update references to use + multi-assertion separator"
```

---

### Task 9: Update Test Parser Test Expectation

**Files:**
- Modify: `tests/core/test_parsers/test_test_parser.py:74-87`

**Step 1: Update multi-assertion test**

The test at line 74 (`test_REQ_d00066_D_validates_multi_assertion_reference`) currently expects `REQ-d00060-A-B` as a raw unexpanded string. With the new syntax, multi-assertion in test names uses `+`:

Update the test input and expectation:

```python
def test_REQ_d00066_D_validates_multi_assertion_reference(self):
    """REQ-d00066-D: Test names with multiple assertion labels are validated."""
    parser = TestParser()
    lines = [
        (1, "def test_REQ_d00060_A+B_combined_test():"),
        (2, "    assert True"),
    ]
    ctx = ParseContext(file_path="tests/test_mcp.py")

    results = list(parser.claim_and_parse(lines, ctx))

    assert len(results) == 1
    # TestParser extracts raw ref — builder expands A+B later
    assert "REQ-d00060-A+B" in results[0].parsed_data["validates"]
```

Note: Also verify the TestParser regex can capture `+` in function names. If the test parser's regex strips `+`, the extraction pattern in `test.py` line ~151 may need adjustment to allow `+` through. Check and fix if needed.

**Step 2: Run test**

Run: `pytest tests/core/test_parsers/test_test_parser.py::TestTestParserBasic::test_REQ_d00066_D_validates_multi_assertion_reference -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/core/test_parsers/test_test_parser.py
git commit -m "test(REQ-d00081): update test parser multi-assertion expectation"
```

---

### Task 10: Integration Test — Full Pipeline

**Files:**
- Test: `tests/core/test_integration/test_pipeline.py`

**Step 1: Write integration test**

Add to `tests/core/test_integration/test_pipeline.py`:

```python
class TestMultiAssertionPipeline:
    """REQ-d00081-D: End-to-end multi-assertion expansion across all parser types."""

    def test_REQ_d00081_D_code_ref_multi_assertion_resolves(self, integration_spec_dir):
        """Code # Implements: REQ-x-A+B+C should expand and link to assertions."""
        # Create spec file
        spec_file = integration_spec_dir / "spec" / "test.md"
        spec_file.write_text(
            "## REQ-d00001: Test\n"
            "**Level**: DEV | **Status**: Active | **Implements**: -\n"
            "Body.\n\n"
            "## Assertions\n\n"
            "A. First assertion.\n\n"
            "B. Second assertion.\n\n"
            "*End* *REQ-d00001* <!-- hash:00000000 -->\n"
        )
        # Create code file with multi-assertion ref
        code_dir = integration_spec_dir / "src"
        code_dir.mkdir(exist_ok=True)
        code_file = code_dir / "impl.py"
        code_file.write_text("# Implements: REQ-d00001-A+B\ndef impl(): pass\n")

        builder = GraphBuilder(
            repo_root=integration_spec_dir,
            multi_assertion_separator="+",
        )
        # Parse and build (using appropriate parsers)
        # ... setup parsers, parse files, add to builder ...

        graph = builder.build()
        assert len(graph.broken_references) == 0
```

Note: Adapt this to the existing integration test patterns in the file. The exact setup may need to use the parser pipeline from `factory.py` or set up parsers manually as other integration tests do.

**Step 2: Run integration test**

Run: `pytest tests/core/test_integration/test_pipeline.py::TestMultiAssertionPipeline -v`
Expected: PASS

**Step 3: Run full suite**

Run: `pytest tests/ -x -q`
Expected: All pass

**Step 4: Commit**

```bash
git add tests/core/test_integration/test_pipeline.py
git commit -m "test(REQ-d00081-D): add integration test for multi-assertion pipeline"
```

---

### Task 11: Verify Graph Health Improvement

**Step 1: Rebuild graph and check status**

Run: `python -m elspais validate --mode core -v`

**Step 2: Check broken references via MCP**

Use `get_graph_status()` and `get_broken_references()` to confirm the multi-assertion broken refs are resolved.

**Step 3: Document results**

Note how many broken references were resolved by this change. The Category 4 refs (~6) should be gone. Remaining broken references are addressed in subsequent phases.

**Step 4: Final commit (if any cleanup needed)**

```bash
git add -A
git commit -m "chore(REQ-d00081): verify graph health after multi-assertion fix"
```
