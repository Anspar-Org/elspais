# Core Product Requirements

# REQ-p00001: Requirements Management Tool

**Level**: prd | **Status**: Active | **Implements**: -

## Rationale

Software projects—especially those subject to regulatory oversight (medical devices, aerospace, automotive)—require formal requirements that are validated, traceable, and auditable. Traditional requirements management tools are heavyweight, expensive, and poorly integrated with modern development workflows.

elspais addresses this gap by providing a lightweight, file-based requirements management system that:

- Lives alongside code in version control
- Uses plain Markdown for human readability
- Validates structure and relationships automatically
- Integrates with CI/CD pipelines
- Supports AI-assisted workflows

The name derives from Terry Pratchett's "L-Space"—the dimension where all libraries connect through accumulated knowledge.

## Assertions

A. The tool SHALL provide command-line validation of requirement documents stored as Markdown files.

B. The tool SHALL generate *Traceability* matrices showing requirement relationships.

C. The tool SHALL detect changes to requirements using content hashing and git integration.

D. [DEPRECATED]

## Changelog

- 2026-07-31 | 2d10975a | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-04-23 | ce489de6 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Requirements Management Tool* | **Hash**: 2d10975a
---

# REQ-p00002: Requirements Validation

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001

## Rationale

Requirements documents are only useful if they follow a consistent structure. Inconsistent formatting, broken links between requirements, and outdated content hashes undermine the reliability of the requirements baseline.

Automated validation catches these issues early, before they propagate into design documents, test plans, and regulatory submissions. Validation must be fast enough to run on every commit and flexible enough to accommodate different organizational conventions.

The validation system enforces:

- **Format compliance**: Headers, metadata, *Assertion* sections, and hash footers follow the canonical grammar
- **Hierarchy integrity**: Child requirements correctly reference parents; no circular dependencies
- **Traceability completeness**: All requirements are reachable from root-level product requirements
- **Content freshness**: Hashes match current content; changes are intentional

