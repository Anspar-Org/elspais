# MASTER PLAN - Phase 4: TestParser and Result Parsers Refactor

## Goal

Refactor TestParser, JUnitXMLParser, and PytestJSONParser to use the shared reference config infrastructure. Remove all hardcoded patterns.

## Phase Details

### TestParser Changes

Remove hardcoded patterns:

```python
# REMOVE:
TEST_NAME_REQ_PATTERN = re.compile(r"def\s+test_\w*(?P<ref>REQ_[a-z]\d+(?:_[A-Z])*)")
COMMENT_REQ_PATTERN = re.compile(...)
```

New structure:

```python
class TestParser:
    priority = 80

    def __init__(
        self,
        pattern_config: PatternConfig,
        reference_resolver: ReferenceResolver,
    ) -> None:
        self.pattern_config = pattern_config
        self.reference_resolver = reference_resolver
```

### JUnitXMLParser Changes

Remove hardcoded patterns:

```python
# REMOVE:
REQ_PATTERN = re.compile(
    r"REQ[-_]([A-Za-z]?\d+(?:[-_][A-Z])?)|...",
    re.IGNORECASE,
)
```

New structure:

```python
class JUnitXMLParser:
    def __init__(
        self,
        pattern_config: PatternConfig,
        reference_resolver: ReferenceResolver,
        base_path: Path,
    ) -> None:
        self.pattern_config = pattern_config
        self.reference_resolver = reference_resolver
        self.base_path = base_path

    def _extract_req_ids(self, text: str, source_file: Optional[str]) -> list[str]:
        """Extract requirement IDs using file-appropriate pattern."""
        if source_file:
            ref_config = self.reference_resolver.resolve(
                Path(source_file), self.base_path
            )
        else:
            ref_config = self.reference_resolver.defaults

        return extract_ids_from_text(text, self.pattern_config, ref_config)
```

### PytestJSONParser Changes

Same changes as JUnitXMLParser (they share extraction logic).

### Files to Modify

| File | Changes |
|------|---------|
| `src/elspais/graph/parsers/test.py` | **MAJOR**: Use shared reference config |
| `src/elspais/graph/parsers/results/junit_xml.py` | Use shared reference config |
| `src/elspais/graph/parsers/results/pytest_json.py` | Use shared reference config |

### Implementation Steps

- [x] 1. Update TestParser:
  - [x] Add `__init__` with config parameters
  - [x] Remove class-level pattern constants
  - [x] Custom `_build_test_comment_pattern()` for no-colon syntax
  - [x] Custom `_build_test_name_pattern()` with negative lookahead
- [x] 2. Update JUnitXMLParser:
  - [x] Add `__init__` with config parameters
  - [x] Remove REQ_PATTERN constant
  - [x] Update `_extract_req_ids()` to use `extract_ids_from_text()`
- [x] 3. Update PytestJSONParser:
  - [x] Same changes as JUnitXMLParser
- [x] 4. Fix `build_id_pattern()` with `(?![a-z])` negative lookahead
- [x] 5. Add 9 new tests for custom config capabilities

## Phase 4 ✓ COMPLETE
