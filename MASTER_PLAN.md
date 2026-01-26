# Architecture 3.0 Re-implementation Plan

## Overview

Re-implement elspais with Architecture 3.0 in a parallel `arch3/` directory, implementing:
1. **DomainDeserializer** - Unified controller for text domain → graph deserialization
2. **MDparser** - Line-claiming parser system (parsers claim lines in priority order)
3. **Clean Graph module** - GraphNode, relations, annotators separation

## Approach: Parallel Implementation in `src/elspais/arch3/`

Create the new architecture in a separate directory to:
- Preserve original code for reference during development
- Enable side-by-side comparison and validation
- Allow gradual migration without breaking existing functionality

## Target Directory Structure

```
src/elspais/arch3/
├── __init__.py
├── Graph/
│   ├── __init__.py
│   ├── GraphNode.py           # Node definitions (from core/graph.py)
│   ├── relations.py           # Edge definitions (new)
│   ├── annotators.py          # Graph annotations (from core/annotators.py)
│   ├── builder.py             # Graph builder (from core/graph_builder.py)
│   ├── serialize.py           # Graph → output formats
│   ├── DomainDeserializer.py  # Abstract controller
│   │   ├── DomainFile.py      # Directory/file deserializer
│   │   ├── DomainStdio.py     # stdin deserializer
│   │   └── DomainCLI.py       # CLI args deserializer
│   └── MDparser/
│       ├── __init__.py        # LineClaimingParser protocol
│       ├── comments.py        # Priority 0: Comment blocks
│       ├── heredocs.py        # Priority 10: Variables/heredocs
│       ├── requirement.py     # Priority 50: Requirements
│       │   └── assertions.py  # Sub-parser for assertions
│       ├── journey.py         # Priority 60: User journeys
│       ├── code.py            # Priority 70: Code references
│       ├── test.py            # Priority 80: Test references
│       ├── results/
│       │   ├── junit_xml.py   # JUnit XML results
│       │   └── pytest_json.py # Pytest JSON results
│       └── remainder.py       # Priority 999: Unclaimed lines
├── config/
│   ├── __init__.py
│   ├── ConfigLoader.py        # Abstract config loader
│   ├── LoaderFile.py          # TOML file loader
│   ├── LoaderStdio.py         # Stdin config
│   └── defaults.py            # Default configuration
└── utilities/
    ├── __init__.py
    ├── patterns.py            # ID pattern validation
    ├── hasher.py              # Content hashing
    └── git.py                 # Git integration
```

## Real-World Test Data

The `spec/` directory contains real-world requirement specifications that serve as integration test fixtures. Use these for:
- Validating parser behavior against actual spec files
- Testing edge cases in requirement format
- Ensuring output equivalence between old and new architecture

## Implementation Phases

### [x] Phase 1: Foundation (TDD) - COMPLETE

**Files to Create:**
1. `arch3/Graph/GraphNode.py` - Port NodeKind, SourceLocation, TraceNode → GraphNode
2. `arch3/Graph/relations.py` - New: Edge types (implements, refines, validates)
3. `arch3/utilities/patterns.py` - Port from core/patterns.py
4. `arch3/utilities/hasher.py` - Port from core/hasher.py

**Tests First:**
```
tests/arch3/
├── conftest.py
├── test_graph_node.py
└── test_relations.py
```

**Key Test Cases:**
- `test_create_minimal_node` - Node with id and kind
- `test_implements_relation_creates_edge` - Bidirectional linking
- `test_refines_vs_implements_semantics` - Coverage rollup differences

### [x] Phase 2: MDparser Infrastructure - COMPLETE

**Files to Create:**
1. `arch3/Graph/MDparser/__init__.py` - LineClaimingParser protocol
2. `arch3/Graph/MDparser/comments.py` - Priority 0 parser
3. `arch3/Graph/MDparser/remainder.py` - Priority 999 parser

**Core Protocol:**
```python
class LineClaimingParser(Protocol):
    @property
    def priority(self) -> int: ...

    def claim_and_parse(
        self,
        lines: list[tuple[int, str]],  # (line_number, content)
        context: ParseContext,
    ) -> Iterator[ParsedContent]: ...
```

**Tests First:**
```
tests/arch3/test_mdparser/
├── conftest.py
├── test_mdparser_base.py
├── test_comments_parser.py
└── test_remainder_parser.py
```

### [x] Phase 3: Node-Type Parsers - COMPLETE

**Files to Create:**
1. `arch3/Graph/MDparser/requirement.py` - Adapt from core/parser.py
2. `arch3/Graph/MDparser/requirement/assertions.py` - Assertion sub-parser
3. `arch3/Graph/MDparser/journey.py` - Port from parsers/journey.py
4. `arch3/Graph/MDparser/code.py` - Port from parsers/code.py
5. `arch3/Graph/MDparser/test.py` - Port from parsers/test.py

**Tests:**
```
tests/arch3/test_mdparser/
├── test_requirement_parser.py
├── test_assertion_parser.py
├── test_journey_parser.py
├── test_code_parser.py
└── test_test_parser.py
```

### [x] Phase 4: DomainDeserializer - COMPLETE

**Files to Create:**
1. `arch3/Graph/DomainDeserializer.py` - Abstract protocol
2. `arch3/Graph/DomainFile.py` - File/directory iteration
3. `arch3/Graph/DomainStdio.py` - stdin reading
4. `arch3/Graph/DomainCLI.py` - CLI argument parsing

