# Trace View Server Specifications

These requirements define the *Traceability* viewer server and federation.

---

# REQ-d00010: Review API Server

**Level**: dev | **Status**: Active | **Implements**: REQ-p00006

**Purpose:** Flask-based REST API server for the review system.

## Assertions

A. The API server SHALL be implemented as a Flask application with `create_app(repo_root, static_dir)` factory function.

B. Thread endpoints SHALL support:
    - `POST /api/reviews/reqs/{id}/threads`: Create thread
    - `POST /api/reviews/reqs/{id}/threads/{tid}/comments`: Add comment
    - `POST /api/reviews/reqs/{id}/threads/{tid}/resolve`: Resolve thread
    - `POST /api/reviews/reqs/{id}/threads/{tid}/unresolve`: Unresolve thread

C. Status endpoints SHALL support:
    - `GET /api/reviews/reqs/{id}/status`: Get current status
    - `POST /api/reviews/reqs/{id}/status`: Change status
    - `GET /api/reviews/reqs/{id}/requests`: Get status requests
    - `POST /api/reviews/reqs/{id}/requests`: Create status request
    - `POST /api/reviews/reqs/{id}/requests/{rid}/approvals`: Add approval

D. Package endpoints SHALL support:
    - `GET/POST /api/reviews/packages`: List/create packages
    - `GET/PUT/DELETE /api/reviews/packages/{id}`: CRUD operations
    - `POST/DELETE /api/reviews/packages/{id}/reqs/{req_id}`: Membership
    - `GET/PUT /api/reviews/packages/active`: Active package management

E. Sync endpoints SHALL support:
    - `GET /api/reviews/sync/status`: Sync status
    - `POST /api/reviews/sync/push`: Manual push
    - `POST /api/reviews/sync/fetch`: Fetch from remote
    - `POST /api/reviews/sync/fetch-all-package`: Fetch all package branches

F. CORS SHALL be enabled for cross-origin requests.

G. Static file serving SHALL be supported from configured directory.

H. All write endpoints SHALL optionally trigger auto-sync based on configuration.

I. Archive endpoints SHALL support:
    - `POST /api/reviews/packages/{id}/archive`: Manual archive
    - `GET /api/reviews/archive`: List archived packages
    - `GET /api/reviews/archive/{id}`: Get archived package
    - `GET /api/reviews/archive/{id}/reqs/{req_id}/threads`: Get archived threads

J. Health check endpoint SHALL be available at `/api/health`.

## Changelog

- 2026-04-23 | b647ec64 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Review API Server* | **Hash**: b647ec64

---

## REQ-d00206: Server Federation and Staleness

**Level**: dev | **Status**: Active | **Implements**: REQ-d00010, REQ-d00200

The Flask review server SHALL expose federation repo metadata and staleness information.

## Assertions

A. `/api/repos` SHALL return a list of federated repos from `iter_repos()` with name, path, status (ok/error), git_origin, and error fields.

B. `/api/repos` SHALL include staleness info (remote_diverged, branch) for repos with a `git_origin` configured, using `git_status_summary()` per-repo.

C. `/api/status` SHALL include federation repo metadata from `iter_repos()`, replacing the legacy `associated_repos` field.

D. Staleness info SHALL be informational only and SHALL NOT affect build or health check results.

## Rationale

Multi-repo federation users need visibility into which repos are current and which are behind their remotes. The viewer/server surfaces this as informational metadata without gating builds on it.

## Changelog

- 2026-04-23 | b4fae1d0 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Server Federation and Staleness* | **Hash**: b4fae1d0
