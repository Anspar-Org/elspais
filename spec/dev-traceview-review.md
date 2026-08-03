# Trace View Server Specifications

These requirements define the *Traceability* viewer server and federation.

---

# REQ-d00010: Traceability API Server

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

**Purpose:** REST API server backing the interactive *Traceability* viewer.

## Rationale

This requirement originally specified an API server for a planned review-package
workflow (review threads, status requests, packages, sync, archives). That design
was never built; the shipped annotation layer is the comment system, which
deliberately diverged (append-only event storage, graph anchors, graph mutations)
and is specified by its own requirements. The endpoint families of the abandoned
design are retired below with their labels preserved -- assertion labels are
append-only and never reused.

This requirement now covers only the server application shell: how the server is
constructed, cross-origin access, and static asset serving. Individual endpoint
families are specified by the requirements that refine this server.

## Assertions

A. The system SHALL construct the API server through an application factory function that assembles the server from pre-built application state.

B. [Removed - review-thread endpoints belong to the abandoned review-package design and were never implemented; the shipped comment system (REQ-d00226) supersedes them]

C. [Removed - review status and approval endpoints belong to the abandoned review-package design and were never implemented]

D. [Removed - review-package endpoints belong to the abandoned review-package design and were never implemented]

E. [Removed - review sync endpoints belong to the abandoned review-package design and were never implemented]

F. The API server SHALL accept cross-origin requests.

G. The API server SHALL serve bundled static assets over HTTP.

H. [Removed - auto-sync of review data belongs to the abandoned review-package design and was never implemented]

I. [Removed - review archive endpoints belong to the abandoned review-package design and were never implemented]

J. [Removed - a dedicated health-check endpoint was never implemented]

## Changelog

- 2026-07-31 | aaae0fb2 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms, update hash
- 2026-07-31 | 8ae37685 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-04-23 | b647ec64 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Traceability API Server* | **Hash**: aaae0fb2

---

## REQ-d00206: Server Federation and Staleness

**Level**: dev | **Status**: Active | **Implements**: REQ-d00010, REQ-d00200

The review server SHALL expose federation repo metadata and staleness information.

### Assertions

A. `/api/repos` SHALL return a list of federated repos from `iter_repos()` with name, path, status (ok/error), git_origin, and error fields.

B. `/api/repos` SHALL include staleness info (remote_diverged, branch) for repos with a `git_origin` configured, using `git_status_summary()` per-repo.

C. `/api/status` SHALL include federation repo metadata from `iter_repos()`, replacing the legacy `associated_repos` field.

D. Staleness info SHALL be informational only and SHALL NOT affect build or health check results.

### Rationale

Multi-repo federation users need visibility into which repos are current and which are behind their remotes. The viewer/server surfaces this as informational metadata without gating builds on it.

### Changelog

- 2026-07-31 | ddd6dc73 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | b4fae1d0 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | b4fae1d0 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Server Federation and Staleness* | **Hash**: ddd6dc73