**Assertion-level parsing directives.** *Assertion* text that begins with a non-letter character (such as `<`, `[`, or `{`) introduces a parsing directive scoped to that *Assertion*. Today's expected form is a bare directive (`F. <RETIRED>`), where a missing closing delimiter is tolerable; future directives may prefix real text (`G. [CRITICAL] Don't push the red button`), which is why the closing delimiter matters — the enclosure is what separates the directive from the *Assertion*'s remaining content. Assertion E states the invariant cleanly; parsing leniency for an unclosed bare directive is mechanism latitude, not an obligation. A directive the tool does not recognize must not silently degrade to ordinary *Assertion* text: content admitted into the graph under a meaning the author did not intend is the same silent-admission defect REQ-p00015-A guards against for unadmitted requirement content — the reporting principle is cited here, not restated. The semantics of individual directives (such as RETIRED) are the concern of the requirements governing the affected accounting, not of this format requirement.

## Assertions

A. The tool SHALL validate requirement format against configurable patterns and rules.

B. The tool SHALL detect and report hierarchy violations including circular dependencies and orphaned requirements.

C. The tool SHALL verify content hashes match requirement body text.

D. The tool SHALL accept configuration of user journey identifier patterns with capabilities equivalent to those it accepts for requirement identifier patterns.

E. When an *Assertion*'s text begins with a non-letter opening character that has a matching closing counterpart, the tool SHALL parse the text enclosed by the opening character and its matching closer as a parsing directive, with any text following the closer constituting the *Assertion*'s content.

F. If an *Assertion* carries a parsing directive the tool does not recognize, then the tool SHALL report the unrecognized directive and its location rather than treating the directive as ordinary *Assertion* text.

G. The tool SHALL form journey-step references from the journey identifier and the step designator using the separator rules configured for *Assertion* references.

## Changelog

- 2026-08-02 | c8440f64 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-02 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-47: journey-step references use the configured assertion-separator machinery (G) — one reference grammar for assertions and steps
- 2026-07-31 | 03a4a779 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-47: author assertion-level parsing directive grammar (E) and unknown-directive reporting (F)
- 2026-07-31 | d9f87a2a | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-26: journey identifiers configurable equivalently to requirement identifiers (D)
- 2026-07-31 | b29ef9b6 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-03-30 | e8f0e4eb | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms

*End* *Requirements Validation* | **Hash**: c8440f64
---

# REQ-p00003: Traceability Matrix Generation

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001

## Rationale

Regulatory submissions and internal reviews require evidence that high-level product requirements flow down to detailed specifications and test coverage. A *Traceability* matrix provides this view—showing which detailed requirements implement which product requirements, and which tests verify which specifications.

Manual maintenance of *Traceability* matrices is error-prone and quickly becomes stale. Automated generation from the `Implements:` metadata in requirement documents ensures the matrix always reflects the current state of the requirements baseline.

Multiple output formats serve different audiences:

- **Markdown**: Embeddable in documentation
- **HTML**: Interactive viewing with clickable links
- **CSV**: Import into spreadsheets or compliance tools

## Assertions

A. The tool SHALL generate *Traceability* matrices in Markdown, HTML, and CSV formats.

B. The tool SHALL derive *Traceability* from `Implements:` metadata without manual matrix maintenance.

## Changelog

- 2026-07-31 | 3121ad66 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-04-23 | 6a3a9426 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Traceability Matrix Generation* | **Hash**: 3121ad66
---

# REQ-p00004: Change Detection and Auditability

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001

## Rationale

Requirements change over time. Regulators and auditors need to know what changed, when, and whether downstream artifacts (tests, code, documentation) have been updated accordingly.

elspais provides two complementary change detection mechanisms:

- **Content hashing**: A SHA-256 hash of each requirement's body is stored in the document footer. When the hash no longer matches the content, the requirement has changed and downstream artifacts may need review.
- **Git integration**: The tool detects uncommitted changes, changes relative to the main branch, and requirements that have moved between files.

Together, these mechanisms support:

- Pre-commit validation (catch accidental changes)
- Pull request review (see exactly what requirements changed)
- Audit trails (link requirement changes to commits)

**Dependency-change review.** A requirement's references make it dependent on content it does not own: an `Implements:` or `Refines:` target, a `Satisfies:` template subtree, an `Integrates:` target in an associate repository. When that content changes, the referencing requirement's claim may no longer hold, so the requirement is flagged for review at the granularity its reference declares — a reference naming an assertion is sensitive to that assertion alone; a reference naming a whole requirement is sensitive to the requirement. A review flag records a human obligation: only an explicit review action discharges it. Automated fixing (hash regeneration, `elspais fix`) never discharges one — a flag the tool can acknowledge to itself is noise, not audit evidence. And when the referenced source cannot be consulted at all (an associate repository not checked out, for example), the honest verdict is "cannot verify", never "unchanged"; treating absence as stability is the same silent-omission defect REQ-p00015 guards against in reporting. One candidate mechanism (proposed, not obligated): store beside each reference a bounded record of the target's content hash plus a one-level subtree summary hash, compared at build time. Assertion G formerly stated this obligation for `Satisfies:` references only; assertion K generalizes it to all reference kinds, and G is superseded so a single obligation family governs.

**Change reasons.** An audit trail answers *why* a requirement changed, not only *what* changed. Changes arrive through multiple editing surfaces; where the audit record requires a reason, every surface must be able to carry one. The obligation falls on each surface to gain the capability — never on the set of supported surfaces to shrink to those that already can.

## Assertions

A. The tool SHALL compute and verify content hashes for change detection.

B. The tool SHALL detect uncommitted and branch-relative changes to requirement files using git.

C. The tool SHALL provide a git status summary reporting current branch, main-branch detection, dirty spec files, and remote divergence state.

D. The tool SHALL create and switch to a new git branch, using stash to preserve dirty working tree changes across the switch.

E. The tool SHALL commit modified spec files and optionally push, refusing to operate on main/master branches.

F. The tool SHALL fetch and fast-forward-merge from the remote tracking branch, aborting if the merge is not fast-forwardable.

G. [Removed - flagging satisfying requirements on template-subtree change is a special case of the reference-granularity review obligation stated in assertion K; superseded so one obligation family governs dependency-change review]

H. The tool SHALL list all local and remote git branches, stripping remote prefixes and deduplicating branches that exist both locally and remotely.

I. The tool SHALL switch to an existing local or remote git branch, refusing if in-memory mutations are pending, and falling back from remote checkout to local checkout when the local branch already exists.

J. The tool SHALL re-read configuration from disk when reloading the graph, ensuring branch switches with different configurations produce correct rebuilds.

K. When the content designated by any of a requirement's references changes — the designated *Assertion* where the reference names one, the designated requirement otherwise — the tool SHALL flag the referencing requirement for review.

L. The tool SHALL clear a review flag only in response to an explicit review action acknowledging the flagged change.

M. If the source of referenced content is unavailable for comparison, then the tool SHALL report the reference as unverifiable rather than reporting it as unchanged.

N. Where the audit record requires a reason for a change, each editing surface the tool supports SHALL capture a reason from its operator and supply it with the change.

## Changelog

- 2026-07-31 | 7930cf78 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-40: author dependency-change review invariants K/L/M at reference granularity; supersede G (SATISFIES-only special case) so one obligation family governs
- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-16: author N - every supported editing surface captures and supplies a change reason when the audit record requires one
- 2026-07-31 | 9bb163a9 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-30 | bb148227 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-38: G flags satisfiers on any change within the template subtree, not just the root
- 2026-04-23 | f8ff5509 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Change Detection and Auditability* | **Hash**: 7930cf78
---

# REQ-p00013: Automated Testing

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001

## Rationale

A requirements management tool must itself be rigorously tested to maintain credibility. Unit tests verify individual components in isolation, but integration and end-to-end tests are essential to catch cross-component failures, CLI subprocess regressions, and real-world workflow breakages that mocked unit tests miss.

The testing strategy follows a pyramid:

- **Unit tests**: Fast, isolated tests for individual functions and classes
- **Integration tests**: Tests that exercise multiple components together
- **End-to-end tests**: Subprocess-based tests that invoke the CLI binary and verify real output
- **Self-validation**: The tool validates its own repository as the strongest regression test

## Assertions

A. The project SHALL maintain unit tests for all core modules with *Assertion*-linked test names.

B. The project SHALL maintain end-to-end tests that invoke the CLI as a subprocess and verify command output, exit codes, and file artifacts.

C. The project SHALL include self-validation tests that run elspais against its own repository and assert health, summary, and trace outputs are correct.

D. The project SHALL include multi-command workflow tests that verify cross-command consistency and sequential operation correctness.

E. The project SHALL include MCP protocol tests that verify tool invocation, search, cursor pagination, and mutation roundtrips via the stdio transport.

F. All tests marked `@pytest.mark.e2e` SHALL invoke the `elspais` CLI as a subprocess. Tests that call internal Python functions or submodules directly SHALL NOT be marked e2e; they are unit or integration tests.

## Changelog

- 2026-07-31 | 4318202c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-04-23 | 962216d8 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Automated Testing* | **Hash**: 4318202c
---

## REQ-p00061: Requirement Decomposition Rules

**Level**: prd | **Status**: Active | **Implements**: -

A child requirement refines a parent when it adds specificity, constraints, or commits to mechanisms or guarantees.

### Assertions

A. A child requirement that adds specificity, constraints, or commits to mechanisms or guarantees SHALL declare its parent requirement using `Implements:` or `Refines:` in its metadata block.

B. `Implements:` and `Refines:` declarations apply to requirements only; code references and test nodes use their own linkage mechanisms.

C. Multiple requirements MAY exist at the same Level each declaring a relationship to the same parent requirement.

### Changelog

- 2026-07-31 | 462c146e | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | fc1e85fe | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | fc1e85fe | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Requirement Decomposition Rules* | **Hash**: 462c146e
---

# REQ-p00080: Spec-to-PDF Compilation

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001
**Satisfies**: REQ-p00019

## Rationale

UAT documentation review requires formal PDF output with professional formatting. A single compiled document with table of contents, per-requirement page breaks, and a topic index enables offline review, regulatory submission, and stakeholder sign-off. Currently, spec files exist only as Markdown with no PDF generation pipeline.

The `elspais pdf` command compiles requirement spec files into a professional PDF using Pandoc and LaTeX. Python assembles a clean Markdown document from the *Traceability* graph; a custom LaTeX template controls formatting; Pandoc handles Markdown-to-LaTeX conversion.

The compiler declares `Satisfies:` against the REQ-p00019 anti-pattern template: a compiled document that silently drops a repository's content, substitutes a degraded rendering without disclosure, or fails without naming the missing prerequisite exhibits exactly the defect classes the template prohibits. A prerequisite-reporting obligation formerly stated here as its own assertion was removed as too narrow; the template's unactionable-failure class now carries that obligation in its general form.

## Assertions

A. The tool SHALL provide an `elspais pdf` CLI command that compiles spec files into a PDF document.

B. The assembled Markdown SHALL group requirements by level (PRD, OPS, DEV) with each level as a top-level section, and order files within each level by graph depth (root requirements first).

C. The generated PDF SHALL include an auto-generated table of contents derived from requirement headings.

D. The tool SHALL generate an alphabetized topic index with entries derived from filename words, file-level Topics lines, and requirement-level Topics lines, rendered as a Markdown section with hyperlinks.

E. The tool SHALL insert page breaks before each requirement heading to ensure each requirement starts on a new page.

F. The tool SHALL support an `--overview` flag that generates a stakeholder-oriented PDF containing only PRD-level requirements, with an optional `--max-depth` flag to limit core PRD graph depth while always including all associated-repo PRDs.

G. The PDF generator SHALL support content derived from a variety of sources and media types.

H. The PDF generator SHALL support inclusion of content from every repository of a federated graph.

I. When a referenced image or diagram cannot be located in any repository of the compiled graph, the compiler SHALL report the reference as written, the spec file declaring it, and the locations searched.

J. When a requirement's source file cannot be read from its owning repository, the compiler SHALL report the omitted file and the repository it was expected in, rather than emitting the document as though that content did not exist.

K. When referenced content was omitted from the compiled document or substituted by a degraded rendering, the completion report SHALL disclose the degradation rather than reporting unqualified success.

## Changelog

- 2026-08-07 | acc97ca9 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-07 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-31/TOOL-32: concretize the REQ-p00019 anti-pattern instance with assertions I (unresolvable asset reference reported), J (unreadable owning-repo source file reported), and K (completion report discloses degradation)
- 2026-08-01 | 01da5fa4 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: sync changelog hash
- 2026-08-01 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-47: declare satisfaction of the REQ-p00019 anti-pattern template; the removed prerequisite-reporting assertion's obligation returns via the template's unactionable-failure class
- 2026-08-01 | 01da5fa4 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | 01771861 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms, update hash
- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-35/TOOL-47 review: author compiled-output assertions G (multi-source, multi-media content) and H (federated-graph content inclusion); prerequisite-reporting assertion removed pending a general actionable-errors rule
- 2026-07-31 | 24f063f6 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-04-23 | bfc0cadf | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Spec-to-PDF Compilation* | **Hash**: acc97ca9
---

# REQ-p00015: Complete and Current Reporting

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001
**Satisfies**: REQ-p00019

## Rationale

The *Traceability* graph is an audit artifact. A graph that reports healthy while silently omitting requirements cannot serve that role: the verdict certifies completeness it does not have. Silent omission and silent staleness are the same defect told two ways — omission withholds content from an answer, staleness withholds time from it. Both let a consumer act on a picture of the requirements estate that the tool knows, or could know, to be wrong.

Observed failure shapes this requirement guards against:

- Content in a scanned file that looks like a requirement but is dropped (for example, its declared level is not configured) while every check stays healthy — so "no matches" is indistinguishable from "never admitted".
- A configured repository that fails to load and is simply absent from answers — so "no matches" is indistinguishable from "could not look".
- Derived data (coverage rollups, term and keyword indexes, change-state summaries) served mid-editing-session from sources that have since changed.
- An operation log that records a write the tool never made.
- A long-running server answering from a configuration that has since changed on disk.

This requirement declares `Satisfies:` against the REQ-p00019 anti-pattern template and concretizes its truthful-representation classes for the tool's reporting core: assertions A and C pin silent omission to the shapes observed here (unadmitted requirement-form content; an unloadable configured repository), E and G pin silent staleness (derived values; superseded configuration), B and F pin unreported non-performance and phantom success on the write path, and D pins verdict integrity to the tool's own healthy verdict. The template's error-discipline classes (actionable failure reports, no suppressed error signals) bind to this subsystem through the template instance without a tool-specific strengthening.

Interplay with existing requirements: REQ-p00004-J obliges the tool to re-read configuration from disk when reloading the graph; this requirement complements it by covering the interval between reloads — divergence must be disclosed, not silently served. REQ-p00005-E covers the configuration-time error for an invalid associate path; assertion C here covers the answer-time consequence of any load failure. REQ-p00081-D applies the same principle to workspace discovery specifically. Other spec units cite this requirement rather than restating these invariants.

## Assertions

A. When the tool encounters content that matches a requirement form but does not admit it into the graph, the tool SHALL report the excluded content and the cause of its exclusion.

B. When the tool does not apply a requested change, the tool SHALL report the unapplied change and the cause.

C. If a repository configured into the graph cannot be loaded, then the tool SHALL report the missing repository and the cause alongside every answer computed over the reduced graph.

D. If content, repositories, or requested changes are absent from the graph without having been reported, then the tool SHALL NOT report a healthy verdict.

E. When the tool serves a value derived from source content that has changed since the value was computed, the tool SHALL serve a value recomputed from the current content or mark the served value as stale.

F. The tool SHALL record a change as applied only when the change is present at the destination the record names.

G. While the tool serves answers computed from a configuration that no longer matches the configuration on disk, the tool SHALL disclose that the answers reflect a superseded configuration.

## Changelog

- 2026-08-01 | 9aa9a8aa | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: sync changelog hash
- 2026-08-01 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-47: declare satisfaction of the REQ-p00019 anti-pattern template; rationale maps assertions to template classes
- 2026-07-31 | 9aa9a8aa | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms, update hash
- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-10: author completeness/freshness invariant (merges GI-1 silent omission and GI-2 silent staleness)

*End* *Complete and Current Reporting* | **Hash**: 9aa9a8aa
---

# REQ-p00017: Reference Integrity Under Mutation

**Level**: prd | **Status**: Active | **Implements**: REQ-p00001

## Rationale

The *Traceability* graph is held together by references: `Implements:`, `Verifies:`, and `Validates:` markers in code, tests, and journeys designate requirements and assertions by identifier. A reference that breaks is visible — the tool reports it. A reference that still parses but now designates something *other than what it designated before* is worse than broken: it is silently wrong, and every coverage number computed over it is silently wrong too. The governing invariant of this requirement: no mutation leaves a reference that still parses but designates something other than what it designated before.

The failure shapes this requirement guards against:

- Assertion labels treated as positions. If deleting assertion B renumbers C to B, every `Implements: REQ-x-B` in code silently repoints from the old B's obligation to the old C's. Labels must bind to content, never to position. Requirement hashing is already order-independent (REQ-d00131-J), so reordering assertions perturbs nothing on the hash side — label stability is the remaining reorder hazard, and this requirement closes it.
- A requirement-ID rename that updates the spec file but not the estate's other spec references, leaving stale designations inside the graph itself.
- References the tool cannot see. Requirement IDs appear in artifacts elspais does not parse — prose documentation, SQL migrations, Terraform, shell scripts, commit messages. The tool cannot update these, but it can refuse to strand them: an identity mapping from former to successor identifiers makes out-of-graph references mechanically updatable. The obligation is the mapping's existence and availability, not its format.
- Deletion that ignores lifecycle. The estate classifies statuses into roles (active, provisional, aspirational, retired). A provisional or aspirational requirement has attracted no committed references, so removing or renumbering it is routine. An active requirement is load-bearing; removing it outright would strand every reference to it, so it retires in place instead. A retired requirement is a historical record; editing it would falsify the record that its identifier preserves.

**Assertion-level retirement (the RETIRED directive).** The estate's `[Removed - ...]` placeholder convention is convention-only: the parser builds ordinary ASSERTION nodes from placeholders, so retired letters (REQ-d00010 carries seven; REQ-p00004-G is another) count as permanently-uncovered assertions in every coverage denominator, and gap surfaces cannot distinguish "retired by design" from "never verified". The RETIRED parsing directive (syntax per REQ-p00002-E) makes retirement machine-readable: an *Assertion* carrying it "does not exist" for coverage and *Traceability* purposes — it exits every denominator (no longer counted among assertions expected to be implemented, tested, or validated), and references to it break loudly instead of designating a withdrawn obligation, which is precisely this requirement's governing invariant applied at *Assertion* granularity. What retirement does NOT release is the label: the letter stays allocated forever, the assertion-level analogue of the label-stability invariant assertion A states for reorder/delete mutations and of the identifier-reuse prohibition assertion F states for requirements. G/H/I are the *Assertion*-granularity counterparts of the requirement-level retire-in-place discipline in D/E/F. The adjacent concept in REQ-p00016 (a declaring requirement marking a template *Assertion* NOT APPLICABLE for one instance) is per-instance exclusion; RETIRED withdraws the obligation estate-wide at its definition site. Migrating existing placeholders to the directive form, the parser and coverage implementation, and the assertions-docs update are implementation-phase work: these assertions land uncovered by design, and current placeholder behavior becomes a tracked conformance gap.

Interplay with existing requirements: this requirement governs what an *applied* mutation must preserve. When a mutation cannot be applied — or can be applied only partially — reporting the unapplied change and its cause is REQ-p00015-B's obligation, cited here rather than restated. REQ-d00201 and REQ-d00065 specify *which layer executes* mutations (delegation of mutation logic to the graph); they are complementary plumbing and say nothing about designation integrity, which is this requirement's subject. Protection against concurrent writers (lost updates, conflict detection) is the concern of the MCP mutation tooling spec under REQ-o00062, not of this requirement — scope here is designation integrity of the mutations that are applied.

## Assertions

A. If a mutation reorders or deletes *Assertions* within a requirement, then the tool SHALL NOT assign a label previously borne by one *Assertion* to a different *Assertion*.

B. When a mutation renames the identifier of a requirement or of one of its *Assertions*, the tool SHALL update every reference held in the graph to the former identifier so that it designates the same entity under its new identifier.

C. When a mutation changes or removes an identifier, the tool SHALL make available a mapping from each former identifier to its successor identifier, or to its removal, in a form consumable by processes that update references outside the graph.

D. If a mutation would delete a requirement whose status is in the active role, then the tool SHALL transition the requirement to a retired-role status preserving its identifier rather than removing it.

E. While a requirement's status is in a retired role, the tool SHALL NOT apply mutations that alter the requirement's content or identifier.

F. The tool SHALL NOT assign an identifier previously borne by a requirement whose status reached the active role to a different requirement.

G. While an *Assertion* carries the RETIRED parsing directive, the tool SHALL exclude that *Assertion* from every coverage and *Traceability* calculation.

H. If a reference targets an *Assertion* carrying the RETIRED parsing directive, then the tool SHALL treat the reference exactly as a reference to a nonexistent *Assertion*: unresolved, and surfaced as a broken reference.

I. The tool SHALL NOT assign a label borne by an *Assertion* carrying the RETIRED parsing directive to a different *Assertion*.

## Changelog

- 2026-07-31 | 8ddf7122 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-47: author RETIRED-directive semantics — coverage/traceability nonexistence (G), broken-reference resolution (H), permanent label allocation (I)
- 2026-07-31 | c0aae59d | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms, update hash
- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-20: author reference-integrity-under-mutation invariant (GI-3)

*End* *Reference Integrity Under Mutation* | **Hash**: 8ddf7122
---

# REQ-p00018: Compiled Risk Register

**Level**: prd | **Status**: Active | **Implements**: REQ-p00004

## Rationale

Regulated development requires a risk register: what can go wrong, how each risk is mitigated, and what residual risk is accepted. A register maintained as a separate document detaches from the requirements that carry the mitigations and goes stale the day after it is written. Documenting each residual risk inline, within the requirement it concerns, keeps the risk statement next to the obligations that mitigate it — and the register becomes a derived artifact, compiled from the requirements estate, never hand-maintained.

Attributing each risk to the requirement that documents it and to the specific assertions carrying its mitigation (or recording its acceptance) makes the register auditable through the same *Traceability* graph as everything else: an auditor can walk from a risk to the obligations that answer it, and from those obligations to the tests that verify them. A mitigation citation that resolves to nothing is precisely the silent-omission defect REQ-p00015 guards against in reporting surfaces — a register that quietly drops or ignores an unresolvable citation misrepresents the estate's risk posture; assertion C applies that reporting principle here rather than restating it.

Table layouts, command shapes, and severity or likelihood vocabularies are mechanism choices; the assertions deliberately fix none of them.

## Assertions

A. The tool SHALL compile residual-risk documentation recorded inline within requirements into a single register spanning every repository of the graph.

B. The register SHALL attribute each documented risk to the requirement documenting it and to the *Assertions* carrying its mitigation or accepting its residual risk.

C. If a mitigation citation within residual-risk documentation does not resolve to an *Assertion* present in the graph, then the tool SHALL report the unresolved citation.

## Changelog

- 2026-07-31 | 0f0438e9 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: sync changelog hash
- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-4: author compiled cross-spec risk register requirement (inline residual risk, attribution to mitigating assertions, unresolved-citation reporting)

*End* *Compiled Risk Register* | **Hash**: 0f0438e9
---

# REQ-p00019: Truthful Reporting and Error Discipline

**Level**: prd | **Status**: Active | **Template** | **Implements**: -

## Rationale

A catalog of behavioral anti-pattern classes, stated once and consumed by subsystem requirements via `Satisfies:`; in each assertion, "the system" reads as the satisfying subsystem. Each class names a point where several behaviors are individually defensible — serving a cached value, substituting a default, taking no action on an error — and prohibits choosing one silently or stranding the receiver of a failure without a path to action. Declaring satisfaction obliges the author to consider every class for that subsystem: concretize it with the satisfier's own assertions, exclude it per-instance (REQ-p00016), or leave it visibly uncovered.

## Assertions

A. When the system omits from an answer content that lies within the scope the answer claims to cover, the system SHALL report the omission and its cause.

B. When the system serves a value derived from sources that have changed since the value was computed, the system SHALL disclose the divergence or serve a value recomputed from the current sources.

C. When the system delivers a default, cached, partial, or degraded result in place of the requested result, the system SHALL disclose the substitution.

D. The system SHALL NOT represent an action as performed unless the action's effect is present at the destination the representation names.

E. When the system does not perform a requested action, the system SHALL report the unperformed action and the cause.

F. If an omission, divergence, substitution, or unperformed action remains undisclosed, then the system SHALL NOT report a healthy verdict.

G. When the system reports a failure, the report SHALL identify the operation that failed, the cause, and the remedial action available to the caller (or state that none is known).

H. The system SHALL act on or report every error signal it receives, except signals whose point of suppression carries a recorded justification that no action is required.

## Changelog

- 2026-08-01 | b2a947fb | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-02 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-47: condense rationale to a short orientation preamble per review
- 2026-08-01 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-47: author behavioral anti-pattern template — silent omission, staleness, substitution, phantom success, unreported non-performance, verdict integrity, unactionable failures, suppressed error signals

*End* *Truthful Reporting and Error Discipline* | **Hash**: b2a947fb
---

## REQ-d00220: TermDictionary Data Model

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

### Assertions

A. `TermDictionary.add()` SHALL store a `TermEntry` keyed by normalized (lowercased) term name. If the term already exists, it SHALL return the existing entry without overwriting.

B. `TermDictionary.lookup()` SHALL perform case-insensitive lookup and return the `TermEntry` or `None`.

C. `TermDictionary.iter_indexed()` SHALL yield only entries where `indexed` is `True`. `iter_collections()` SHALL yield only entries where `collection` is `True`.

D. `TermDictionary.merge()` SHALL combine two dictionaries and return a list of `(TermEntry, TermEntry)` pairs for duplicate terms detected across namespaces.

E. `TermRef` SHALL have a `wrong_marking` field (str, default "") that records the incorrect emphasis delimiter used (e.g., `"__"` when the configured markup_styles are `["*", "**"]`). When non-empty, `marked` SHALL be `False`.

### Changelog

- 2026-07-31 | 986251c3 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 0d0fd97c | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 0d0fd97c | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *TermDictionary Data Model* | **Hash**: 986251c3

<!-- markdownlint-disable MD038 -->

## REQ-d00221: Grammar Extension for Definition Blocks

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

### Assertions

A. The grammar SHALL include a `DEF_LINE` terminal matching `: ` followed by non-newline text, a `CONT_LINE` terminal matching two or more leading spaces followed by non-newline text, and a `definition_block` rule matching `TEXT _NL (DEF_LINE _NL (CONT_LINE _NL)*)+`. Continuation lines SHALL attach to the preceding `DEF_LINE` and be joined with a newline before metadata classification. The `definition_block` rule SHALL be an alternative in `_item`, `preamble_line`, `content_line`, `jny_body_line`, and `jny_content_line` but NOT in `assertion_item` or `changelog_block`.

B. The transformer SHALL handle `definition_block` nodes by extracting the term name from the TEXT token, definition text from DEF_LINE tokens, and metadata flags (Collection, Indexed) from definition lines. It SHALL return a `ParsedContent` with `content_type="definition_block"` and parsed_data containing `term`, `definition`, `collection`, and `indexed` fields.

### Changelog

- 2026-07-31 | 5a3c278b | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 6adaa258 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-24 | 6adaa258 | - | Developer (<dev@example.com>) | Auto-fix: update hash
- 2026-04-23 | 078ce203 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Grammar Extension for Definition Blocks* | **Hash**: 5a3c278b

## REQ-d00222: TraceGraph Terms and GraphBuilder Integration

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

### Assertions

A. `TraceGraph` SHALL have a `_terms: TermDictionary` field. `GraphBuilder` SHALL handle `content_type == "definition_block"` by creating a REMAINDER node with `content_type` field set to `"definition_block"` and adding a `TermEntry` to the graph's `_terms` dictionary.

B. The `defined_in` field of each `TermEntry` SHALL point to the nearest REQUIREMENT or FILE ancestor node ID, not the REMAINDER node itself.

C. `FederatedGraph` SHALL merge per-repo `_terms` dictionaries into a single federated `TermDictionary`, detecting cross-namespace duplicates.

D. `GraphBuilder` SHALL accept a `namespace` parameter (str, default "") and set `TermEntry.namespace` from it during term creation.

### Changelog

- 2026-07-31 | 0299f7c2 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 96b5223f | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 96b5223f | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *TraceGraph Terms and GraphBuilder Integration* | **Hash**: 0299f7c2

## REQ-d00223: Term Health Checks

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

### Assertions

A. `check_term_duplicates()` SHALL return a `HealthCheck` reporting duplicate term definitions across all namespaces, using the configured `duplicate_severity`.

B. `check_undefined_terms()` SHALL return a `HealthCheck` for `*token*`/`**token**` references that do not match any *Defined Term* and are not known structural patterns, using the configured `undefined_severity`.

C. `check_unmarked_usage()` SHALL return a `HealthCheck` for whole-word case-insensitive matches of terms in prose that lack `*...*` or `**...**` markup, using the configured `unmarked_severity`. Only terms whose unmarked-usage scanning is enabled SHALL be checked.

D. When any severity is set to `"off"`, the corresponding check SHALL be skipped and return a passed HealthCheck with severity `"info"`.

E. A `run_term_checks(graph, config)` aggregator SHALL call `check_term_duplicates`, `check_undefined_terms`, and `check_unmarked_usage` with data extracted from `graph._terms` and `graph._term_duplicates`, reading severity from `config["terms"]["severity"]`. It SHALL be wired into `render_section()` and `compute_checks()`.

F. `check_unmarked_usage()` SHALL produce distinct messages for wrong-marking references (e.g., "Wrong markup for 'term' (uses __, should use configured style)") versus plain unmarked references (e.g., "Unmarked usage of 'term'").

G. The tool SHALL apply each term-declaration behavior — glossary and index inclusion, unmarked-usage scanning, canonical-form fixing, and reference-panel visibility — according to that behavior's own per-term setting, unaffected by the settings of the other behaviors.

H. If a term occurrence functions as system syntax — a heading, a status value, or a metadata key — then the tool SHALL NOT report that occurrence as unmarked colloquial use.

I. When scanning for unmarked usage, the tool SHALL recognize inflected forms of a term, including singular and plural variants, as occurrences of that term.

### Rationale

Term declarations historically carried one bundled flag (`Indexed: false`) that both removed a term from the generated index and exempted it from colloquial-use checking, so deliberately unindexed terms could accumulate unmarked usages invisibly. G makes the behaviors orthogonal: inclusion in generated glossary/index output, unmarked-usage scanning, canonical-form fixing, and reference-panel visibility are separate per-term decisions, and excluding a term from one does not silently exempt it from another. The per-behavior flag names sketched during design (`Check Unmarked:`, `Syntax Word:`, `Show References:`) are proposed mechanism, not obligations — only the separability is asserted here. Per the project rule against backwards-compatibility paths, existing bundled `Indexed: false` declarations migrate outright to the separated settings when the mechanism lands; no compatibility mode preserves the bundled meaning. H and I make the scanner context-aware in both directions: a word serving as system syntax (a heading, a status value, a metadata key) is not colloquial use even though the same word in prose is, and an unmarked usage is not missed merely because it appears inflected. Existing behavior that contradicts these assertions — in particular the bundled indexed gate — is conformance-defect territory for later implementation tickets.

### Changelog

- 2026-07-31 | aac4da7f | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-5: orthogonal term-declaration behaviors (G) and context-aware unmarked-usage scanning (H, I); decouple C from the bundled indexed flag
- 2026-07-31 | b2d02a05 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 0d96cc34 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 0d96cc34 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Term Health Checks* | **Hash**: aac4da7f

## REQ-d00224: Glossary and Term Index Generators

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

### Assertions

A. `generate_glossary()` SHALL produce an alphabetically-organized Markdown glossary with letter headings, including definition text, `defined_in` attribution, and annotation for collection/non-indexed terms.

B. `generate_term_index()` SHALL produce a term index listing only indexed terms, with references grouped by namespace (one per line).

C. `generate_collection_manifest()` SHALL produce a standalone manifest file per collection term, listing all reference sites.

D. All generated files SHALL include an auto-generated header comment. Both `--format markdown` and `--format json` SHALL be supported.

### Changelog

- 2026-07-31 | c8ce4253 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | f2da30fb | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | f2da30fb | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Glossary and Term Index Generators* | **Hash**: c8ce4253

## REQ-d00225: CLI Registration for Glossary and Term Index

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

### Assertions

A. `GlossaryArgs` and `TermIndexArgs` dataclasses SHALL be defined in `commands/args.py` with `format` and `output_dir` fields. They SHALL be registered in the `Command` union and `_CMD_MAP`.

B. `elspais fix` SHALL call glossary and term-index generation after existing fix operations when the graph has defined terms.

### Changelog

- 2026-07-31 | 2b8a5235 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | d18fc2c9 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | d18fc2c9 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *CLI Registration for Glossary and Term Index* | **Hash**: 2b8a5235

## REQ-d00236: Comment Extraction Utilities

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

### Assertions

A. `extract_comments(source, ext)` SHALL return a `list[tuple[str, int]]` of (comment_text, line_number) pairs extracted from source code text based on file extension.

B. For Python files (`.py`), the extractor SHALL use `tokenize` to extract `#` line comments and `ast` to extract docstrings, ignoring string literals that are not docstrings.

