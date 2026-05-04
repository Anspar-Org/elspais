# Core Product Requirements

# REQ-p00001: Requirements Management Tool

**Level**: prd | **Status**: Active | **Implements**: -

## Rationale

Software projects—especially those subject to regulatory oversight (medical devices, aerospace, automotive)—require formal requirements that are validated, traceable, and auditable. Traditional requirements management tools are heavyweight, expensive, and poorly integrated with modern development workflows.

elspais addresses this gap by providing a lightweight, file-based requirements management system that:

- Lives alongside code in version control
- Uses plain Markdown for human readability
- Validates structure and relationships automatically
- Integrates with CI/CD pipelines
- Supports AI-assisted workflows

The name derives from Terry Pratchett's "L-Space"—the dimension where all libraries connect through accumulated knowledge.

## Assertions

A. The tool SHALL provide command-line validation of requirement documents stored as Markdown files.

B. The tool SHALL generate *Traceability* matrices showing requirement relationships.

C. The tool SHALL detect changes to requirements using content hashing and git integration.

D. [DEPRECATED]

## Changelog

- 2026-04-23 | ce489de6 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Requirements Management Tool* | **Hash**: ce489de6
---

# REQ-p00002: Requirements Validation

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001

## Rationale

Requirements documents are only useful if they follow a consistent structure. Inconsistent formatting, broken links between requirements, and outdated content hashes undermine the reliability of the requirements baseline.

Automated validation catches these issues early, before they propagate into design documents, test plans, and regulatory submissions. Validation must be fast enough to run on every commit and flexible enough to accommodate different organizational conventions.

The validation system enforces:

- **Format compliance**: Headers, metadata, *Assertion* sections, and hash footers follow the canonical grammar
- **Hierarchy integrity**: Child requirements correctly reference parents; no circular dependencies
- ****Traceability** completeness**: All requirements are reachable from root-level product requirements
- **Content freshness**: Hashes match current content; changes are intentional

## Assertions

A. The tool SHALL validate requirement format against configurable patterns and rules.

B. The tool SHALL detect and report hierarchy violations including circular dependencies and orphaned requirements.

C. The tool SHALL verify content hashes match requirement body text.

## Changelog

- 2026-03-30 | e8f0e4eb | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Requirements Validation* | **Hash**: e8f0e4eb
---

# REQ-p00003: Traceability Matrix Generation

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001

## Rationale

Regulatory submissions and internal reviews require evidence that high-level product requirements flow down to detailed specifications and test coverage. A *Traceability* matrix provides this view—showing which detailed requirements implement which product requirements, and which tests verify which specifications.

Manual maintenance of *Traceability* matrices is error-prone and quickly becomes stale. Automated generation from the `Implements:` metadata in requirement documents ensures the matrix always reflects the current state of the requirements baseline.

Multiple output formats serve different audiences:

- **Markdown**: Embeddable in documentation
- **HTML**: Interactive viewing with clickable links
- **CSV**: Import into spreadsheets or compliance tools

## Assertions

A. The tool SHALL generate *Traceability* matrices in Markdown, HTML, and CSV formats.

B. The tool SHALL derive *Traceability* from `Implements:` metadata without manual matrix maintenance.

## Changelog

- 2026-04-23 | 6a3a9426 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Traceability Matrix Generation* | **Hash**: 6a3a9426
---

# REQ-p00004: Change Detection and Auditability

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001

## Rationale

Requirements change over time. Regulators and auditors need to know what changed, when, and whether downstream artifacts (tests, code, documentation) have been updated accordingly.

elspais provides two complementary change detection mechanisms:

- **Content hashing**: A SHA-256 hash of each requirement's body is stored in the document footer. When the hash no longer matches the content, the requirement has changed and downstream artifacts may need review.
- **Git integration**: The tool detects uncommitted changes, changes relative to the main branch, and requirements that have moved between files.

Together, these mechanisms support:

- Pre-commit validation (catch accidental changes)
- Pull request review (see exactly what requirements changed)
- Audit trails (link requirement changes to commits)

## Assertions

A. The tool SHALL compute and verify content hashes for change detection.

B. The tool SHALL detect uncommitted and branch-relative changes to requirement files using git.

C. The tool SHALL provide a git status summary reporting current branch, main-branch detection, dirty spec files, and remote divergence state.

D. The tool SHALL create and switch to a new git branch, using stash to preserve dirty working tree changes across the switch.

E. The tool SHALL commit modified spec files and optionally push, refusing to operate on main/master branches.

F. The tool SHALL fetch and fast-forward-merge from the remote tracking branch, aborting if the merge is not fast-forwardable.

