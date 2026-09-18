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

B. <RETIRED> review-thread endpoints belong to the abandoned review-package design and were never implemented; the shipped comment system (REQ-d00226) supersedes them

C. <RETIRED> review status and approval endpoints belong to the abandoned review-package design and were never implemented

D. <RETIRED> review-package endpoints belong to the abandoned review-package design and were never implemented

E. <RETIRED> review sync endpoints belong to the abandoned review-package design and were never implemented

F. The API server SHALL accept cross-origin requests.

G. The API server SHALL serve bundled static assets over HTTP.

H. <RETIRED> auto-sync of review data belongs to the abandoned review-package design and was never implemented

I. <RETIRED> review archive endpoints belong to the abandoned review-package design and were never implemented

J. <RETIRED> a dedicated health-check endpoint was never implemented

## Changelog

- 2026-08-24 | cd30d3da | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | aaae0fb2 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms, update hash
- 2026-07-31 | 8ae37685 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-04-23 | b647ec64 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Traceability API Server* | **Hash**: cd30d3da

---

## REQ-d00206: Server Federation and Staleness

**Level**: dev | **Status**: Active | **Implements**: REQ-d00010, REQ-d00200

The review server SHALL expose federation repo metadata and staleness information.

### Assertions

A. `/api/repos` SHALL return every member of the federation, each with its name, its path, and its git origin.

B. `/api/repos` SHALL include staleness info (remote_diverged, branch) for repos with a `git_origin` configured, using `git_status_summary()` per-repo.

C. `/api/status` SHALL include federation repo metadata from `iter_repos()`, replacing the legacy `associated_repos` field.

D. Staleness info SHALL be informational only and SHALL NOT affect build or health check results.

### Rationale

Multi-repo federation users need visibility into which repos are current and which are behind their remotes. The viewer/server surfaces this as informational metadata without gating builds on it.

### Changelog

- 2026-09-12 | a8300f60 | - | Michael Lewis (<michael@anspar.org>) | A drops status and error fields; no member can be either
- 2026-07-31 | ddd6dc73 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | b4fae1d0 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | b4fae1d0 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Server Federation and Staleness* | **Hash**: a8300f60

---

## REQ-d00295: Viewer Served Under a Configured Prefix

**Level**: dev | **Status**: Active | **Implements**: REQ-d00010

The viewer server SHALL serve its whole surface under a configured path prefix, so that a router placing each workspace under a path of its own reaches the viewer, the page and the agent surface at that path.

### Assertions

A. When a prefix is configured, every route the server exposes SHALL answer under that prefix and at no other path.

B. Every URL the served page requests SHALL carry the configured prefix.

C. With no prefix configured, the server SHALL serve exactly what it serves without this capability: the same routes at the same paths and the same page.

D. The agent surface SHALL be reachable under the same prefix as the page.

E. A prefix that is not empty and does not take the form of a path beginning with a slash and ending without one SHALL be refused with a message naming that form.

F. State the page keeps in the browser SHALL be kept apart per configured prefix, so that pages served under different prefixes on one host do not read each other's.

### Rationale

A hosted deployment runs one viewer per workspace behind a single router that tells them apart by the leading part of the path. A viewer that assumed it owned the root of the site would answer only the first workspace. The prefix is configured on the viewer rather than rewritten by the router, because the page builds URLs of its own and a rewriting router cannot reach into a script.

### Changelog

- 2026-09-17 | c1ac9032 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-09-17 | cd69f63b | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-09-17 | - | - | Michael Lewis (<michael@anspar.org>) | Initial version

*End* *Viewer Served Under a Configured Prefix* | **Hash**: c1ac9032
