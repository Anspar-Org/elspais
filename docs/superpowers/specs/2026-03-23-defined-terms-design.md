# Defined Terms: Glossary, Index, and Collection Manifests

## Motivation

In regulated environments (e.g., FDA 21 CFR Part 11), requirements documents must use controlled vocabulary. When a term like "electronic record" appears, there must be exactly one unambiguous definition, and auditors expect a traceable glossary. Beyond regulatory compliance, collecting tagged instances of concept classes (e.g., all Questionnaires, all Notifications) provides authoritative catalogs generated from the source material rather than hand-maintained.

## Overview

Defined terms are authored inline in spec files using Markdown definition list syntax. elspais parses them, collects them into a term dictionary on the graph, resolves references, and generates three output artifacts:

- **Glossary** — all defined terms with their definitions
- **Term Index** — all indexed terms with every location they are referenced
- **Collection Manifests** — one file per "collection" term listing all reference sites

## Syntax

### Definition Blocks

Standard Markdown definition list syntax, with optional metadata lines:

```markdown
Electronic Record
: Any combination of text, graphics, data, audio, or pictorial
  information stored in digital form.

Questionnaire
: A structured set of questions administered to a participant.
: Collection: true

Level
: The classification tier of a requirement (PRD, OPS, DEV).
: Indexed: false
```

Rules:

- Term name is a line of text followed by `\n: ` on the next line
- Definition continues on subsequent `: ` lines (multi-line supported)
- Special metadata lines: `: Collection: true`, `: Indexed: false`
- A blank line is required before and after each definition block
- Multiple definitions can appear in sequence (blank line between each)

### Metadata Flags

| Flag | Default | Effect |
|------|---------|--------|
| `Collection: true` | `false` | Term gets its own manifest file |
| `Indexed: false` | `true` | Suppresses index entries and unmarked-usage health check |

### Term References

Normal Markdown emphasis in prose text:

- `*electronic record*` (italic)
- `**electronic record**` (bold)

Matched case-insensitively against the term dictionary. References are detected in body text, rationale, named block content, journey content, and assertion text.

### Duplicate Definitions

If the same term (case-insensitive) is defined in two locations, this is an error by default, regardless of whether the definition text matches. Two definition sites create ambiguity about which is authoritative.

## Placement Rules

Definition blocks are allowed in any prose context:

- Between requirements (file level)
- Requirement preamble (body text before first `##` heading)
- Named blocks (`## Rationale`, `## Context`, etc.)
- Journey preamble and sections
- REMAINDER blocks

Definition blocks are NOT allowed in:

- `## Assertions` blocks
- `## Changelog` blocks
- Metadata lines

Term references (`*term*` / `**term**`) are allowed everywhere prose appears, including assertion text.

## Data Model

Terms are stored as a `TermDictionary` on `TraceGraph._terms`, populated during graph construction. `TermDictionary` is a lightweight wrapper around a dict, not a graph node type.

```python
@dataclass
class TermEntry:
    term: str              # display form (original casing)
    definition: str        # full definition text (metadata lines stripped)
    collection: bool       # generates its own manifest
    indexed: bool          # True by default; False suppresses index + health check
    defined_in: str        # node ID of nearest REQUIREMENT or FILE ancestor
    defined_at_line: int   # for error reporting
    namespace: str         # repo namespace (e.g., "main", "sponsor-a")
    references: list[TermRef]

@dataclass
class TermRef:
    node_id: str           # enclosing element (REQ, ASSERTION, REMAINDER)
    namespace: str         # repo where the reference occurs
    marked: bool           # True = *term*/**term**, False = plain text
    line: int              # for error reporting

class TermDictionary:
    """Term index, keyed by normalized (lowercased) term name."""
    _entries: dict[str, TermEntry]

    def add(self, entry: TermEntry) -> None: ...
    def lookup(self, term: str) -> TermEntry | None: ...
    def iter_all(self) -> Iterator[TermEntry]: ...
    def iter_indexed(self) -> Iterator[TermEntry]: ...
    def iter_collections(self) -> Iterator[TermEntry]: ...
```

`TraceGraph._terms: TermDictionary` is populated by `GraphBuilder` during construction. `FederatedGraph` aggregates per-repo dictionaries via a merge method.

### `defined_in` Semantics

The `defined_in` field stores the nearest REQUIREMENT or FILE ancestor node ID — not the REMAINDER node itself. This ensures glossary attribution (e.g., "Defined in: prd-core.md (main)") can always resolve to a meaningful location.

### Multi-Repo Aggregation