**Core Pattern:**
```python
class DomainDeserializer(Protocol):
    def iterate_sources(self) -> Iterator[tuple[DomainContext, str]]: ...
    def deserialize(self, parsers: list[LineClaimingParser]) -> TraceGraph: ...
```

**Tests:**
```
tests/arch3/test_deserializer/
├── conftest.py
├── test_domain_base.py
├── test_domain_file.py
├── test_domain_stdio.py
└── test_domain_cli.py
```

### [ ] Phase 5: Graph Builder & Serialization

**Files to Create:**
1. `arch3/Graph/builder.py` - Graph building from nodes
2. `arch3/Graph/serialize.py` - Output format generation
3. `arch3/Graph/annotators.py` - Port from core/annotators.py

### [ ] Phase 6: Config Layer

**Files to Create:**
1. `arch3/config/ConfigLoader.py` - Abstract loader
2. `arch3/config/LoaderFile.py` - TOML loading (from config/loader.py)
3. `arch3/config/LoaderStdio.py` - stdin config stripping
4. `arch3/config/defaults.py` - Port from config/defaults.py

### [ ] Phase 7: Integration & Migration

**Integration Tests:**
```
tests/arch3/test_integration/
├── test_pipeline.py            # Full Deserializer → MDparser → Graph
├── test_mcp_compatibility.py   # Verify MCP tools still work
└── test_output_equivalence.py  # Compare old vs new output
```

**Migration Strategy:**
1. Add `ELSPAIS_ARCH3=1` environment flag
2. Create adapter: `arch3/compat.py` wrapping new Graph for old interfaces
3. Update commands to conditionally use arch3
4. Run parallel validation with all fixtures

## Critical Files to Modify/Port

| Source File | Target File | Notes |
|-------------|-------------|-------|
| `core/graph.py` | `arch3/Graph/GraphNode.py` | Port TraceNode, NodeKind, SourceLocation |
| `core/graph_builder.py` | `arch3/Graph/builder.py` | Adapt to use relations.py |
| `core/parser.py` | `arch3/Graph/MDparser/requirement.py` | Adapt to line-claiming |
| `core/patterns.py` | `arch3/utilities/patterns.py` | Direct port |
| `core/hasher.py` | `arch3/utilities/hasher.py` | Direct port |
| `core/annotators.py` | `arch3/Graph/annotators.py` | Direct port |
| `parsers/__init__.py` | `arch3/Graph/MDparser/__init__.py` | Evolve SpecParser → LineClaimingParser |
| `parsers/journey.py` | `arch3/Graph/MDparser/journey.py` | Adapt to line-claiming |
| `parsers/code.py` | `arch3/Graph/MDparser/code.py` | Adapt to line-claiming |
| `parsers/test.py` | `arch3/Graph/MDparser/test.py` | Adapt to line-claiming |
| `config/loader.py` | `arch3/config/LoaderFile.py` | Split into loader hierarchy |

## TDD Implementation Order

| # | Component | Test File | Depends On |
|---|-----------|-----------|------------|
| 1 | GraphNode | `test_graph_node.py` | None |
| 2 | Relations | `test_relations.py` | GraphNode |
| 3 | MDparser base | `test_mdparser_base.py` | None |
| 4 | CommentsParser | `test_comments_parser.py` | MDparser |
| 5 | RemainderParser | `test_remainder_parser.py` | MDparser |
| 6 | RequirementParser | `test_requirement_parser.py` | MDparser |
| 7 | AssertionParser | `test_assertion_parser.py` | RequirementParser |
| 8 | JourneyParser | `test_journey_parser.py` | MDparser |
| 9 | DomainDeserializer | `test_domain_base.py` | MDparser |
| 10 | DomainFile | `test_domain_file.py` | DomainDeserializer |
| 11 | Graph Builder | `test_builder.py` | GraphNode, Relations |
| 12 | Pipeline Integration | `test_pipeline.py` | All above |
| 13 | MCP Compatibility | `test_mcp_compatibility.py` | Pipeline |

## Verification Plan

### Unit Tests
```bash
# Run arch3 tests only
pytest tests/arch3/ -v

# Run with coverage
pytest tests/arch3/ --cov=src/elspais/arch3
```

### Integration Tests
```bash
# Compare outputs between architectures
pytest tests/arch3/test_integration/test_output_equivalence.py -v
```

### Manual Validation
```bash
# Enable arch3 mode
export ELSPAIS_ARCH3=1

# Test CLI commands
elspais validate
elspais trace --graph
elspais analyze hierarchy

# Test MCP server
elspais mcp
```

### Fixture Coverage
- Use existing fixtures: `hht-like`, `fda-style`, `jira-style`, `assertions`
- Add new fixtures for line-claiming edge cases

## Constraints

1. **Zero Dependencies** - Must not add external packages
2. **Python 3.9+** - Use compatible typing syntax
3. **Backward Compatibility** - CLI and MCP interfaces unchanged
4. **Config Format** - `.elspais.toml` format preserved

## Success Criteria

1. All existing tests pass (via adapters if needed)
2. All fixtures produce equivalent output
3. MCP tools work identically
4. Line-claiming exhaustive (every line assigned to exactly one node)
5. Performance comparable to current implementation
