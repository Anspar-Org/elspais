# CLI Development Requirements

## REQ-d00080: Diagnostic Command Exit Code Contract

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002, REQ-p00005-E

Diagnostic commands (`doctor`, `health`) SHALL exit non-zero when they detect configuration or validation failures, ensuring CI pipelines and callers can rely on exit codes to gate merges.

## Assertions

A. Diagnostic commands (`doctor`, `health`) SHALL exit non-zero when any check produces a warning-level or error-level finding. The `--lenient` flag SHALL relax this so that only error-level findings cause non-zero exit.

B. `health` SHALL exit non-zero when zero requirements are found and a spec directory is configured. A configured project with no parseable requirements is an error, not an empty success.

C. `doctor` and `health` path-existence checks SHALL verify directories exist on disk, not merely that a path string is present in the config.

D. For `project.type = "associated"`, `doctor` SHALL validate that the `[associated]` section exists and has a non-empty `prefix`. A missing or misconfigured `[associated]` section in an associated project is a configuration error.

E. For `project.type = "core"` with configured associate paths, `health` SHALL exit non-zero when an associate path is missing, misconfigured, or produces zero requirements. A silent requirement count drop is a data-loss condition.

## Rationale

Warnings represent real problems: missing paths, orphaned nodes, unresolved references. By default, any warning causes a non-zero exit code, making diagnostic commands safe for CI gating (REQ-o00066-C). The `--lenient` flag provides an escape hatch for development workflows where warnings are informational and should not block.

The previous `validate` command's responsibilities are absorbed by `health`. References to `validate` in assertions B and E now refer to the `health` command's spec-checking category.

## Changelog

- 2026-04-23 | ada92a29 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Diagnostic Command Exit Code Contract* | **Hash**: ada92a29
---

## REQ-d00081: Multi-Assertion Reference Expansion

**Level**: dev | **Status**: Active | **Implements**: REQ-p00001

Multi-*Assertion* references allow compact notation for referencing multiple assertions of the same requirement. A dedicated separator character (distinct from ID separators) joins *Assertion* labels after the first: `REQ-p00001-A+B+C` expands to individual *Assertion* references `REQ-p00001-A`, `REQ-p00001-B`, `REQ-p00001-C`.

## Assertions

A. The `multi_assertion_separator` key SHALL be available in `[references.defaults]` configuration.

B. The default value of `multi_assertion_separator` SHALL be `"+"`.

C. Config validation SHALL reject configurations where the multi-*Assertion* separator character appears in the `separators` list.

D. Expansion SHALL occur in the graph builder's link resolution, applying uniformly to all parser types (requirement, code, test, result).

E. The expansion pattern SHALL derive from the configured *Assertion* label pattern and multi-*Assertion* separator.

F. When `multi_assertion_separator` is empty or `false`, expansion SHALL be disabled.

G. A reference containing no multi-*Assertion* separator character SHALL pass through unchanged.

## Rationale

The previous implementation hardcoded expansion in RequirementParser only, using a regex that assumed uppercase letter labels and hyphen separators. This created silent failures when code comments (`# Implements: REQ-x-A-B-C`) and test names (`test_REQ_x_A_B_C`) were not expanded. A dedicated separator character eliminates ambiguity regardless of the configured *Assertion* label style (uppercase, numeric, alphanumeric).

## Changelog

- 2026-03-30 | 313fe52b | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Multi-Assertion Reference Expansion* | **Hash**: 313fe52b
---

## REQ-d00082: Unified Reference Configuration

**Level**: dev | **Status**: Active | **Implements**: REQ-p00001-A

The system SHALL provide a unified, configurable reference pattern system used by all parsers (CodeParser, TestParser, JUnitXMLParser, PytestJSONParser) to locate requirement references in source files.

## Assertions

D. The reference configuration SHALL support case-sensitive and case-insensitive ID matching.

E. The reference configuration SHALL support configurable ID separators including underscore and hyphen.

F. The reference configuration SHALL support file-type specific overrides via glob patterns (e.g., `*.py`, `tests/legacy/**`).

G. The reference configuration SHALL extract ID components (prefix, type, number) from matched references.

H. The reference configuration SHALL support configurable comment styles (e.g., `#`, `//`, `--`) for code reference detection.

I. CodeParser SHALL accept PatternConfig and ReferenceResolver for configurable reference matching in source files.

J. TestParser SHALL accept PatternConfig and ReferenceResolver for configurable reference matching in test files.

