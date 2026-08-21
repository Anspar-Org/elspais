# CLI Development Requirements

## REQ-d00080: Diagnostic Command Exit Code Contract

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002, REQ-p00005-E

Diagnostic commands (`doctor`, `health`) SHALL exit non-zero when they detect configuration or validation failures, ensuring CI pipelines and callers can rely on exit codes to gate merges.

### Assertions

A. Diagnostic commands (`doctor`, `health`) SHALL exit non-zero when any check produces a warning-level or error-level finding. The `--lenient` flag SHALL relax this so that only error-level findings cause non-zero exit.

B. `health` SHALL exit non-zero when zero requirements are found and a spec directory is configured. A configured project with no parseable requirements is an error, not an empty success.

C. `doctor` and `health` path-existence checks SHALL verify directories exist on disk, not merely that a path string is present in the config.

D. For `project.type = "associated"`, `doctor` SHALL validate that the `[associated]` section exists and has a non-empty `prefix`. A missing or misconfigured `[associated]` section in an associated project is a configuration error.

E. For `project.type = "core"` with configured associate paths, `health` SHALL exit non-zero when an associate path is missing, misconfigured, or produces zero requirements. A silent requirement count drop is a data-loss condition.

### Rationale

Warnings represent real problems: missing paths, orphaned nodes, unresolved references. By default, any warning causes a non-zero exit code, making diagnostic commands safe for CI gating (REQ-o00066-C). The `--lenient` flag provides an escape hatch for development workflows where warnings are informational and should not block.

The previous `validate` command's responsibilities are absorbed by `health`. References to `validate` in assertions B and E now refer to the `health` command's spec-checking category.

### Changelog

- 2026-07-31 | acc2aa77 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | ada92a29 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | ada92a29 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Diagnostic Command Exit Code Contract* | **Hash**: acc2aa77
---

## REQ-d00081: Multi-Assertion Reference Expansion

**Level**: dev | **Status**: Active | **Implements**: REQ-p00001

Multi-*Assertion* references allow compact notation for referencing multiple assertions of the same requirement. A dedicated separator character (distinct from ID separators) joins *Assertion* labels after the first: `REQ-p00001-A+B+C` expands to individual *Assertion* references `REQ-p00001-A`, `REQ-p00001-B`, `REQ-p00001-C`.

### Assertions

A. The character joining *Assertion* labels within one reference SHALL be configurable per repository.

B. The multi-*Assertion* separator SHALL default to `+`.

C. [Removed - named a list of accepted alternate separators that no longer exists. The multi-*Assertion* separator is constrained against the characters an *Assertion* label can contain, per REQ-d00251-J.]

D. A multi-*Assertion* reference SHALL expand to the same set of individual references wherever it is written.

E. [Removed - restated the derivation of a pattern rather than an obligation the tool must meet. What a multi-*Assertion* reference expands to is D; which strings the grammar admits is REQ-d00212-G.]

F. [Removed - an empty separator is not a configurable state. A separator is exactly one character, per REQ-d00251-K, so there is no value of it that disables expansion.]

G. A reference containing no multi-*Assertion* separator character SHALL pass through unchanged.

### Rationale

The previous implementation hardcoded expansion in RequirementParser only, using a regex that assumed uppercase letter labels and hyphen separators. This created silent failures when code comments (`# Implements: REQ-x-A-B-C`) and test names (`test_REQ_x_A_B_C`) were not expanded. A dedicated separator character eliminates ambiguity regardless of the configured *Assertion* label style (uppercase, numeric, alphanumeric).

### Changelog

- 2026-08-12 | b1812806 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | c40a462e | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | 67ee3df9 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: A and B name the configured separator, D states expansion uniformity; retire E (superseded) and F (empty is not a state)
- 2026-08-10 | e001c08a | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: retire C, which named a list of accepted alternate separators that no longer exists
- 2026-07-31 | 25c43ce2 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 313fe52b | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | 313fe52b | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Multi-Assertion Reference Expansion* | **Hash**: b1812806
---

## REQ-d00082: Unified Reference Configuration

**Level**: dev | **Status**: Active | **Implements**: REQ-p00001-A

The system SHALL provide a unified, configurable reference pattern system used by all parsers (CodeParser, TestParser, JUnitXMLParser, PytestJSONParser) to locate requirement references in source files.

### Assertions

D. [Removed - named a configurable case-matching mode that does not exist. An identifier is admitted in one spelling only, per REQ-d00212-G, so there is no case-matching mode to configure.]