G. The tool SHALL flag all requirements with SATISFIES edges for review when the referenced template's content hash changes.

H. The tool SHALL list all local and remote git branches, stripping remote prefixes and deduplicating branches that exist both locally and remotely.

I. The tool SHALL switch to an existing local or remote git branch, refusing if in-memory mutations are pending, and falling back from remote checkout to local checkout when the local branch already exists.

J. The tool SHALL re-read configuration from disk when reloading the graph, ensuring branch switches with different configurations produce correct rebuilds.

## Changelog

- 2026-04-23 | f8ff5509 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Change Detection and Auditability* | **Hash**: f8ff5509
---

# REQ-p00013: Automated Testing

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001

## Rationale

A requirements management tool must itself be rigorously tested to maintain credibility. Unit tests verify individual components in isolation, but integration and end-to-end tests are essential to catch cross-component failures, CLI subprocess regressions, and real-world workflow breakages that mocked unit tests miss.

The testing strategy follows a pyramid:

- **Unit tests**: Fast, isolated tests for individual functions and classes
- **Integration tests**: Tests that exercise multiple components together
- **End-to-end tests**: Subprocess-based tests that invoke the CLI binary and verify real output
- **Self-validation**: The tool validates its own repository as the strongest regression test

## Assertions

A. The project SHALL maintain unit tests for all core modules with *Assertion*-linked test names.

B. The project SHALL maintain end-to-end tests that invoke the CLI as a subprocess and verify command output, exit codes, and file artifacts.

C. The project SHALL include self-validation tests that run elspais against its own repository and assert health, summary, and trace outputs are correct.

D. The project SHALL include multi-command workflow tests that verify cross-command consistency and sequential operation correctness.

E. The project SHALL include MCP protocol tests that verify tool invocation, search, cursor pagination, and mutation roundtrips via the stdio transport.

F. All tests marked `@pytest.mark.e2e` SHALL invoke the `elspais` CLI as a subprocess. Tests that call internal Python functions or submodules directly SHALL NOT be marked e2e; they are unit or integration tests.

## Changelog

- 2026-04-23 | 962216d8 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Automated Testing* | **Hash**: 962216d8
---

## REQ-p00061: Requirement Decomposition Rules

**Level**: prd | **Status**: Active | **Implements**: -

A child requirement refines a parent when it adds specificity, constraints, or commits to mechanisms or guarantees.

## Assertions

A. A child requirement that adds specificity, constraints, or commits to mechanisms or guarantees SHALL declare its parent requirement using `Implements:` or `Refines:` in its metadata block.

B. `Implements:` and `Refines:` declarations apply to requirements only; code references and test nodes use their own linkage mechanisms.

C. Multiple requirements MAY exist at the same Level each declaring a relationship to the same parent requirement.

## Changelog

- 2026-04-23 | fc1e85fe | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Requirement Decomposition Rules* | **Hash**: fc1e85fe
---

# REQ-p00080: Spec-to-PDF Compilation

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001

## Rationale

UAT documentation review requires formal PDF output with professional formatting. A single compiled document with table of contents, per-requirement page breaks, and a topic index enables offline review, regulatory submission, and stakeholder sign-off. Currently, spec files exist only as Markdown with no PDF generation pipeline.

The `elspais pdf` command compiles requirement spec files into a professional PDF using Pandoc and LaTeX. Python assembles a clean Markdown document from the *Traceability* graph; a custom LaTeX template controls formatting; Pandoc handles Markdown-to-LaTeX conversion.

## Assertions

A. The tool SHALL provide an `elspais pdf` CLI command that compiles spec files into a PDF document.

B. The assembled Markdown SHALL group requirements by level (PRD, OPS, DEV) with each level as a top-level section, and order files within each level by graph depth (root requirements first).

C. The generated PDF SHALL include an auto-generated table of contents derived from requirement headings.

D. The tool SHALL generate an alphabetized topic index with entries derived from filename words, file-level Topics lines, and requirement-level Topics lines, rendered as a Markdown section with hyperlinks.

E. The tool SHALL insert page breaks before each requirement heading to ensure each requirement starts on a new page.

F. The tool SHALL support an `--overview` flag that generates a stakeholder-oriented PDF containing only PRD-level requirements, with an optional `--max-depth` flag to limit core PRD graph depth while always including all associated-repo PRDs.

## Changelog

- 2026-04-23 | bfc0cadf | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Spec-to-PDF Compilation* | **Hash**: bfc0cadf
---

## REQ-d00220: TermDictionary Data Model

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

## Assertions