K. JUnitXMLParser SHALL accept PatternConfig and ReferenceResolver for configurable reference matching in JUnit XML reports.

L. PytestJSONParser SHALL accept PatternConfig and ReferenceResolver for configurable reference matching in pytest JSON reports.

## Rationale

Different projects use different ID conventions, comment styles, and directory structures. A unified reference configuration allows all parsers to share the same configurable pattern matching, avoiding duplicated logic and ensuring consistent behavior across parser types.

## Changelog

- 2026-04-23 | 89956cd7 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Unified Reference Configuration* | **Hash**: 89956cd7
---

## REQ-d00084: Trace Command

**Level**: dev | **Status**: Active | **Implements**: REQ-p00003

The `trace` command SHALL generate *Traceability* output from the requirement graph, supporting multiple output formats with configurable column presets and detail levels.

## Assertions

A. The command SHALL support structured JSON graph output via `--graph-json`, including git change annotations when available.

B. The command SHALL support column presets (`--preset minimal|standard|full`) controlling which columns appear in tabular output: minimal (ID, Title, Level, Status), standard (+ Implemented, Validated), full (+ Passing).

C. The command SHALL support independent detail flags (`--body`, `--assertions`, `--tests`) that control whether expanded rows appear beneath each requirement, orthogonal to column presets.

D. Coverage columns SHALL show per-requirement *Assertion*-level coverage: Implemented (assertions with code refs, direct or transitive), Validated (assertions with test refs), Passing (validated assertions whose tests pass), each displayed as N/M (%).

## Rationale

A JSON graph output mode enables programmatic consumption of the full *Traceability* graph with git-aware change tracking, supporting dashboard integrations and automated analysis pipelines. Column presets and detail flags are independent axes of control: a user may want a compact table with full coverage columns, or a minimal table with expanded *Assertion* rows.

## Changelog

- 2026-03-30 | f8f0e0f2 | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Trace Command* | **Hash**: f8f0e0f2
---

## REQ-d00085: Unified Report Composition

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002, REQ-p00003

The CLI SHALL support composable report output by accepting multiple section names as positional arguments. Sections are rendered in the order specified and concatenated into a single output stream.

## Assertions

A. The CLI SHALL accept multiple section names (`health`, `coverage`, `trace`, `changed`) as positional arguments, rendering each in order and concatenating the output.

B. Shared flags (`--format`, `-o`, `-q`/`--quiet`, `-v`/`--verbose`, `--lenient`, `--mode`) SHALL apply globally across all sections in a composed report.

C. The exit code of a composed report SHALL be the worst-of-all-sections: non-zero if any section reports errors, or warnings without `--lenient`.

D. When a single section is specified, it SHALL behave identically to a standalone command invocation.

E. The `--format` flag SHALL support `text`, `markdown`, `json`, and `csv` output modes. Not all formats are valid for all sections; invalid combinations SHALL produce a clear error.

F. The `-q`/`--quiet` flag SHALL suppress all output except a single summary line per section. The `-v`/`--verbose` flag SHALL expand all available detail.

G. The `--lenient` flag SHALL allow warnings to pass without affecting the exit code. Without `--lenient`, any warning-level finding SHALL cause a non-zero exit code.

H. The `--format junit` option SHALL render health checks as JUnit XML, mapping categories to `<testsuite>` elements, checks to `<testcase>` elements, failures to `<failure>` elements, warnings to `<system-err>`, and info to `<system-out>`.

I. Each `HealthCheck` SHALL carry a `findings` list of `HealthFinding` dataclass instances, each with `message`, `file_path`, `line`, `node_id`, and `related` fields. The `to_dict()` serialization SHALL include findings. Existing renderers (text, markdown, JUnit) SHALL remain unchanged.

J. The `--format sarif` option SHALL render health findings as SARIF v2.1.0 JSON, with one `reportingDescriptor` per unique check name, one `result` per `HealthFinding` with physical locations, passing checks omitted, and coverage stats in `run.properties`.

## Rationale

Report-producing commands (`health`, `trace`, `coverage`, `changed`) currently exist as independent subcommands with inconsistent format support. Composing a combined report (e.g. health + coverage for a CI PR comment) requires multiple invocations and manual concatenation. A composable system builds the graph once, renders each section, and produces unified output. The `--lenient` flag provides an escape hatch for workflows that want to observe warnings without gating on them.

## Changelog

- 2026-04-23 | 82d76f1a | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Unified Report Composition* | **Hash**: 82d76f1a
---

## REQ-d00086: Coverage Report Section