- Each `TraceGraph` builds its own `_terms` during parsing
- `FederatedGraph` merges them into a single `TermDictionary`: duplicate detection runs across namespaces
- Reference resolution runs after federation — a term defined in repo A can be referenced in repo B
- Generated output groups references by namespace

## Pipeline

### 1. Parser (Lark Grammar Extension)

Definition blocks are parsed as first-class grammar rules. The key insight is that the `: definition text` continuation line is a distinctive terminal (`DEF_LINE`), providing the 1-token LALR lookahead needed to distinguish a definition block from a regular text line.

After the parser shifts `TEXT _NL`, the next token resolves the ambiguity:
- `DEF_LINE` → shift, building a `definition_block`
- Anything else → reduce to `remainder_line` / `body_line`

Grammar additions to `requirement.lark`:

```
// New terminal — definition continuation line (higher priority than TEXT)
DEF_LINE.3: /: [^\n]+/

// Top level (between requirements)
_item: requirement
     | journey
     | definition_block
     | stray_marker
     | remainder_line
     | _NL

// Inside requirement body
?preamble_line: metadata_line
              | satisfies_line
              | definition_block
              | body_line

// Inside named blocks (## Rationale, etc.)
content_line: definition_block
            | TEXT _NL
            | _NL

// Journey contexts
jny_body_line: definition_block
             | TEXT _NL
             | _NL

jny_content_line: definition_block
                | TEXT _NL
                | _NL

// The definition block rule
definition_block: TEXT _NL (DEF_LINE _NL)+
```

Definition blocks are NOT added to `assertion_item` or `changelog_block` — the grammar enforces placement rules structurally.

**Transformer** — a `definition_block` handler in the requirement transformer extracts:
- Term name (from the TEXT token)
- Definition text and metadata flags (from DEF_LINE tokens)
- Returns a `ParsedContent` with `content_type="definition_block"`

**Candidate reference extraction** — the transformer also collects `*...*` and `**...**` tokens from TEXT, ASSERT_CONT, and body content as candidate references for deferred resolution.

### 2. Graph Builder (Deferred Resolution)

After all files are parsed:

1. Collect all term definitions into `TraceGraph._terms`
2. Flag duplicate definitions (same term, two locations)
3. Resolve candidate references against the term dictionary (case-insensitive)
4. Matched candidates become `TermRef` entries on the `TermEntry`
5. Unmatched candidates flagged per `undefined_severity` (excluding known structural patterns: `*End*`, metadata field names, assertion sub-headings, section headers)

### 3. Rendering and Round-Trip Fidelity

Definition blocks are stored as `REMAINDER` nodes with `content_type: "definition_block"` stored as a `GraphNode` field (via `set_field("content_type", "definition_block")`):

- File-level definitions: REMAINDER node with CONTAINS edge from FILE
- Requirement-level definitions: REMAINDER node with STRUCTURES edge from REQUIREMENT

The `_render_remainder()` function in `render.py` is extended to check `node.get_field("content_type")`: if `"definition_block"`, it renders using definition list syntax; otherwise, it returns raw text as before. `render_order` metadata preserves original file position. This ensures definition blocks survive `render_save()` mutations unchanged.

## Health Checks

Three term-related checks, each with configurable severity:

### Duplicate Definitions (`duplicate_severity`: error)

```
ERROR: Duplicate definition of 'Audit Trail'
  - prd-core.md:23 (in REQ-p00001)
  - prd-compliance.md:56 (between requirements)
```

### Undefined Terms (`undefined_severity`: warning)

```
WARN: Possible undefined term 'Flowchart' in REQ-p00003-B (prd-core.md:47)
```

A `*token*` or `**token**` in prose that doesn't match any defined term and doesn't match a known structural pattern.

### Unmarked Usage (`unmarked_severity`: warning)

```
WARN: Unmarked usage of 'Electronic Record' in REQ-d00045 (dev-records.md:12)
```

Whole-word, case-insensitive match of an indexed term in prose text without `*...*` or `**...**` markup. Only checked for terms where `Indexed: true` (the default). Plural/inflection matching is deferred — only exact whole-word matches are detected in v1. This is the safety net: an auditor will interpret the term regardless of whether the author marked it up.

### Integration

These appear as a `Terms` section in `elspais checks` output:

```
Terms:
  2 defined terms (1 collection)
  WARN: Possible undefined term 'Flowchart' in REQ-p00003-B (prd-core.md:47)
  WARN: Unmarked usage of 'Electronic Record' in REQ-d00045 (dev-records.md:12)
  ERROR: Duplicate definition of 'Audit Trail' in prd-core.md:23 and prd-compliance.md:56
```