C. For slash-comment languages (`.js`, `.ts`, `.jsx`, `.tsx`, `.java`, `.c`, `.h`, `.cpp`, `.go`, `.rs`, `.dart`), the extractor SHALL extract `//` line comments and `/* */` block comments.

D. For hash-comment languages (`.rb`, `.sh`, `.bash`, `.yaml`, `.yml`), the extractor SHALL extract `#` line comments.

E. For dash-comment languages (`.sql`, `.lua`), the extractor SHALL extract `--` line comments.

F. For markup languages (`.html`, `.xml`, `.svg`), the extractor SHALL extract `<!-- -->` comments.

G. For file extensions with no known comment style, `extract_comments()` SHALL return an empty list.

### Changelog

- 2026-07-31 | 2e5b4960 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 499123f1 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 499123f1 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Comment Extraction Utilities* | **Hash**: 2e5b4960

## REQ-d00237: Term Reference Scanner Core

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

### Assertions

A. `scan_text_for_terms(text, td, node_id, namespace, line_offset, markup_styles)` SHALL return a `list[TermRef]` classifying each term occurrence as marked, wrong-marking, or unmarked.

B. For each configured `markup_style` in `markup_styles`, the scanner SHALL detect terms wrapped in that delimiter as `marked=True, wrong_marking=""`.