**Level**: dev | **Status**: Active | **Implements**: REQ-p00003

The `coverage` section SHALL produce a coverage report showing implementation, validation, and test-passing status at the requirement and *Assertion* level.

## Assertions

A. The report SHALL group requirements by level (PRD, OPS, DEV) and show counts and percentages of requirements with code references, test references, and passing tests.

B. The report SHALL compute per-requirement *Assertion* coverage: implemented (assertions with `Implements:` code refs, direct or transitive), validated (assertions with test refs), and passing (validated assertions whose tests pass).

C. The report SHALL support `text`, `markdown`, `json`, and `csv` output formats.

D. The report SHALL use existing graph aggregate functions and annotator data rather than reimplementing coverage logic.

## Rationale

Coverage data is already computed during graph construction but is only surfaced through the interactive viewer or the underpowered `analyze coverage` text output. A dedicated coverage section with multi-format support enables CI badge generation, PR comment summaries, and developer-facing markdown reports.

## Changelog

- 2026-03-30 | 2fd4ab13 | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Coverage Report Section* | **Hash**: 2fd4ab13
---

## REQ-d00073: Link Suggestion CLI Command

**Level**: dev | **Status**: Active | **Implements**: REQ-o00065

The `commands/link_suggest.py` module SHALL provide the `elspais link suggest` CLI command.

## Assertions

A. `elspais link suggest` SHALL scan all unlinked test nodes and print suggestions with confidence scores.

B. `--file <path>` SHALL restrict analysis to a single file.

C. `--format json` SHALL output suggestions as a JSON array for programmatic consumption.

D. `--min-confidence high|medium|low` SHALL filter suggestions by confidence band (high >= 0.8, medium >= 0.5, low < 0.5).

E. `--apply [--dry-run]` SHALL insert `# Implements:` comments into source files at the suggested locations, with dry-run previewing changes without writing.

## Rationale

CLI exposure enables both interactive use and CI pipeline integration. JSON output mode supports tooling and scripting workflows.

## Changelog

- 2026-04-23 | 44fd54e9 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Link Suggestion CLI Command* | **Hash**: 44fd54e9
---

## REQ-d00124: Graph Analysis Engine

**Level**: dev | **Status**: Active | **Implements**: REQ-p00003

The `analysis` module SHALL provide read-only analytical functions that operate on a `TraceGraph` to rank requirements by foundational importance. The module SHALL NOT modify the graph or create parallel data structures.

## Assertions

A. The module SHALL compute PageRank-style centrality scores for requirement nodes by iterating on reversed edges (children distribute score to parents) with a configurable damping factor, converging within a tolerance threshold.

B. The module SHALL compute fan-in as the count of distinct direct parents (among included node kinds) for each node, identifying cross-cutting requirements that serve multiple independent areas.

C. The module SHALL compute neighborhood density by walking up through each node's ancestors and counting siblings/cousins at each level, applying exponential decay by distance (siblings=1.0, cousins=decay, second-cousins=decay^2).

D. The module SHALL compute uncovered dependent counts by walking descendants and counting leaf requirements with zero coverage.

E. The module SHALL produce a composite score by normalizing each metric to 0.0-1.0 and applying configurable weights (default 0.3 centrality, 0.2 fan-in, 0.2 neighborhood, 0.3 uncovered).

F. The module SHALL filter nodes by `NodeKind`, defaulting to REQUIREMENT and *Assertion*, with *Assertion* nodes included in computation but excluded from ranked output.

G. The module SHALL rank actionable leaf nodes by summing the composite scores of their ancestors, surfacing the most impactful uncovered work items.

## Rationale

In a large requirements DAG, naive metrics like descendant count always favor the root node. PageRank centrality naturally handles DAGs and rewards cross-cutting dependencies. Combined with fan-in (how many independent areas depend on a node) and coverage gaps, this enables evidence-based prioritization of foundational work.

## Changelog

- 2026-03-30 | 86bb619b | - | Michael Lewis (michael@anspar.org) | Auto-fix: canonicalize term forms

*End* *Graph Analysis Engine* | **Hash**: 86bb619b
---

## REQ-d00125: Analysis CLI Command

**Level**: dev | **Status**: Active | **Implements**: REQ-p00003

The `elspais analysis` command SHALL invoke the graph analysis engine and render ranked results in table or JSON format.

## Assertions

A. The command SHALL accept `--top N` to limit the number of results displayed (default 10).

B. The command SHALL accept `--weights W1,W2,W3[,W4]` to configure the composite score weights (3 or 4 values).

