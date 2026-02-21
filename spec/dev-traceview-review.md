# Trace View Review System Specifications

These requirements define the collaborative review system for requirement traceability.

---

# REQ-d00001: Review Package Management

**Level**: Dev | **Status**: Draft | **Implements**: REQ-p00009

**Purpose:** Define package organization for grouping reviews.

## Assertions

A. The Package model SHALL contain:

    - `packageId`: UUID string
    - `name`: Human-readable package name
    - `description`: Optional description text
    - `reqIds`: Array of requirement IDs included in this package
    - `createdBy`: Username of package creator
    - `createdAt`: ISO 8601 timestamp

B. Packages SHALL be explicitly created by users; the system SHALL NOT auto-create packages.

C. A requirement SHALL belong to at most one package at a time within a branch.

D. The system SHALL allow a requirement to belong to different packages over time (across branches/archive cycles).

E. All threads and comments SHALL be owned by exactly one package.

F. Package deletion SHALL archive (not destroy) the package and its threads.

*End* *Review Package Management* | **Hash**: 8d2f827b

---

# REQ-d00002: Review Storage Architecture

**Level**: Dev | **Status**: Draft | **Implements**: REQ-p00009

**Purpose:** Define file-based storage layout for review data.

## Assertions

A. Review data SHALL be stored under `.reviews/` directory in the repository root.

B. Package metadata SHALL be stored at: `.reviews/packages.json` containing:

    - `version`: Format version string (currently "1.0")
    - `packages`: Array of ReviewPackage objects
    - `activePackageId`: Currently active package ID (optional)

C. Threads for each requirement SHALL be stored at: `.reviews/reqs/{req-id}/threads.json`

D. Review flags SHALL be stored at: `.reviews/reqs/{req-id}/flag.json`

E. Status requests SHALL be stored at: `.reviews/reqs/{req-id}/status.json`

F. Configuration SHALL be stored at: `.reviews/config.json`

G. Storage operations SHALL use atomic writes (temp file + rename pattern).

H. Requirement IDs in paths SHALL be normalized (colons/slashes replaced with underscores).

## Rationale

V2 package-centric storage paths are defined in the codebase but not actively used. The current implementation uses the V1 format described above.

*End* *Review Storage Architecture* | **Hash**: 9ba72e6f

---

# REQ-d00003: Review Package Archival

**Level**: Dev | **Status**: Draft | **Implements**: REQ-p00011

**Purpose:** Define archival behavior for resolved or deleted packages.

## Assertions

A. Archived packages SHALL be stored at: `.reviews/archive/{pkg-id}/`

B. Archive SHALL preserve complete package structure:

    - `package.json` with archive metadata added
    - `reqs/` directory with all thread data

C. Archive metadata SHALL include:

    - `archivedAt`: ISO 8601 timestamp
    - `archivedBy`: Username who triggered archive
    - `archiveReason`: One of `"resolved"`, `"deleted"`, `"manual"`

D. Archive SHALL be triggered by:

    - Resolving all threads in a package (reason: `"resolved"`)
    - Deleting a package (reason: `"deleted"`)
    - Manual archive action (reason: `"manual"`)

E. Deleting a package SHALL move it to archive rather than destroying it.

F. Archived data SHALL be read-only and preserved indefinitely.

*End* *Review Package Archival* | **Hash**: 458be109

---

# REQ-d00004: Review Git Audit Trail

**Level**: Dev | **Status**: Draft | **Implements**: REQ-p00010

**Purpose:** Track git context for review packages.

## Assertions

A. Package SHALL record `branchName` when created (current git branch).

B. Package SHALL record `creationCommitHash` when created (HEAD commit).

C. Package SHALL update `lastReviewedCommitHash` on each comment activity.

D. Archived packages SHALL preserve all commit hash references for audit.

E. The UI SHALL display commit information with appropriate context:

    - For active packages: Show current commit tracking
    - For archived packages: Show "Commit: {hash} (may be squashed)" with search link

F. Commit tracking SHALL handle squash-merge scenarios gracefully (archived hash may not exist post-merge).

*End* *Review Git Audit Trail* | **Hash**: f1829e0a

---

# REQ-d00005: Review Archive Viewer

**Level**: Dev | **Status**: Draft | **Implements**: REQ-p00011

**Purpose:** Provide read-only access to archived packages via API and UI.

## Assertions

A. The API SHALL provide endpoints to list archived packages with:

    - Package name and description
    - Archive date and reason
    - Number of threads/comments
    - Branch and commit info

B. Archived packages SHALL be accessible in read-only mode via API.

C. The API SHALL NOT allow adding or editing comments in archived packages.

D. The archive API SHALL return archival metadata:

    - Date archived
    - Archive reason (resolved/deleted/manual)
    - Archived by (username)