A. `TermDictionary.add()` SHALL store a `TermEntry` keyed by normalized (lowercased) term name. If the term already exists, it SHALL return the existing entry without overwriting.

B. `TermDictionary.lookup()` SHALL perform case-insensitive lookup and return the `TermEntry` or `None`.

C. `TermDictionary.iter_indexed()` SHALL yield only entries where `indexed` is `True`. `iter_collections()` SHALL yield only entries where `collection` is `True`.

D. `TermDictionary.merge()` SHALL combine two dictionaries and return a list of `(TermEntry, TermEntry)` pairs for duplicate terms detected across namespaces.

E. `TermRef` SHALL have a `wrong_marking` field (str, default "") that records the incorrect emphasis delimiter used (e.g., `"__"` when the configured markup_styles are `["*", "**"]`). When non-empty, `marked` SHALL be `False`.

## Changelog

- 2026-04-23 | 0d0fd97c | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *TermDictionary Data Model* | **Hash**: 0d0fd97c

<!-- markdownlint-disable MD038 -->

## REQ-d00221: Grammar Extension for Definition Blocks

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

## Assertions

A. The grammar SHALL include a `DEF_LINE` terminal matching `: ` followed by non-newline text, a `CONT_LINE` terminal matching two or more leading spaces followed by non-newline text, and a `definition_block` rule matching `TEXT _NL (DEF_LINE _NL (CONT_LINE _NL)*)+`. Continuation lines SHALL attach to the preceding `DEF_LINE` and be joined with a newline before metadata classification. The `definition_block` rule SHALL be an alternative in `_item`, `preamble_line`, `content_line`, `jny_body_line`, and `jny_content_line` but NOT in `assertion_item` or `changelog_block`.

B. The transformer SHALL handle `definition_block` nodes by extracting the term name from the TEXT token, definition text from DEF_LINE tokens, and metadata flags (Collection, Indexed) from definition lines. It SHALL return a `ParsedContent` with `content_type="definition_block"` and parsed_data containing `term`, `definition`, `collection`, and `indexed` fields.

## Changelog

- 2026-04-24 | 6adaa258 | - | Developer (dev@example.com) | Auto-fix: update hash
- 2026-04-23 | 078ce203 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Grammar Extension for Definition Blocks* | **Hash**: 6adaa258

## REQ-d00222: TraceGraph Terms and GraphBuilder Integration

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

## Assertions

A. `TraceGraph` SHALL have a `_terms: TermDictionary` field. `GraphBuilder` SHALL handle `content_type == "definition_block"` by creating a REMAINDER node with `content_type` field set to `"definition_block"` and adding a `TermEntry` to the graph's `_terms` dictionary.

B. The `defined_in` field of each `TermEntry` SHALL point to the nearest REQUIREMENT or FILE ancestor node ID, not the REMAINDER node itself.

C. `FederatedGraph` SHALL merge per-repo `_terms` dictionaries into a single federated `TermDictionary`, detecting cross-namespace duplicates.

D. `GraphBuilder` SHALL accept a `namespace` parameter (str, default "") and set `TermEntry.namespace` from it during term creation.

## Changelog

- 2026-04-23 | 96b5223f | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *TraceGraph Terms and GraphBuilder Integration* | **Hash**: 96b5223f

## REQ-d00223: Term Health Checks

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

## Assertions

A. `check_term_duplicates()` SHALL return a `HealthCheck` reporting duplicate term definitions across all namespaces, using the configured `duplicate_severity`.

B. `check_undefined_terms()` SHALL return a `HealthCheck` for `*token*`/`**token**` references that do not match any *Defined Term* and are not known structural patterns, using the configured `undefined_severity`.

C. `check_unmarked_usage()` SHALL return a `HealthCheck` for whole-word case-insensitive matches of indexed terms in prose that lack `*...*` or `**...**` markup, using the configured `unmarked_severity`. Only terms with `indexed=True` SHALL be checked.

D. When any severity is set to `"off"`, the corresponding check SHALL be skipped and return a passed HealthCheck with severity `"info"`.

E. A `run_term_checks(graph, config)` aggregator SHALL call `check_term_duplicates`, `check_undefined_terms`, and `check_unmarked_usage` with data extracted from `graph._terms` and `graph._term_duplicates`, reading severity from `config["terms"]["severity"]`. It SHALL be wired into `render_section()` and `compute_checks()`.

F. `check_unmarked_usage()` SHALL produce distinct messages for wrong-marking references (e.g., "Wrong markup for 'term' (uses __, should use configured style)") versus plain unmarked references (e.g., "Unmarked usage of 'term'").

## Changelog

- 2026-04-23 | 0d96cc34 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Term Health Checks* | **Hash**: 0d96cc34

