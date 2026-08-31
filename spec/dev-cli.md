# CLI Development Requirements

## REQ-d00080: Diagnostic Command Exit Code Contract

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002, REQ-p00005-E

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

C. <RETIRED> named a list of accepted alternate separators that no longer exists. The multi-*Assertion* separator is constrained against the characters an *Assertion* label can contain, per REQ-d00251-J.

D. A multi-*Assertion* reference SHALL expand to the same set of individual references wherever it is written.

E. <RETIRED> restated the derivation of a pattern rather than an obligation the tool must meet. What a multi-*Assertion* reference expands to is D; which strings the grammar admits is REQ-d00212-G.

F. <RETIRED> an empty separator is not a configurable state. A separator is exactly one character, per REQ-d00251-K, so there is no value of it that disables expansion.

G. A reference containing no multi-*Assertion* separator character SHALL pass through unchanged.

### Rationale

Expansion belongs to the identifier grammar rather than to any one parser: a compact reference means the same set of assertions in a requirement's metadata and in a code or test annotation, and a reader that expands in one place and not the other loses references silently. A dedicated separator character keeps the expansion unambiguous whatever *Assertion* label style is configured (uppercase, numeric, alphanumeric).

### Changelog

- 2026-08-24 | 6d66ba55 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-24 | b1812806 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: sync changelog hash
- 2026-08-24 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-66: rationale states why expansion belongs to the grammar, not which parsers once missed it
- 2026-08-12 | b1812806 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | c40a462e | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | 67ee3df9 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: A and B name the configured separator, D states expansion uniformity; retire E (superseded) and F (empty is not a state)
- 2026-08-10 | e001c08a | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: retire C, which named a list of accepted alternate separators that no longer exists
- 2026-07-31 | 25c43ce2 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 313fe52b | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | 313fe52b | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Multi-Assertion Reference Expansion* | **Hash**: 6d66ba55
---

## REQ-d00082: Unified Reference Configuration

**Level**: dev | **Status**: Active | **Implements**: REQ-p00001-A

A single, configurable reference pattern is used to locate requirement references across every kind of source file.

### Assertions

D. <RETIRED> named a configurable case-matching mode that does not exist. An identifier is admitted in one spelling only, per REQ-d00212-G, so there is no case-matching mode to configure.

E. Locating a reference in a source file SHALL use the separator the repository owning the referenced identifier configures, so that a reference is recognised in exactly the form that repository writes and in no other.

F. <RETIRED> named per-file reference overrides that do not exist. One set of acceptance rules applies in every context that accepts a reference, per REQ-p00014-T.

G. Reading a reference SHALL yield the parts its grammar defines, so that a consumer works from the identifier's structure rather than from the matched text.

H. <RETIRED> named a reference-configuration artifact that does not exist. The limitation it described is real: a *Traceability* keyword inside a block comment is never read, so a block-comment-only language has no reference form.

I. <RETIRED> named classes that do not exist; source-file reference matching derives from the identifier grammar authority.

J. <RETIRED> named classes that do not exist; test-file reference matching derives from the identifier grammar authority.

K. <RETIRED> a result record is matched to its test by recorded identity, not by reading requirement references out of a reported test name.

L. <RETIRED> a result record is matched to its test by recorded identity, not by reading requirement references out of a reported test name.

### Rationale

Different projects use different ID conventions, comment styles, and directory structures. A unified reference configuration allows all parsers to share the same configurable pattern matching, avoiding duplicated logic and ensuring consistent behavior across parser types.

### Changelog

- 2026-08-24 | edbd5d9a | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | f0808bb9 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | 268cdb9f | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: retire D and F, which named configuration that does not exist; G states the parts a read reference yields
- 2026-08-10 | 6289e433 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: E names the configured separator rather than a list of accepted alternates
- 2026-08-10 | 109921be | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | 00cd96fc | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 89956cd7 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 89956cd7 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Unified Reference Configuration* | **Hash**: edbd5d9a
---

## REQ-d00084: Trace Command

**Level**: dev | **Status**: Active | **Implements**: REQ-p00003

### Assertions

A. The command SHALL support structured JSON graph output via `--graph-json`, including git change annotations when available.

B. The command SHALL offer named default sets of values, each selecting as REQ-d00282 governs, so that a reader who names none is answered with a set chosen for the report rather than with every value the tool can state.