E. The archive API SHALL return git audit trail information:

    - Branch name
    - Creation commit hash
    - Last reviewed commit hash

F. The UI SHALL provide visual indication of read-only state for archived packages.

G. The UI SHALL display a collapsible archive panel listing all archived packages.

H. The UI SHALL provide an archive viewer modal showing package details, metadata, and contained requirements.

I. The UI SHALL display commit hashes with warning that they may not exist post-squash-merge.

*End* *Review Archive Viewer* | **Hash**: 0bcf8525

---

# REQ-d00006: Review Threads and Comments

**Level**: Dev | **Status**: Draft | **Implements**: REQ-p00009

**Purpose:** Define data models for review threads and comments.

## Assertions

A. All review data types SHALL be implemented as dataclasses with:

    - `to_dict()`: JSON-serializable dictionary conversion
    - `from_dict()`: Deserialization from dictionaries
    - `validate()`: Returns (is_valid, list_of_errors)

B. Enums SHALL use string values for JSON compatibility (PositionType, RequestState, ApprovalDecision).

C. The Thread model SHALL contain:

    - `threadId`: UUID string
    - `reqId`: Requirement ID (without REQ- prefix)
    - `createdBy`: Username who started thread
    - `createdAt`: ISO 8601 timestamp
    - `position`: CommentPosition object
    - `resolved`: Boolean
    - `resolvedBy`: Optional username
    - `resolvedAt`: Optional ISO 8601 timestamp
    - `comments`: List of Comment objects
    - `packageId`: Optional package ownership

D. The Comment model SHALL contain:

    - `id`: UUID string
    - `author`: Username
    - `timestamp`: ISO 8601 timestamp
    - `body`: Markdown content

E. The CommentPosition model SHALL support anchor types:

    - `line`: Specific line number with `lineNumber` field
    - `block`: Range of lines with `lineRange` tuple
    - `word`: Keyword occurrence with `keyword` and `keywordOccurrence` fields
    - `general`: No specific position (whole REQ)

F. Factory methods (`create()`) SHALL auto-generate UUIDs and timestamps.

G. Container classes (ThreadsFile, StatusFile, PackagesFile) SHALL include version tracking.

H. CommentPosition SHALL include `hashWhenCreated` for content drift detection and `fallbackContext` for position recovery.

I. StatusRequest state SHALL be automatically calculated from approval votes.

J. All timestamps SHALL be UTC in ISO 8601 format.

*End* *Review Threads and Comments* | **Hash**: 74becc99

---

# REQ-d00007: Review Storage Operations

**Level**: Dev | **Status**: Draft | **Implements**: REQ-p00009

**Purpose:** Define CRUD and merge operations for review data.

## Assertions

A. Storage operations SHALL use atomic writes (temp file + rename pattern) for all write operations.

B. Thread operations SHALL support:

    - `load_threads()`: Returns empty ThreadsFile if not exists
    - `save_threads()`: Atomic write
    - `add_thread()`: Append and persist
    - `add_comment_to_thread()`: Find thread, append comment, persist
    - `resolve_thread()` / `unresolve_thread()`: Update resolution state

C. Status request operations SHALL support:

    - `load_status_requests()`: Returns empty StatusFile if not exists
    - `save_status_requests()`: Atomic write
    - `create_status_request()`: Append and persist
    - `add_approval()`: Find request, add approval, recalculate state
    - `mark_request_applied()`: Transition to applied state

D. Review flag operations SHALL support:

    - `load_review_flag()`: Returns cleared flag if not exists
    - `save_review_flag()`: Atomic write

E. Package operations SHALL support:

    - `load_packages()`: Returns file with default package if not exists
    - `save_packages()`: Atomic write
    - `create_package()` / `update_package()` / `delete_package()`
    - `add_req_to_package()` / `remove_req_from_package()`

F. Configuration operations SHALL support:

    - `load_config()`: Returns default config if not exists
    - `save_config()`: Atomic write

G. Merge operations SHALL combine data from multiple user branches:

    - `merge_threads()`: Deduplicate by ID, merge comments by ID, use OR for resolution
    - `merge_status_files()`: Deduplicate by ID, merge approvals, recalculate state
    - `merge_review_flags()`: Newer flag wins, merge scopes

H. Storage paths SHALL follow convention: `.reviews/reqs/{normalized-req-id}/`

I. Requirement IDs SHALL be normalized (colons/slashes replaced with underscores).

J. Merge conflict resolution SHALL use timestamp-based deduplication for overlapping data.

*End* *Review Storage Operations* | **Hash**: bffc007d

---

# REQ-d00008: Position Resolution

**Level**: Dev | **Status**: Draft | **Implements**: REQ-p00012

