# MASTER PLAN

> **Directive**: Use the elspais MCP to mutate spec files when it is necessary to modify a requirement, as a test of that system.

## Overview

Add a configurable `hash_mode` setting under `[validation]` in `.elspais.toml` with two modes:

- **`full-text`**: Hash every line between header and footer, no normalization.
- **`normalized-text`** (default): Hash assertions only, with cosmetic normalization. More forgiving of formatting changes.

### Design Decisions

- **Configurable**: Projects choose their hash mode via `[validation].hash_mode`
- **Default is `full-text`**: No breaking change for existing projects
- **`normalized-text` rules**: assertions-only, cosmetic normalization (see Phase 3)
- **Assertion order**: Physical file order preserved (NOT sorted by label)
- **NOT doing**: Case-invariance, Unicode normalization, trailing period stripping, label prefix stripping

### Configuration

```toml
[validation]
hash_algorithm = "sha256"    # existing
hash_length = 8              # existing
hash_mode = "full-text"      # NEW — "full-text" | "normalized-text"
```

### Normalization Rules (for `normalized-text` mode)

For each assertion (in physical file order):

1. Collect the assertion line and any continuation lines (until next assertion or end)
2. Join into a single line, collapsing internal newlines to spaces
3. Collapse multiple internal spaces to single space
4. Strip trailing whitespace
5. Normalize line endings to `\n`

Join all normalized assertion lines with `\n`, then hash.

## Phases

1. Spec Update
2. Config Defaults
3. Hasher Normalization Functions
4. Builder + Commands (hash mode branching)
5. Tests
6. Fixture Alignment + Final Validation

---

## Phase 1: Spec Update

### Problem

The spec (`spec/requirements-spec.md` ~line 346-357) defines only one hash algorithm (full body text). It needs to document both modes and the new config option.

### Solution

Expand the "Hash Definition" section to document:

- `hash_mode` configuration option with two values
- `full-text`: every line AFTER Header, BEFORE Footer (current, no normalization)
- `normalized-text`: assertion text only, with normalization rules
- Explicit statement: assertions hashed in physical file order, NOT sorted
- Non-assertion body text excluded in `normalized-text` mode
- Note: "Any material behavioral constraint SHALL be expressed as an Assertion"

### Tasks

- [x] Update `spec/requirements-spec.md` Hash Definition section

---

## Phase 2: Config Defaults

### Problem

The `DEFAULT_CONFIG` in `config/__init__.py` has no `validation` section with `hash_mode`. The config system needs to know about the new setting.

### Solution

Add `hash_mode` to the config defaults following the existing pattern. The `[validation]` section already exists in test fixture configs (`hash_algorithm`, `hash_length`) but may not be in `DEFAULT_CONFIG`.

### Tasks

- [x] Add `"validation": {"hash_mode": "full-text"}` to `DEFAULT_CONFIG` in `src/elspais/config/__init__.py`

---

## Phase 3: Hasher Normalization Functions

### Problem

`src/elspais/utilities/hasher.py` has `calculate_hash()` for raw text hashing but no assertion-specific normalization.

### Solution

Add new functions to the hasher module:

- `normalize_assertion_text(label: str, text: str) -> str` — normalize a single assertion (collapse multiline, strip whitespace, collapse internal spaces)
- `compute_normalized_hash(assertions: list[tuple[str, str]], algorithm="sha256", length=8) -> str` — full pipeline for normalized-text mode

Keep existing `calculate_hash()` unchanged — used by `full-text` mode.

### Tasks

- [x] Add `normalize_assertion_text()` to `src/elspais/utilities/hasher.py`
- [x] Add `compute_normalized_hash()` to `src/elspais/utilities/hasher.py`

---

## Phase 4: Builder + Commands (Hash Mode Branching)

### Problem

The graph builder's `_recompute_requirement_hash()` and both command modules (`hash_cmd.py`, `validate.py`) currently use `body_text` unconditionally. They need to branch on `hash_mode`.

### Solution

**`src/elspais/graph/builder.py`** — `_recompute_requirement_hash()`:

- Read `hash_mode` from config (builder already has config access)
- `full-text`: use body_text (current behavior)
- `normalized-text`: iterate assertion children, call `compute_normalized_hash()`

**`src/elspais/commands/hash_cmd.py`** — `_get_requirement_body()`:

- `full-text`: return `node.get_field("body_text", "")` (current)
- `normalized-text`: extract assertion label+text from children, normalize

**`src/elspais/commands/validate.py`** — same branching logic.

**`src/elspais/graph/parsers/requirement.py`** — no changes needed:

- Keep `_extract_body_text()` for full-text mode and mutation API
- Assertions already parsed by `_parse_assertions()` and stored as child nodes

### Tasks

- [x] Update `_recompute_requirement_hash()` in `src/elspais/graph/builder.py`
- [x] Update `_get_requirement_body()` in `src/elspais/commands/hash_cmd.py`
- [x] Update `_get_requirement_body()` in `src/elspais/commands/validate.py`

---

## Phase 5: Tests

### Problem

Existing tests assume one hash mode. Need tests for both modes and normalization edge cases.

### Solution

**`tests/core/test_hasher.py`** — new normalization function tests:

- Trailing whitespace stripped
- Multiline assertion collapsed to single line
- Multiple internal spaces collapsed
- `\r\n` normalized to `\n`

**`tests/commands/test_hash_update.py`** — config-aware tests for both modes.

**`tests/core/test_mutation_hash_consistency.py`** — test both modes.

**New tests for `normalized-text` mode**:

- Blank lines between assertions don't affect hash
- Non-assertion body text changes don't affect hash
- Assertion reordering DOES change hash (explicit)
- Case changes DO change hash (explicit)

**Full-text mode tests**: Existing behavior preserved, body text changes DO affect hash.

### Tasks

- [x] Add normalization unit tests to `tests/core/test_hasher.py` (20 tests)
- [x] Add `normalized-text` mode integration tests in `tests/core/test_hash_mode.py` (17 tests)
- [ ] ~Add config-aware tests to `tests/commands/test_hash_update.py`~ (covered by integration tests)
- [ ] ~Update `tests/core/test_mutation_hash_consistency.py` for both modes~ (covered by integration tests)

---

## Phase 6: Fixture Alignment + Final Validation

### Problem

Test fixture hashes were computed with the old assertions-only algorithm (pre-`ff143f9`), then the algorithm changed to full-body-text. Under `full-text` default mode, fixture hashes need to match.

### Solution

- Run `elspais hash update` on all test fixtures to align stored hashes with `full-text` mode
- Optionally add `hash_mode = "full-text"` explicitly to `tests/fixtures/hht-like/.elspais.toml`
- Optionally add a small fixture with `hash_mode = "normalized-text"` for integration testing

### Tasks

- [x] Update fixture hashes via `elspais hash update`
- [x] Run full test suite (`pytest`)
- [ ] Run `git push` — verify pre-push hook passes

---

## Verification Checklist

After each phase:

- [ ] All tests pass (`pytest`)
- [ ] No lint errors (`ruff check`)
- [ ] Commit with ticket prefix

Final verification:

- [ ] `elspais hash verify` on fixtures — no mismatches (full-text mode)
- [ ] Temporarily set `hash_mode = "normalized-text"` on a fixture, run `elspais hash update`, verify:
  - Non-assertion text change → hash unchanged
  - Assertion text change → hash changes
  - Trailing space on assertion → hash unchanged
- [ ] `git push` — pre-push hook passes

## Commit Template

```text
[CUR-514] type: Description

Details of what was done.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```
