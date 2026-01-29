# MASTER PLAN - Phase 2: Pattern Builder Implementation

## Goal

Create the unified reference config module with dataclasses and pattern builder functions that will be shared by all parsers.

## Phase Details

### New File: `src/elspais/utilities/reference_config.py`

Create this file with:

#### 1. Dataclasses

```python
@dataclass
class ReferenceConfig:
    """Configuration for reference pattern matching.
    Used by all parsers: TestParser, CodeParser, JUnitXMLParser, PytestJSONParser
    """
    separators: List[str] = field(default_factory=lambda: ["-", "_"])
    case_sensitive: bool = False
    prefix_optional: bool = False
    comment_styles: List[str] = field(default_factory=lambda: ["#", "//", "--"])
    keywords: Dict[str, List[str]] = field(default_factory=lambda: {
        "implements": ["Implements", "IMPLEMENTS"],
        "validates": ["Validates", "Tests", "VALIDATES", "TESTS"],
        "refines": ["Refines", "REFINES"],
    })

@dataclass
class ReferenceOverride:
    """Override rule for specific file types or directories."""
    match: str  # Glob pattern (*.py, tests/legacy/**)
    separators: Optional[List[str]] = None
    case_sensitive: Optional[bool] = None
    prefix_optional: Optional[bool] = None
    comment_styles: Optional[List[str]] = None
    keywords: Optional[Dict[str, List[str]]] = None

    def applies_to(self, file_path: Path, base_path: Path) -> bool:
        """Check if this override applies to the given file."""
```

#### 2. ReferenceResolver Class

```python
class ReferenceResolver:
    """Resolves which reference config to use for a given file.
    This is the SINGLE entry point for all parsers.
    """
    def __init__(self, defaults: ReferenceConfig, overrides: List[ReferenceOverride]):
        ...

    def resolve(self, file_path: Path, base_path: Path) -> ReferenceConfig:
        """Return merged config for file (defaults + matching overrides)."""
```

#### 3. Pattern Builder Functions

```python
def build_id_pattern(
    pattern_config: PatternConfig,
    ref_config: ReferenceConfig,
    include_assertion: bool = True,
) -> re.Pattern:
    """Build regex pattern for matching requirement IDs."""

def build_comment_pattern(
    pattern_config: PatternConfig,
    ref_config: ReferenceConfig,
    keyword_type: str = "implements",
) -> re.Pattern:
    """Build pattern for matching reference comments."""

def build_block_header_pattern(
    ref_config: ReferenceConfig,
    keyword_type: str = "implements",
) -> re.Pattern:
    """Build pattern for multi-line block headers."""

def extract_ids_from_text(
    text: str,
    pattern_config: PatternConfig,
    ref_config: ReferenceConfig,
) -> List[str]:
    """Extract all requirement/assertion IDs from text."""

def normalize_extracted_id(match: re.Match, pattern_config: PatternConfig) -> str:
    """Normalize extracted ID to canonical format."""
```

### Files to Create

| File | Purpose |
|------|---------|
| `src/elspais/utilities/reference_config.py` | **NEW**: All config classes and pattern builders |

### Implementation Steps

- [x] 1. Create new file with imports and dataclasses
- [x] 2. Implement `ReferenceOverride.applies_to()` with glob matching
- [x] 3. Implement `ReferenceResolver.resolve()` with override merging
- [x] 4. Implement `build_id_pattern()` using PatternConfig + ReferenceConfig
- [x] 5. Implement `build_comment_pattern()` for single-line comments
- [x] 6. Implement `build_block_header_pattern()` for multi-line blocks
- [x] 7. Implement `extract_ids_from_text()` and `normalize_extracted_id()`
- [x] 8. Add unit tests for each function (40 tests)

## Phase 2 ✓ COMPLETE
