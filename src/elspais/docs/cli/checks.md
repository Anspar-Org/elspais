# CHECKS

The `elspais checks` command performs **traceability verification** — confirming that requirements are properly traced through implementation, tests, and validation results. In FDA CSV (Computer System Validation) terms, this is the automated equivalent of verifying a Requirements Traceability Matrix (RTM).

## Quick Start

```bash
# Run all checks
elspais checks

# Check specific category only
elspais checks --spec         # Spec file checks
elspais checks --code-checks  # Code reference checks
elspais checks --tests        # Test mapping checks
elspais checks --terms        # Defined-term checks

# See what each failing check actually found
elspais -v checks

# Narrow the findings to the ones you are working on
elspais -v checks --severity error
elspais checks --check references.malformed
elspais checks --code E_IDENTIFIER_WITH_TRAILING_TEXT
elspais checks --file 'spec/*.md'
```

`elspais unresolved`, `elspais errors` and `elspais uncited` are that last
narrowing under a shorter name — each is this report narrowed to the checks
that answer one question, and each prints the `--check` flags that reproduce
it.

## Check Severity

Every check carries a severity, and every severity is a project decision. The
vocabulary is four words:

| Severity | Meaning |
|----------|---------|
| `off` | The condition is not reported here. The check reports as skipped and produces no findings. |
| `info` | Worth saying; never a failure. |
| `warning` | Needs attention; the run exits non-zero unless `--lenient`. |
| `error` | A defect; the run exits non-zero. |

A value outside those four is refused when the configuration is read, so a
setting can never name a severity nothing acts on.

`off` is how a single check is turned off, and it withholds the findings as
well as the verdict — nothing about the condition appears in any output format.
To keep seeing the findings without failing the run, use `info`.

### Where a check's severity is configured

A check reads ONE setting and only one, so a project that sets the setting it
read about always sees it take effect. Checks that answer a question with a
setting of their own keep it:

| Setting | Checks it governs |
|---------|-------------------|
| `[rules.references] <class>` | the `references.*` checks, and the `code.*_references` / `tests.*_references` status checks |
| `[rules.format] no_assertions_severity` | `spec.no_assertions` |
| `[rules.format] no_traceability_severity` | `code.no_traceability` |
| `[rules.coverage] uncredited_evidence` | `tests.uncredited_evidence` |
| `[rules.coverage] external_test_failure` | `tests.external` |
| `[terms.severity] <name>` | the `terms.*` checks |

Every other check is configured under the general `[rules.severity]` table,
keyed by the name the check reports under. Check names contain a dot, so the
key must be quoted:

```toml
[rules.severity]
"spec.parseable" = "off"
"tests.results" = "info"
"docs.config_drift" = "error"
```

Two entries are refused when the configuration is read: a name no check reports
under, and a name that has a named setting of its own — putting it here would
be read by nothing. The catalog below is the list of names this table accepts;
its **Configured by** column says which of the two routes each check takes.

Coverage tier severities (`[rules.coverage.<dimension>]`, below) use the same
four words.

## Check Categories

### Configuration Checks

Configuration checks always run as part of traceability verification. For focused configuration and environment diagnostics, use `elspais doctor`.

<!-- generated: check-catalog:config -->
<!-- Rendered from the program's own definitions; edits here are overwritten. Regenerate: python -m elspais.utilities.doc_tables -->

| Check | Description | Default severity | Configured by | Remedy |
| --- | --- | --- | --- | --- |
| `config.load` | The configuration file loads at all | error | `[rules.severity]` | `elspais doctor` |
| `config.exists` | Verifies config file exists or using defaults | error | `[rules.severity]` | `elspais init` |
| `config.syntax` | Validates TOML syntax is correct | error | `[rules.severity]` | `elspais doctor` |
| `config.required_fields` | Ensures required sections present | error | `[rules.severity]` | `elspais doctor` |
| `config.pattern_tokens` | Validates pattern template tokens | error | `[rules.severity]` | `elspais doctor` |
| `config.hierarchy_rules` | Checks hierarchy rules consistency | error | `[rules.severity]` | `elspais doctor` |
| `config.paths_exist` | Verifies spec directories exist | error | `[rules.severity]` | `elspais doctor` |
| `config.project_type` | The declared project type is one the tool knows | error | `[rules.severity]` | `elspais doctor` |
| `config.associated_section` | Every associate declaration reads (both a path and a namespace) | error | `[rules.severity]` | `elspais doctor` |
<!-- /generated: check-catalog:config -->

Each table in this catalog holds the checks reporting under one category, so
a check appears exactly where its findings do. A `config.` check that needs a
built graph reports under **spec** and is listed there, not here.

### Environment Checks (`elspais doctor`)

<!-- generated: check-catalog:environment -->
<!-- Rendered from the program's own definitions; edits here are overwritten. Regenerate: python -m elspais.utilities.doc_tables -->

| Check | Description | Default severity | Configured by | Remedy |
| --- | --- | --- | --- | --- |
| `local_toml.exists` | Reports whether a `.elspais.local.toml` developer override is present | error | `[rules.severity]` | no command resolves this; resolve it by hand |
| `cross_repo.in_committed` | Cross-project paths written into the shared, committed configuration (they belong in the local override) | warning | `[rules.severity]` | no command resolves this; resolve it by hand |
| `worktree.status` | The state of the git worktree the run was invoked from | info | `[rules.severity]` | no command resolves this; resolve it by hand |
| `associate.paths_resolvable` | Every configured associate path resolves to a directory | error | `[rules.severity]` | `elspais associate list` |
| `mcp.registration` | No client registration reaching this tree names a fixed address | warning | `[rules.severity]` | `elspais mcp install` |
| `daemon.status` | What serves this working tree, and whether it holds unsaved changes | info | `[rules.severity]` | `elspais daemon restart --persist` |
| `associate.configs_valid` | Every configured associate's own configuration loads | error | `[rules.severity]` | `elspais associate list` |
<!-- /generated: check-catalog:environment -->

### Documentation Checks (`elspais doctor`)

Documentation checks compare what the tool offers against what its
documentation says about it.

<!-- generated: check-catalog:docs -->
<!-- Rendered from the program's own definitions; edits here are overwritten. Regenerate: python -m elspais.utilities.doc_tables -->

| Check | Description | Default severity | Configured by | Remedy |
| --- | --- | --- | --- | --- |
| `docs.config_drift` | Compares config schema sections against `docs/configuration.md`; reports undocumented and stale sections (runs in `elspais doctor`) | warning | `[rules.severity]` | no command resolves this; resolve it by hand |
<!-- /generated: check-catalog:docs -->