C. For Markdown emphasis delimiters (`*`, `**`, `__`, `_`) NOT in `markup_styles`, the scanner SHALL detect wrapped terms as `marked=False` with `wrong_marking` set to the delimiter used.

D. For terms with `indexed=True`, the scanner SHALL perform whole-word case-insensitive matching for unmarked (plain text) occurrences, excluding positions already matched as marked or wrong-marking.

E. Terms with `indexed=False` SHALL be scanned for marked and wrong-marking references only; unmarked scanning SHALL be skipped.

F. An unmarked occurrence that is a proper part of a larger compound identifier (e.g. a term appearing between hyphens inside a requirement ID such as `CAL-PRD-portal-Session-configuration`) SHALL be recorded as a reference with `embedded=True`. Embedded references SHALL be counted toward the term index, SHALL NOT be auto-marked during canonicalization, and SHALL NOT be reported as unmarked-emphasis or non-canonical-form violations.

G. When one *Defined Term*'s text contains another (e.g. `Sponsor Portal` contains `Sponsor`), matching SHALL be leftmost-longest (maximal munch) and independent of term definition order: the scanner and the canonicalizer SHALL process terms longest-first and SHALL NOT match a shorter term within a span already claimed by a longer term. A shorter nested term SHALL still match where it occurs on its own.