E. Locating a reference in a source file SHALL use the separator the repository owning the referenced identifier configures, so that a reference is recognised in exactly the form that repository writes and in no other.

F. [Removed - named per-file reference overrides that do not exist. One set of acceptance rules applies in every context that accepts a reference, per REQ-p00014-T.]

G. Reading a reference SHALL yield the parts its grammar defines, so that a consumer works from the identifier's structure rather than from the matched text.

H. [Removed - named a reference-configuration artifact that does not exist. The limitation it described is real: a *Traceability* keyword inside a block comment is never read, so a block-comment-only language has no reference form.]

I. [Removed - named classes that do not exist; source-file reference matching derives from the identifier grammar authority.]

J. [Removed - named classes that do not exist; test-file reference matching derives from the identifier grammar authority.]

K. [Removed - a result record is matched to its test by recorded identity, not by reading requirement references out of a reported test name.]

L. [Removed - a result record is matched to its test by recorded identity, not by reading requirement references out of a reported test name.]

### Rationale

Different projects use different ID conventions, comment styles, and directory structures. A unified reference configuration allows all parsers to share the same configurable pattern matching, avoiding duplicated logic and ensuring consistent behavior across parser types.

### Changelog

- 2026-08-10 | f0808bb9 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | 268cdb9f | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: retire D and F, which named configuration that does not exist; G states the parts a read reference yields
- 2026-08-10 | 6289e433 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: E names the configured separator rather than a list of accepted alternates
- 2026-08-10 | 109921be | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | 00cd96fc | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 89956cd7 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 89956cd7 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Unified Reference Configuration* | **Hash**: f0808bb9
---

## REQ-d00084: Trace Command

**Level**: dev | **Status**: Active | **Implements**: REQ-p00003

The `trace` command SHALL generate *Traceability* output from the requirement graph, supporting multiple output formats with configurable column presets and detail levels.

### Assertions

A. The command SHALL support structured JSON graph output via `--graph-json`, including git change annotations when available.

B. The command SHALL support column presets (`--preset minimal|standard|full`) controlling which columns appear in tabular output: minimal (ID, Title, Level, Status), standard and full (+ Implemented, Tested, Passing per *Assertion* D).

C. The command SHALL support independent detail flags (`--body`, `--assertions`, `--tests`) that control whether expanded rows appear beneath each requirement, orthogonal to column presets.

D. The standard and full presets SHALL include per-requirement coverage columns for Implemented, Tested and Passing as REQ-d00277 defines them, each displayed as N/M (%) on the total coverage of REQ-d00069-N, with the measures behind it available per REQ-d00258-A and no caveat marker standing in for one not shown.

### Rationale

A JSON graph output mode enables programmatic consumption of the full *Traceability* graph with git-aware change tracking, supporting dashboard integrations and automated analysis pipelines. Column presets and detail flags are independent axes of control: a user may want a compact table with full coverage columns, or a minimal table with expanded *Assertion* rows.

### Changelog

- 2026-08-19 | 67887c51 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-18 | 3a6da144 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-17 | 66981b81 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | 1bd6bca1 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-02 | 64954432 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-02 | f4e1d611 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | f8f0e0f2 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | f8f0e0f2 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Trace Command* | **Hash**: 67887c51
---

## REQ-d00085: Unified Report Composition

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002, REQ-p00003

The CLI SHALL support composable report output by accepting multiple section names as positional arguments. Sections are rendered in the order specified and concatenated into a single output stream.

### Assertions

A. The CLI SHALL accept multiple section names (`health`, `coverage`, `trace`, `changed`) as positional arguments, rendering each in order and concatenating the output.

B. Shared flags (`--format`, `-o`, `-q`/`--quiet`, `-v`/`--verbose`, `--lenient`, `--mode`) SHALL apply globally across all sections in a composed report.

C. The exit code of a composed report SHALL be the worst-of-all-sections: non-zero if any section reports errors, or warnings without `--lenient`.

D. When a single section is specified, it SHALL behave identically to a standalone command invocation.

E. The `--format` flag SHALL support `text`, `markdown`, `json`, and `csv` output modes. Not all formats are valid for all sections; invalid combinations SHALL produce a clear error.

F. The `-q`/`--quiet` flag SHALL suppress all output except a single summary line per section.

G. The `--lenient` flag SHALL allow warnings to pass without affecting the exit code.