### Spec File Checks (`--spec`)

<!-- generated: check-catalog:spec -->
<!-- Rendered from the program's own definitions; edits here are overwritten. Regenerate: python -m elspais.utilities.doc_tables -->

| Check | Description | Default severity | Configured by | Remedy |
| --- | --- | --- | --- | --- |
| `config.associate_paths` | Validates that every federated repository — those declared here and those reached through an associate's own `[associates]` declarations — loads and contains spec files, reporting each failure with its path and reason | error | `[rules.severity]` | `elspais associate list` |
| `config.no_requirements` | Flags when no requirements are found (likely config issue) | warning | `[rules.severity]` | `elspais example` |
| `config.governed_rules` | Discloses each governed setting (coverage rules, reference severities, status roles) a federated member would judge by differently from the repository the run was invoked from — whether the member declared it or kept a default the invoking project overrode — naming the setting, both values and the member; never fails a run | info | `[rules.severity]` | no command resolves this; resolve it by hand |
| `graph.build` | The traceability graph builds at all | error | `[rules.severity]` | no command resolves this; resolve it by hand |
| `spec.parseable` | All spec files can be parsed | warning | `[rules.severity]` | `elspais errors` |
| `spec.unknown_directive` | Assertions opening with a parsing directive the tool does not recognize | warning | `[rules.severity]` | no command resolves this; resolve it by hand |
| `spec.no_duplicates` | No duplicate requirement IDs | error | `[rules.severity]` | `elspais -v checks --spec` |
| `spec.implements_resolve` | All Implements: references resolve | warning | `[rules.severity]` | `elspais unresolved` |
| `spec.refines_resolve` | All Refines: references resolve | warning | `[rules.severity]` | `elspais unresolved` |
| `spec.satisfies_resolve` | All Satisfies: references resolve | warning | `[rules.severity]` | `elspais unresolved` |
| `spec.needs_rewrite` | Flags requirements that will be rewritten on next save (duplicate refs, stale hash) | warning | `[rules.severity]` | `elspais fix` |
| `spec.unfixable_issues` | Issues `elspais fix` cannot repair, so a person has to | error | `[rules.severity]` | `elspais errors` |
| `spec.undefined_levels` | No requirement carries a level the configuration does not define (such a requirement is still counted and grouped, so this discloses it rather than dropping it) | info | `[rules.severity]` | no command resolves this; resolve it by hand |
| `spec.hierarchy_levels` | Requirements follow hierarchy rules | warning | `[rules.severity]` | `elspais -v checks --spec` |
| `spec.structural_orphans` | No nodes without a FILE ancestor (build bugs) | error | `[rules.severity]` | `elspais -v checks --spec` |
| `spec.format_rules` | Requirements satisfy the enabled `[rules.format]` rules | error | `[rules.severity]` | `elspais errors` |
| `spec.hash_integrity` | Flags Satisfies-linked requirements for review when their template hash is stale | warning | `[rules.severity]` | `elspais fix` |
| `spec.changelog_present` | Active requirements must have at least one changelog entry (when `changelog.present = true`) | error | `[rules.severity]` | `elspais fix` |
| `spec.changelog_current` | Active requirements' latest changelog hash must match content hash (when `changelog.hash_current = true`) | error | `[rules.severity]` | `elspais fix -m 'Update changelog'` |
| `spec.changelog_format` | Changelog entries must include required fields (reason, author, etc.) | error | `[rules.severity]` | `elspais -v checks --spec` |
| `spec.index_current` | INDEX.md must be up to date with current requirements and journeys | warning | `[rules.severity]` | `elspais fix` |
| `spec.no_cycles` | No cycle in the requirement hierarchy | error | `[rules.severity]` | `elspais -v checks --spec` |
| `spec.no_assertions` | Requirements with no assertions (not testable) | warning | `[rules.format] no_assertions_severity` | `elspais errors` |
<!-- /generated: check-catalog:spec -->

#### `spec.no_assertions` — Not Testable Requirements

The `spec.no_assertions` check flags requirements that have no assertions defined.
A requirement with no assertions cannot be covered by automated tests or UAT, making
it untraceable at the assertion level.

- **Default severity**: warning (does not cause a non-zero exit by itself)
- **Always on**: this check runs unconditionally, unlike `require_assertions` (which
  is opt-in and produces an error when enabled)
- **Gaps report**: requirements flagged by this check appear in `elspais gaps` with
  the label `NOT TESTABLE (no assertions)` under the `no_assertions` gap type

**Configuration** — adjust severity via `[rules.format]` in `.elspais.toml`:

```toml
[rules.format]
no_assertions_severity = "info"   # off | info | warning (default) | error
```

**Comparison with `require_assertions`:**

| | `spec.no_assertions` | `require_assertions = true` |
|---|---|---|
| Always runs | Yes | No (opt-in) |
| Default severity | warning | error |
| Purpose | Surface untestable REQs for review | Enforce assertions as a hard rule |

Use `require_assertions = true` when you want assertions to be mandatory for all
requirements. Use `no_assertions_severity` to tune the visibility of the advisory
check that is always present.

#### `spec.changelog_*` — Changelog Enforcement

Three checks enforce changelog discipline on Active requirements when enabled
in `[changelog]` config:

- **`spec.changelog_present`** — requires at least one changelog entry.
  Enabled when `changelog.present = true`.
- **`spec.changelog_current`** — the latest entry's hash must match the
  requirement's current content hash. Enabled when `changelog.hash_current = true`.
- **`spec.changelog_format`** — entries must include fields marked as required
  in `[changelog.require]` (reason, author_name, author_id, change_order).

**Configuration:**

```toml
[changelog]
present = true          # require changelog section on Active REQs
hash_current = true     # latest entry hash must match content

[changelog.require]
reason = false          # require a reason in each entry
author_name = false     # require author name
author_id = false       # require author ID
change_order = false    # require change order number
```

**Follow-up:** Run `elspais fix` to add missing changelog entries or update
stale hashes.

#### `spec.index_current` — INDEX.md Staleness

Checks that `INDEX.md` lists exactly the requirements and journeys in the
current graph. Reports missing IDs, extra IDs, or both.

**Follow-up:** Run `elspais fix` to rebuild INDEX.md.

#### `spec.needs_rewrite` — Pending Rewrites