C. The command SHALL support independent detail flags (`--body`, `--assertions`, `--tests`) that control whether expanded rows appear beneath each requirement, orthogonal to column presets.

D. The default sets other than the most compact SHALL state the Implemented, Tested and Passing dimensions of REQ-d00277, each as the per-*Assertion* total of REQ-d00069-N.

### Rationale

A JSON graph output mode enables programmatic consumption of the full *Traceability* graph with git-aware change tracking, supporting dashboard integrations and automated analysis pipelines. Named default sets and detail flags are independent axes of control: a reader may want a compact table with full coverage columns, or a minimal table with expanded *Assertion* rows. A default set is what a reader who names nothing receives; which columns a report may be asked for, and what a column stating a measure must say about itself, are REQ-d00282's.

### Changelog

- 2026-08-21 | 5728e809 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-21 | a6ede1e4 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-19 | 67887c51 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-18 | 3a6da144 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-17 | 66981b81 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | 1bd6bca1 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-02 | 64954432 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-02 | f4e1d611 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | f8f0e0f2 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | f8f0e0f2 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Trace Command* | **Hash**: 5728e809
---

## REQ-d00085: Unified Report Composition

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002, REQ-p00003

### Assertions

A. The CLI SHALL accept multiple section names (`health`, `coverage`, `trace`, `changed`) as positional arguments, rendering each in order and concatenating the output.

B. Shared flags (`--format`, `-o`, `-q`/`--quiet`, `-v`/`--verbose`, `--lenient`, `--mode`) SHALL apply globally across all sections in a composed report.

C. The exit code of a composed report SHALL be the worst-of-all-sections: non-zero if any section reports errors, or warnings without `--lenient`.

D. When a single section is specified, it SHALL behave identically to a standalone command invocation.

E. The `--format` flag SHALL support `text`, `markdown`, `json`, and `csv` output modes. Not all formats are valid for all sections; invalid combinations SHALL produce a clear error.

F. The `-q`/`--quiet` flag SHALL suppress all output except a single summary line per section.

G. The `--lenient` flag SHALL allow warnings to pass without affecting the exit code.

H. The `--format junit` option SHALL render health checks as JUnit XML, mapping categories to `<testsuite>` elements, checks to `<testcase>` elements, failures to `<failure>` elements, warnings to `<system-err>`, and info to `<system-out>`.

I. Each check SHALL carry the findings it raised.

J. The `--format sarif` option SHALL render health findings as SARIF v2.1.0 JSON, with one `reportingDescriptor` per unique check name, one `result` per `HealthFinding` with physical locations, passing checks omitted, and coverage stats in `run.properties`.

K. The `-v`/`--verbose` flag SHALL expand all available detail.

L. Without `--lenient`, any warning-level finding SHALL cause a non-zero exit code.

M. Detail for a passing check SHALL be suppressed by default and included on request.

N. A format that always carries complete findings, or that omits passing checks entirely, SHALL render identically whether or not passing-check detail is requested.

### Rationale

Report-producing commands (`health`, `trace`, `coverage`, `changed`) currently exist as independent subcommands with inconsistent format support. Composing a combined report (e.g. health + coverage for a CI PR comment) requires multiple invocations and manual concatenation. A composable system builds the graph once, renders each section, and produces unified output. The `--lenient` flag provides an escape hatch for workflows that want to observe warnings without gating on them.

Quietness and verbosity are separate obligations (F, K), as are leniency and the default it departs from (G, L). Each pair was carried under one label until evidence for one half was found standing in for both: coverage is reported per assertion, so a label holding two obligations cannot distinguish an implementation from half of one.

A check is where a report groups what it found, so I attaches each finding to the check that raised it; that grouping is what a report counts against a check, renders beneath it, and suppresses or expands under M. What an individual finding carries, and its agreement across the formats a report is rendered in, is REQ-d00285's subject rather than this requirement's.

A failing check's findings are what the reader came for; a passing check's are noise until asked for, which is why M suppresses them by default and makes the request explicit rather than the reverse. The request is about passing checks only and is orthogonal to overall verbosity — a format carries a passing check's detail because it was asked for, not because the report as a whole is verbose. N is separate from M because a format can be wrong about invariance while the request itself works: complete findings and omitted passing checks are properties of those formats, not outcomes of the request.

