# Defined Terms

elspais supports inline glossary definitions using Markdown definition-list syntax.
Terms are parsed during graph construction, validated by health checks, and used to
generate glossary, index, and collection manifest outputs.

## Definition Syntax

Standard Markdown definition lists with optional metadata:

```markdown
Electronic Record
: Any combination of text, graphics, data, audio, or pictorial
  information stored in digital form.
```

Metadata flags follow the definition text on separate `:` lines:

| Flag | Default | Effect |
|------|---------|--------|
| `Collection: true` | `false` | Term gets its own collection manifest file |
| `Indexed: false` | `true` | Suppresses index entries and unmarked-usage health check |

## Reference-Type Definitions

External standards and regulatory documents can be defined as reference-type terms.
Add `: Reference` as a metadata line, then provide structured citation fields:

```markdown
21 CFR Part 11
: FDA regulation governing electronic records and electronic signatures.
: Reference
: Title: 21 CFR Part 11 - Electronic Records; Electronic Signatures
: Version: 2024-03
: Effective Date: 1997-08-20
: URL: https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-11
```

Supported citation fields (all optional):

- **Title** -- full document title
- **Version** -- version or revision identifier
- **Effective Date** -- date the standard became effective
- **URL** -- link to the authoritative source

Reference fields are included in the definition hash, so changes to citation
metadata (e.g., a new version) are detected by change tracking.

## Synonym and Alias Support

A term can declare that it is a synonym for an official name in a reference
document using `: Reference Term:` and `: Reference Source:` metadata:

```markdown
e-signature
: An electronic equivalent of a handwritten signature.
: Reference Term: Electronic Signature
: Reference Source: 21 CFR Part 11
```

This links the local term to the canonical name in the referenced standard.
The glossary output displays the synonym relationship, and health checks
validate that the referenced source term exists in the term dictionary.

## Term References

Terms are referenced in prose using Markdown emphasis:

- `*electronic record*` (italic)
- `**electronic record**` (bold)

Matching is case-insensitive. The configured `markup_styles` (default `["*", "**"]`)
control which delimiters are recognized. References are detected in body text,
rationale, named blocks, journey content, and assertion text.

## Definition Change Tracking

Each term definition is hashed (SHA-256, 8 chars) at parse time. The hash covers
the definition text and all reference fields (title, version, effective date, URL).
This enables:

- **`diff_terms(old, new)`** -- compares two `TermDictionary` snapshots and returns
  added, removed, and changed terms with their old/new hashes.
- **`changed` severity** -- the health check flags definitions whose content has
  changed since the last reviewed baseline. Set `terms.severity.changed` to
  `"error"`, `"warning"`, or `"off"`.

## MCP Tools

Three MCP tools provide programmatic access to term data:

- **`get_terms(kind?)`** -- list all terms, optionally filtered by kind
  (`"all"`, `"indexed"`, `"collection"`). Returns term name, definition,
  metadata flags, and reference count.

- **`get_term_detail(term)`** -- full detail for a single term including
  definition text, reference fields, synonym info, definition hash,
  and all reference locations (node ID, line, marked/unmarked).

- **`search_terms(query)`** -- free-text search across term names and
  definitions. Returns matching terms ranked by relevance.

## Configuration Reference

All settings live under `[terms]` in `.elspais.toml`:

```toml
[terms]
# Where generated glossary/index files go (relative to repo root)
output_dir = "spec/_generated"

# Which markdown emphasis delimiters count as "marked" term references
# Default: ["*", "**"] (italic and bold)
markup_styles = ["*", "**"]

# Glob patterns to skip during term reference scanning
exclude_files = []

# Severity levels for defined-terms health checks
# Each value is "error" | "warning" | "off"
[terms.severity]
duplicate = "error"           # same term defined in two locations
undefined = "warning"         # bold/italic token with no definition
unmarked = "warning"          # known term used without markup
unused = "warning"            # defined term never referenced
bad_definition = "error"      # malformed definition block
collection_empty = "warning"  # collection term with no references
canonical_form = "warning"    # term used in non-canonical form (case/spelling)
changed = "warning"           # definition content changed, pending review
```
