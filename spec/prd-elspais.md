# elspais Product Requirements

This document defines the high-level product requirements for elspais, a requirements validation and traceability tool.

---

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

D. This edit SHALL be reverted, eventually.

*End* *Requirements Management Tool* | **Hash**: 3cddd08e
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

# REQ-p00005: Multi-Repository Requirements

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001

## Rationale

Large organizations often split requirements across multiple repositories:

- A **core** repository containing product-level requirements
- **Associated** repositories for subsystems, services, or components
- **Sponsor** repositories for customer-specific or partner-specific requirements

Each repository maintains its own spec directory, but requirements must reference and implement requirements from other repositories. The tool must validate these cross-repository links and generate combined traceability matrices.

This architecture supports:

- Independent versioning of subsystem specifications
- Access control (not everyone needs access to all specs)
- Modular development with clear interface contracts
- Combined views for regulatory submissions

CI/CD pipelines and diverse developer environments mean associated repositories may be located at different filesystem paths on each machine. Rather than requiring each environment to maintain a separate override file, the tool treats all cross-repository resolution as a local path concern: CI systems clone repos and then configure paths via the CLI, developers set paths to match their local directory layout, and the associated repository's own configuration file declares its identity (project type, namespace prefix). This keeps repository topology — which repos exist and where they are hosted — as a CI/infrastructure concern outside the tool, while the tool focuses on discovering and validating whatever local repos it is pointed at.

## Assertions

A. The tool SHALL support requirement references across repository boundaries using configurable namespace prefixes.

B. The tool SHALL generate combined traceability matrices spanning multiple repositories.

C. The tool SHALL support CLI-based configuration of associate repository paths so that external systems can register associates without manually editing configuration files.

D. The tool SHALL discover an associated repository's identity — including its project type and namespace prefix — by reading that repository's own configuration file.

E. The tool SHALL report a clear configuration error when a configured associate path does not exist or does not contain a valid associated-repository configuration.

F. The tool SHALL resolve relative associate paths from the canonical (non-worktree) repository root so that cross-repository paths remain valid when working from git worktrees.

*End* *Multi-Repository Requirements* | **Hash**: 7964180f
---

# REQ-p00006: Interactive Traceability Viewer

**Level**: prd | **Status**: Active | **Implements**: REQ-p00003

## Rationale

Static traceability matrices—whether Markdown tables or CSV exports—answer the question "what implements what?" but fail to support exploratory analysis. Reviewers need to navigate requirement hierarchies, drill into specific branches, and understand the full context of a requirement including its test coverage, implementation references, and change history.

The interactive trace viewer transforms the traceability matrix into an explorable interface:

- **Clickable navigation**: Click a requirement to see what it implements and what implements it
- **Test coverage overlay**: See which requirements have tests, which are untested, and test pass/fail status
- **Git state awareness**: Visual indicators for uncommitted changes, moved requirements, and branch differences
- **Implementation references**: Links to source files that reference each requirement
- **Embedded content**: Optionally include full requirement text for offline review

This supports:

- Design reviews (navigate the hierarchy without switching files)
- Test planning (identify coverage gaps)
- Change impact analysis (see what's affected by a modification)
- Regulatory audits (demonstrate complete traceability in one view)

## Assertions

A. The tool SHALL generate an interactive HTML view with clickable requirement navigation.

B. The tool SHALL display test coverage information per requirement when test data is available.

C. The viewer SHALL display source files inline in a side panel with syntax-highlighted content and stable line numbers, when embedded content is enabled.

*End* *Interactive Traceability Viewer* | **Hash**: b3dd4d1a
---

---

---

---

---

---

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