Flags requirements that have been parsed with differences from their on-disk
format (duplicate references, stale hashes). These will be rewritten on the
next `elspais fix`, or when pending in-memory changes are saved from
the viewer or by an agent.

#### `spec.hash_integrity` — Template Hash Review

When a template requirement's content changes (stale hash), all requirements
that declare `Satisfies:` pointing to it are flagged for review. This ensures
that changes to cross-cutting requirements are propagated to their consumers.

### Code Reference Checks (`--code-checks`)

<!-- generated: check-catalog:code -->
<!-- Rendered from the program's own definitions; edits here are overwritten. Regenerate: python -m elspais.utilities.doc_tables -->

| Check | Description | Default severity | Configured by | Remedy |
| --- | --- | --- | --- | --- |
| `code.uncited_file` | A scanned code file that cites nothing -- no `# Implements:`, no `# Verifies:`. Not the same population as the unlinked NODES the graph API and the MCP `get_unlinked_nodes` tool answer about | info | `[rules.severity]` | `elspais uncited` |
| `code.code_tested` | Line coverage over the implementation lines attributed to requirements | info | `[rules.severity]` | no command resolves this; resolve it by hand |
| `code.whole_req_only_coverage` | Coverage resting entirely on whole-requirement evidence, with no citation naming an assertion | info | `[rules.severity]` | no command resolves this; resolve it by hand |
| `code.implemented` | The `implemented` coverage dimension (CODE or child REQ covers assertions) | error | `[rules.severity]` | `elspais uncovered` |
| `code.no_traceability` | Code files holding a citation that reaches no requirement -- the files of the unlinked CODE nodes (test files are covered separately by `tests.uncited_file`) | warning | `[rules.format] no_traceability_severity` | no command resolves this; resolve it by hand |
| `code.unscanned_keyword_file` | A file inside a scanned directory that the ignore configuration does not exclude, that the patterns declared for its kind do not select, and that carries a *Traceability* keyword anyway -- the citation was never read | info | `[rules.severity]` | no command resolves this; resolve it by hand |
| `code.retired_references` | Code referencing requirements with retired status (Deprecated, Superseded, Rejected) | warning | `[rules.references] retired` | no command resolves this; resolve it by hand |
| `code.provisional_references` | Code referencing requirements with provisional status (Draft, Proposed) | info | `[rules.references] provisional` | no command resolves this; resolve it by hand |
| `code.aspirational_references` | Code referencing requirements with aspirational status (Roadmap, Future, Idea) | info | `[rules.references] aspirational` | no command resolves this; resolve it by hand |
<!-- /generated: check-catalog:code -->

### Test Mapping Checks (`--tests`)

<!-- generated: check-catalog:tests -->
<!-- Rendered from the program's own definitions; edits here are overwritten. Regenerate: python -m elspais.utilities.doc_tables -->

| Check | Description | Default severity | Configured by | Remedy |
| --- | --- | --- | --- | --- |
| `tests.uncited_file` | A scanned test file in which no test cites anything -- either no test functions found, or no test in the file links to any requirement (a file with at least one linked test is not flagged). Not the same population as the unlinked NODES the graph API and the MCP `get_unlinked_nodes` tool answer about | info | `[rules.severity]` | `elspais uncited` |
| `tests.results` | Test pass/fail status from JUnit XML or pytest JSON results | warning | `[rules.severity]` | `elspais failing` |
| `tests.results_stale` | Test results older than the code they cover | warning | `[rules.severity]` | `elspais checks --run-tests` |
| `tests.unmatched_results` | Results matching no known test | warning | `[rules.severity]` | `elspais -v checks --tests` |
| `tests.tested` | The `tested` coverage dimension (TEST nodes linked to assertions) | error | `[rules.severity]` | `elspais untested` |
| `tests.verified` | The `verified` (Passing) coverage dimension | error | `[rules.severity]` | `elspais failing` |
| `tests.lcov_tested` | Line-coverage-derived credit keyed by assertion label | error | `[rules.severity]` | no command resolves this; resolve it by hand |
| `tests.uncredited_evidence` | Evidence naming an assertion its dimension does not count -- a test on an assertion nothing implements -- so it reaches no coverage figure | error | `[rules.coverage] uncredited_evidence` | `elspais -v checks --tests` |
| `tests.external` | A test that failed and reaches no requirement, so nobody will find the failure through the spec | warning | `[rules.coverage] external_test_failure` | `elspais failing` |
| `tests.unbound_citation` | A citation in a scanned test file that found no test to attach to -- it names assertions but sits where no test was declared, so no result can ever reach it; it contributes no coverage and is reported here instead | warning | `[rules.severity]` | no command resolves this; resolve it by hand |
| `tests.ingestion_fault` | An artifact ingestion could not read at all -- a results or coverage report that would not parse, one in a format no reporter reads, a reporter name that matches none, a results pattern that matched nothing, a coverage file that is not there, or a target whose working directory leaves the repository. What went unread is absent from every figure, and absence reads as a zero | warning | `[rules.severity]` | no command resolves this; resolve it by hand |
| `tests.partial_read` | An artifact ingestion read only in part -- a coverage report whose per-file re-analysis failed, so the lines it recorded as executed are known but the totals are not. Those files are left out of any line-coverage figure rather than counted at their executed size, and this says how many | info | `[rules.severity]` | no command resolves this; resolve it by hand |
| `tests.unrunnable_file` | A scanned test file that no configured test target can execute, so what it verifies can raise the Tested figure while Passing has no way to move | info | `[rules.severity]` | no command resolves this; resolve it by hand |
| `tests.retired_references` | Tests referencing requirements with retired status (Deprecated, Superseded, Rejected) | warning | `[rules.references] retired` | no command resolves this; resolve it by hand |
| `tests.provisional_references` | Tests referencing requirements with provisional status (Draft, Proposed) | info | `[rules.references] provisional` | no command resolves this; resolve it by hand |
| `tests.aspirational_references` | Tests referencing requirements with aspirational status (Roadmap, Future, Idea) | info | `[rules.references] aspirational` | no command resolves this; resolve it by hand |
<!-- /generated: check-catalog:tests -->

#### Reference Status Checks — Retired, Provisional, Aspirational

The `*.retired_references`, `*.provisional_references`, and
`*.aspirational_references` checks (for both `code` and `tests` categories)
flag traceability links that target requirements whose status suggests the
reference may be stale or premature:

- **Retired** (Deprecated, Superseded, Rejected) — the requirement is no
  longer valid; code or tests referencing it may need cleanup.
