# Multi-Assertion Reference Expansion

**Date**: 2026-03-05
**Status**: Approved

## Problem

Multi-assertion expansion (`REQ-p00001-A-B-C` -> individual refs) exists as a hardcoded feature in `RequirementParser` only. It:

1. Has no formal requirement specification
2. Is not configurable via `.elspais.toml`
3. Does not work in CodeParser or TestParser (bug)
4. Uses a hardcoded regex that ignores configurable assertion label styles and separators
5. Is undocumented in configuration docs

The CLI docs (`docs/cli/linking.md`) claim it works "in all contexts" but it doesn't.

## Design

### Syntax

Multi-assertion references use a dedicated separator (distinct from the ID separator) to list multiple assertion labels:

```text
REQ-p00001-A+B+C
```

Expands to: `REQ-p00001-A`, `REQ-p00001-B`, `REQ-p00001-C`.

The `+` separator is unambiguous because it MUST differ from the ID separators (`-`, `_`). This eliminates all parsing ambiguity regardless of assertion label style (uppercase, numeric, alphanumeric).

Works in all contexts:
- Spec files: `**Implements**: REQ-p00001-A+B+C`
- Code comments: `# Implements: REQ-p00001-A+B+C`
- Test names: `def test_REQ_p00001_A+B+C_description():`

### Configuration

New key in `[references.defaults]`:

```toml
[references.defaults]
multi_assertion_separator = "+"
```

**Rules**:
- Default value: `"+"` (set in init template and config defaults)
- MUST differ from all configured `separators` — config validation rejects overlap
- Allowed characters: `/`, `|`, `+`, `&` (and potentially others that don't conflict with regex or shell)
- Set to `""` or `false` to disable expansion entirely

### Config Validation

On config load, validate that `multi_assertion_separator` is not present in `separators`. Example error:

```text
Configuration error: multi_assertion_separator "+" conflicts with
configured separators ["-", "_", "+"]. The multi-assertion separator
must be distinct from ID separators.
```

### Implementation Location

Expansion moves from `RequirementParser._expand_multi_assertion()` to the builder's link resolution loop (`builder.py` ~line 1941). This is the single convergence point where all parsers' pending links are resolved, so all parser types benefit automatically.

```python
# In builder._build_graph(), before resolving pending links:
for source_id, target_id, edge_kind in self._pending_links:
    # Expand multi-assertion refs first
    expanded = self._expand_multi_assertion(target_id)
    for resolved_target in expanded:
        # ... existing link resolution logic ...
```

The expansion method reads the configured `multi_assertion_separator` and `assertion_label_pattern` from config to build the expansion regex dynamically.

### Pattern Construction

The expansion regex is built from config at graph-build time:

```python
# Given:
#   multi_assertion_separator = "+"
#   assertion_label_pattern = "[A-Z]"  (from get_assertion_label_pattern())
#
# Builds regex:
#   ^(.+?)(?:\+([A-Z]))(?:\+([A-Z]))*$
#
# Which matches: REQ-p00001-A+B+C
# Groups: base="REQ-p00001-A", additional=["B", "C"]
```

The first label is part of the base ID (using the normal ID separator). Subsequent labels use the multi-assertion separator. This means:
- `REQ-p00001-A+B+C` -> base `REQ-p00001-A` + expand `B`, `C`
- Result: `REQ-p00001-A`, `REQ-p00001-B`, `REQ-p00001-C`

### Requirement Spec

A new DEV-level requirement will be added covering:

- A. The `multi_assertion_separator` config key SHALL be available in `[references.defaults]`
- B. The default value SHALL be `"+"`
- C. Config validation SHALL reject configurations where the multi-assertion separator overlaps with ID separators
- D. Expansion SHALL occur in the builder's link resolution, applying to all parser types (requirement, code, test, result)
- E. The expansion pattern SHALL derive from the configured assertion label pattern and multi-assertion separator
- F. When `multi_assertion_separator` is empty or false, expansion SHALL be disabled
- G. A reference with a single label (no multi-assertion separator present) SHALL pass through unchanged

### Documentation Updates

1. **`docs/configuration.md`**: Add `multi_assertion_separator` to `[references.defaults]` section
2. **`docs/cli/linking.md`**: Update multi-assertion syntax examples to use `+` separator
3. **`src/elspais/commands/init.py`**: Add `multi_assertion_separator = "+"` to generated template
4. **CLAUDE.md**: Update multi-assertion syntax description

### Migration of Existing References

After the feature is implemented, all existing multi-assertion references in the codebase must be updated from `-` to `+` syntax:

- `.github/workflows/ci.yml`: `REQ-o00066-A-B-C-D-E` -> `REQ-o00066-A+B+C+D+E`
- `.github/workflows/pr-validation.yml`: `REQ-o00066-F-G` -> `REQ-o00066-F+G`
- Test names using multi-assertion: update `_F_G` patterns where they represent multiple assertions

### Files to Modify

| File | Change |
|------|--------|
| `src/elspais/config/__init__.py` | Add `multi_assertion_separator` to defaults |
| `src/elspais/utilities/reference_config.py` | Read and expose new config key |
| `src/elspais/graph/builder.py` | Move expansion here, make config-driven |
| `src/elspais/graph/parsers/requirement.py` | Remove `_expand_multi_assertion()` |
| `src/elspais/graph/parsers/code.py` | No change (builder handles it) |
| `src/elspais/graph/parsers/test.py` | Ensure multi-assertion separator passes through in extracted refs |
| `src/elspais/validation/format.py` | Add config validation for separator conflict |
| `src/elspais/commands/init.py` | Update template |
| `docs/configuration.md` | Document new key |
| `docs/cli/linking.md` | Update syntax examples |
| `spec/` | Add formal requirement |
| `tests/` | New tests for expansion in all parser contexts |
