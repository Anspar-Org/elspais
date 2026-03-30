# DEFINED TERMS

Defined terms provide controlled vocabulary for requirements documents. Each term has exactly one authoritative definition, and elspais tracks where terms are defined, referenced, and used. This is essential in regulated environments (e.g., FDA 21 CFR Part 11) where auditors expect a traceable glossary.

## Defining a Term

Use standard Markdown definition list syntax in any spec file:

```
Electronic Record
: Any combination of text, graphics, data, audio, or pictorial
  information stored in digital form.
```

Rules:
- Term name is a line of text followed by `:` on the next line
- Definition continues on subsequent `:` lines (multi-line supported)
- A blank line is required before and after each definition block
- Each term must be defined exactly once across all spec files

### Metadata Flags

Add metadata on additional `:` lines after the definition:

```
Questionnaire
: A structured set of questions administered to a participant.
: Collection: true

Level
: The classification tier of a requirement (PRD, OPS, DEV).
: Indexed: false
```

| Flag | Default | Effect |
|------|---------|--------|
| `Collection: true` | `false` | Term gets its own collection manifest file |
| `Indexed: false` | `true` | Suppresses index entries and unmarked-usage health check |

## Referencing Terms

Use Markdown emphasis in prose text:

```
The *electronic record* must be stored securely.
All **electronic record** instances are encrypted at rest.
```

References are matched case-insensitively against the term dictionary. They are detected in body text, rationale, named block content, journey content, and assertion text.

### Three-Way Classification

Each occurrence of a defined term in prose is classified into one of three categories:

| Classification | Meaning | Example |
|----------------|---------|---------|
| **Marked** | Term wrapped in a configured `markup_styles` delimiter | `*electronic record*` or `**electronic record**` |
| **Wrong-marking** | Term wrapped in emphasis NOT listed in `markup_styles` | `~~electronic record~~` when only `*` and `**` are configured |
| **Unmarked** | Plain text occurrence of an indexed term | `electronic record` with no emphasis |

The `markup_styles` config option (default: `["*", "**"]`) controls which Markdown emphasis delimiters count as "marked". Any emphasis delimiter not in this list produces a wrong-marking finding.

## Placement Rules

Definition blocks are allowed in:
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

## Health Checks

Six term-related checks appear in `elspais checks` under the **Terms** category:

| Check | Default Severity | Description |
|-------|-----------------|-------------|
| `terms.duplicates` | error | Same term defined in two locations |
| `terms.undefined` | warning | `*token*` or `**token**` with no matching definition |
| `terms.unmarked` | warning | Indexed term used in prose without markup, or with wrong markup |
| `terms.unused` | warning | Defined term with zero references anywhere |
| `terms.bad_definition` | error | Term with blank or trivial definition text |
| `terms.collection_empty` | warning | Collection term (`Collection: true`) with no references |

Example output:

```
Terms:
  2 defined terms (1 collection)
  WARN: Possible undefined term 'Flowchart' in REQ-p00003-B (prd-core.md:47)
  WARN: Unmarked usage of 'Electronic Record' in REQ-d00045 (dev-records.md:12)
  ERROR: Duplicate definition of 'Audit Trail' in prd-core.md:23 and prd-compliance.md:56
  WARN: Unused term 'Legacy System' defined in prd-core.md:80
  ERROR: Bad definition for 'TBD' in ops-spec.md:15 — blank body
  WARN: Collection term 'Questionnaire' has no references
```

## CLI Commands

### `elspais glossary`

Generate a glossary from all defined terms:

```bash
elspais glossary                    # Markdown to stdout
elspais glossary --format json      # JSON to stdout
```

### `elspais term-index`

Generate a term index with reference locations:

```bash
elspais term-index                  # Markdown to stdout
elspais term-index --format json    # JSON to stdout
```

### `elspais fix`

The `fix` command auto-generates glossary, term index, and collection manifests alongside other generated artifacts.

## Generated Output

Output goes to `spec/_generated/` by default (configurable via `[terms] output_dir`).

All generated files include an auto-generation header and should not be edited manually.

### Glossary (`glossary.md`)

Alphabetically organized with letter headings:

```
# Glossary

## E

**Electronic Record**
: Any combination of text, graphics, data, audio, or pictorial
  information stored in digital form.
*Defined in: prd-core.md (main)*
```

### Term Index (`term-index.md`)

Only indexed terms. References grouped by namespace:

```
# Term Index

## Electronic Record

**main:**
- REQ-p00003
- REQ-p00003-B
- REQ-d00045
```

### Collection Manifests (`collections/<term>.md`)

One file per term with `Collection: true`, listing all reference locations.

## Configuration

In `.elspais.toml`:

```toml
[terms]
# Where generated files go (relative to repo root)
output_dir = "spec/_generated"

# Which markdown emphasis delimiters count as "marked" term references
markup_styles = ["*", "**"]       # default: italic and bold

# Glob patterns to skip during term reference scanning
exclude_files = []

# Severity levels for defined-terms health checks
# Each value is "error" | "warning" | "off"
[terms.severity]
duplicate = "error"               # same term defined in two locations
undefined = "warning"             # bold/italic token with no definition
unmarked = "warning"              # known term used without markup
unused = "warning"                # defined term never referenced
bad_definition = "error"          # malformed definition block
collection_empty = "warning"      # collection term with no references
```

## Comment Extraction for Code/Test Files

Term references are also scanned inside comments in code and test files. The extraction strategy depends on the language:

- **Python files**: Uses `ast.parse()` for 100% accurate comment and docstring extraction (immune to multiline strings and other syntax that could mislead regex)
- **Other languages**: Uses regex-based extraction matching common comment styles (`#`, `//`, `/* */`, etc.)

Note: Regex-based comment extraction may produce false positives in some edge cases (e.g., comment-like patterns inside string literals in non-Python files). If this causes noisy findings, use `exclude_files` to skip those files from term scanning.

## Related Check: `code.no_traceability`

While not a terms check, `code.no_traceability` (configured in `[rules.format]`) is closely related to the terms workflow. It reports code and test files that contain no traceability markers at all -- no `Implements:`, `Verifies:`, or REQ-xxx references in comments. This helps identify source files that have not been linked to any requirement.

**Configuration:**

```toml
[rules.format]
no_traceability_severity = "info"   # or "warning" or "error"
```

## Multi-Repo Support

In federated setups with `[associates]`:
- Each repo builds its own term dictionary during parsing
- Dictionaries merge during federation -- duplicates across repos are flagged
- Reference resolution runs after federation (a term defined in repo A can be referenced in repo B)
- Generated output groups references by namespace