- **Provisional** (Draft, Proposed) — the requirement is not yet approved;
  references are premature but may be intentional during development.
- **Aspirational** (Roadmap, Future, Idea) — the requirement is planned
  but not committed; references are informational.

### `--treat-active` interaction

Naming a status with `--treat-active` promotes those requirements to
active-like status, so `code.provisional_references` and
`tests.provisional_references` stop flagging references to them —
`--treat-active Draft` silences the Draft references specifically.

**Configuration** — adjust severity via `[rules.references]` in `.elspais.toml`:

```toml
[rules.references]
retired = "warning"            # off | info | warning | error
provisional = "info"           # off | info | warning | error
aspirational = "info"          # off | info | warning | error
malformed = "warning"          # off | info | warning | error
unknown_namespace = "info"     # off | info | warning | error
unknown_requirement = "error"  # off | info | warning | error
unknown_assertion = "error"    # off | info | warning | error
forbidden = "error"            # off | info | warning | error
keyword_form = "warning"       # off | info | warning | error
identifier_form = "warning"    # off | info | warning | error
undeclared = "warning"         # off | info | warning | error
```

### Reference Checks (`--spec`)

A reference check reports on what a citation SAYS, wherever it is written — a
spec metadata line, a code comment, a test comment. The five below are ordered
by how far reading the reference got; the two after them are style findings
that never cost the relationship they name.

<!-- generated: check-catalog:references -->
<!-- Rendered from the program's own definitions; edits here are overwritten. Regenerate: python -m elspais.utilities.doc_tables -->

| Check | Description | Default severity | Configured by | Remedy |
| --- | --- | --- | --- | --- |
| `references.malformed` | No reference fails to read as a reference at all | warning | `[rules.references] malformed` | `elspais unresolved` |
| `references.unknown_namespace` | No reference names a target no configured repository claims | info | `[rules.references] unknown_namespace` | `elspais unresolved` |
| `references.unknown_requirement` | No claimed reference names a requirement that repository does not hold | error | `[rules.references] unknown_requirement` | `elspais unresolved` |
| `references.unknown_assertion` | No claimed reference names an assertion label its requirement lacks | error | `[rules.references] unknown_assertion` | `elspais unresolved` |
| `references.forbidden` | No reference that reads and resolves has its relationship refused — a keyword the file kind may not use, or a target the list names twice | error | `[rules.references] forbidden` | `elspais unresolved` |
| `references.keyword_form` | No keyword is written in a non-canonical case, spacing, or markdown-emphasis form (never costs the edge its keyword introduces) | warning | `[rules.references] keyword_form` | `elspais -v checks --spec` |
| `references.identifier_form` | No reference is spelled in a non-canonical form the configuration admits (never costs the relationship it names) | warning | `[rules.references] identifier_form` | `elspais -v checks --spec` |
| `references.undeclared` | No comment opens with an identifier that no keyword introduces (produces no relationship) | warning | `[rules.references] undeclared` | `elspais -v checks --spec` |
<!-- /generated: check-catalog:references -->

#### The Five Reference Checks — How Far Reading Got

A reference is recognised by *where* it is written, not by what it names: a
*Traceability* keyword opening a comment, or opening a metadata line in a
spec file, introduces a reference, and everything after the colon is its
target. Reading that target proceeds through stages, and a fault is
reported under exactly one check — the furthest stage reading it reached,
never a later one:

| Check | What reading found |
|---|---|
| `references.malformed` | The text never read as a reference at all (bad syntax, wrong separator, an empty item). |
| `references.unknown_namespace` | The text reads, but no configured repository's identifier grammar claims it. |
| `references.unknown_requirement` | A repository claims the identifier format, but holds no such requirement. |
| `references.unknown_assertion` | The requirement exists, but not that assertion label. |
| `references.forbidden` | The reference reads and resolves, but the relationship it declares is refused — its keyword is not valid for this file kind (e.g. `Refines:` in a code file), or the list names the same target more than once. |

A target no repository claims is by definition outside every configured ID
pattern, so its shape says nothing about whether the author meant a
reference — only its position can, which is why documentation may show a
keyword inside backticks or a fenced block without invoking one.

Two consequences worth knowing. A section banner such as
`# Verifies: how the parser handles blank lines` is a reference to a target
named "how the parser handles blank lines" — reword it or move the keyword
off the front of the comment. And a reference whose target lives in a repo
you have not configured is reported under `references.unknown_namespace`
rather than discarded, so a federation assembled from a partial checkout
still tells you what it could not read. Set `unknown_namespace = "off"` to
silence expected cross-repository references entirely — the check then reports
as skipped and lists nothing. To keep seeing them without failing the run, set
`"info"` instead.

A keyword written in a non-canonical case, spacing, or markdown-emphasis
form is reported separately, under `references.keyword_form` — a style
finding never costs the edge its keyword introduces, so it does not join a
check that counts references that failed to bind. `references.identifier_form`
says the same thing about the referent: a reference spelled in a form the
configuration admits but that is not the canonical one — different case,
different padding, an alias — produces the relationship it names, and its
spelling is reported rather than charged to it. The report names the file and
the line so the spelling can be brought into line by hand; nothing rewrites a
code or test annotation for you.

#### `references.undeclared` — A Relationship Meant, Not Declared

Opening a comment with an identifier and then explaining, in prose, why the
code below answers to it — `# REQ-d00252-F: covered through the associate,
so not a gap` — is a natural way to write, and an author doing it means the
relationship. Nothing about the line is malformed, so reporting it as a
malformed reference would name a defect the author does not have. It is
reported under `references.undeclared` instead, with the message that
saying it with a keyword would make it count.

It produces no relationship. An informal citation is evidence of intent,
and inferring an edge from intent would credit a requirement nobody
declared. Two comments are excluded, because neither is a citation: one a
*Traceability* keyword introduces is already a declaration, and one
continuing a reference list is an item of that list.

Where prose citations are house style, set `undeclared = "info"` — the
findings still appear, and the run does not fail on them. Set `"off"` instead
to stop reporting them altogether.

**Follow-up:** Run `elspais unresolved` to list every unresolved reference,
across every class.

### UAT Checks

UAT (User Acceptance Testing) checks run automatically with `--tests` and report
coverage and results from user journey validation.

<!-- generated: check-catalog:uat -->
<!-- Rendered from the program's own definitions; edits here are overwritten. Regenerate: python -m elspais.utilities.doc_tables -->