### Changelog

- 2026-07-31 | 637ac760 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-06-09 | f2b673a4 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms, update hash
- 2026-06-09 | 2849c41b | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-06-09 | d1eb27f4 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 63cb874b | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 63cb874b | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Term Reference Scanner Core* | **Hash**: 637ac760

## REQ-d00238: Graph-Wide Term Scan

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

### Assertions

A. `scan_graph(terms, nodes, namespace, markup_styles, exclude_files)` SHALL populate `TermEntry.references` by scanning graph nodes for term occurrences.

B. REQUIREMENT, *Assertion*, REMAINDER (excluding `definition_block`), and JOURNEY nodes SHALL be scanned using their full text content.

C. CODE and TEST nodes SHALL be scanned via comment extraction only (not raw source code), to avoid false positives on variable names and string literals.

D. Files matching any `exclude_files` glob pattern SHALL be skipped during scanning.

### Changelog

- 2026-07-31 | b14edde9 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | d3a202d4 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | d3a202d4 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Graph-Wide Term Scan* | **Hash**: b14edde9

## REQ-d00239: Federated Graph Term Scanner Pass

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

### Assertions

A. After `FederatedGraph._merge_terms()`, the scanner SHALL run across all repos using the merged `TermDictionary` so that cross-repo term references resolve correctly.