## REQ-d00224: Glossary and Term Index Generators

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

## Assertions

A. `generate_glossary()` SHALL produce an alphabetically-organized Markdown glossary with letter headings, including definition text, `defined_in` attribution, and annotation for collection/non-indexed terms.

B. `generate_term_index()` SHALL produce a term index listing only indexed terms, with references grouped by namespace (one per line).

C. `generate_collection_manifest()` SHALL produce a standalone manifest file per collection term, listing all reference sites.

D. All generated files SHALL include an auto-generated header comment. Both `--format markdown` and `--format json` SHALL be supported.

## Changelog

- 2026-04-23 | f2da30fb | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Glossary and Term Index Generators* | **Hash**: f2da30fb

## REQ-d00225: CLI Registration for Glossary and Term Index

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

## Assertions

A. `GlossaryArgs` and `TermIndexArgs` dataclasses SHALL be defined in `commands/args.py` with `format` and `output_dir` fields. They SHALL be registered in the `Command` union and `_CMD_MAP`.

B. `elspais fix` SHALL call glossary and term-index generation after existing fix operations when the graph has defined terms.

## Changelog

- 2026-04-23 | d18fc2c9 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *CLI Registration for Glossary and Term Index* | **Hash**: d18fc2c9

## REQ-d00236: Comment Extraction Utilities

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

## Assertions

A. `extract_comments(source, ext)` SHALL return a `list[tuple[str, int]]` of (comment_text, line_number) pairs extracted from source code text based on file extension.

B. For Python files (`.py`), the extractor SHALL use `tokenize` to extract `#` line comments and `ast` to extract docstrings, ignoring string literals that are not docstrings.

C. For slash-comment languages (`.js`, `.ts`, `.jsx`, `.tsx`, `.java`, `.c`, `.h`, `.cpp`, `.go`, `.rs`, `.dart`), the extractor SHALL extract `//` line comments and `/* */` block comments.

D. For hash-comment languages (`.rb`, `.sh`, `.bash`, `.yaml`, `.yml`), the extractor SHALL extract `#` line comments.

E. For dash-comment languages (`.sql`, `.lua`), the extractor SHALL extract `--` line comments.

F. For markup languages (`.html`, `.xml`, `.svg`), the extractor SHALL extract `<!-- -->` comments.

G. For file extensions with no known comment style, `extract_comments()` SHALL return an empty list.

## Changelog

- 2026-04-23 | 499123f1 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Comment Extraction Utilities* | **Hash**: 499123f1

## REQ-d00237: Term Reference Scanner Core

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

## Assertions

A. `scan_text_for_terms(text, td, node_id, namespace, line_offset, markup_styles)` SHALL return a `list[TermRef]` classifying each term occurrence as marked, wrong-marking, or unmarked.

B. For each configured `markup_style` in `markup_styles`, the scanner SHALL detect terms wrapped in that delimiter as `marked=True, wrong_marking=""`.

C. For Markdown emphasis delimiters (`*`, `**`, `__`, `_`) NOT in `markup_styles`, the scanner SHALL detect wrapped terms as `marked=False` with `wrong_marking` set to the delimiter used.

D. For terms with `indexed=True`, the scanner SHALL perform whole-word case-insensitive matching for unmarked (plain text) occurrences, excluding positions already matched as marked or wrong-marking.

E. Terms with `indexed=False` SHALL be scanned for marked and wrong-marking references only; unmarked scanning SHALL be skipped.

## Changelog

- 2026-04-23 | 63cb874b | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Term Reference Scanner Core* | **Hash**: 63cb874b

## REQ-d00238: Graph-Wide Term Scan

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

## Assertions

A. `scan_graph(terms, nodes, namespace, markup_styles, exclude_files)` SHALL populate `TermEntry.references` by scanning graph nodes for term occurrences.

B. REQUIREMENT, *Assertion*, REMAINDER (excluding `definition_block`), and JOURNEY nodes SHALL be scanned using their full text content.

C. CODE and TEST nodes SHALL be scanned via comment extraction only (not raw source code), to avoid false positives on variable names and string literals.

D. Files matching any `exclude_files` glob pattern SHALL be skipped during scanning.

## Changelog

- 2026-04-23 | d3a202d4 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Graph-Wide Term Scan* | **Hash**: d3a202d4

## REQ-d00239: Federated Graph Term Scanner Pass

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

## Assertions

A. After `FederatedGraph._merge_terms()`, the scanner SHALL run across all repos using the merged `TermDictionary` so that cross-repo term references resolve correctly.

B. Each repo's scan SHALL use its own config for `markup_styles` and `exclude_files`.