| Check | Description | Default severity | Configured by | Remedy |
| --- | --- | --- | --- | --- |
| `uat.results` | Journey pass/fail status from a CSV results file | warning | `[rules.severity]` | `elspais failing` |
| `uat.uat_coverage` | The `uat_coverage` (UAT Covered) coverage dimension, counted over requirements at levels that set `expects_validation = true`. Levels without `expects_validation` are not counted; when no level expects validation the check passes trivially. Which requirements are unvalidated is reported by `uat.unvalidated` | error | `[rules.severity]` | `elspais unvalidated` |
| `uat.unvalidated` | A requirement at a level that sets `expects_validation = true` that no USER_JOURNEY validates, or that a journey names without naming its assertions -- reported by name, on the same verdict `elspais unvalidated` reaches | warning | `[rules.severity]` | `elspais unvalidated` |
| `uat.uat_verified` | The `uat_verified` (UAT Passed) coverage dimension | error | `[rules.severity]` | `elspais failing` |
<!-- /generated: check-catalog:uat -->

### Terms Checks (`--terms`)

<!-- generated: check-catalog:terms -->
<!-- Rendered from the program's own definitions; edits here are overwritten. Regenerate: python -m elspais.utilities.doc_tables -->

| Check | Description | Default severity | Configured by | Remedy |
| --- | --- | --- | --- | --- |
| `terms.duplicates` | Same term defined in two locations | error | `[terms.severity] duplicate` | `elspais -v checks --terms` |
| `terms.undefined` | Bold/italic token with no matching definition | warning | `[terms.severity] undefined` | `elspais glossary` |
| `terms.unmarked` | Indexed term used without markup or with wrong markup | warning | `[terms.severity] unmarked` | `elspais -v checks --terms` |
| `terms.unused` | Defined term with zero references | warning | `[terms.severity] unused` | `elspais -v checks --terms` |
| `terms.bad_definition` | Term with blank or trivial definition text | error | `[terms.severity] bad_definition` | `elspais -v checks --terms` |
| `terms.collection_empty` | Collection term with no references | warning | `[terms.severity] collection_empty` | `elspais -v checks --terms` |
| `terms.canonical_form` | Term references must use canonical casing and markup | warning | `[terms.severity] canonical_form` | `elspais fix` |
<!-- /generated: check-catalog:terms -->

Each value is one of the four severities. See `elspais docs terms` for full configuration details.

#### UAT Results CSV Format

Create a `uat-results.csv` file in the repository root (or configure the path
via `scanning.journey.results_file` in `.elspais.toml`):

```csv
journey_id,status
JNY-Onboard-01,pass
JNY-Onboard-02,pass
JNY-Deploy-01,fail
JNY-Deploy-02,skip
```

**Columns:**

| Column | Required | Values |
|--------|----------|--------|
| `journey_id` | Yes | The journey ID (e.g., `JNY-Onboard-01`) |
| `status` | Yes | `pass`/`passed`, `fail`/`failed`, or `skip`/`skipped` |

The file is a standard CSV with a header row. When present, `elspais checks`
reports pass/fail/skip counts and flags failing journeys.

**Configuration:**

```toml
[scanning.journey]
results_file = "uat-results.csv"   # default
```

## Coverage Dimensions

Coverage checks report six **dimensions**, each tracking how thoroughly
requirements are implemented, tested, and validated. The five *Assertion*
dimensions are each read on four independent **measures**, crossing what a
citation named with where the evidence sits:

- **cited by name here** (immediate direct) — a citation on this requirement named the assertion
- **whole-requirement** (immediate indirect) — a citation on this requirement named the requirement, implying every assertion
- **conducted direct** (rolled direct) — a refining requirement's assertion-naming evidence, carried up a `Refines:` chain
- **conducted indirect** (rolled indirect) — a refining requirement's whole-requirement evidence, carried up the same chain

None is derived from another, and they overlap: an assertion can be covered on
several at once. Beside them sits the **total** — each assertion counted once,
at the greatest of its four measures — which is what a reporting surface
headlines. Because the measures overlap, they do not sum to the total.

The sixth dimension, `code_tested`, is measured in LINES rather than
assertions and carries none of the four measures. It is reported in its own
right and never folded into the *Assertion* dimensions (REQ-d00254-B).

### The six dimensions

| Dimension | What it measures |
|-----------|-----------------|
| `implemented` | CODE or child-REQ covers assertions |
| `tested` | TEST nodes linked to assertions |
| `verified` | TEST results PASSING for those assertions |
| `uat_coverage` | USER_JOURNEY validates assertions |
| `uat_verified` | USER_JOURNEY results PASSING for those assertions |
| `code_tested` | Implementation source lines hit by line-coverage data |

### How coverage sources map to dimensions

The system classifies *how specifically* coverage was claimed:

| Source | When | Measure credited |
|--------|------|------------------|
| `DIRECT` | TEST or CODE names specific assertions (`REQ-xxx-A`) | `implemented` / `tested` immediate direct |
| `EXPLICIT` | Child REQ names specific assertions (`Implements: REQ-xxx-A+B`) | `implemented` immediate direct |
| `INFERRED` | Child REQ targets whole parent (`Implements: REQ-xxx`) | `implemented` immediate indirect |
| `INDIRECT` | TEST targets whole REQ (no assertion labels) | `tested` immediate indirect |
| `UAT_EXPLICIT` | JNY names specific assertions (`Validates: REQ-xxx-A`) | `uat_coverage` immediate direct |
| `UAT_INFERRED` | JNY targets whole REQ (`Validates: REQ-xxx`) | `uat_coverage` immediate indirect |

Every source above is *immediate*: the evidence is attached to the requirement
that carries the assertion. The two *rolled* measures hold value conducted up a
`Refines:` chain from a refining requirement, and nothing else.

### Roll-up: how RESULT nodes contribute

RESULT nodes do **not** add coverage — they add **verification**. A RESULT
inherits the assertion targets from its parent TEST's edge:

```text
REQ (assertion "A")
  |
  +-- VERIFIES (assertion_targets=["A"]) --> TEST
                                               |
                                               +-- RESULT (status="passed")
```

What gets credited:

- `tested` immediate direct += "A" — from the VERIFIES edge (assertion-targeted)
- `verified` immediate direct += "A" — from the RESULT with `status=passed`

If the RESULT is absent or failing, `tested` still gets credit but `verified`
does not. The same pattern applies to UAT: a journey RESULT populates
`uat_verified` but not `uat_coverage`.