B. Each repo's scan SHALL use its own config for `markup_styles` and `exclude_files`.

### Changelog

- 2026-07-31 | e27abfeb | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 7d9a30c4 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 7d9a30c4 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Federated Graph Term Scanner Pass* | **Hash**: e27abfeb

## REQ-d00240: New Term Health Checks

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

### Assertions

A. `check_term_unused(entries, severity)` SHALL return a `HealthCheck` reporting defined terms with zero references. Default severity: `"warning"`. When `severity="off"`, return passed/info.

B. `check_term_bad_definition(entries, severity)` SHALL return a `HealthCheck` reporting terms with blank or trivially short (less than 10 characters) definition text. Default severity: `"error"`. When `severity="off"`, return passed/info. Reference-type terms (`is_reference=True`) SHALL be exempted from this check because their content lives in structured `reference_fields` instead of prose.

C. `check_term_collection_empty(entries, severity)` SHALL return a `HealthCheck` reporting collection terms (`collection=True`) with zero references. Default severity: `"warning"`. When `severity="off"`, return passed/info.

D. `run_term_checks()` SHALL call all six term checks (`duplicates`, `undefined`, `unmarked`, `unused`, `bad_definition`, `collection_empty`) with severity from `config["terms"]["severity"]`.

### Changelog