## Changelog

- 2026-04-23 | 7d9a30c4 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Federated Graph Term Scanner Pass* | **Hash**: 7d9a30c4

## REQ-d00240: New Term Health Checks

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

## Assertions

A. `check_term_unused(entries, severity)` SHALL return a `HealthCheck` reporting defined terms with zero references. Default severity: `"warning"`. When `severity="off"`, return passed/info.

B. `check_term_bad_definition(entries, severity)` SHALL return a `HealthCheck` reporting terms with blank or trivially short (less than 10 characters) definition text. Default severity: `"error"`. When `severity="off"`, return passed/info. Reference-type terms (`is_reference=True`) SHALL be exempted from this check because their content lives in structured `reference_fields` instead of prose.

C. `check_term_collection_empty(entries, severity)` SHALL return a `HealthCheck` reporting collection terms (`collection=True`) with zero references. Default severity: `"warning"`. When `severity="off"`, return passed/info.

D. `run_term_checks()` SHALL call all six term checks (`duplicates`, `undefined`, `unmarked`, `unused`, `bad_definition`, `collection_empty`) with severity from `config["terms"]["severity"]`.

## Changelog

- 2026-04-24 | 76a49db3 | - | Developer (dev@example.com) | Auto-fix: update hash
- 2026-03-29 | 9788814d | - | Michael Lewis (michael@anspar.org) | Initial creation

*End* *New Term Health Checks* | **Hash**: 76a49db3

## REQ-d00241: Code No-Traceability Health Check

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

## Assertions

A. `check_no_traceability(unlinked_files, severity)` SHALL return a `HealthCheck` reporting code and test files with no *Traceability* markers. Default severity: `"warning"`. When `severity="off"`, return passed/info.

B. The check SHALL be wired into `run_code_checks()` using `graph.iter_unlinked()` to find CODE/TEST nodes not linked to any requirement.

C. Severity SHALL be read from `[rules.format] no_traceability_severity` (default `"warning"` if None).

## Changelog

- 2026-03-30 | e1272219 | - | Michael Lewis (michael@anspar.org) | Auto-fix: sync changelog hash
- 2026-03-29 | 6e481d63 | - | Michael Lewis (michael@anspar.org) | Initial creation

*End* *Code No-Traceability Health Check* | **Hash**: e1272219

## REQ-d00246: Markdown Emphasis Normalization Utility

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

## Assertions

A. The codebase SHALL provide a `strip_emphasis(s: str) -> str` utility in `utilities/markdown.py` that strips balanced pairs of `**`, `__`, `*`, and `_` from the start and end of `s`, in order of width (widest first). Outer whitespace SHALL be trimmed. Unbalanced wrappers (e.g. `*Foo_`, `**Foo`) SHALL leave the string intact. The function SHALL be idempotent.

B. Lark transformers SHALL use `strip_emphasis()` to normalize all user-text captured from emphasis-decorated spec source: term names extracted from `definition_block` TEXT tokens, value text extracted from journey `Actor`/`Goal`/`Context` metadata fields, and `reference term`/`reference source` definition-block fields. Ad-hoc per-character strip calls (e.g., `.strip("*")`, `.strip("_")`) SHALL NOT remain in the transformer modules.

## Changelog

- 2026-05-04 | 16af6c80 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Markdown Emphasis Normalization Utility* | **Hash**: 16af6c80

## REQ-d00247: Fenced Code Block Preservation

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

## Assertions

A. Fenced code block content (lines between ``` markers) SHALL be preserved verbatim across the parse-render round trip. Any preprocessing applied to fenced content for grammar matching (e.g., line replacement with neutralization placeholders) SHALL be ephemeral, used only as parser input, and SHALL NOT be persisted to disk via render. The lark spec parser SHALL pass the original un-preprocessed source content to the transformer's `source` parameter so REMAINDER nodes capture the original text.

## Changelog

- 2026-05-04 | 1270eb2b | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Fenced Code Block Preservation* | **Hash**: 1270eb2b

## REQ-d00248: Fix Command Idempotency

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

## Assertions

A. `elspais fix` SHALL be idempotent: running the command twice in succession on the same project SHALL produce identical files. The second invocation SHALL detect no pending changes and SHALL not modify any spec, journey, code, test, or generated artifact file. This invariant SHALL be exercised by a fixture that includes fenced code blocks with markdown emphasis, a glossary term with emphasis-wrapped name, a user journey with emphasized actor field, and a REMAINDER section containing emphasized text.

## Changelog

- 2026-05-04 | 8a92207b | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Fix Command Idempotency* | **Hash**: 8a92207b
