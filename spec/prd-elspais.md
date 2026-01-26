# elspais Product Requirements

This document defines the high-level product requirements for elspais, a requirements validation and traceability tool.

---

# REQ-p00001: Requirements Management Tool

**Level**: PRD | **Status**: Active | **Implements**: -

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

*End* *Requirements Management Tool* | **Hash**: dd780287
---

# REQ-p00002: Requirements Validation

**Level**: PRD | **Status**: Active | **Implements**: REQ-p00001

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

*End* *Requirements Validation* | **Hash**: c1ae20e4
---

# REQ-p00003: Traceability Matrix Generation

**Level**: PRD | **Status**: Active | **Implements**: REQ-p00001

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

*End* *Traceability Matrix Generation* | **Hash**: 6c612b18
---

# REQ-p00004: Change Detection and Auditability

**Level**: PRD | **Status**: Active | **Implements**: REQ-p00001

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

*End* *Change Detection and Auditability* | **Hash**: 0e7c1870
---

# REQ-p00005: Multi-Repository Requirements

**Level**: PRD | **Status**: Active | **Implements**: REQ-p00001

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

## Assertions

A. The tool SHALL support requirement references across repository boundaries using configurable namespace prefixes.

B. The tool SHALL generate combined traceability matrices spanning multiple repositories.

*End* *Multi-Repository Requirements* | **Hash**: 7928a1a8
---

# REQ-p00006: Interactive Traceability Viewer

**Level**: PRD | **Status**: Active | **Implements**: REQ-p00003

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

*End* *Interactive Traceability Viewer* | **Hash**: 9ace8857
---

# REQ-p00007: Collaborative Review System

**Level**: PRD | **Status**: Active | **Implements**: REQ-p00001

## Rationale

Requirements undergo review before approval. Traditional review workflows rely on document comments, email threads, or heavyweight tools that don't integrate with version control. This creates disconnected feedback that's hard to track and easy to lose.

The collaborative review system brings review conversations directly into the requirements workflow:

- **Threaded comments**: Attach discussion threads to specific requirements
- **Review packages**: Group related requirements for focused review sessions
- **Resolution tracking**: Mark threads as resolved; archive completed reviews
- **Git integration**: Track which commit each comment addresses; handle branch merges gracefully
- **Audit preservation**: Archived reviews remain accessible for regulatory evidence

This supports:

- Peer review of new requirements before approval
- Change review when requirements are modified
- Regulatory evidence of review activities
- Historical context (why was this requirement written this way?)

## Assertions

A. The tool SHALL support threaded comments attached to individual requirements.

B. The tool SHALL allow users to group requirements into review packages for focused review sessions.

C. The tool SHALL display the git commit context for each review, enabling users to understand which version of the requirements was reviewed.

D. The tool SHALL provide access to archived reviews for audit and historical reference.

E. The tool SHALL preserve review history through archival rather than deletion.

*End* *Collaborative Review System* | **Hash**: da35db96
---

# REQ-p00008: Review User Interface

**Level**: PRD | **Status**: Draft | **Implements**: REQ-p00007

## Rationale

The collaborative review system requires an interactive user interface that enables reviewers to navigate requirements, attach comments to specific locations, and manage review workflows efficiently. The UI must support precise position anchoring (line, block, word, or general) while gracefully handling content drift when requirements change.

Key UI capabilities:

- **Review mode toggle**: Switch between normal viewing and review mode
- **Position-aware commenting**: Click on lines or select text to anchor comments
- **Visual highlighting**: Show where comments are anchored with confidence indicators
- **Resizable panels**: Adjust review panel width for comfortable reading
- **Contextual help**: Guide users through review workflows

## Assertions

A. The UI SHALL provide a review mode toggle that activates interactive review features.

B. The UI SHALL display interactive line numbers that users can click to select comment anchor positions.

C. The UI SHALL highlight the anchored position when a user clicks on a comment's position label.

D. The UI SHALL visually indicate when comment positions may have drifted due to content changes.

E. The UI SHALL provide a resizable review panel for managing threads and comments.

F. The UI SHALL provide contextual help explaining review workflows and features.

*End* *Review User Interface* | **Hash**: f7e1d9ea
---

# REQ-p00009: Review Data Model

**Level**: PRD | **Status**: Draft | **Implements**: REQ-p00007

## Rationale

The collaborative review system requires a well-defined data model for organizing review artifacts. This includes packages that group related requirements for focused review sessions, threads that contain discussion comments, and storage structures that persist this data reliably.

Key data concepts:

- **Packages**: Named collections of requirements under review together
- **Threads**: Comment discussions anchored to specific requirement locations
- **Comments**: Individual messages within threads with author and timestamp
- **Position anchors**: Location references that survive content changes

## Assertions

A. The system SHALL define a package model for grouping requirements into reviewable units.

B. The system SHALL define a thread model for comment discussions attached to requirements.

C. The system SHALL define storage structures that persist review data reliably with atomic writes.

D. The system SHALL support position anchoring that identifies specific locations within requirement text.

*End* *Review Data Model* | **Hash**: 04e442fe
---

# REQ-p00010: Review Git Integration

**Level**: PRD | **Status**: Draft | **Implements**: REQ-p00007

## Rationale

Reviews occur in the context of specific code versions. When a reviewer comments on a requirement, they're commenting on the requirement as it existed at a particular commit. The system must track this git context to support:

- Understanding which version was reviewed
- Detecting when requirements change after review
- Managing review branches for isolated work
- Merging review data from multiple contributors

## Assertions

A. The system SHALL record the git commit context when reviews are created or updated.

B. The system SHALL support review branches that isolate reviewer work until ready to merge.

C. The system SHALL merge review data from multiple contributor branches.

*End* *Review Git Integration* | **Hash**: 3184ae65
---

# REQ-p00011: Review Package Lifecycle

**Level**: PRD | **Status**: Draft | **Implements**: REQ-p00007

## Rationale

Review packages progress through a lifecycle: creation, active review, resolution, and archival. Completed reviews must be preserved for audit purposes rather than deleted. The system must support viewing archived reviews to understand historical context and demonstrate regulatory compliance.

Lifecycle stages:

- **Active**: Package is open for comments and discussion
- **Resolved**: All threads resolved, ready for archival
- **Archived**: Read-only preservation for audit trail

## Assertions

A. The system SHALL support archiving completed review packages rather than deleting them.

B. The system SHALL preserve archived reviews in a read-only state for audit purposes.

C. The system SHALL provide access to view archived packages and their contents.

*End* *Review Package Lifecycle* | **Hash**: 0949cebc
---

# REQ-p00012: Review Backend Services

**Level**: PRD | **Status**: Draft | **Implements**: REQ-p00007

## Rationale

The review system requires backend services to handle comment position resolution, serve the review API, and modify requirement status based on review outcomes. These services bridge the gap between stored review data and the interactive user interface.

Key services:

- **Position resolution**: Map comment anchors to current document locations
- **API server**: RESTful endpoints for CRUD operations on review data
- **Status modification**: Update requirement status in spec files based on review decisions

## Assertions

A. The system SHALL resolve comment positions to current document locations, handling content drift gracefully.

B. The system SHALL provide API endpoints for creating, reading, updating, and managing review data.

C. The system SHALL support modifying requirement status in spec files based on review outcomes.

*End* *Review Backend Services* | **Hash**: 7a95a46c