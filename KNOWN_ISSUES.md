# Known Issues

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


[ ] Bug: Fix get_requirement() MCP/API call to NOT return a uselessly large result. 
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

[ ] Feature: Viewer. Allow editing of multi-Assertion references in REQUIREMENTS.
- Use multi-select dropdown, then render the reference using the configured settings, e.g. REQ-p12345-A+B+C+X

[ ] Feature: change ID of a Requirement
- All references are updated, creating a complete list of graph mutation operations to do so
- The list of before / after IDs are written/appended to a file (`elspais-renumbering-<before-hash>.csv`)
- This file is intended to allow updating references in non-graph locations, such as:
- docs/
- database/ (although this will eventually be a code/ dir, with filetypes .sql
- infrastructure/ (although that will eventually be a code/ dir, with filetypes .tf, .tfvars, .yaml, .sh, etc.
- we could also, perhaps optionally, process all of those files as well.

---

[ ] Feature: Add the ability to select a different commit on the current branch
- as part of the 'select branch' modal
- this is like a 'rewind' for the user - or an 'undo save'
- there are many ways this could be complicated, but let's keep it simple: if they check out the non-HEAD of a branch, then any future commits will be a force and non merge with the intermediate commits

[ ] Feature: **Dart/Flutter parser support** (function detection strategy, result parser)

[ ] Chore: review specs, docs, help, init for accuracy

---

[x] Major Project: In elspais repo, udpdate spec file naming convention
- Rename spec/ files more sensibly  and consistently
- Renumber REQs to follow a pre-fix-per-file convention (not enforced, just for convenience)
- The file mutators should be renumbering easy- just make sure it also catches the code and test file references, not just REQ/JNY refs.

[ ] Chore: start using Changelog in REQs

[ ] Wishlist **Drag-and-drop reordering** in the UI (render_order mutation) - prospective only

[ ] Wishlist: **Assertion reordering** with automatic label recomputation and reference updating
- Also handle Assertion deletion re-numbering (when state is 'prospective'), or marking 'deprecated' (active states)
- Don't allow editing of state = retired REQs

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
