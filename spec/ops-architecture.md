# Architecture Operations Requirements

## REQ-o00050: Graph Builder as Single Entry Point

**Level**: ops | **Status**: Active | **Implements**: REQ-p00050

TraceGraphBuilder SHALL be the single entry point for constructing requirement graphs from parsed data.

### Assertions

A. The system SHALL use TraceGraphBuilder to construct all TraceGraph instances.

B. No module SHALL directly instantiate TraceGraph except TraceGraphBuilder.

C. TraceGraphBuilder SHALL handle all relationship linking (implements, refines, addresses, satisfies, instance).

D. TraceGraphBuilder SHALL create *Assertion* nodes as children of requirement nodes.

E. TraceGraphBuilder SHALL support optional TODO node creation for lossless reconstruction.

### Rationale

Centralizing graph construction ensures consistent hierarchy building, cycle detection, and validation across all entry points.

### Changelog

- 2026-07-31 | 33e0f3ec | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 65d2ad6a | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 65d2ad6a | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Graph Builder as Single Entry Point* | **Hash**: 33e0f3ec
---

## REQ-o00051: Composable Annotation Design

**Level**: ops | **Status**: Active | **Implements**: REQ-p00050

The system SHALL use a composable annotation pattern where the graph provides iteration and separate annotator functions enrich nodes.

### Assertions

A. The graph SHALL provide an iterator (`graph.all_nodes()`) for traversing all nodes.

B. Annotation SHALL be a separate concern from graph construction.

C. Annotator functions SHALL be standalone pure functions that mutate `node.metrics` in place.

D. Annotator functions SHALL operate on individual TraceNode instances.

E. Annotation SHALL be composable - multiple annotators can be applied in sequence.

F. The system SHALL support phased annotation (e.g., base graph -> git state -> display info -> coverage).

### Rationale

Separating iteration from annotation enables:

- Reusable annotator functions across different contexts
- Clear separation of concerns
- Easy testing of individual annotators
- Flexible composition of annotation pipelines

### Changelog

- 2026-07-31 | 2fabd3d4 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | c73a6e32 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | c73a6e32 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Composable Annotation Design* | **Hash**: 2fabd3d4
---

## REQ-o00072: Domain Deserialization Layer

**Level**: ops | **Status**: Active | **Implements**: REQ-p00050

Domain deserializers SHALL convert a source domain (file, stdin, or CLI input) into a stream of parsed content that carries accurate provenance and line location, through one uniform contract regardless of source domain.

### Assertions

A. Every domain deserializer SHALL pair each unit of parsed content with a `DomainContext` identifying the source domain kind (file, stdin, CLI) and a source identifier, so the origin of any node built from that content is always recoverable.

B. Every domain deserializer SHALL partition its source text into contiguous, 1-indexed line ranges that accurately reflect the original text, so every node built from that content carries a correct source location.

C. All domain deserializers (file, stdin, CLI) SHALL conform to one uniform `DomainDeserializer` contract (`iterate_sources` plus `deserialize`), so the graph builder can consume any source domain interchangeably.

### Rationale

The deserialization layer is the abstract controller that turns raw text into the `ParsedContent` stream the graph builder consumes; it does not construct graph nodes itself, so it must guarantee only the properties the builder depends on: knowing where each unit came from (A), knowing exactly which lines it spans (B), and treating every source domain the same way (C). Completeness -- that every line of a text-based source is eventually claimed by some node -- is a build-pipeline guarantee owned by REQ-d00128-G (RemainderParser is mandatory for SPEC/JOURNEY/CODE/TEST file types); this requirement does not duplicate it.

### Changelog

- 2026-07-31 | 53789928 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-03 | e568082e | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: add missing changelog section

*End* *Domain Deserialization Layer* | **Hash**: 53789928
---

# REQ-o00066: CI/CD Pipeline Enforcement

**Level**: ops | **Status**: Active | **Implements**: REQ-p00004

## Rationale

