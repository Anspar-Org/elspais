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

B. The tool SHALL generate traceability matrices showing requirement relationships.

C. The tool SHALL detect changes to requirements using content hashing and git integration.

D. [DEPRECATED]

*End* *Requirements Management Tool* | **Hash**: d94ef7d7
---

# REQ-p00002: Requirements Validation

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001

## Rationale

Requirements documents are only useful if they follow a consistent structure. Inconsistent formatting, broken links between requirements, and outdated content hashes undermine the reliability of the requirements baseline.

Automated validation catches these issues early, before they propagate into design documents, test plans, and regulatory submissions. Validation must be fast enough to run on every commit and flexible enough to accommodate different organizational conventions.

The validation system enforces:

- **Format compliance**: Headers, metadata, assertion sections, and hash footers follow the canonical grammar
- **Hierarchy integrity**: Child requirements correctly reference parents; no circular dependencies
- **Traceability completeness**: All requirements are reachable from root-level product requirements
- **Content freshness**: Hashes match current content; changes are intentional

## Assertions

A. The tool SHALL validate requirement format against configurable patterns and rules.

B. The tool SHALL detect and report hierarchy violations including circular dependencies and orphaned requirements.

C. The tool SHALL verify content hashes match requirement body text.

*End* *Requirements Validation* | **Hash**: e8f0e4eb
---

# REQ-p00003: Traceability Matrix Generation

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001

## Rationale

Regulatory submissions and internal reviews require evidence that high-level product requirements flow down to detailed specifications and test coverage. A traceability matrix provides this view—showing which detailed requirements implement which product requirements, and which tests verify which specifications.

Manual maintenance of traceability matrices is error-prone and quickly becomes stale. Automated generation from the `Implements:` metadata in requirement documents ensures the matrix always reflects the current state of the requirements baseline.

Multiple output formats serve different audiences:

- **Markdown**: Embeddable in documentation
- **HTML**: Interactive viewing with clickable links
- **CSV**: Import into spreadsheets or compliance tools

## Assertions

A. The tool SHALL generate traceability matrices in Markdown, HTML, and CSV formats.

B. The tool SHALL derive traceability from `Implements:` metadata without manual matrix maintenance.

*End* *Traceability Matrix Generation* | **Hash**: b935bd53
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

A. The project SHALL maintain unit tests for all core modules with assertion-linked test names.

B. The project SHALL maintain end-to-end tests that invoke the CLI as a subprocess and verify command output, exit codes, and file artifacts.

C. The project SHALL include self-validation tests that run elspais against its own repository and assert health, summary, and trace outputs are correct.

D. The project SHALL include multi-command workflow tests that verify cross-command consistency and sequential operation correctness.

E. The project SHALL include MCP protocol tests that verify tool invocation, search, cursor pagination, and mutation roundtrips via the stdio transport.

F. All tests marked `@pytest.mark.e2e` SHALL invoke the `elspais` CLI as a subprocess. Tests that call internal Python functions or submodules directly SHALL NOT be marked e2e; they are unit or integration tests.

*End* *Automated Testing* | **Hash**: 3fc90ebc
---

## REQ-p00061: Requirement Decomposition Rules

**Level**: prd | **Status**: Active | **Implements**: -

A child requirement refines a parent when it adds specificity, constraints, or commits to mechanisms or guarantees.

## Assertions

A. A child requirement that adds specificity, constraints, or commits to mechanisms or guarantees SHALL declare its parent requirement using `Implements:` or `Refines:` in its metadata block.

B. `Implements:` and `Refines:` declarations apply to requirements only; code references and test nodes use their own linkage mechanisms.

C. Multiple requirements MAY exist at the same Level each declaring a relationship to the same parent requirement.

*End* *Requirement Decomposition Rules* | **Hash**: fc1e85fe
---

# REQ-p00080: Spec-to-PDF Compilation

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001

## Rationale

UAT documentation review requires formal PDF output with professional formatting. A single compiled document with table of contents, per-requirement page breaks, and a topic index enables offline review, regulatory submission, and stakeholder sign-off. Currently, spec files exist only as Markdown with no PDF generation pipeline.

The `elspais pdf` command compiles requirement spec files into a professional PDF using Pandoc and LaTeX. Python assembles a clean Markdown document from the traceability graph; a custom LaTeX template controls formatting; Pandoc handles Markdown-to-LaTeX conversion.

## Assertions

A. The tool SHALL provide an `elspais pdf` CLI command that compiles spec files into a PDF document.

B. The assembled Markdown SHALL group requirements by level (PRD, OPS, DEV) with each level as a top-level section, and order files within each level by graph depth (root requirements first).

C. The generated PDF SHALL include an auto-generated table of contents derived from requirement headings.

D. The tool SHALL generate an alphabetized topic index with entries derived from filename words, file-level Topics lines, and requirement-level Topics lines, rendered as a Markdown section with hyperlinks.

E. The tool SHALL insert page breaks before each requirement heading to ensure each requirement starts on a new page.

F. The tool SHALL support an `--overview` flag that generates a stakeholder-oriented PDF containing only PRD-level requirements, with an optional `--max-depth` flag to limit core PRD graph depth while always including all associated-repo PRDs.

*End* *Spec-to-PDF Compilation* | **Hash**: bfc0cadf
---

## REQ-d00220: TermDictionary Data Model

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

## Assertions

A. `TermDictionary.add()` SHALL store a `TermEntry` keyed by normalized (lowercased) term name. If the term already exists, it SHALL return the existing entry without overwriting.

B. `TermDictionary.lookup()` SHALL perform case-insensitive lookup and return the `TermEntry` or `None`.

C. `TermDictionary.iter_indexed()` SHALL yield only entries where `indexed` is `True`. `iter_collections()` SHALL yield only entries where `collection` is `True`.

D. `TermDictionary.merge()` SHALL combine two dictionaries and return a list of `(TermEntry, TermEntry)` pairs for duplicate terms detected across namespaces.

*End* *TermDictionary Data Model* | **Hash**: 31915ae3