**Purpose:** Resolve comment positions within requirement text with content drift handling.

## Assertions

A. `resolve_position()` SHALL resolve CommentPosition anchors to current document coordinates.

B. Resolution confidence levels SHALL be:

    - `EXACT`: Hash matches, position trusted
    - `APPROXIMATE`: Fallback resolution succeeded
    - `UNANCHORED`: All fallbacks failed

C. When document hash matches position's `hashWhenCreated`, resolution SHALL be EXACT using stored coordinates.

D. When hash differs, fallback resolution SHALL be attempted yielding APPROXIMATE confidence.

E. For LINE positions with hash mismatch, SHALL search for `fallbackContext` string.

F. For BLOCK positions with hash mismatch, SHALL search for context and expand to block boundaries.

G. For WORD positions, SHALL find the Nth occurrence based on `keywordOccurrence` field.

H. GENERAL positions SHALL always resolve with EXACT confidence (apply to entire REQ).

I. ResolvedPosition SHALL include `resolutionPath` describing the fallback strategy used.

J. When no fallback succeeds, SHALL resolve as UNANCHORED with original position preserved.

*End* *Position Resolution* | **Hash**: ad27b8e5

---

# REQ-d00009: Git Branch Management

**Level**: Dev | **Status**: Draft | **Implements**: REQ-p00010

**Purpose:** Handle git branch operations for the review system.

## Assertions

A. Review branches SHALL follow naming convention: `reviews/{package_id}/{username}`

B. `get_review_branch_name()` SHALL return formatted branch name from package and user.

C. `parse_review_branch_name()` SHALL extract (package_id, username) from valid branch names.

D. `is_review_branch()` SHALL return True only for branches matching the naming pattern.

E. `list_package_branches()` SHALL return all branch names for a given package across all users.

F. `get_current_package_context()` SHALL return (package_id, username) when on a review branch, or (None, None) otherwise.

G. `commit_and_push_reviews()` SHALL commit all changes in `.reviews/` and push to remote tracking branch.

H. Branch operations SHALL detect and report conflicts via `has_conflicts()` and `has_uncommitted_changes()`.

I. `fetch_package_branches()` SHALL fetch all remote branches for a package to enable merge operations.

J. Branch cleanup operations SHALL:

    - Never delete current branch
    - Warn about unmerged branches (unless force=True)
    - Warn about unpushed commits (unless force=True)

*End* *Git Branch Management* | **Hash**: ec2a7171

---

# REQ-d00010: Review API Server

**Level**: Dev | **Status**: Draft | **Implements**: REQ-p00012

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

*End* *Review API Server* | **Hash**: 41715183

---

# REQ-d00011: Status Modifier

**Level**: Dev | **Status**: Draft | **Implements**: REQ-p00012

**Purpose:** Modify REQ status in spec files.

## Assertions

A. `find_req_in_file()` SHALL locate a requirement in a spec file and return status line information.

B. `get_req_status()` SHALL read and return the current status value from the spec file.

C. `change_req_status()` SHALL update the status value in the spec file atomically.

D. Status values SHALL be validated against allowed set: Draft, Active, Deprecated.

E. The status modifier SHALL preserve all other content in the spec file.

F. The status modifier SHALL update the requirement's content hash footer after status changes.

G. Failed status changes SHALL NOT leave the spec file in a corrupted or partial state.

H. `find_req_in_spec_dir()` SHALL search both core spec/ and sponsor/*/spec/ directories.

*End* *Status Modifier* | **Hash**: 3e581bc6

---

# REQ-d00012: Review UI Framework

**Level**: Dev | **Status**: Draft | **Implements**: REQ-p00008

**Purpose:** Implement the interactive review user interface.

## Assertions

A. The UI SHALL provide a review mode toggle button that adds/removes `review-mode` class on the document body.

B. The UI SHALL render interactive line numbers for requirement content when review mode is active.

C. Line numbers SHALL be clickable to select anchor positions for new comments.

D. The UI SHALL support keyboard navigation for line selection (arrow keys, shift for range).

E. Clicking a position label SHALL highlight the corresponding lines in the requirement card.

F. Highlight styling SHALL reflect position confidence: `highlight-exact`, `highlight-approximate`, `highlight-unanchored`.

G. For GENERAL position type, the entire requirement card SHALL be highlighted.

H. The review panel SHALL be resizable via a drag handle.

I. The UI SHALL dispatch custom events for review state changes (`traceview:review-mode-changed`, `traceview:line-selected`).

J. The UI SHALL provide a help panel with onboarding guidance and tooltips.

K. JavaScript modules SHALL be loaded in dependency order via the `ReviewSystem` (RS) namespace.

*End* *Review UI Framework* | **Hash**: 448be3b9
