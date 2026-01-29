# MASTER PLAN - Phase 3: CodeParser Refactor

## Goal

Refactor CodeParser to use the shared reference config infrastructure. Remove hardcoded patterns. **Preserve multi-line block parsing capability.**

## Phase Details

### Current CodeParser Patterns to Remove

```python
# REMOVE THESE CLASS CONSTANTS:
IMPLEMENTS_PATTERN = re.compile(
    r"(?:#|//|--)\s*Implements:\s*(?P<refs>[A-Z]+-[A-Za-z0-9-]+...)"
)
VALIDATES_PATTERN = re.compile(...)
```

### New CodeParser Structure

```python
class CodeParser:
    """Parser for code references (Implements:, Refines:, Validates:)."""

    priority = 70

    def __init__(
        self,
        pattern_config: PatternConfig,
        reference_resolver: ReferenceResolver,
    ) -> None:
        self.pattern_config = pattern_config
        self.reference_resolver = reference_resolver

    def claim_and_parse(
        self,
        lines: list[tuple[int, str]],
        context: ParseContext,
    ) -> Iterator[ParsedContent]:
        # Get file-specific config
        ref_config = self.reference_resolver.resolve(
            context.source_path, context.repo_root
        )

        # Build patterns for this file
        implements_pattern = build_comment_pattern(
            self.pattern_config, ref_config, "implements"
        )
        block_header_pattern = build_block_header_pattern(
            ref_config, "implements"
        )

        # ... parsing logic using ref_config
```

### Files to Modify

| File | Changes |
|------|---------|
| `src/elspais/graph/parsers/code.py` | **MAJOR**: Use shared reference config |

### Implementation Steps

- [x] 1. Add `__init__` accepting `PatternConfig` and `ReferenceResolver`
- [x] 2. Remove class-level IMPLEMENTS_PATTERN, VALIDATES_PATTERN constants
- [x] 3. Update `claim_and_parse()` to get file-specific config via resolver
- [x] 4. Use `build_comment_pattern()` for single-line detection
- [x] 5. Use `build_block_header_pattern()` for multi-line block detection
- [x] 6. Use `build_block_ref_pattern()` for block reference matching
- [x] 7. **CRITICAL**: Preserve multi-line block parsing (`_is_empty_comment()` helper)
- [x] 8. Add 20 comprehensive tests (all 24 total tests pass)

## Phase 3 ✓ COMPLETE