### Dimension tiers

Each dimension resolves to a **tier** that drives severity and UI color:

| Tier | Meaning |
|------|---------|
| `missing` | No coverage at all (grey/neutral when the denominator is empty; a red gap only when in-scope) |
| `partial` | Some assertions covered, not all |
| `full` | All assertions covered |
| `failing` | Coverage exists but results are failing |

Tier, per-assertion standing, and bucket share this one vocabulary
(`full` / `partial` / `failing` / `missing`).

**Relative denominators.** `Tested` and `Passing` are measured against their
*own* denominator, not the whole spec: `Tested` counts tested / **implemented**
assertions, and `Passing` counts passing / **tested** assertions. An empty
denominator (nothing implemented, or nothing tested) resolves to `missing` at
neutral severity (grey) rather than a red gap -- you cannot test what is not
built. A failing in-denominator label is always `failing` (red), regardless of
the fraction.

**Which evidence credits a tier.** A tier is scored on the total measure: each
assertion counted once, at the greatest of its four measures -- what a citation
named here, what whole-requirement evidence reached, and what `Refines:`
conduction carried up in each of those two shapes. Work-list surfaces (`gaps`,
`untested`, `unvalidated`) answer a different question and so read a different
measure: they count only "cited by name here" -- evidence that named the
assertion, attached to it -- so they can report work a tier calls done.

**Evidence outside the denominator.** Measuring over the prior link means
evidence can name an assertion the dimension does not count -- a test on an
assertion nothing implements. It credits nothing, and `tests.uncredited_evidence`
reports it rather than letting it vanish into a denominator it was never in:
the assertion named, the dimension not reached, and the file and line the
evidence was written on. Where the evidence carries a verdict of its own the
finding says so -- "A test names", "A passing test names" and "A failing test
names" are three different reports, and a test that failed against an assertion
nothing implements is the sharpest form of the defect. It is an `error` by default (`[rules.coverage]
uncredited_evidence`) because the condition has only two explanations and both
are defects -- a missing `Implements:` reference, or a test aimed at an
assertion it does not exercise. Only assertion-targeted evidence names an
assertion: a whole-requirement `Verifies: REQ-xxx` names the requirement, so it
is never reported against an individual assertion — it is reported against the
requirement, and only where the dimension counts no assertion of it at all,
which is one finding rather than one per assertion. What the dimension counts
is read from the same definition the coverage tier uses, so a finding and the
figure beside it cannot disagree.

### `code_tested` — line coverage

`code_tested` is not a coverage dimension at all: it counts **source lines**
rather than assertions, and carries its own three figures rather than the four
measures. It cross-references implementation line ranges (from `Implements:`
edges to CODE nodes) against file-level line-coverage data (LCOV or
coverage.json).

- `total_lines` -- implementation lines attributed to the requirement.
- `covered_lines` -- lines any coverage run executed, whichever test did it.
- `attributed_lines` -- lines a run executed *and* whose recorded context
  names a test that verifies the requirement.