- 2026-07-31 | b4e70076 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 76a49db3 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-24 | 76a49db3 | - | Developer (<dev@example.com>) | Auto-fix: update hash
- 2026-03-29 | 9788814d | - | Michael Lewis (<michael@anspar.org>) | Initial creation

*End* *New Term Health Checks* | **Hash**: b4e70076

## REQ-d00263: Scoped Term Binding

**Level**: dev | **Status**: Draft | **Implements**: REQ-p00002, REQ-p00081

A marked term whose definition varies by context SHALL resolve through an explicit, position-independent binding declaration, so that requirement text stays terse at the point of use while its meaning stays deterministic.

### Assertions

A. A file or an individual requirement SHALL be able to declare a binding that maps a base term to a specific bound term for its own scope.

B. A marked base term SHALL resolve using only explicit binding declarations in its scope; resolution SHALL NOT depend on document position, preceding content, or declaration order.

C. When a marked base term has no binding declaration in scope, validation SHALL report an error naming the term and its location.

D. A requirement's term resolution SHALL be identical after file reordering, file splitting, and template cloning of the requirement into another document context.

E. Render surfaces SHALL be able to expand a bound term to its resolved form at generation time.

### Rationale

Cross-cutting policy text wants to say `*system*` once and mean `portal system` in one repo and `diary system` in another. Positional binding ("most recently previously declared system in the same document") was considered and rejected: inserting a requirement above would silently change a later requirement's meaning without changing its hash, `fix` reorders content, files get split, and template cloning places requirements into new document contexts — all of which would make meaning depend on position. It also contradicts the project's rule that every assertion be independently decidable without additional context. Explicit scoped binding keeps the terseness while failing loudly when unbound. Assertion D is what makes binding safe under the same reordering and cloning operations the hash system already contends with.