### Changelog

- 2026-08-24 | ee68f8ee | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-24 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-66: restate I as the attachment of a finding to the check that raised it; what a finding carries and its agreement across formats is REQ-d00285's
- 2026-08-11 | 587285b0 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-11 | 650b3641 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-11 | 0d1e518a | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: specify passing-check detail (M) and its format invariance (N)
- 2026-08-11 | 0d1e518a | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: split the verbose half of F into K and the without-lenient half of G into L
- 2026-07-31 | 0d1e518a | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 82d76f1a | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 82d76f1a | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Unified Report Composition* | **Hash**: ee68f8ee
---

## REQ-d00271: Diagnostic Code Vocabulary

**Level**: dev | **Status**: Active | **Implements**: REQ-p00015

A report groups findings so they can be counted and a severity chosen for them, and names each finding's defect so it can be acted on. Those are separate vocabularies with separate obligations: the first is closed so a project can configure against it, the second is open so a diagnosis can become more specific without anything having to be reconfigured.

### Assertions

A. Every finding SHALL carry a code naming its defect, and the codes SHALL be documented with an example of input that produces each.

B. A finding MAY carry more than one code, so that a defect determined in several independent respects is reported in all of them rather than in whichever was tested first.

C. There SHALL be a code meaning that the defect could not be determined beyond the category, and a finding whose defect is undetermined SHALL carry it. A finding carrying only that code is the report that nothing more specific is known, and SHALL NOT be read as the absence of a diagnosis.

D. A code SHALL be issued only where the input determines the defect it names. Where the input admits two accounts of equal extent, neither SHALL be issued.

E. <RETIRED> forbade introducing a code from changing a category, a configured severity, or the meaning of a code in use. Nothing permits introducing a code to do any of those, so nothing had to forbid it.

### Rationale

The two vocabularies fail in opposite directions, which is why they are separated. A category that grows breaks configuration that referred to the old set and reopens a decision the project already made. A diagnosis that cannot grow leaves the tool unable to say more than it once could, so every improvement in what it can determine has to be paid for in churn somewhere. Fixing the categories and leaving the codes open lets diagnosis improve indefinitely at no cost to the project's settings.

D is what keeps B from becoming guesswork. Reporting several respects in which an input is defective is a statement of fact only where each respect is determined by the input; where two accounts explain it equally, naming either asserts something the input does not support, and an author acting on the wrong one is worse off than an author told only the category. C is what makes that refusal reportable rather than silent: without a code for "no further account", declining to guess is indistinguishable from not having looked.

### Changelog

- 2026-08-25 | fb458e96 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-16 | 6f4019d1 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: sync changelog hash
- 2026-08-16 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: Active — every reported fault carries codes, the codes are documented with a producing input in `elspais docs linking`, and two codes no input could produce are retired from the vocabulary
- 2026-08-15 | - | - | Michael Lewis (<michael@anspar.org>) | Initial authoring: closed categories over open codes, multiple codes per finding, a generic code, and issuance only where determined

*End* *Diagnostic Code Vocabulary* | **Hash**: fb458e96

## REQ-d00285: The Shape of a Finding

**Level**: dev | **Status**: Draft | **Implements**: REQ-p00015
**Satisfies**: REQ-p00019

A finding is what the tool hands back when something is wrong with the content or the configuration it was given. REQ-d00271 governs the vocabulary a finding names its defect in. This governs what a finding must carry besides that name, so that a reader can act on it and so that two surfaces reporting the same condition cannot disagree about it.

### Assertions

A. Every finding SHALL carry the location of what it is about — the file, and the line within that file — where what it is about has one.

B. Every finding SHALL carry the action available to resolve it, naming that none is known where that is so.

C. A finding SHALL carry the same identity, severity, location and remedy whatever format the report is rendered in.

D. Every finding SHALL fall in a category for which a severity can be configured.

E. One authority SHALL decide a finding's severity from its category.

F. A name under which findings are reported SHALL identify one condition.

G. Where a condition the tool detected is not reported, the point at which it is withheld SHALL record what was withheld and why.

H. <RETIRED> forbade a narrowing of which findings a report presents from changing the verdict that report reaches. Nothing permits which findings are shown to bear on the verdict, so nothing had to forbid it.

