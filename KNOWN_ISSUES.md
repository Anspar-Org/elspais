# Known Issues

[ ] feature: config
- make journey IDs configurable like REQ IDs
- second instand of IDresolver?

[x] testing: bug
- xml test results are all on 'one line' so its hard to link to them (all results are on line 1).
- Fixed: pre-push hook now pretty-prints JUnit XML after pytest runs (ET.indent).
- JUnit XML parser assigns per-testcase line numbers when XML is pretty-printed.

[x] viewer: bug
- expand collapse icons in tree should be same size as in header.
- Fixed: nav-tree-toggle font-size changed from 8px to 16px to match card header expand icons.

[x] Feature: Viewer. Allow editing of multi-Assertion references in REQUIREMENTS.
- Fixed: JS was reading data.children but API returns data.assertions. One-line fix.

[x] Feature: Viewer. Edit mode supports editing of Journey in the Card interface.
- Full CRUD: title, actor, goal, context inline editing (save on blur)
- Section-based body editing: each ## section has header editor + content textarea
- Add/delete sections, add/delete journey (with file picker modal)
- Validates references: add/remove with requirement picker + multi-assertion selector
- Move to file reuses existing dialog
- Body reconstructed from structured fields for round-trip fidelity

[x] Bug: daemon doesn't work for all commands
- elspais checks, twice in a row: 2nd call is always fast
- elspais checks broken, never fast
- Fixed: added compute_broken() + /api/run/broken endpoint + _engine.call() in broken.py run()
- Audited all commands: all read-only graph commands now use daemon; write commands (fix, validate, reformat) intentionally local-only.

[x] viewer: feature
- Collapse arrow doubled (8px→16px), card headers consistent (req-card-id class for all)
- Hierarchy filter text area moved first in toolbar
- + REQ and + JNY buttons added to card stack header bar

[x] viewer: bug
- Coverage filter fixed: computed from combined_color tier instead of unpopulated field
- Selecting none/partial/full now correctly filters tree

[x] viewer: feature
- Add new REQ with file picker modal, level selector, auto-opens card after creation

[x] viewer: bug (was old, already works)
- REQ Card: multi-select ASSERTION save toast

[x] viewer: bug
- Clicking relationship link opens target card and flashes targeted assertions
- Uses same flash mechanism as coverage header badges


[x] tweak: In Viewer Card: Add Refined badge to Assertion lines
- Implemented: 6 assertion badges (IMP/REF/TST/VER/VAL/ACC) shown only when direct links exist
- Header badges clickable to expand REQ-level links + flash matching assertions
- Journey links open Journey card; VER shows results, ACC shows journey results
- 3 display modes (full/abbrev/dots); badge colors driven by config severity
- Multi-assertion references (A+B+C) now properly parsed in test/code refs


[x] feature: move file dialog
- show list of existing spec/ files
- with "new file" button
- Implemented: modal dialog with radio buttons for existing spec files + "New file" option; new GET /api/spec-files endpoint returns SPEC-type FILE nodes; new filenames validated against scanning config

[x] feature: add to checks: REQs with no Assertions should be flagged.
- warning (default) or info level (configurable).
- Add these to gaps report.
- clasify as "not_testable"
- Implemented: spec.no_assertions health check (always-on, default warning); no_assertions gap type in gaps report labeled "NOT TESTABLE (no assertions)"; configurable via [rules.format] no_assertions_severity

---

[ ] wishlist: viewer: edit assertions-> must give a 'reason' iff CHANGELOG is enforced and status=active
- Shows CHANGELOG section of the card. 'Reason' field in the newest entry is editable.
- Cannot save to disk without reason
- handle adding CHANGELOG if its not already there
- auto-fill all changelog fields, but make them editable in edit mode

[ ] chore (major): general code review. file sizes, duped code, workarounds, sloppiness, etc.