### Changelog

- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-38: author scoped term binding (org-wide terms)

*End* *Scoped Term Binding* | **Hash**: d13a3c53

## REQ-d00264: Usage-Driven Glossary Selection

**Level**: dev | **Status**: Draft | **Implements**: REQ-p00002, REQ-p00081

A generated glossary SHALL be selected by usage: definitions may live anywhere in the federated view, and a generation context emits exactly the terms referenced within it.

### Assertions

A. Glossary generation for a context SHALL include every *Defined Term* referenced within that context, including terms whose definitions are owned by another federated repository.

B. Glossary generation for a context SHALL exclude defined terms with no reference within that context, regardless of where the definitions are owned.

C. The selection of terms for a context SHALL be derived from the graph's recorded term references, not from a separate scan or list.

### Rationale

Definitions can be authored org-wide while each generated document carries only its own vocabulary: a term defined in the policy repo appears in a consuming repo's glossary because it is used there, without dragging in its unreferenced siblings. Per-entry index eligibility on the write/generation surfaces is the same control at its coarsest granularity; this REQ is the fine-grained rule. The boundary with document tooling holds here: elspais owns the graph, term usage, and *selection* — "which terms belong in this context" is a reachability question over data the graph already holds — while layout, ordering, numbering, and per-sponsor chrome belong to the document tool (the extensibility seam is tracked in TOOL-34/TOOL-35).

### Changelog

- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-38: author usage-driven glossary selection (org-wide terms)

*End* *Usage-Driven Glossary Selection* | **Hash**: 12f529a3

## REQ-d00241: Code No-Traceability Health Check

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

### Assertions

A. `check_no_traceability(unlinked_files, severity)` SHALL return a `HealthCheck` reporting code files with no *Traceability* markers. Default severity: `"warning"`. When `severity="off"`, return passed/info. Test files SHALL NOT be reported here because the separate `tests.unlinked` check already covers marker-less test files; including them in both would double-report the same file.

B. The check SHALL be wired into `run_code_checks()` using `graph.iter_unlinked()` to find CODE nodes not linked to any requirement.

C. Severity SHALL be read from `[rules.format] no_traceability_severity` (default `"warning"` if None).

D. The `tests.unlinked` check (`check_unlinked_tests()`) SHALL flag a test file when it contains no TEST nodes, or when it contains TEST nodes none of which link to any requirement. A test file with at least one linked test SHALL NOT be flagged. The second condition is required because the parser emits a TEST node for every discovered test function whether or not it carries a *Traceability* marker, so a fully marker-less test file still has TEST children; without it such files would escape both `tests.unlinked` and the code-only `code.no_traceability`.

### Changelog

- 2026-07-31 | de72736f | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-03 | 583588f9 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-03 | c1be56e5 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | e1272219 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | e1272219 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: sync changelog hash
- 2026-03-29 | 6e481d63 | - | Michael Lewis (<michael@anspar.org>) | Initial creation

*End* *Code No-Traceability Health Check* | **Hash**: de72736f

## REQ-d00246: Markdown Emphasis Normalization Utility

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

### Assertions

A. The codebase SHALL provide a `strip_emphasis(s: str) -> str` utility in `utilities/markdown.py` that strips balanced pairs of `**`, `__`, `*`, and `_` from the start and end of `s`, in order of width (widest first). Outer whitespace SHALL be trimmed. Unbalanced wrappers (e.g. `*Foo_`, `**Foo`) SHALL leave the string intact. The function SHALL be idempotent.

B. Lark transformers SHALL use `strip_emphasis()` to normalize all user-text captured from emphasis-decorated spec source: term names extracted from `definition_block` TEXT tokens, value text extracted from journey `Actor`/`Goal`/`Context` metadata fields, and `reference term`/`reference source` definition-block fields. Ad-hoc per-character strip calls (e.g., `.strip("*")`, `.strip("_")`) SHALL NOT remain in the transformer modules.

### Changelog

- 2026-07-31 | 6db4d559 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 16af6c80 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-05-04 | 16af6c80 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Markdown Emphasis Normalization Utility* | **Hash**: 6db4d559

## REQ-d00247: Fenced Code Block Preservation

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

### Assertions

A. Fenced code block content (lines between ``` markers) SHALL be preserved verbatim across the parse-render round trip. Any preprocessing applied to fenced content for grammar matching (e.g., line replacement with neutralization placeholders) SHALL be ephemeral, used only as parser input, and SHALL NOT be persisted to disk via render. The lark spec parser SHALL pass the original un-preprocessed source content to the transformer's `source` parameter so REMAINDER nodes capture the original text.

### Changelog

- 2026-07-31 | 499a4ce4 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 1270eb2b | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-05-04 | 1270eb2b | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Fenced Code Block Preservation* | **Hash**: 499a4ce4

## REQ-d00248: Fix Command Idempotency

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

### Assertions

A. `elspais fix` SHALL be idempotent: running the command twice in succession on the same project SHALL produce identical files. The second invocation SHALL detect no pending changes and SHALL not modify any spec, journey, code, test, or generated artifact file. This invariant SHALL be exercised by a fixture that includes fenced code blocks with markdown emphasis, a glossary term with emphasis-wrapped name, a user journey with emphasized actor field, and a REMAINDER section containing emphasized text.

### Changelog

- 2026-07-31 | 2b421222 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 8a92207b | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-05-04 | 8a92207b | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Fix Command Idempotency* | **Hash**: 2b421222