H. The `--format junit` option SHALL render health checks as JUnit XML, mapping categories to `<testsuite>` elements, checks to `<testcase>` elements, failures to `<failure>` elements, warnings to `<system-err>`, and info to `<system-out>`.

I. Each `HealthCheck` SHALL carry a `findings` list of `HealthFinding` dataclass instances, each with `message`, `file_path`, `line`, `node_id`, and `related` fields. The `to_dict()` serialization SHALL include findings. Existing renderers (text, markdown, JUnit) SHALL remain unchanged.

J. The `--format sarif` option SHALL render health findings as SARIF v2.1.0 JSON, with one `reportingDescriptor` per unique check name, one `result` per `HealthFinding` with physical locations, passing checks omitted, and coverage stats in `run.properties`.

K. The `-v`/`--verbose` flag SHALL expand all available detail.

L. Without `--lenient`, any warning-level finding SHALL cause a non-zero exit code.

M. Detail for a passing check SHALL be suppressed by default and included on request.

N. A format that always carries complete findings, or that omits passing checks entirely, SHALL render identically whether or not passing-check detail is requested.

### Rationale

Report-producing commands (`health`, `trace`, `coverage`, `changed`) currently exist as independent subcommands with inconsistent format support. Composing a combined report (e.g. health + coverage for a CI PR comment) requires multiple invocations and manual concatenation. A composable system builds the graph once, renders each section, and produces unified output. The `--lenient` flag provides an escape hatch for workflows that want to observe warnings without gating on them.

Quietness and verbosity are separate obligations (F, K), as are leniency and the default it departs from (G, L). Each pair was carried under one label until evidence for one half was found standing in for both: coverage is reported per assertion, so a label holding two obligations cannot distinguish an implementation from half of one.

A failing check's findings are what the reader came for; a passing check's are noise until asked for, which is why M suppresses them by default and makes the request explicit rather than the reverse. The request is about passing checks only and is orthogonal to overall verbosity — a format carries a passing check's detail because it was asked for, not because the report as a whole is verbose. N is separate from M because a format can be wrong about invariance while the request itself works: complete findings and omitted passing checks are properties of those formats, not outcomes of the request.

### Changelog

- 2026-08-11 | 587285b0 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-11 | 650b3641 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-11 | 0d1e518a | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: specify passing-check detail (M) and its format invariance (N)
- 2026-08-11 | 0d1e518a | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: split the verbose half of F into K and the without-lenient half of G into L
- 2026-07-31 | 0d1e518a | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 82d76f1a | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 82d76f1a | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Unified Report Composition* | **Hash**: 587285b0
---

## REQ-d00271: Diagnostic Code Vocabulary

**Level**: dev | **Status**: Active | **Implements**: REQ-p00015

A report groups findings so they can be counted and a severity chosen for them, and names each finding's defect so it can be acted on. Those are separate vocabularies with separate obligations: the first is closed so a project can configure against it, the second is open so a diagnosis can become more specific without anything having to be reconfigured.

### Assertions

A. Every finding SHALL carry a code naming its defect, and the codes SHALL be documented with an example of input that produces each.

B. A finding MAY carry more than one code, so that a defect determined in several independent respects is reported in all of them rather than in whichever was tested first.

C. There SHALL be a code meaning that the defect could not be determined beyond the category, and a finding whose defect is undetermined SHALL carry it. A finding carrying only that code is the report that nothing more specific is known, and SHALL NOT be read as the absence of a diagnosis.

D. A code SHALL be issued only where the input determines the defect it names. Where the input admits two accounts of equal extent, neither SHALL be issued.

E. Introducing a code SHALL NOT change which category a finding falls in, the severity configured for that category, or the meaning of a code already in use.

### Rationale

The two vocabularies fail in opposite directions, which is why they are separated. A category that grows breaks configuration that referred to the old set and reopens a decision the project already made. A diagnosis that cannot grow leaves the tool unable to say more than it once could, so every improvement in what it can determine has to be paid for in churn somewhere. Fixing the categories and leaving the codes open lets diagnosis improve indefinitely at no cost to the project's settings.

D is what keeps B from becoming guesswork. Reporting several respects in which an input is defective is a statement of fact only where each respect is determined by the input; where two accounts explain it equally, naming either asserts something the input does not support, and an author acting on the wrong one is worse off than an author told only the category. C is what makes that refusal reportable rather than silent: without a code for "no further account", declining to guess is indistinguishable from not having looked.

### Changelog