C. The command SHALL accept `--format table|json` to select output format, defaulting to table.

D. The command SHALL accept `--show foundations|leaves|all` to select which sections to display, defaulting to all.

E. The command SHALL accept `--level prd|ops|dev` to filter results by requirement level.

F. The command SHALL accept `--include-code` to include CODE nodes in the analysis.

G. The table output SHALL display columns for Rank, ID, Title, Centrality, Fan-In, Neighbors, Uncovered, and Score.

H. The JSON output SHALL serialize the full `FoundationReport` structure.

## Rationale

A CLI command provides immediate visibility into which requirements are most foundational, enabling project planning without requiring MCP or viewer integration.

## Changelog

- 2026-04-23 | 3cd66dbe | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Analysis CLI Command* | **Hash**: 3cd66dbe
---

## REQ-d00213: Version Check and Update Notification

**Level**: dev | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The tool SHALL parse semantic version strings into comparable representations, stripping pre-release/dev/local suffixes.

B. The tool SHALL determine whether a remote version is strictly newer than the locally installed version.

C. The tool SHALL detect the installation method (pipx, brew, editable, user install, virtual environment) to determine the appropriate upgrade path.

D. The tool SHALL provide the correct upgrade command for the detected installation method.

E. The tool SHALL query the package index for the latest published version, returning gracefully on network failure without raising.

F. The tool SHALL compare local vs. remote versions and report whether the installation is up-to-date, an update is available (with upgrade instructions), or the check failed (silently suppressed).

## Changelog

- 2026-04-23 | 56b62d01 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Version Check and Update Notification* | **Hash**: 56b62d01

## REQ-d00217: INDEX.md Regeneration

**Level**: dev | **Status**: Active | **Implements**: REQ-p00003

## Assertions

A. INDEX.md generation SHALL read the project name and level rank/display name from project configuration to populate headers and table structure.

B. INDEX.md generation SHALL bucket each requirement and journey node by its owning repository name, resolved via `FederatedGraph.repo_for(node.id).name`. Path-based classification against `spec_dirs` SHALL NOT be used to resolve the owning repo. Nodes whose ownership cannot be determined SHALL bucket as `Unattributed`, distinct from any per-repo bucket.

C. The regenerated INDEX.md SHALL contain per-level requirement tables sorted by dependency order.

D. When multiple `(repo, spec_dir)` buckets contribute requirements within a level, the INDEX.md SHALL include `###` subsections per bucket. Each subsection's label SHALL be derived from the bucket's spec directory (`{project_name}/{spec_subpath}`) when the bucket has an associated spec dir; otherwise the bucket is labeled with the owning `RepoEntry.name`. The `Unattributed` bucket retains its fixed label.

## Changelog

- 2026-05-04 | 4310931a | - | Developer (dev@example.com) | Auto-fix: update hash
- 2026-05-04 | 7c4f1816 | - | Developer (dev@example.com) | Auto-fix: update hash
- 2026-04-23 | a1e3915a | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *INDEX.md Regeneration* | **Hash**: 4310931a

## REQ-d00218: Health Check Coverage Rollup

**Level**: dev | **Status**: Active | **Implements**: REQ-d00085

## Assertions

A. The tests.coverage health check SHALL use the rollup coverage metric from the annotation pipeline, not a direct parent walk from TEST nodes.

B. The tests.coverage check SHALL report test-specific coverage (assertions verified by TEST nodes) separately from code coverage.

C. When a child requirement has test coverage, its parent requirement SHALL receive coverage credit through the rollup mechanism.

## Changelog

- 2026-04-23 | 64b0dfbb | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *Health Check Coverage Rollup* | **Hash**: 64b0dfbb

## REQ-d00219: UAT Health Check Section

**Level**: dev | **Status**: Active | **Implements**: REQ-d00085

## Assertions

A. The health report SHALL include a UAT section below the TESTS section, reporting journey-based validation coverage and results separately.

B. The uat.coverage check SHALL report requirements validated through USER_JOURNEY nodes via Validates edges, using the rollup UAT coverage metric.

C. The uat.results check SHALL parse a CSV file with journey_id and status columns, reporting pass/fail/skip counts and flagging failing journeys.

D. When no UAT results CSV file exists, the uat.results check SHALL report as skipped (informational) without failing.

## Changelog

- 2026-04-23 | 3a95ff57 | - | Developer (dev@example.com) | Auto-fix: add missing changelog section

*End* *UAT Health Check Section* | **Hash**: 3a95ff57