Automated CI/CD checks ensure that requirement *Traceability*, code quality, and security standards are maintained on every change to the codebase. Without automated enforcement, manual reviews are prone to oversight and do not scale.

The pipeline validates at three levels:

- **Quality gates**: Automated test suite and linting prevent regressions
- **Traceability gates**: PR titles and commit messages must reference Linear tickets and requirements, maintaining the audit trail from code change to requirement
- **Security gates**: Secret scanning and dependency vulnerability auditing prevent accidental exposure or use of known-vulnerable libraries

These checks are required status checks on the main branch, preventing merges that do not meet the standards.

I, J and K divide the test suite by trigger. I and J apply to a pull request whatever it targets: a pull request stacked on another pull request's branch is reviewed and merged like any other, and a change that reaches main through a stack would otherwise reach it untested.

L exists because a merge queue tests the combination that will actually land -- the pull request on top of everything queued ahead of it -- and does so on a commit no pull request event describes. A required check that does not report on that commit holds the queue indefinitely, so a check that only makes sense for a pull request (a title, a commit range) still reports, by passing as not applicable.

I, J and K divide the test suite by trigger. The end-to-end tier is the slowest part of the suite, and a difference between Python versions shows first in the unit tier. Consequently, a pull request runs the end-to-end tier on one supported version, and every push to main runs the whole suite on every supported version.

H is stated apart from B because formatting and linting are enforced by the same tool and were not enforced in the same places. A local hook cannot be the only gate for a standard: it is absent from a fresh clone until configured, a contributor may bypass it, and it never runs at all for a commit created on the forge -- an automated version bump, or an edit accepted through the web. A standard enforced only there reaches main unenforced, and is then inherited by whoever next touches the tree.

## Assertions

A. <RETIRED> The CI pipeline SHALL run the full test suite across supported Python versions on every push to main and every pull request targeting main.

B. The CI pipeline SHALL run static analysis (linting) to enforce code quality standards.

C. The CI pipeline SHALL validate requirement format and generate *Traceability* artifacts by running elspais against its own spec files.

D. The CI pipeline SHALL scan for leaked secrets in the git history using gitleaks.

E. The CI pipeline SHALL audit dependencies for known security vulnerabilities.

F. The PR validation pipeline SHALL require a Linear ticket reference in PR titles — a bracketed uppercase team prefix and issue number (e.g. `[TOOL-38]`, `[CUR-514]`) — to maintain commit *Traceability* through squash merges.

G. The PR validation pipeline SHALL require both a ticket reference (uppercase team prefix and issue number) and a requirement reference (REQ-XXXXX) in commit messages.

H. The CI pipeline SHALL enforce the project's code formatting.

I. For every pull request, whichever branch it targets, the CI pipeline SHALL run the unit tier on every supported Python version.

J. For every pull request, whichever branch it targets, the CI pipeline SHALL run the end-to-end tier on at least one supported Python version.

L. For every candidate the merge queue builds for main, the CI pipeline SHALL run the checks it runs for a pull request targeting main, and every check a pull request is required to pass SHALL report a result for that candidate.

K. For every push to main, the CI pipeline SHALL run the full test suite on every supported Python version.

## Changelog

- 2026-10-12 | 3fdfd014 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-10-12 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-155: I and J cover a pull request whatever branch it targets, so a stacked pull request is tested; L adds the merge queue
- 2026-10-03 | 3f2127be | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-10-03 | - | - | Michael Lewis (<michael@anspar.org>) | A retired: a pull request runs the unit tier on every supported version and the end-to-end tier on one (I, J); a push to main runs the full suite on every supported version (K)
- 2026-09-10 | 133e2f0d | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | 67d7ec07 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | 84723bf6 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-37: F/G accept any Linear team prefix, not only CUR — the repo's team moved to TOOL; matches the commit-msg hook's existing pattern
- 2026-03-30 | 315accce | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *CI/CD Pipeline Enforcement* | **Hash**: 3fdfd014
---

# REQ-o00078: Release Completeness Across Distribution Channels

