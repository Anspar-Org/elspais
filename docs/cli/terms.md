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

Three term-related checks appear in `elspais checks` under the **Terms** category:

| Check | Default Severity | Description |
|-------|-----------------|-------------|
| `terms.duplicates` | error | Same term defined in two locations |
| `terms.undefined` | warning | `*token*` or `**token**` with no matching definition |
| `terms.unmarked` | warning | Indexed term used in prose without `*...*` or `**...**` markup |

Example output:

```
Terms:
  2 defined terms (1 collection)
  WARN: Possible undefined term 'Flowchart' in REQ-p00003-B (prd-core.md:47)
  WARN: Unmarked usage of 'Electronic Record' in REQ-d00045 (dev-records.md:12)
  ERROR: Duplicate definition of 'Audit Trail' in prd-core.md:23 and prd-compliance.md:56
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

# Severity for duplicate definitions (same term, two locations)
duplicate_severity = "error"      # "error" | "warning" | "off"

# Severity for undefined terms (bold/italic token with no definition)
undefined_severity = "warning"    # "error" | "warning" | "off"

# Severity for unmarked usage of indexed terms in prose
unmarked_severity = "warning"     # "error" | "warning" | "off"
```

## Multi-Repo Support

In federated setups with `[associates]`:
- Each repo builds its own term dictionary during parsing
- Dictionaries merge during federation -- duplicates across repos are flagged
- Reference resolution runs after federation (a term defined in repo A can be referenced in repo B)
- Generated output groups references by namespace
