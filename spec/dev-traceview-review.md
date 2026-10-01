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

C. With no prefix configured, the server SHALL answer the same routes at the same paths as it does without this capability.

D. The agent surface SHALL be reachable under the same prefix as the page.

E. A prefix that is not empty and is not one or more path segments, each introduced by a single slash and made only of ASCII letters, ASCII digits and the characters `-`, `_`, `.` and `~`, no segment being `.` or `..`, SHALL be refused with a message naming that form.

F. <RETIRED> Superseded by REQ-d00300-C.

G. A prefix applies to the served surface; a request to generate the page as a file while naming a prefix SHALL be refused with a message naming that the prefix applies to the server alone.

H. With no prefix configured, the served page SHALL request the same URLs as it does without this capability.

I. <RETIRED> Superseded by REQ-d00300-B.

### Rationale

A hosted deployment runs one viewer per workspace behind a single router that tells them apart by the leading part of the path. A viewer that assumed it owned the root of the site would answer only the first workspace. The prefix is configured on the viewer rather than rewritten by the router, because the page builds URLs of its own and a rewriting router cannot reach into a script. The accepted form is the one the page, a router and the mount all spell identically: a space, a `?`, a `#` or a `%` is spelt differently by each, so one such prefix would name a different path in each, and it is refused before the server starts rather than discovered as a page requesting one path of a server answering at another.

### Changelog

- 2026-09-28 | ae94b103 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-09-18 | b3c8493f | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-09-18 | 041a7999 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-09-17 | c1ac9032 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-09-17 | cd69f63b | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-09-17 | - | - | Michael Lewis (<michael@anspar.org>) | Initial version

*End* *Viewer Served Under a Configured Prefix* | **Hash**: ae94b103

---

## REQ-d00300: Viewer Remembered State

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

The viewer remembers how a reader left it and restores that the next time the reader opens it. *Project State* stays with the viewer that saved it. A *Reader Preference* follows the reader to every viewer on the host.

### Assertions

A. When a reader opens a viewer again in the same browser, the viewer SHALL restore the state that it saved for that reader.

B. The viewer SHALL restore *Project State* only from a viewer at the same origin. The origin is the scheme, the host and the port of the page address.

C. The viewer SHALL restore *Project State* only from a viewer at the same path. The path is the page address up to its last slash.

D. The viewer SHALL restore each *Reader Preference* as the reader last set it in any viewer on the same host.

### Rationale

Each viewer shows one project, and a filter, an open card or a collapsed node means something only in that project. Restored into a viewer for another project, such state can hide the whole tree with nothing on screen to say why. Two viewers can share a host in two ways: on different ports, as when a reader runs one viewer per repository or worktree, or under different paths of one origin, as with workspaces served under a configured prefix (REQ-d00295) or static pages published side by side. Both ways must keep *Project State* apart, so a viewer is told apart by its origin and by its path. A served viewer is always loaded at its prefix followed by a slash, and a static page loaded by its directory or by its file name ends at the same last slash, so each viewer has exactly one path. *Project State* that does not show which origin and path saved it cannot meet B or C, so a viewer does not restore it. A *Reader Preference* such as the theme, the font size or a panel width is how the reader likes to work, not a fact about a project, so it follows the reader.

### Changelog

- 2026-09-28 | f794104b | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms, update hash, add missing changelog section

*End* *Viewer Remembered State* | **Hash**: f794104b

---

## REQ-d00313: Served Graph Currency

**Level**: dev | **Status**: Active | **Implements**: REQ-p00015-E

A process that serves a graph to many requests answers from a graph it built earlier. This requirement states what that process compares its graph against, and what it says when it answers from a graph that is behind the files on disk.

### Assertions

A. The system SHALL judge whether a served graph is current against every file that graph was built from, in every member of the federation.

B. The files a served graph is built from SHALL include the results, the coverage and the run record of every test target that a member of the federation declares.

C. While a served graph predates a file it was built from, the system SHALL disclose with each answer it serves from that graph that the graph predates that file, naming the file.

D. While a run of a test target is in progress, the system SHALL treat a change in the output area of that target as a change to the files a served graph was built from only where the change is to the record of that run.

### Rationale

A served graph is current only against the files it was compared with. Results and coverage are files the graph was built from as surely as specifications are, and an associate's files are as much a part of the answer as the root repository's. A process that watches less than it reads reports a file that arrived after its build as absent, which is the reading a project that never ran its tests would get.

A serving process does not rebuild over changes somebody has not saved, so a graph can stay behind the files on disk while it is served. C makes that state visible on the answer itself rather than in a separate place a reader has to know to look.

A run writes into its output area for as long as it runs. Rebuilding on each write would read an area that is half written and repeat the work on every request. The record of the run changes when a run starts and when it finishes, and those are the two changes that say something about what the area holds.

### Changelog

- 2026-10-01 | e791c1a1 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash, add missing changelog section

*End* *Served Graph Currency* | **Hash**: e791c1a1