- 2026-08-16 | 6f4019d1 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: sync changelog hash
- 2026-08-16 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: Active — every reported fault carries codes, the codes are documented with a producing input in `elspais docs linking`, and two codes no input could produce are retired from the vocabulary
- 2026-08-15 | - | - | Michael Lewis (<michael@anspar.org>) | Initial authoring: closed categories over open codes, multiple codes per finding, a generic code, and issuance only where determined

*End* *Diagnostic Code Vocabulary* | **Hash**: 6f4019d1
---

## REQ-d00086: Coverage Report Section

**Level**: dev | **Status**: Active | **Implements**: REQ-p00003

The `coverage` section SHALL produce a coverage report showing implemented, tested, and passing status at the requirement and *Assertion* level.

### Assertions

A. The report SHALL group requirements by level as REQ-d00281 determines those groups, and show counts and percentages of requirements with code references, test references, and passing tests.

B. The report SHALL compute per-requirement *Assertion* coverage for Implemented, Tested and Passing as REQ-d00277 defines them, each on the total coverage of REQ-d00069-N, with the measures behind it available per REQ-d00258-A and no caveat marker standing in for one not shown.

C. The report SHALL support `text`, `markdown`, `json`, and `csv` output formats.

D. The report SHALL use existing graph aggregate functions and annotator data rather than reimplementing coverage logic.

### Rationale

Coverage data is already computed during graph construction but is only surfaced through the interactive viewer or the underpowered `analyze coverage` text output. A dedicated coverage section with multi-format support enables CI badge generation, PR comment summaries, and developer-facing markdown reports.

### Changelog

- 2026-08-20 | 067a62c4 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-20 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-74: level groups follow the requirements reported on rather than a fixed set named here
- 2026-08-19 | 4559fce7 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-18 | 0cca2a88 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-17 | 185b2d34 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | a12d2826 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-02 | a17871db | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 2fd4ab13 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | 2fd4ab13 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Coverage Report Section* | **Hash**: 067a62c4
---

## REQ-d00073: Link Suggestion CLI Command

**Level**: dev | **Status**: Active | **Implements**: REQ-o00065

The `commands/link_suggest.py` module SHALL provide the `elspais link suggest` CLI command.

### Assertions

A. `elspais link suggest` SHALL scan all unlinked test nodes and print suggestions with confidence scores.

B. `--file <path>` SHALL restrict analysis to a single file.

C. `--format json` SHALL output suggestions as a JSON array for programmatic consumption.

D. `--min-confidence high|medium|low` SHALL filter suggestions by confidence band (high >= 0.8, medium >= 0.5, low < 0.5).

E. `--apply [--dry-run]` SHALL insert `# Implements:` comments into source files at the suggested locations, with dry-run previewing changes without writing.

### Rationale

CLI exposure enables both interactive use and CI pipeline integration. JSON output mode supports tooling and scripting workflows.

### Changelog

- 2026-07-31 | 975970c4 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 44fd54e9 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 44fd54e9 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Link Suggestion CLI Command* | **Hash**: 975970c4
---

## REQ-d00124: Graph Analysis Engine

**Level**: dev | **Status**: Active | **Implements**: REQ-p00003

The `analysis` module SHALL provide read-only analytical functions that operate on a `TraceGraph` to rank requirements by foundational importance. The module SHALL NOT modify the graph or create parallel data structures.

### Assertions

A. The module SHALL compute PageRank-style centrality scores for requirement nodes by iterating on reversed edges (children distribute score to parents) with a configurable damping factor, converging within a tolerance threshold.

B. The module SHALL compute fan-in as the count of distinct direct parents (among included node kinds) for each node, identifying cross-cutting requirements that serve multiple independent areas.

C. The module SHALL compute neighborhood density by walking up through each node's ancestors and counting siblings/cousins at each level, applying exponential decay by distance (siblings=1.0, cousins=decay, second-cousins=decay^2).

D. The module SHALL compute uncovered dependent counts by walking descendants and counting leaf requirements with zero coverage.

E. The module SHALL produce a composite score by normalizing each metric to 0.0-1.0 and applying configurable weights (default 0.3 centrality, 0.2 fan-in, 0.2 neighborhood, 0.3 uncovered).

F. The module SHALL filter nodes by `NodeKind`, defaulting to REQUIREMENT and *Assertion*, with *Assertion* nodes included in computation but excluded from ranked output.

G. The module SHALL rank actionable leaf nodes by summing the composite scores of their ancestors, surfacing the most impactful uncovered work items.

### Rationale