I. A report that narrows which findings it presents SHALL disclose the narrowing and the extent of what it withheld.

### Rationale

A finding a reader cannot locate costs them the search the tool already performed, and a finding that names no remedy leaves them to infer one from the defect — which is exactly the inference the tool is better placed to make. A and B put both on the finding itself rather than in a table consulted at render time, because a table keyed by name covers only the names someone remembered to add, and it cannot travel to a surface that renders differently.

C is the same property REQ-p00084-C establishes for scope, applied to findings: a report a reader checks and a report they file must not disagree. A finding that reaches one format and not another is indistinguishable, to the reader of the quieter format, from a finding that was never raised.

D and E separate two questions that are easy to merge. D is about coverage — no finding may sit outside the settings a project can reach, which is what leaves a condition unconfigurable. E is about agreement — one finding, one severity, however many surfaces ask. Where two places decide severity independently, a project that changes a setting sees one of them move.

F concretizes REQ-p00019-J and -K in the direction those assertions do not reach. They oblige a description to be true of every finding it covers and a finding to be reported once; F obliges the converse, that a name not be reused for a second condition. Two conditions under one name make a count uninterpretable in the same way double-reporting does, and the reader has no way to see it.

G concretizes REQ-p00019-H. Suppression is legitimate; silent suppression is not, and the difference is a record at the point the decision is made. Without it, a condition detected and dropped is indistinguishable from a condition never detected, and the code that drops it reads as if nothing were being decided.

H and I govern a report narrowed to the findings a reader asked for, by severity, by category, by the code a finding carries or by where it is located. A verdict is what the run found, not what the reader chose to look at; taken over the surviving findings instead, a narrowing would become a way to pass a run that failed, and the narrower the question the healthier the answer. I is the disclosure REQ-p00084-D asks of a scoped report, reached by another route: a report holding fewer findings than the run produced is indistinguishable, from the output alone, from a run that found fewer. Naming the narrowing and the extent of what it withheld separates the two without listing the withheld findings, which would undo the narrowing the reader asked for. G is the same principle where the tool rather than the reader decides.

Classes of REQ-p00019 not concretized here are bound through the instance rather than left uncovered: D, E and F are properties of what a report says overall, which REQ-p00015 governs for this tool; B is governed for content staleness by the hash and index checks. This requirement concretizes A and C through I, a report narrowed to the findings a reader asked for being one that omits the rest and hands back a part of what the run found; G through B, H through G, and J and K through F.

D and E are where a finding's severity is settled, for every finding the tool produces. No other requirement states that a condition is reported at a configurable severity: saying it again would put a second copy of this rule somewhere it could drift from, and a requirement that named its own severity would be describing the registry rather than an obligation.

### Changelog

- 2026-08-24 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-66: govern narrowing a report to selected findings — the verdict stays the run's, and the narrowing and the extent of what it withheld are disclosed
- 2026-08-24 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-66: Initial authoring — a finding carries its location, its remedy and one severity decided in one place, and reads the same in every format

*End* *The Shape of a Finding* | **Hash**: b0ffe9ce

## REQ-d00286: Built-In User Documentation

**Level**: dev | **Status**: Draft | **Implements**: REQ-p00001

A user asks the tool what one of its subjects means and the tool answers, without a network and without the repository it was built from. This states where that documentation lives, what it must cover, and why it cannot drift from the program it describes.

### Assertions

A. The tool's user documentation SHALL have one source.

B. Every surface presenting that documentation SHALL render it from that source.

C. Each subject the tool exposes SHALL have a documentation topic.

D. The documentation SHALL travel with the installed program, so that an installation and a checkout answer alike.

E. A set the program defines and the documentation presents SHALL be presented from that definition, so that the two cannot disagree.

F. The tool SHALL render a topic without display formatting on request.

### Rationale

Documentation that is copied is documentation that diverges, and the copy a reader happens to open is the one that misleads them. A and B put the whole estate behind one source so there is no second copy to fall behind, and D carries that source into the installed program so a user who never cloned anything gets the same answer as a developer reading the file.

