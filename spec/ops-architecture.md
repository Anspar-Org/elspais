# Architecture Operations Requirements

## REQ-o00050: Graph Builder as Single Entry Point

**Level**: ops | **Status**: Active | **Implements**: REQ-p00050

TraceGraphBuilder SHALL be the single entry point for constructing requirement graphs from parsed data.

## Assertions

A. The system SHALL use TraceGraphBuilder to construct all TraceGraph instances.

B. No module SHALL directly instantiate TraceGraph except TraceGraphBuilder.

C. TraceGraphBuilder SHALL handle all relationship linking (implements, refines, addresses, satisfies, instance).

D. TraceGraphBuilder SHALL create *Assertion* nodes as children of requirement nodes.

E. TraceGraphBuilder SHALL support optional TODO node creation for lossless reconstruction.

## Rationale

Centralizing graph construction ensures consistent hierarchy building, cycle detection, and validation across all entry points.

*End* *Graph Builder as Single Entry Point* | **Hash**: 65d2ad6a
---

## REQ-o00051: Composable Annotation Design

**Level**: ops | **Status**: Active | **Implements**: REQ-p00050

The system SHALL use a composable annotation pattern where the graph provides iteration and separate annotator functions enrich nodes.

## Assertions

A. The graph SHALL provide an iterator (`graph.all_nodes()`) for traversing all nodes.

B. Annotation SHALL be a separate concern from graph construction.

C. Annotator functions SHALL be standalone pure functions that mutate `node.metrics` in place.

D. Annotator functions SHALL operate on individual TraceNode instances.

E. Annotation SHALL be composable - multiple annotators can be applied in sequence.

F. The system SHALL support phased annotation (e.g., base graph -> git state -> display info -> coverage).

## Rationale

Separating iteration from annotation enables:

- Reusable annotator functions across different contexts
- Clear separation of concerns
- Easy testing of individual annotators
- Flexible composition of annotation pipelines

*End* *Composable Annotation Design* | **Hash**: c73a6e32
---

# REQ-o00066: CI/CD Pipeline Enforcement

**Level**: ops | **Status**: Active | **Implements**: REQ-p00004

## Rationale

Automated CI/CD checks ensure that requirement *Traceability*, code quality, and security standards are maintained on every change to the codebase. Without automated enforcement, manual reviews are prone to oversight and do not scale.

The pipeline validates at three levels:

- **Quality gates**: Automated test suite and linting prevent regressions
- ****Traceability** gates**: PR titles and commit messages must reference Linear tickets and requirements, maintaining the audit trail from code change to requirement
- **Security gates**: Secret scanning and dependency vulnerability auditing prevent accidental exposure or use of known-vulnerable libraries

These checks are required status checks on the main branch, preventing merges that do not meet the standards.

## Assertions

A. The CI pipeline SHALL run the full test suite across supported Python versions on every push to main and every pull request targeting main.

B. The CI pipeline SHALL run static analysis (linting) to enforce code quality standards.

C. The CI pipeline SHALL validate requirement format and generate *Traceability* artifacts by running elspais against its own spec files.

D. The CI pipeline SHALL scan for leaked secrets in the git history using gitleaks.

E. The CI pipeline SHALL audit dependencies for known security vulnerabilities.

F. The PR validation pipeline SHALL require a Linear ticket reference ([CUR-XXX]) in PR titles to maintain commit *Traceability* through squash merges.

G. The PR validation pipeline SHALL require both ticket (CUR-XXX) and requirement (REQ-XXXXX) references in commit messages.

## Changelog

- 2026-03-30 | 315accce | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *CI/CD Pipeline Enforcement* | **Hash**: 315accce
---