In a large requirements DAG, naive metrics like descendant count always favor the root node. PageRank centrality naturally handles DAGs and rewards cross-cutting dependencies. Combined with fan-in (how many independent areas depend on a node) and coverage gaps, this enables evidence-based prioritization of foundational work.

### Changelog

- 2026-07-31 | b153d5f6 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 86bb619b | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | 86bb619b | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Graph Analysis Engine* | **Hash**: b153d5f6
---

## REQ-d00125: Analysis CLI Command

**Level**: dev | **Status**: Active | **Implements**: REQ-p00003

The `elspais analysis` command SHALL invoke the graph analysis engine and render ranked results in table or JSON format.

### Assertions

A. The command SHALL accept `--top N` to limit the number of results displayed (default 10).

B. The command SHALL accept `--weights W1,W2,W3[,W4]` to configure the composite score weights (3 or 4 values).

C. The command SHALL accept `--format table|json` to select output format, defaulting to table.

D. The command SHALL accept `--show foundations|leaves|all` to select which sections to display, defaulting to all.

E. The command SHALL accept `--level prd|ops|dev` to filter results by requirement level.

F. The command SHALL accept `--include-code` to include CODE nodes in the analysis.

G. The table output SHALL display columns for Rank, ID, Title, Centrality, Fan-In, Neighbors, Uncovered, and Score.

H. The JSON output SHALL serialize the full `FoundationReport` structure.

### Rationale

A CLI command provides immediate visibility into which requirements are most foundational, enabling project planning without requiring MCP or viewer integration.

### Changelog

- 2026-07-31 | 474fa8af | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 3cd66dbe | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 3cd66dbe | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Analysis CLI Command* | **Hash**: 474fa8af
---

## REQ-d00213: Version Check and Update Notification

**Level**: dev | **Status**: Active | **Implements**: REQ-p00001

### Assertions

A. The tool SHALL parse semantic version strings into comparable representations, stripping pre-release/dev/local suffixes.

B. The tool SHALL determine whether a remote version is strictly newer than the locally installed version.

C. The tool SHALL detect the installation method (pipx, brew, editable, user install, virtual environment) to determine the appropriate upgrade path.

D. The tool SHALL provide the correct upgrade command for the detected installation method.

E. The tool SHALL query the package index for the latest published version, returning gracefully on network failure without raising.

F. The tool SHALL compare local vs. remote versions and report whether the installation is up-to-date, an update is available (with upgrade instructions), or the check failed (silently suppressed).

### Changelog

- 2026-07-31 | cedd398b | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 56b62d01 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 56b62d01 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Version Check and Update Notification* | **Hash**: cedd398b

## REQ-d00217: INDEX.md Regeneration

**Level**: dev | **Status**: Active | **Implements**: REQ-p00003

### Assertions

A. INDEX.md generation SHALL read the project name and level rank/display name from project configuration to populate headers and table structure.

B. INDEX.md generation SHALL bucket each requirement and journey node by its owning repository name, resolved via `FederatedGraph.repo_for(node.id).name`. Path-based classification against `spec_dirs` SHALL NOT be used to resolve the owning repo. Nodes whose ownership cannot be determined SHALL bucket as `Unattributed`, distinct from any per-repo bucket.

C. The regenerated INDEX.md SHALL contain per-level requirement tables sorted by dependency order.

D. When multiple `(repo, spec_dir)` buckets contribute requirements within a level, the INDEX.md SHALL include `###` subsections per bucket. Each subsection's label SHALL be derived from the bucket's spec directory (`{project_name}/{spec_subpath}`) when the bucket has an associated spec dir; otherwise the bucket is labeled with the owning `RepoEntry.name`. The `Unattributed` bucket retains its fixed label.

### Changelog

- 2026-07-31 | 7cff1581 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 4310931a | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-05-04 | 4310931a | - | Developer (<dev@example.com>) | Auto-fix: update hash
- 2026-05-04 | 7c4f1816 | - | Developer (<dev@example.com>) | Auto-fix: update hash
- 2026-04-23 | a1e3915a | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *INDEX.md Regeneration* | **Hash**: 7cff1581

## REQ-d00218: Health Check Coverage Rollup

**Level**: dev | **Status**: Active | **Implements**: REQ-d00085

### Assertions

A. The tests.coverage health check SHALL use the rollup coverage metric from the annotation pipeline, not a direct parent walk from TEST nodes.

B. The tests.coverage check SHALL report test-specific coverage (assertions verified by TEST nodes) separately from code coverage.