`attributed_lines` counts implementation lines whose recorded
test **context** names a test that `Verifies:` the requirement (Python only,
via coverage.py's per-test dynamic contexts). A `coverage.json` produced with
pytest-cov's `--cov-context=test` *and* `show_contexts = true` under
`[tool.coverage.json]` carries a per-line `contexts` array of strings like
`"tests/test_x.py::TestClass::test_method|run"` (or `"...::test_func|run"`
with no class). Only the `|run` phase credits direct attribution --
`|setup`/`|teardown` fixture-phase execution is not evidence the test itself
exercised the line. Coverage formats without a `contexts` map (LCOV, or
coverage.json exported without `show_contexts`) record no attribution at all,
and every surface renders `n/a` rather than a misleading `0`.

Do not set `[tool.coverage.run] dynamic_context = "test_function"` alongside
`--cov-context=test`: that is coverage.py's own (incompatible) context
switcher and silently overrides pytest-cov's nodeid-shaped contexts. See
`elspais docs test-targets` for the full recipe and gotcha.

## Output Formats

### Text Output (default)

```
✓ CONFIG (6 passed, 1 skipped)
----------------------------------------
  ✓ config.exists: Config file found: .elspais.toml
  ✓ config.syntax: TOML syntax is valid
  ...

✓ TESTS (1 passed, 2 skipped)
----------------------------------------
  ~ tests.tested: 82/87 requirements have test coverage (94.3%)
  ✓ tests.uncited_file: All test files have traceability markers
  ~ tests.results: No test results found

✓ UAT (2 skipped)
----------------------------------------
  ~ uat.uat_coverage: 25/87 requirements have UAT coverage (28.7%)
  ~ uat.results: No UAT results file found (uat-results.csv)

========================================
HEALTHY: 21/21 checks passed, 8 skipped
========================================
```

### JSON Output (`--format json`)

```json
{
  "healthy": true,
  "summary": {
    "passed": 12,
    "failed": 0,
    "warnings": 0
  },
  "checks": [
    {
      "name": "config.exists",
      "passed": true,
      "message": "Config file found: .elspais.toml",
      "category": "config",
      "severity": "error",
      "details": {"path": ".elspais.toml"}
    }
  ]
}
```

### JUnit XML Output (`--format junit`)

Produces JUnit XML that CI systems (GitHub Actions, Jenkins, GitLab CI) can ingest natively for test reporting dashboards.

**Mapping:**

| Health Concept | JUnit Element |
|----------------|---------------|
| Category (config, spec, code, tests) | `<testsuite>` |
| Individual check | `<testcase>` with `classname="elspais.health.{category}"` |
| Passing check | Empty `<testcase/>` |
| Failed check (error severity) | `<testcase>` with `<failure>` element |
| Failed check (warning severity) | `<testcase>` with `<system-err>` prefixed `WARNING:` |
| Info message | `<testcase>` with `<system-out>` |
| Narrowed report | extra `<testsuite name="elspais.report">` carrying the run's verdict and the narrowing |

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="config" tests="6" failures="0" errors="0">
    <testcase classname="elspais.health.config" name="config.exists"/>
    <testcase classname="elspais.health.config" name="config.syntax"/>
  </testsuite>
  <testsuite name="spec" tests="6" failures="1" errors="1">
    <testcase classname="elspais.health.spec" name="spec.parseable"/>
    <testcase classname="elspais.health.spec" name="spec.implements_resolve">
      <failure message="2 unresolved Implements references">
        REQ-d99999 referenced by REQ-d00010
      </failure>
    </testcase>
  </testsuite>
</testsuites>
```

**CI Integration Example (GitHub Actions):**

```yaml
- name: Traceability verification (JUnit)
  run: elspais checks --format junit -o health-results.xml

- name: Publish test results
  uses: dorny/test-reporter@v1
  if: always()
  with:
    name: elspais checks
    path: health-results.xml
    reporter: java-junit
```

### SARIF Output (`--format sarif`)

Produces [SARIF v2.1.0](https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html) JSON for GitHub Code Scanning and other static analysis dashboards. Only failing checks are emitted as results; passing checks are omitted.

**Mapping:**

| Health Concept | SARIF Element |
|----------------|---------------|
| Unique failing check name | `reportingDescriptor` in `tool.driver.rules[]` |
| Individual `HealthFinding` | `result` in `results[]` |
| Severity `error` | `level: "error"` |
| Severity `warning` | `level: "warning"` |
| Severity `info` | `level: "note"` |
| Finding with `file_path` | `physicalLocation` with `artifactLocation.uri` |
| Finding with `line` | `region.startLine` |
| Coverage stats | `run.properties` (`passed`, `failed`, `warnings`) |
| Narrowed report | `run.properties.narrowing` (the sentence) and `run.properties.filter` (the values and the extent) |

```json
{
  "$schema": "https://docs.oasis-open.org/sarif/sarif/v2.1.0/cos02/schemas/sarif-schema-2.1.0.json",
  "version": "2.1.0",
  "runs": [
    {
      "tool": {
        "driver": {
          "name": "elspais",
          "informationUri": "https://github.com/anspar-org/elspais",
          "rules": [
            {
              "id": "spec.implements_resolve",
              "shortDescription": {
                "text": "All Implements references resolve"
              }
            }
          ]
        }
      },
      "results": [
        {
          "ruleId": "spec.implements_resolve",
          "level": "error",
          "message": {
            "text": "REQ-d99999 referenced by REQ-d00010"
          },
          "locations": [
            {
              "physicalLocation": {
                "artifactLocation": {
                  "uri": "spec/dev-spec.md"
                },
                "region": {
                  "startLine": 42
                }
              }
            }
          ]
        }
      ],
      "properties": {
        "passed": 11,
        "failed": 1,
        "warnings": 0
      }
    }
  ]
}
```

**CI Integration Example (GitHub Code Scanning):**

```yaml
- name: Traceability verification (SARIF)
  run: elspais checks --format sarif -o health-results.sarif
  continue-on-error: true

- name: Upload SARIF
  uses: github/codeql-action/upload-sarif@v3
  if: always()
  with:
    sarif_file: health-results.sarif
    category: elspais-health
```

## Findings

A check reports a verdict; its findings are what it found. Every finding
carries the same four things whatever format it is rendered in:

| It carries | Which is |
|------------|----------|
| its identity | the check it belongs to, the node it is about, and the diagnostic codes it reached |
| its severity | the severity its check carries, decided by the project |
| its location | the file, and the line within that file, where the finding has one |
| its remedy | the command that resolves it — or a statement that no command does |

### Seeing them

The default report is one line per check: a verdict and a count. `-v` expands
each failing check into the findings behind it.

```text
⚠ REFERENCES (6 passed, 1 failed)
----------------------------------------
  ⚠ references.identifier_form: 2 reference(s) spelled in a non-canonical form
      remedy: elspais -v checks --spec
      - spec/dev-cli.md:247: req-d1 -- spelled in a form the configuration admits...
        node=REQ-d00285 repo=core
      - spec/ops-mcp.md:88: REQ-O00076 -- spelled in a form the configuration admits...
        node=REQ-o00076 repo=core
```

A passing check's findings are a separate request: `--include-passing-details`
shows them, and `-v` on its own does not.

Every format carries the findings. `--format json` and `--format sarif` carry
them as values; `--format markdown` renders them as a nested list; `--format
junit` puts them, with the remedy, in each failure body.

### Narrowing them

Five flags select among findings. They compose with each other and with the
scope flags above.

| Flag | Selects |
|------|---------|
| `--severity error warning` | findings whose check carries one of these severities (`error`, `warning`, `info` — a check configured `off` reports nothing to select) |
| `--category references tests` | findings in one of these check categories |
| `--check references.malformed` | findings raised by one of these checks, by name |
| `--code E_IDENTIFIER_WITH_TRAILING_TEXT` | findings carrying one of these diagnostic codes |
| `--file 'spec/*.md'` | findings located in a file matching one of these glob patterns |

Values named for one flag are alternatives; values named for different flags
are conditions met at once. So `--category references --file 'spec/*.md'`
selects the reference findings that are in a spec file, and nothing else.

`--check`, `--code` and `--file` select findings by name, so the findings they
select are rendered whether or not `-v` was given.

`--check` is what the preset listings are made of. `elspais unresolved` is
this report narrowed to the five reference checks; `elspais errors` to the
spec-file checks; `elspais uncited` to the two uncited-file checks. Each
listing prints the `--check` line that reproduces it, so what a shortcut
selected is always checkable. Because a listing IS the report, every finding
on it carries what every finding carries — the check that raised it, its
severity, its diagnostic codes, its location and its remedy.

A narrowed report says what it withheld — `showing 2 of 47 checks, 3 of 310
findings` — because a report that showed a reader some of what it found and
did not say so reads exactly like a clean run. The exit code is the whole
run's: narrowing chooses what to look at, never what the run found.

Every format says both. `--format json` carries them in a `filter` block
beside the whole run's `healthy` and `summary`. `--format sarif` carries them
in `run.properties` as `narrowing` and `filter`, beside the run's counts.
`--format junit` gains one extra `<testsuite name="elspais.report">`: its
`<properties>` state the narrowing and the run's counts, and its
`report.verdict` testcase FAILS when the run had errors, whichever checks the
reader asked to see. Without it, a document filed to CI would be read as green
whenever the narrowing happened to exclude the failing check — the exit code
that says otherwise is not something a test reporter ever sees. The
per-category `<testsuite failures=…>` counts still speak for the checks the
document actually holds.

A `--severity`, `--category` or `--check` naming something outside the tool's
vocabulary is refused (exit code 2) rather than silently selecting nothing.
`--code` and `--file` are values the estate carries rather than a fixed list,
so they are not judged that way — a code nothing raised simply selects
nothing.

One difference between a reader's narrowing and a preset listing: the exit
code above is the whole run's, because narrowing chooses what to look at. A
preset listing names the population it answers about, so its exit code is
taken over the checks it names and over nothing else — `elspais unresolved`
does not fail on a stale hash.

### Two names that were already taken

`--code` names a diagnostic code. The scope flag that used to hold that name —
"run the code reference checks only" — is `--code-checks`. Both meanings
wanted `--code`, and the one a reader types a value after won it.

The file filter is `--file` rather than `--path` because `--path` already means
something across every command: the repository root the run works from.

## Command Options

Run `elspais checks --help` for the full list of flags.  Options are
defined in `commands/args.py:ChecksArgs` — that dataclass is the single
source of truth for flag names and descriptions.

`elspais checks --run-tests` executes each configured
`[[scanning.test.targets]]` entry before evaluating checks. `--targets NAME
...` restricts `--run-tests` to a named subset (an unknown name is exit
code 2); it only affects execution here. Per-PR selectivity rendering
(`(baseline)` for carried results, `—` for no baseline) is produced by
`summary --targets` / `trace --targets`, not by `checks`. See `elspais docs
test-targets` for the full model.

## Error Drill-Down

When `spec.format_rules` or `spec.no_assertions` fails, `elspais checks` directs
you to `elspais errors` for requirement-level detail:

```bash
elspais errors                     # Show all spec errors
elspais errors --format markdown   # Markdown table output
elspais errors --format json       # JSON output
elspais errors -o errors.txt       # Write to file
```

The drill-down weighs every requirement whatever its status, so it accounts for
exactly what the two checks above counted. It takes no status option: format
rules bind a requirement whatever its status, so there is no baseline to widen.

**Example output (text format):**

```text
FORMAT ERRORS (2):
  REQ-d00003           missing_body: Requirement has no body text  spec/dev-spec.md:45
  REQ-p00002           missing_title: Requirement has no title     spec/prd-spec.md:12

NO ASSERTIONS (2):
  REQ-o00005           no_assertions: No assertions — not testable  spec/ops-spec.md:30
  REQ-p00010           no_assertions: No assertions — not testable  spec/prd-spec.md:88
```

**Options:**

  `--format {text,markdown,json}`  Output format (default: text)
  `-o, --output PATH`              Write output to file instead of stdout

**Performance:** Uses daemon-first execution like other drill-down commands.

## Gap Listings

Use standalone gap commands or compose them with checks:

```bash
elspais gaps                      # All gaps
elspais uncovered                 # Requirements without code coverage
elspais untested                  # Requirements without test coverage
elspais unvalidated               # Requirements without UAT coverage
elspais failing                   # Requirements with failing results
elspais checks gaps               # Checklist + all gaps
elspais checks untested           # Checklist + untested gaps
```

Gap commands support `--format text` (default), `--format markdown`, and `--format json`.

An assertion listed in a gap can carry a `— N% direct` annotation
(text/markdown) or a `fraction` field (json). A gap is decided on one measure:
a citation named the assertion and the evidence is attached to it. A fraction
of `0` (no annotation) means nothing names it at all; `0 < fraction < 1` means
the evidence naming it is itself partial, still a gap but distinguishable from
zero. Whole-requirement evidence and coverage conducted up a `Refines:` chain
are counted by the summary and viewer figures but never close a gap here (see
`elspais docs graph-model` for the conduction model).

## Prospective Reports (What-If Analysis)

By default, `checks` and `gaps` only include requirements with **Active** status
in coverage calculations. Requirements with Draft, Proposed, or other provisional
statuses are excluded.

Use `--treat-active` to count additional statuses as committed and see what
traceability gaps would exist if those requirements were promoted to Active:

```bash
# Show gaps assuming all Draft requirements were active
elspais gaps --treat-active Draft

# Show checks counting both Draft and Proposed
elspais checks --treat-active Draft Proposed

# Combine with gap subcommands
elspais untested --treat-active Draft
```

This is useful for planning: before promoting a batch of Draft requirements,
run a prospective report to see which ones still need code references, tests,
or UAT validation.

A promoted status is counted in the coverage numerator and denominator and is
correspondingly absent from the trailing `[... excluded]` note — the counts and
the note always agree. Under the hood `--treat-active <S>` is an overlay that
forces `expects_implementation = true` for `<S>`, so it is exactly equivalent to
setting `[statuses.<S>] expects_implementation = true` in `.elspais.toml` for the
duration of the run (and composes with any such config already present).

`--treat-active` accepts any configured status name (case-insensitive; the name
is title-cased before matching). See `elspais docs config` for how status roles
are configured.

## Exit Codes

Exit codes use a bitfield so composed reports indicate which sections failed:

| Bit | Value | Section |
|-----|-------|---------|
| 0 | 1 | checks |
| 1 | 2 | summary (reserved) |
| 2 | 4 | trace (reserved) |
| 3 | 8 | changed (reserved) |
| 4 | 16 | gaps (reserved) |

Composed reports OR the bits together. Currently only `checks` returns non-zero (when checks fail). Use `--lenient` to suppress warnings-only failures.

## Severity Levels

- **off**: The condition is not reported here — the check shows as skipped and
  produces no findings
- **info**: Informational (e.g., coverage statistics); never a failure
- **warning**: Advisory issue (does not affect exit code)
- **error**: Configuration or validation issue that causes non-zero exit

These four are the whole vocabulary; a configuration naming anything else is
refused when it is read. See *Check Severity* above for where each check's
severity is set.

## Use Cases

### CI/CD Pipeline Check

```bash
# Fail pipeline if traceability verification fails
elspais checks || exit 1
```

### Quick Config Validation

```bash
# Just check config and environment setup
elspais doctor
```

### Debugging Reference Issues

```bash
# Verbose output for debugging
elspais -v checks --spec
```

### JSON Processing

```bash
# Get failed checks in CI
elspais checks --format json | jq '.checks | map(select(.passed == false))'
```

## Troubleshooting

### "No requirements found"

This usually means:
- The spec directory doesn't exist
- No `.md` files in the spec directory
- Files don't contain valid requirement format

Run with verbose to see details:
```bash
elspais -v checks --spec
```

### "Unresolved Implements references"

A requirement references another that doesn't exist:
1. Check for typos in the requirement ID
2. Ensure the parent requirement exists
3. Check if using assertion syntax (e.g., `REQ-xxx-A`)

### "TOML syntax error"

Your `.elspais.toml` has invalid syntax:
1. Check for unclosed quotes or brackets
2. Validate with a TOML linter
3. Compare against the default config structure