E is the sharper form of the same rule, and it is the one that fails silently. A hand-maintained list of what the program offers — its checks, its settings, the comment patterns it reads — is correct on the day it is written and wrong on the day the program gains one more. Deriving the presentation from the definition removes the opportunity: the two cannot disagree because there is only one of them. Where a fact is genuinely prose, this does not apply; it binds only where the program already holds the set.

C is what makes a subject discoverable at all. A command or a setting a user can reach and cannot read about is indistinguishable, to them, from one that does not work.

F exists because documentation is read by programs as well as people, and display formatting that cannot be turned off makes the text unusable to anything that is not a terminal.

### Changelog

- 2026-08-24 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-66: Initial authoring — one source for the tool's documentation, carried into the installed program, with any set the program defines presented from that definition

*End* *Built-In User Documentation* | **Hash**: d246f21a

---

## REQ-d00086: Coverage Report Section

**Level**: dev | **Status**: Active | **Implements**: REQ-p00003

### Assertions

A. The report SHALL group requirements by level as REQ-d00281 determines those groups, and show counts and percentages of requirements with code references, test references, and passing tests.

B. The report SHALL compute per-requirement *Assertion* coverage for Implemented, Tested and Passing as REQ-d00277 defines them, each on the total coverage of REQ-d00069-N.

C. The report SHALL support `text`, `markdown`, `json`, and `csv` output formats.

D. The report SHALL use existing graph aggregate functions and annotator data rather than reimplementing coverage logic.

### Rationale

Coverage data is already computed during graph construction but is only surfaced through the interactive viewer or the underpowered `analyze coverage` text output. A dedicated coverage section with multi-format support enables CI badge generation, PR comment summaries, and developer-facing markdown reports.

### Changelog

- 2026-08-21 | 8e02f52d | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-20 | 067a62c4 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-20 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-74: level groups follow the requirements reported on rather than a fixed set named here
- 2026-08-19 | 4559fce7 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-18 | 0cca2a88 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-17 | 185b2d34 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | a12d2826 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-02 | a17871db | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 2fd4ab13 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | 2fd4ab13 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Coverage Report Section* | **Hash**: 8e02f52d
---

## REQ-d00073: Link Suggestion CLI Command

**Level**: dev | **Status**: Active | **Implements**: REQ-o00065

`elspais link suggest` is a CLI command.

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

### Assertions

A. The module SHALL compute PageRank-style centrality scores for requirement nodes by iterating on reversed edges (children distribute score to parents) with a configurable damping factor, converging within a tolerance threshold.

B. The module SHALL compute fan-in as the count of distinct direct parents (among included node kinds) for each node, identifying cross-cutting requirements that serve multiple independent areas.

C. The module SHALL compute neighborhood density by walking up through each node's ancestors and counting siblings/cousins at each level, applying exponential decay by distance (siblings=1.0, cousins=decay, second-cousins=decay^2).

D. The module SHALL compute uncovered dependent counts by walking descendants and counting leaf requirements with zero coverage.

E. The module SHALL produce a composite score by normalizing each metric to 0.0-1.0 and applying configurable weights (default 0.3 centrality, 0.2 fan-in, 0.2 neighborhood, 0.3 uncovered).

F. The module SHALL filter nodes by `NodeKind`, defaulting to REQUIREMENT and *Assertion*, with *Assertion* nodes included in computation but excluded from ranked output.

G. The module SHALL rank actionable leaf nodes by summing the composite scores of their ancestors, surfacing the most impactful uncovered work items.

H. Ranking SHALL read the graph without modifying it.

### Rationale

In a large requirements DAG, naive metrics like descendant count always favor the root node. PageRank centrality naturally handles DAGs and rewards cross-cutting dependencies. Combined with fan-in (how many independent areas depend on a node) and coverage gaps, this enables evidence-based prioritization of foundational work.

### Changelog

- 2026-08-30 | 87bc52f2 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | b153d5f6 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 86bb619b | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | 86bb619b | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Graph Analysis Engine* | **Hash**: 87bc52f2
---

## REQ-d00125: Analysis CLI Command

**Level**: dev | **Status**: Active | **Implements**: REQ-p00003

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

### Assertions

A. Invoking `elspais example` with no subcommand SHALL print a quick-reference summary covering the basic requirement structure and the available `example` subcommands.

B. `elspais example requirement` SHALL print example requirement templates for each configured level (PRD, OPS, DEV), each including an `## Assertions` section and an `*End*` footer with a hash placeholder.