C. When a child requirement has test coverage, its parent requirement SHALL receive coverage credit through the rollup mechanism.

### Changelog

- 2026-07-31 | 7783c3f1 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 64b0dfbb | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 64b0dfbb | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Health Check Coverage Rollup* | **Hash**: 7783c3f1

## REQ-d00219: UAT Health Check Section

**Level**: dev | **Status**: Active | **Implements**: REQ-d00085

### Assertions

A. The health report SHALL include a UAT section below the TESTS section, reporting journey-based validation coverage and results separately.

B. The uat.coverage check SHALL report requirements validated through USER_JOURNEY nodes via Validates edges, using the rollup UAT coverage metric.

C. The uat.results check SHALL parse a CSV file with journey_id and status columns, reporting pass/fail/skip counts and flagging failing journeys.

D. When no UAT results CSV file exists, the uat.results check SHALL report as skipped (informational) without failing.

### Changelog

- 2026-07-31 | c2b0cc8e | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 3a95ff57 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 3a95ff57 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *UAT Health Check Section* | **Hash**: c2b0cc8e

## REQ-d00249: Configured test runner execution

**Level**: dev | **Status**: Draft | **Implements**: -

### Assertions

A. The system SHALL execute each entry in `[[scanning.test.runners]]` in declaration order when invoked with `elspais checks --run-tests`, resolving each entry's `cwd` relative to the repository root and rejecting any `cwd` that resolves outside the repository root.

B. The system SHALL stream runner stdout and stderr live to the invoking terminal, emit a per-runner banner before invocation, and a tally line with elapsed seconds and the exit code after invocation.

C. The system SHALL stop at the first failing runner and skip the checks pass entirely when invoked with `elspais checks --run-tests --fail-fast`.

D. When result file patterns are configured but no matching files exist on disk, the system SHALL return the `tests.results` health check with `passed = false` and severity `warning`, flipping the exit code unless `--lenient` is passed.

E. When result files exist but the oldest result file mtime is earlier than the newest scanned spec, code, or test FILE-node mtime, the system SHALL return a separate `tests.results_stale` health check with `passed = false` and severity `warning`, flipping the exit code unless `--lenient` is passed.

F. The system SHALL return exit code 2 and an error message pointing at `docs/cli/checks.md` when `elspais checks --run-tests` is invoked with no runners configured.

G. The system SHALL return a non-zero exit code if any runner failed OR any check failed, and 0 only if all succeeded.

### Rationale

`elspais checks` previously reported verified coverage based on RESULT
nodes parsed from JUnit XML or pytest JSON files. When those files were
missing or stale, the report claimed zero or stale coverage without any
indication that test results were not recent. This requirement closes
both gaps: a single command can execute tests and re-evaluate checks,
and the checks pass warns when results are out of date even without
running tests.

*End* *Configured test runner execution* | **Hash**: 784f8350

## REQ-d00259: Requirement Format Reference Command

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

The `example` command SHALL display requirement format reference material to help authors discover and follow the correct structure, without requiring a spec directory or a built graph.

### Assertions

A. Invoking `elspais example` with no subcommand SHALL print a quick-reference summary covering the basic requirement structure and the available `example` subcommands.

B. `elspais example requirement` SHALL print example requirement templates for each configured level (PRD, OPS, DEV), each including an `## Assertions` section and an `*End*` footer with a hash placeholder.

C. `elspais example journey` SHALL print an example user journey template covering Actor, Goal, Steps, and Requirements sections.

D. `elspais example assertion` SHALL print assertion format rules covering label styles, SHALL/SHOULD/MAY keywords, placeholder values for removed assertions, and the assertion-related configuration syntax.

E. `elspais example ids` SHALL print the ID pattern configuration for the current project (namespace, canonical ID template, and level types), loaded from the active config file when present and falling back to schema defaults otherwise.

F. `elspais example --full` SHALL display the full contents of the project's `requirements-spec.md` (or `requirements-format.md`) file when found, and SHALL return a non-zero exit code with the searched paths listed when neither file exists.

### Rationale

