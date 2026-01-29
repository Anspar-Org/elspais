# Unified References Configuration

## Goal

Add unified `[references]` configuration section to support configurable reference parsing across all parser types (CodeParser, TestParser, JUnitXMLParser, PytestJSONParser) with file-type and directory-based overrides.

### Configuration Structure

All reference parsing (tests, code, results) shares the same configuration structure under a new `[references]` section:

```toml
# Unified reference pattern configuration
# Used by: TestParser, CodeParser, JUnitXMLParser, PytestJSONParser

[references]
# Default pattern options (applied to all files unless overridden)
[references.defaults]
separators = ["-", "_"]           # Separator characters to accept
case_sensitive = false            # Case-insensitive matching
prefix_optional = false           # Prefix (e.g., "REQ") required
comment_styles = ["#", "//", "--"]  # Recognized comment markers

# Keywords for different reference types
[references.defaults.keywords]
implements = ["Implements", "IMPLEMENTS"]
validates = ["Validates", "Tests", "VALIDATES", "TESTS"]
refines = ["Refines", "REFINES"]

# File-type specific overrides
[[references.overrides]]
match = "*.py"
separators = ["_"]                # Python uses underscores
keywords.validates = ["Tests", "Validates"]

[[references.overrides]]
match = "*.java"
separators = ["_"]
comment_styles = ["//"]           # Java uses // comments

[[references.overrides]]
match = "*.go"
separators = ["_"]
case_sensitive = true             # Go is case-sensitive
comment_styles = ["//"]

[[references.overrides]]
match = "*.sql"
separators = ["-"]
comment_styles = ["--"]           # SQL uses -- comments

[[references.overrides]]
match = "tests/legacy/**"
prefix_optional = true            # Legacy tests don't have REQ- prefix
```

### Files to Modify

| File | Changes |
|------|---------|
| `src/elspais/config/__init__.py` | Add `references` section to DEFAULT_CONFIG |

## Phase 1 ✓

- [x] 1.1 Add `references` key to DEFAULT_CONFIG with defaults and empty overrides
- [x] 1.2 Ensure config merging works correctly for nested structures