C. `elspais example journey` SHALL print an example user journey template covering Actor, Goal, Steps, and Requirements sections.

D. `elspais example assertion` SHALL print assertion format rules covering label styles, SHALL/SHOULD/MAY keywords, placeholder values for removed assertions, and the assertion-related configuration syntax.

E. `elspais example ids` SHALL print the ID pattern configuration for the current project (namespace, canonical ID template, and level types), loaded from the active config file when present and falling back to schema defaults otherwise.

F. `elspais example --full` SHALL display the full contents of the project's `requirements-spec.md` (or `requirements-format.md`) file when found, and SHALL return a non-zero exit code with the searched paths listed when neither file exists.

G. The `example` command SHALL run without a spec directory or a built graph.

### Rationale

Authors writing their first requirement, or reviewers checking format conventions, need a fast, offline reference without opening the full *Specification*. `example` fills this role independently of `elspais init` (which scaffolds a new project's configuration) by surfacing format templates and rules on demand.

### Changelog

- 2026-08-30 | 99ce6269 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | c3b67490 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-03 | 8e05d02e | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms, update hash, add missing changelog section

*End* *Requirement Format Reference Command* | **Hash**: 99ce6269

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

M. <RETIRED> forbade admitting a further property a scope can select on from changing which requirements an already expressible scope selects. Nothing permits a scope's meaning to turn on properties it does not name.

### Rationale

C, D, E and F fix how a scope is read. A scope is a set of properties carrying values, and C is what keeps any combination of them writable; D, E and F then fix the reading, because a combination whose meaning is left open is not a vocabulary. Properties named together are conditions a requirement meets at once; values named for one property are alternatives. That is the same narrowing a reader performs when browsing the estate interactively, and a vocabulary meaning anything else would give a reader two incompatible ways to say one thing. F is stated as a refusal rather than as a second kind of scope, so a property carrying both the values a requirement must have and the values it must not resolves the same way wherever they overlap, and the vocabulary needs no rule for their collision.

G keeps a scope correct as a project's statuses grow. Statuses are a project's own and multiply; the roles it assigns them are the stable vocabulary underneath. Were a role a value the status property admitted, a reader would face two things that look alike in one list and behave differently, and every scope would have to be read to discover which it named. Keeping the role out of the value list and making it a widening of the statuses already named leaves one kind of thing in the list, and one question about the scope as a whole: whether a named status stands for itself or for everything sharing its role.

H and I divide a question that would otherwise be answered by whichever member happened to be asked. H says what a vocabulary holds: a value a requirement carries belongs to it whether or not the configuration names it, because a requirement carrying a status the project never listed is one a reader can see and therefore one a reader can ask for. I says whose vocabulary is consulted — each requirement is judged under the vocabulary of the project that wrote it, never one assembled from several, which would let one member's configuration decide what another member's requirements are. REQ-d00251-L settles the same question for identifiers, and the reasons carry over unchanged.

J, K and L are the honesty group, separate because opposite situations produce the same thin report. A name the vocabulary does not admit selects nothing while looking like it selected something, and a federated estate is where that hides best. J is the disclosure; K is what keeps it from becoming a refusal, since a cross-member scope naming a level only some members define is legitimate and a report that stops at the first such name is useless to the reader who wrote it. L is the other side: a scope selecting nothing is frequently the correct result, and reporting it as the answer keeps it distinguishable from the conditions REQ-d00080-B and REQ-d00080-E report, which are about an estate or a member holding no requirements at all.

M is what allows the vocabulary to grow, and growth is owed. Selection axes beyond level and status are foreseeable: a compiled document offering its stakeholder audience the product-level requirements of every member of a federation, or a ranking narrowed to one level (REQ-d00125-E), are selections of this kind and are expressed in this vocabulary. The cost of admitting a property must fall on the scopes that use it and on nothing else — a project whose committed scopes shifted meaning because the tool learned a new property would have to re-audit every report it ever committed.

*End* *Report Scope Selection Vocabulary* | **Hash**: 622363f0

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

## REQ-d00282: Report Value Selection

**Level**: dev | **Status**: Draft | **Implements**: REQ-p00084

A report states values about each of its rows, whether a row is a requirement or a group of them. Which requirements a report is about is a scope; which values it states is this. The two are separate choices about one report, and a reader making one of them says nothing about the other.

### Assertions

A. A report SHALL accept a selection naming which of the values it offers it states.

B. For each coverage dimension of REQ-d00277, a report SHALL admit selecting the count of assertions credited, the count of assertions the credit is taken over, and their proportion, each in its own right and for the dimension's total as for each of the four measures behind it (REQ-d00069-L).

C. A value taken on one measure SHALL be named for both the coverage dimension it measures and the measure it is taken on.

D. A value a report states SHALL equal the value a report stating every value it offers states for the same row.

E. <RETIRED> forbade the values a report states from depending on the format it is rendered in. A format may offer values another does not, so what carries across formats is agreement rather than presence: a value that IS reported is the same in all of them, per REQ-p00084-C.

F. A report SHALL NOT be produced under a selection the tool did not honour in full.

G. <RETIRED> forbade offering a further value from changing which values an already expressible selection states. A selection states the values it names, per REQ-d00282-A and REQ-d00282-K; nothing permits an unnamed value to enter it.

H. <RETIRED> forbade selecting which values a report states from changing which requirements the report is about. Which requirements a report is about is its scope, per REQ-p00084-B; nothing permits a value selection to bear on it.

I. <RETIRED> forbade selecting which requirements a report is about from changing which values it states. A report states the values its selection names, per REQ-d00282-A; nothing permits its scope to bear on them.

J. The names a selection uses SHALL be independent of the words a project configures its values to be displayed under.

K. A report SHALL state its values in the order the selection names them.

L. A report SHALL state what each of its rows is about whatever the selection names.

M. A value a report does not state for a row SHALL be distinguishable from one it states as zero.

N. For a figure measured in lines, a report SHALL admit selecting the lines covered, the lines measured, and their proportion, each in its own right.

### Rationale

B is what the coverage vocabulary already makes possible, taken down to the scalar. A coverage figure is computed on four measures with a total taken from them (REQ-d00069-L+N), and each of those is itself a credit counted over a population -- so a reader may want the credit, the population it was counted over, their proportion, or any combination. Offering only the composite makes a reader who wants one number take three, and makes a program parse a sentence to recover what was a number before it was rendered. Naming each separately is also what keeps a proportion honest: it is derived from the other two, and a report stating all three states the same fact three ways rather than three facts. It names the dimensions of REQ-d00277 rather than coverage at large because line coverage is measured in lines and has no four measures to select among (REQ-d00254-B); a rule written over every coverage figure would oblige a surface to offer what that one cannot.

A value is not a column. A column is how a report with rows and headings renders one, and a report rendered some other way renders it some other way -- so an obligation written over columns says nothing about the report that has none, and invites a composite built for a table to be carried into a format that wanted the numbers. Some values have only the one form: an assertion counted as passed, failed or awaiting a result is a count and has no proportion of its own, and though those three sum to the assertions a dimension counts, a reader wanting only the failures is owed only the failures.

C is what keeps B honest, and it is the hazard peculiar to this axis. A narrowed report is missing rows a reader cannot see, which is why a scope discloses itself; a narrowed report is missing values a reader can see are absent, so their absence needs no announcement. What a reader cannot see is which evidence a figure counts. A requirement whose implementation is entirely conducted or cited whole shows nothing against the measure counting citations that name its assertions, and a value named only for the dimension would state that as the dimension's figure -- the reader is not missing information, they are being given the wrong information. Naming both halves is what settles it: the dimension alone leaves the evidence unsaid, and the measure alone leaves unsaid what it is a measure of.

D fixes what a selection may not disturb, and names its own comparand rather than leaving "unchanged" to be argued. Choosing which facts to see is a choice about the report, never about the estate, and a figure computed differently because fewer were asked for would make the narrow report and the wide one disagree about the same requirement. The risk it guards is real rather than theoretical: coverage conducted up a `Refines:` chain is expensive, and a surface that skipped conducting because no conducted measure was selected would move the total, which is a different question's answer.

E, H and I are three independences, and they fail separately. E is between renderings of one report: a selection meaning one thing in the artifact a reader checks and another in the one they file is the divergence REQ-p00084-C forbids for requirements, reached here for the values stated about them. It binds which values are stated and not how each is spelled. A table renders a value in a cell and a structured format renders it as a number; a figure made of several numbers is one cell to the first and those numbers to the second, and both have stated the same value. A format that flattened it to the cell's spelling would oblige its reader to recover by parsing what it had before it rendered. H and I are between the two axes. Selecting fewer columns cannot drop a requirement and selecting fewer requirements cannot drop a column, so a reader may reach the same report by narrowing either first -- which is what makes the two genuinely separate choices rather than one choice with two names. A named set of values that also filtered rows would be a second row-selection outside the authority REQ-d00279-A establishes, and no reader could predict which one won.

F is the opposite disposition from the one REQ-d00278-K takes for a value a scope's vocabulary does not admit, and the difference is in where the vocabulary lives. A scope is read against each member's own vocabulary, so a name one member does not admit is an ordinary state of a federated estate and must not stop the rest of the scope selecting. The values a report offers are the tool's own and identical everywhere, so a name among them that does not resolve is a mistake rather than a difference, and honouring the rest of the selection would hand the reader a narrower report than they asked for while looking exactly like the one they wanted.

G and J are what a committed selection is worth. G bounds what the tool may do: a project whose committed selections changed meaning because the tool learned a new value would have to re-audit every report it committed under one. A default set may grow; a selection is what a project commits when it needs the shape to hold. J bounds what the project may do to itself: the words a value is displayed under are configurable (REQ-d00258-K), so a selection written in display words would break every committed report the day someone renamed a label, which is the same churn arriving by the other door.

K and L are what make a stated selection a stated shape. A committed artifact is read by something that expects its values where it left them, so an order decided differently on two runs breaks a consumer exactly as a changed set would. L is the floor beneath every selection: a row that cannot be attributed to what it is a fact about is not a report about anything, whatever else it states.

N reaches the one figure B cannot. Line coverage is measured in lines and confers no assertion credit (REQ-d00254-B), so it has none of the four measures B decomposes and was left whole -- but whole is not the same as indivisible. It is a count of lines covered out of lines measured, and a reader wanting the proportion should not have to take a rendering and read the numbers back out of it. A further reading of the same lines, how many of them a verifying test can be named for, is a different question again: it is named for that attribution rather than for the figure at large (C), and where the tooling records no test contexts it is not stated at all rather than stated as none (REQ-d00258-E). What that suppression must not do is take the lines covered with it -- they were measured, and a report that has them and says nothing has withheld an answer it holds.

M is the distinction between having nothing to say and saying nothing. Not every value a report offers exists for every row -- a coverage figure has none for a group whose requirements confer none. Where those two look alike a reader reads absence as zero and concludes work is undone that was never owed, which is the same defect REQ-d00258-E keeps out of line coverage by recording whether a measurement was taken rather than letting an absent one read as none.

*End* *Report Value Selection* | **Hash**: b0d3912d

---

## REQ-d00280: Named Report Declarations

**Level**: dev | **Status**: Draft | **Implements**: REQ-p00084

A report run from an invocation is defined only where that invocation was written down. This requirement covers what a project declares under a name, and what a report produced under that name contains.

### Assertions

A. A project SHALL be able to declare a scope under a name in its own configuration.

B. A scope referred to by name SHALL select the requirements that the scope declared under that name selects when stated in full.

C. A project SHALL be able to declare, under one name, both the scope a report is produced under and the values it states.

### Rationale

A, B and C are what REQ-p00084-F asks for in a form a project can commit and a reader can check. A is where the scope comes to rest — in the project, beside the requirements it selects over, versioned with them — and B is what keeps the name honest: a name is a reference to a scope, never a second selection that happens to share a spelling. An author reading a declaration then knows what a report produced under it contains without running it; once the two can differ, a committed report is evidence of a scope nobody can reconstruct.

C is what makes a declaration answer for a whole audience rather than half of one. An audience is defined by the requirements it reads and by the facts it reads about them, and a project able to commit only the first carries the second in whatever invoked the report, which is the drift a declaration exists to end. One name for both does not join the two choices: they remain independent everywhere REQ-d00282-H and REQ-d00282-I say they are, a declaration naming no columns constrains none, and a selection stated on an invocation stands without a declaration to belong to. What the name buys is that an audience can be referred to once.

*End* *Named Report Declarations* | **Hash**: ab0a70bb