Authors writing their first requirement, or reviewers checking format conventions, need a fast, offline reference without opening the full *Specification*. `example` fills this role independently of `elspais init` (which scaffolds a new project's configuration) by surfacing format templates and rules on demand.

### Changelog

- 2026-07-31 | c3b67490 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-03 | 8e05d02e | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms, update hash, add missing changelog section

*End* *Requirement Format Reference Command* | **Hash**: c3b67490

## REQ-d00266: Mechanical Style Checks

**Level**: dev | **Status**: Draft | **Implements**: REQ-p00002-A

The tool checks requirement text against the mechanically-decidable subset of the organization's requirement style rules, so that style review effort concentrates on judgment calls rather than pattern violations.

### Assertions

A. The tool SHALL evaluate requirement text against a configured set of style rules, each of which is decidable from spec content and graph structure alone, without human judgment.

B. The tool SHALL flag keyword-discipline violations, including obligation keywords appearing outside Assertions sections and obligation words outside the canonical keyword set.

C. The tool SHALL flag assertion text that references another requirement or assertion identifier.

D. The tool SHALL flag assertion text containing compound-connective patterns that indicate multiple independently-decidable obligations in a single assertion.

E. The tool SHALL flag notation violations, including dates not in ISO 8601 format and configurable values not written in the canonical placeholder syntax.

F. The tool SHALL flag assertions whose count of attached verifying tests exceeds a configurable threshold, as a signal that the assertion is too coarse.

G. The tool SHALL flag each verification link that names a requirement without naming a specific assertion.

H. The tool SHALL report style findings through the standard checks reporting surface, with severity configurable per rule.

### Rationale

Agent-generated code routinely cannot reliably be constrained to generate assertions according to a set of rules, so we must rely on checks instead. Not all checks can be automated, but those that can, are.

*End* *Mechanical Style Checks* | **Hash**: 084c17a0

---

## REQ-d00278: Report Scope Selection Vocabulary

**Level**: dev | **Status**: Draft | **Implements**: REQ-p00084

A scope is written by a person and read by the tool, so it needs a vocabulary: which properties of a requirement can be selected on, which values those properties admit, what a requirement must and must not carry to satisfy them, whose configuration a name is read against, and what becomes of a name the vocabulary does not account for. This requirement fixes that vocabulary and leaves it open to properties not yet named.

### Assertions

A. A requirement's level SHALL be a property a scope can select on.

B. A requirement's status SHALL be a property a scope can select on.

C. A scope SHALL admit any combination of the properties it selects on and the values each of those properties admits.

D. A requirement SHALL be in scope only where it satisfies every property the scope names.

E. A requirement SHALL satisfy a property where it carries any of the values the scope requires for that property.

F. A requirement SHALL NOT satisfy a property where it carries any of the values the scope excludes for that property.

G. A scope SHALL admit selecting, in place of a status it names, every status the project assigns the same role as that status.

H. The values a scope may name for a property SHALL be those a member's configuration defines for that property together with those that member's requirements carry.

I. A name a scope uses SHALL only be resolved in the vocabulary of the member that owns the requirement being judged.

J. Where a scope names a property or a value the vocabulary it is resolved against does not admit, the tool SHALL report the unadmitted name together with the vocabulary it was resolved against.

K. A name the vocabulary does not admit SHALL select no requirement in that vocabulary, leaving the rest of the scope to select as it otherwise would.

L. Where a scope selects no requirement from an estate that holds requirements, the tool SHALL report the empty selection as the scope's answer rather than as an absence of requirements.

M. Admitting a further property a scope can select on SHALL NOT change which requirements an already expressible scope selects.

### Rationale

C, D, E and F fix how a scope is read. A scope is a set of properties carrying values, and C is what keeps any combination of them writable; D, E and F then fix the reading, because a combination whose meaning is left open is not a vocabulary. Properties named together are conditions a requirement meets at once; values named for one property are alternatives. That is the same narrowing a reader performs when browsing the estate interactively, and a vocabulary meaning anything else would give a reader two incompatible ways to say one thing. F is stated as a refusal rather than as a second kind of scope, so a property carrying both the values a requirement must have and the values it must not resolves the same way wherever they overlap, and the vocabulary needs no rule for their collision.

G keeps a scope correct as a project's statuses grow. Statuses are a project's own and multiply; the roles it assigns them are the stable vocabulary underneath. Were a role a value the status property admitted, a reader would face two things that look alike in one list and behave differently, and every scope would have to be read to discover which it named. Keeping the role out of the value list and making it a widening of the statuses already named leaves one kind of thing in the list, and one question about the scope as a whole: whether a named status stands for itself or for everything sharing its role.

H and I divide a question that would otherwise be answered by whichever member happened to be asked. H says what a vocabulary holds: a value a requirement carries belongs to it whether or not the configuration names it, because a requirement carrying a status the project never listed is one a reader can see and therefore one a reader can ask for. I says whose vocabulary is consulted — each requirement is judged under the vocabulary of the project that wrote it, never one assembled from several, which would let one member's configuration decide what another member's requirements are. REQ-d00251-L settles the same question for identifiers, and the reasons carry over unchanged.

J, K and L are the honesty group, separate because opposite situations produce the same thin report. A name the vocabulary does not admit selects nothing while looking like it selected something, and a federated estate is where that hides best. J is the disclosure; K is what keeps it from becoming a refusal, since a cross-member scope naming a level only some members define is legitimate and a report that stops at the first such name is useless to the reader who wrote it. L is the other side: a scope selecting nothing is frequently the correct result, and reporting it as the answer keeps it distinguishable from the conditions REQ-d00080-B and REQ-d00080-E report, which are about an estate or a member holding no requirements at all.

M is what allows the vocabulary to grow, and growth is owed. Selection axes beyond level and status are foreseeable: a compiled document offering its stakeholder audience the product-level requirements of every member of a federation (REQ-p00080-F), or a ranking narrowed to one level (REQ-d00125-E), are selections of this kind and are expressed in this vocabulary. The cost of admitting a property must fall on the scopes that use it and on nothing else — a project whose committed scopes shifted meaning because the tool learned a new property would have to re-audit every report it ever committed.

*End* *Report Scope Selection Vocabulary* | **Hash**: ef2221cc

---

## REQ-d00279: One Authority for Report Scope Membership

**Level**: dev | **Status**: Draft | **Implements**: REQ-p00084

Whether a requirement falls within a scope is a judgement, and a judgement made independently in several places drifts. This requirement fixes where that judgement is made and what is owed by a surface that answers it elsewhere.

### Assertions

A. There SHALL be one authority determining whether a requirement falls within a scope.

B. A surface that answers whether a requirement falls within a scope without consulting that authority SHALL yield the membership that authority yields for that scope over the same requirement set.

C. Where a report is produced by composing sections rather than by emitting a section alone, or by a serving process rather than where it was asked for, every such path SHALL yield the same scoped set.

### Rationale

A is what makes the promises above this requirement hold everywhere at once instead of being re-established path by path, which is how paths that agreed at first stop agreeing later. The agreement REQ-p00084-C asks for between renderings is one instance; C names the seams that are not about rendering at all. A report composed of several sections is assembled differently from the same section asked for alone — REQ-d00085-D binds the single-section case to a standalone invocation, and C is what carries the same agreement into the composed one, where a reporting option lost in assembly costs a reader the requirements it selected. A report computed by a process serving several readers runs a different route again from one computed where it was asked for. A lost scope is worse than a lost option because the output still looks complete.

B grants a second evaluator without granting a second semantics. A view that must answer immediately as a reader narrows it cannot wait on an authority elsewhere, and that responsiveness is worth having; what it is not worth is a reader seeing one set on screen and a different set in the report they then take away. Naming the authority's answer as the comparand is what makes the permission safe to grant: agreement is decided by comparison against a stated referent, so a second evaluator that is consistent with itself and wrong is not conforming. The estate elsewhere requires a shared decision to be computed once and read by every surface — the per-*Assertion* coverage standing of REQ-d00258-G is computed where the graph is and applied on first render rather than being re-derived by the reader's view. That is the right settlement where the decision is expensive and the inputs are not to hand. Scope membership is the opposite case on both counts: it is a comparison of properties the view already holds for every requirement it is displaying, and the reader is changing it continuously, so equivalence is the obligation that fits and derivation is not owed.

*End* *One Authority for Report Scope Membership* | **Hash**: 2b755b50

---

## REQ-d00280: Named Report Scopes

**Level**: dev | **Status**: Draft | **Implements**: REQ-p00084

A scope spelled out at the moment a report is run is known only to whoever spelled it. This requirement covers scopes a project declares under a name, and what such a name selects.

### Assertions

A. A project SHALL be able to declare a scope under a name in its own configuration.

B. A scope referred to by name SHALL select the requirements that the scope declared under that name selects when stated in full.

### Rationale

A and B are what REQ-p00084-F asks for in a form a project can commit and a reader can check. A is where the scope comes to rest — in the project, beside the requirements it selects over, versioned with them — and B is what keeps the name honest: a name is a reference to a scope, never a second selection that happens to share a spelling. An author reading a declaration then knows what a report produced under it contains without running it; once the two can differ, a committed report is evidence of a scope nobody can reconstruct.

*End* *Named Report Scopes* | **Hash**: 9ddbf905