[ ] Feature (major): change ID of a Requirement
- All references are updated, creating a complete list of graph mutation operations to do so
- The list of before / after IDs are written/appended to a file (`elspais-renumbering-<before-hash>.csv`)
- This file is intended to allow updating references in non-graph locations, such as:
- docs/
- database/ (although this will eventually be a code/ dir, with filetypes .sql
- infrastructure/ (although that will eventually be a code/ dir, with filetypes .tf, .tfvars, .yaml, .sh, etc.
- we could also, perhaps optionally, process all of those files as well.

[x] Feature (high): Viewer. Add the ability to select a different commit on the current branch
- Implemented: two-panel branch picker (branches left, commit history right) with rewind-to-checkpoint
- Rewinding enters read-only mode; enabling edit mode creates a new branch (e.g., feat-auth-v2)
- Also added: Checkpoint button (local commit), slide-to-share push widget, removed Revert/Refresh buttons
- Pipeline: Edit -> Undo/Save -> Checkpoint -> Share

[x] UX (medium): Viewer vs checks report coverage disagreement.
- Implemented: Replaced CODE/TEST/UAT coverage checks with 5 CoverageDimension checks (implemented, tested, verified, uat_coverage, uat_verified). Each reports both REQ-level ("X/Y REQs have any coverage") and assertion-level ("X/Y assertions direct, Y indirect") metrics. Unified check_dimension_coverage() function.

[ ] Feature: **Dart/Flutter parser support** (function detection strategy, result parser)

[x] Chore: review specs, docs, help, init for accuracy

[x] Naming (minor): `coverage_pct` in `RollupMetrics` was misleading — it measured assertion *reference* coverage, not traditional code coverage. Renamed to `referenced_pct` (also `indirect_referenced_pct`, `uat_referenced_pct`).

[ ] Feature (medium): `code_tested` metric 
— traditional code-test coverage (which lines of code are executed during tests). 
- Distinct from the current code-requirement traceability (`# Implements:` references). 
- Will require test runner integration to collect line-level execution data.
- Can we also map lines tested to Requirements, through the TEST->line coverage link? 

[ ] Chore (low): start using Changelog in REQs after v 1.0.0

[ ] Wishlist **Drag-and-drop reordering** in the UI (render_order mutation) - prospective only

[ ] Wishlist: **Assertion reordering** with automatic label recomputation and reference updating
- Also handle Assertion deletion re-numbering (when state is 'prospective'), or marking 'deprecated' (active states)
- Don't allow editing of state = retired REQs

[ ] chore (med): Unify `file_patterns` / `directories` in scanning config. `file_patterns` (glob against repo root, no skip logic) and `directories` (recursive walk with hardcoded `DEFAULT_CODE_PATTERNS` + skip/ignore) are partially redundant. Consider replacing both with a single `patterns` list that supports glob + skip/ignore.

---

[x] feature: cli search 'search terms string' : invokes the 'search' api. takes a string.

[x] Bug: Elspais should check the ENV var for ELSPAIS_VERSION and error if the current install is not compatible

[x] Tweak: allow_unresolved_cross_repo or similar in [validation], so we can run health and ignore unresolved refs to associated repos

[x] Change: We now define User Journeys to "Validate" Requirements (or Assertions).
- Implemented: JNYs declare `Validates: REQ-xxx-A+B` to create VALIDATES edges in the traceability graph.
- UAT coverage is now calculated separately from automated test coverage (CoverageSource.UAT).
- RollupMetrics tracks `uat_covered` and `uat_total` alongside standard coverage fields.
- Multi-assertion syntax supported (e.g., `Validates: REQ-p00001-A+B` expands to two edges).
- We can now calculate a second 'coverage' 'Validated' value: which REQs (or Assertions) are validated by a JNY?
- This will be used for UAT: we treat the JNYs as a the set of manual tests to run that will cover all the REQs and demonstrate the correct functionality.
- This corresponds to the PQ

[x] Parsing Schema
- formal schema for REQUIREMENTS
- formal schema for USER-JOURNEYS (the PQ of PQ/EQ/IQ system)

[x] Bug: Fix get_requirement() MCP/API call to NOT return a uselessly large result.
- LLMs confidently say "give me everything", but that's not what they really need.
- Lets define a better set of MCP endpoints that return practical info.
- There is use-case for just hiearchy info (REQs and ASSERTION and refines: and implements:),
- ...and for details (like the original text and all the Structure Nodes)
- but there is rarely a use-case for "all the tests and code and results"

[x] Feature: Change the current auto-publish-on-merge-to-main.
- Implemented: add the `publish` label to a PR before merging to trigger release + PyPI + Homebrew publish.
- Merges without the label are silent (no publish, no spam).

[x] CONFIG_DESIGN.md

[x] LARK_PARSER_DESIGN.md

[x] Chore: The elspais fix command output is confusing. It makes it look like errors have occured, rather than being fixed.

[x] Feature: **Declarative config schema and versioned migration**
- There is no single authoritative schema for .elspais.toml. Config fields are defined across three sources that drift independently: `DEFAULT_CONFIG` (code), `elspais init` template (hardcoded string), and `docs/configuration.md`.
- Some fields used in code are absent from DEFAULT_CONFIG (e.g. `version`, `associated.prefix`, `core.path`, `directories.code`, `directories.ignore`, `traceability.scan_patterns`, `traceability.source_roots`).
- Unknown config keys are silently ignored; missing keys silently fall back to defaults. No validation errors for typos or stale settings.
- `_migrate_legacy_patterns()` is a temporary compat shim for pre-v2 configs using old `[patterns]` format. It should be replaced by a proper version-gated migration system.
- A single declarative schema should drive: config validation (error on unknown/missing keys), `elspais init` template generation, version-to-version migration, and docs verification.
- Add a `version` field to .elspais.toml (v2 = current [id-patterns] format). Configs without `version` get the legacy migration path until sunset.

[x] Bug: Health. Don't count errors in Retired REQs as errors for HEALTH calculations. They can still be put into the detailed report.

[x] Feature: Health. If not HEALTHY, show the command to get a detailed list of errors: e.g. --code -o filename.json, or whatever is appropriate

[x] Bug: Viewer does not display the Tree with items sorted by ID.
- e.g. p00001 should be above p00002, etc.

[x] Bug: Viewer Push button (in edit mode) isn't active unless changes were made in the viewer. But there could be changes on-disk (and therefore in memory) that could be pushed.
- The push-able state should depend on the actual file states, not on elspais activity.

[x] Feature: select branch to view and reload the graph.
- triggered by clicking on the branch name
- Both local and remote branches can be selected.
- If a remote branch, pull it local first, of course.
- If there a conflicts on the pull, just show an error and don't change anything.
- obviously refresh the GUI after loading a new branch.
- warn if unsaved in-memory edits will be lost

[x] Major Project: In elspais repo, udpdate spec file naming convention
- Rename spec/ files more sensibly  and consistently
- Renumber REQs to follow a pre-fix-per-file convention (not enforced, just for convenience)
- The file mutators should be renumbering easy- just make sure it also catches the code and test file references, not just REQ/JNY refs.