**Level**: ops | **Status**: Active | **Implements**: -
**Satisfies**: REQ-p00019

## Rationale

A release publishes the tool through more than one channel — the package index and the Homebrew tap — and the two complete on different timescales through different repositories. The index accepts the upload during the release run; the tap raises a formula change that a bottle build must pass before anything merges. A release that treats its own dispatch as the end of the tap's story reports success while an installer on that channel still receives the previous version.

The defect classes are the ones REQ-p00019 already names, concretized here for release. Reporting a version released while a channel does not carry it is that template's phantom-success class: the effect is absent at the destination the claim names. A channel that never completes and is never mentioned is its unreported-non-performance class. A green verdict standing over an undisclosed outcome is its verdict-integrity class. The template's actionable-failure class binds through the instance without restatement, so the report obligation here says what a release failure must identify without respecifying the general form.

What makes this hard to notice is that no single run observes the whole outcome. The release run finishes before the tap does and cannot wait for it; the tap knows its own result but not who asked for it. Nothing in the assertions requires the release run itself to do the observing, only that the claim a channel carries a version is not made ahead of the fact and that a channel left behind is reported to the person who released it. Where that reporting happens is an implementation choice.

## Assertions

A. The release process SHALL NOT represent a version as available through a distribution channel until that channel carries that version.

B. When a distribution channel does not come to carry a released version, the release process SHALL report the channel, the cause, and the action available, to the person who cut the release.

C. The release process SHALL NOT report a release complete while the outcome of any distribution channel it publishes to is undisclosed.

## Changelog

- 2026-09-10 | 3f2d4577 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-09-10 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-92: govern release completeness across distribution channels — a released version is carried by every channel, or the channel it did not reach is reported to whoever released it

*End* *Release Completeness Across Distribution Channels* | **Hash**: 3f2d4577
---

# REQ-o00080: Stacked Pull Requests

**Level**: ops | **Status**: Active | **Implements**: REQ-p00004

## Rationale

A change too large to review at once is split into a stack: each pull request is based on the branch of the one below it, so each can be reviewed, merged or reverted on its own. Two events break a stack unless something repairs it. When the bottom pull request merges, the one above it is still based on a branch whose work now lives in main; it must be pointed at main, and it must be brought up to date with main, or it shows the merged work again as its own. When a lower branch gains commits -- a review fix -- every pull request above it must take them, or it is tested and reviewed against a base it will not land on.

Repairing a stack by hand is slow and is where mistakes enter, so the repair is automatic. It only ever adds commits: a contributor's checkout of their branch stays valid, and no history anyone has reviewed is rewritten. A repair that cannot be made without a person's judgement -- a conflict -- is reported where the author will see it, and the branch is left exactly as it was.

This repository merges pull requests by squashing them. A squash commit is not related to the commits it replaced, so an ordinary merge of main into the pull request above would meet the merged work twice and can conflict with itself wherever the upper pull request edited lines the lower one introduced. Recording the merged pull request's last commit as already merged before bringing main in avoids that: the merge then sees only what main gained beyond it.

## Assertions

A. When a pull request merges, each open pull request based on its branch SHALL be retargeted to the branch the merged pull request merged into.

B. When a pull request merges, each open pull request based on its branch SHALL be brought up to date with the branch it is retargeted to, without the merged pull request's own changes appearing in it again.

C. When a branch gains commits, each open pull request based on that branch, and each pull request stacked above those, SHALL be brought up to date with the branch below it.

D. Bringing a pull request's branch up to date SHALL add commits to it and SHALL NOT rewrite its existing history.

E. When bringing a pull request's branch up to date conflicts, its branch and those stacked above it SHALL be left unchanged, and the conflict SHALL be reported on that pull request once.

F. A pull request whose branch lives in another repository SHALL NOT be changed.

## Changelog

- 2026-10-12 | 140f7543 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-10-12 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-155: a stack of pull requests is kept consistent when one merges or gains commits, by adding merge commits only

*End* *Stacked Pull Requests* | **Hash**: 140f7543
---