## Generated Output

### Location

`spec/_generated/` by default, configurable via `[terms] output_dir`.

All generated files include:

```markdown
<!-- Auto-generated by: elspais fix -->
<!-- Do not edit manually; changes will be overwritten. -->
```

### Glossary (`spec/_generated/glossary.md`)

Alphabetically organized with letter headings:

```markdown
# Glossary

## E

**Electronic Record**
: Any combination of text, graphics, data, audio, or pictorial
  information stored in digital form.
*Defined in: prd-core.md (main)*

## L

**Level** *(not indexed)*
: The classification tier of a requirement (PRD, OPS, DEV).
*Defined in: prd-core.md (main)*

## Q

**Questionnaire** *(collection)*
: A structured set of questions administered to a participant.
*Defined in: prd-clinical.md (main)*
```

### Term Index (`spec/_generated/term-index.md`)

Only indexed terms. References grouped by namespace, one per line:

```markdown
# Term Index

## Electronic Record

**main:**
- REQ-p00003
- REQ-p00003-B
- REQ-d00045

**sponsor-a:**
- file:src/records/model.dart

## Questionnaire

**main:**
- REQ-p00012
- REQ-p00012-A

**sponsor-a:**
- REQ-d00067-C
- file:src/questionnaire/hhc_qol.dart
```

### Collection Manifests (`spec/_generated/collections/<term>.md`)

Same format as a term index entry but standalone — one file per collection term.

### Format Parameter

`--format markdown` (default) or `--format json`. JSON outputs the same data as structured objects.

## Configuration

New `[terms]` section in `.elspais.toml`:

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

### Pydantic Model

```python
class TermsConfig(_StrictModel):
    """Configuration for defined terms feature."""
    output_dir: str = "spec/_generated"
    duplicate_severity: str = "error"    # "error" | "warning" | "off"
    undefined_severity: str = "warning"  # "error" | "warning" | "off"
    unmarked_severity: str = "warning"   # "error" | "warning" | "off"
```

Severity fields use plain `str` with validation, matching the pattern of existing severity config fields in the codebase. Added as `terms: TermsConfig = Field(default_factory=TermsConfig)` on `ElspaisConfig`.

The `elspais init` template includes this section with all options and valid values documented.

## CLI Commands

### New Commands

- `elspais glossary` — generates glossary file
- `elspais term-index` — generates term index and collection manifests
- Both accept `--format markdown|json` and `--output-dir <path>` (overrides config)

### Integration with Existing Commands

- `elspais fix` — calls glossary + term-index generation (same pattern as INDEX.md)
- `elspais checks` — reports term health findings (duplicates, undefined, unmarked)
- `elspais validate` — includes term validation

## Documentation

A new `docs/cli/terms.md` file covering:

- Definition syntax and placement rules
- Reference markup conventions
- Health check descriptions and configuration
- Generated output formats
- Configuration reference
- Examples with FDA/regulatory context

## Deliverables

1. **TermDictionary** — `TermEntry`, `TermRef`, `TermDictionary` data classes in `graph/terms.py`
2. **Grammar extension** — `DEF_LINE` terminal and `definition_block` rule in `requirement.lark`, added to all prose contexts
3. **Transformer** — `definition_block` handler extracting term data; candidate reference collection from prose tokens
4. **TraceGraph extension** — `_terms: TermDictionary` field on `TraceGraph`
5. **GraphBuilder integration** — populate `_terms` during `build_graph()`, deferred resolution of references
6. **FederatedGraph extension** — cross-repo `TermDictionary` merge
7. **Render extension** — extend `_render_remainder()` to check `content_type` field for definition blocks
8. **Health checks** — three new checks with configurable severity
9. **CLI commands** — `elspais glossary`, `elspais term-index`, integrated into `elspais fix`
10. **Generators** — glossary.md, term-index.md, collection manifests; `--format markdown|json`
11. **Config schema** — `TermsConfig` Pydantic model, `[terms]` section in `ElspaisConfig`
12. **Init template** — `[terms]` section with all options and valid values documented
13. **Docs** — `docs/cli/terms.md`
14. **Tests** — grammar, transformer, builder, health checks, generators, CLI commands

## Deferred (Not in Scope)

- Viewer: hyperlinks and hover text for defined terms in requirement cards
- Code file scanning for term references (.dart, .py, etc.)
- MCP tools for term lookup and cross-reference queries
- Plural/inflection matching in the unmarked-usage health check
- Term aliasing (multiple surface forms mapping to one definition)
