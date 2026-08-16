# Graph Configuration Development Requirements

## REQ-d00207: Declarative Config Schema Cleanup

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

All configuration defaults and validation SHALL be provided by the Pydantic `ElspaisConfig` schema. Legacy `DEFAULT_CONFIG` dict and `ConfigLoader` wrapper class SHALL be removed; all consumer code SHALL access configuration via plain dicts produced by `ElspaisConfig.model_dump()`.

### Assertions

A. `DEFAULT_CONFIG` dict SHALL be removed from `config/__init__.py`; all default values SHALL be defined as Pydantic field defaults in `config/schema.py`.

B. `ConfigLoader` class SHALL be removed; `load_config()` SHALL return a plain `dict[str, Any]` produced by `ElspaisConfig.model_validate()` + `model_dump(by_alias=True)`.

C. All consumer code that references `ConfigLoader` (type annotations, imports, `.from_dict()`, `.get_raw()`, `.get()`) SHALL be updated to use plain dicts directly.

### Changelog

- 2026-07-31 | 6dfbf578 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 8d323813 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 8d323813 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Declarative Config Schema Cleanup* | **Hash**: 6dfbf578
---

## REQ-d00208: JSON Schema Export for IDE Autocomplete

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

The `ElspaisConfig` Pydantic model SHALL be exportable as a JSON Schema file for IDE autocomplete (e.g., Taplo). A CLI subcommand SHALL generate the schema on demand, and a committed schema file SHALL stay in sync with the model.

### Assertions

A. `elspais config schema` SHALL output the JSON Schema to stdout (or to a file with `--output`), generated from `ElspaisConfig.model_json_schema()`.

B. A committed `src/elspais/config/elspais-schema.json` SHALL match the output of `ElspaisConfig.model_json_schema()`. A CI test SHALL verify this.

C. The generated JSON Schema SHALL include `$schema` and `title` top-level keys.

### Changelog

- 2026-07-31 | 27ca773c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 2b82ef02 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 2b82ef02 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *JSON Schema Export for IDE Autocomplete* | **Hash**: 27ca773c
---

## REQ-d00209: Schema-Driven Init Template Generation

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

The `elspais init` command SHALL generate `.elspais.toml` configuration files by walking the `ElspaisConfig` Pydantic model, ensuring generated templates are always in sync with the schema. Hardcoded template strings SHALL be replaced by a schema walker that produces valid TOML from field metadata and defaults. Beyond configuration, initialization gives a new project a working starting point rather than a blank tree.

### Assertions

A. `generate_config("core")` SHALL produce TOML that passes `ElspaisConfig.model_validate()` without error.

B. `generate_config("associated")` SHALL produce TOML that passes `ElspaisConfig.model_validate()` without error when given a valid prefix.

C. The generated TOML SHALL include all sections present in the current hardcoded templates (project, directories, id-patterns, rules, etc.).

D. The generated TOML SHALL include human-readable comments derived from Pydantic field descriptions or the current template comments.

E. When scaffolding a new project, the tool SHALL offer a worked example project, accepted as healthy by the tool's own checks, that demonstrates in combination requirement hierarchy, template satisfaction, journey validation, defined terms, and code and test *Traceability* markers.

F. When scaffolding a new project, the tool SHALL include baseline requirement-authoring conventions in the generated project, covering at minimum assertion granularity, normative keyword usage, and *Traceability* reference forms.

### Rationale

A new project today starts from configuration alone; the first spec file, the first `Satisfies:` declaration, and the first code marker are all authored cold. The worked example (E) closes that gap by showing the concepts *composed* — a small hierarchy whose requirements are satisfied, validated by a journey, use defined terms, and are implemented and verified by marked source files — rather than each concept in isolation. Which files and requirement counts make up the example is deliberately unspecified: content inventory is mechanism, not obligation.

The example is intended to do triple duty: user-facing scaffold, canonical test fixture for the tool's own suite, and fixture for the mechanical style checks. Fixtures must pass their own health checks, which is why E defines the example as checks-healthy as generated. For the same reason, scaffolded templates and conventions (F) must not contradict the mechanically checkable style rules elsewhere in this spec (see the mechanical style-check requirement in the CLI spec): a fresh project that fails its own first style run would teach the wrong lesson. The authoring conventions (F) are the baseline house rules a new author needs before the first requirement — how fine an assertion should be, which normative keywords are canonical, and how requirements are referenced from code and tests.

### Changelog

- 2026-07-31 | b25e4468 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms, update hash
- 2026-07-31 | 0173b043 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | 44aeb496 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | 44aeb496 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Schema-Driven Init Template Generation* | **Hash**: b25e4468
---

## REQ-d00210: Documentation Drift Detection

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

The `elspais doctor` command SHALL detect drift between `ElspaisConfig` Pydantic schema fields and `docs/configuration.md`. Undocumented schema fields and stale documentation sections SHALL be reported as health check findings.

### Assertions

A. `elspais doctor` SHALL include a `docs.config_drift` health check that compares schema top-level sections against documented sections.

B. The drift detection SHALL report undocumented sections (in schema but not in docs) and stale sections (in docs but not in schema).

C. The drift check SHALL pass when all schema sections are documented and no stale sections exist, and fail otherwise.

### Changelog

- 2026-07-31 | 59023724 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | eb94434a | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | eb94434a | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Documentation Drift Detection* | **Hash**: 59023724
---

## REQ-d00211: Config-Driven Viewer UI Values

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

The values the viewer offers a reader — the levels it groups by, the statuses it filters on, the relationships a reader may create — SHALL come from the project's configuration rather than from the viewer, so that a project sees its own vocabulary and not this one's.

### Assertions

A. The viewer SHALL offer the requirement levels the project declares, each with the letter and rank that project gives it.

B. The viewer SHALL offer only those relationships a reader may author. The graph holds kinds the tool derives rather than accepts, and offering one would invite a reader to declare something the tool will overwrite.

C. The viewer SHALL offer the statuses the project declares, which are the statuses its requirements may carry.

D. Statuses presented in order SHALL run active first, then provisional, then aspirational, then retired, keeping the order they were given in within each of those groups. A status belonging to no declared role SHALL be ordered as an active one.

### Changelog

- 2026-08-14 | 254fcba9 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-14 | 3feb798c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-14 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: state what the viewer offers a reader rather than which variables carry it; two assertions named configuration fields that do not exist
- 2026-07-31 | 58192a4f | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | a9cc41d2 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | a9cc41d2 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Config-Driven Viewer UI Values* | **Hash**: 254fcba9
---

## REQ-d00212: Config Schema v3 Models

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

The `ElspaisConfig` Pydantic schema SHALL be restructured to v3 shape with first-class level definitions, unified scanning configuration, simplified references, and cleaner changelog sub-models. New models SHALL be strict (`extra="forbid"`) and frozen by default.

### Assertions

A. A `LevelConfig` model SHALL define per-level properties: `rank` (int), `letter` (str), `display_name` (str, optional), `implements` (list[str]), and `expects_validation` (bool, default false). Unknown fields SHALL be rejected.

B. A `ScanningKindConfig` base model SHALL define common scanning fields: `directories` (list[str]), `file_patterns` (list[str]), `skip_files` (list[str]), `skip_dirs` (list[str]). Per-kind subclasses SHALL add kind-specific extras (e.g., `SpecScanningConfig` adds `index_file`, `TestScanningConfig` adds `enabled`, `prescan_command`, `reference_keyword`, `reference_patterns`).

C. A `ScanningConfig` composite model SHALL contain all scanning kinds (`spec`, `code`, `test`, `result`, `journey`, `docs`) plus a global `skip` list that applies to all kinds.

D. An `OutputConfig` model SHALL define output configuration: `formats` (list[str], default empty) and `dir` (str, default empty).

E. A `ChangelogRequireConfig` sub-model SHALL group changelog requirement booleans: `reason`, `author_name`, `author_id`, `change_order`. `ChangelogConfig` SHALL use renamed fields (`hash_current` for `enforce`, `present` for `require_present`) and a `require` sub-model of type `ChangelogRequireConfig`.

F. `ElspaisConfig` SHALL have `levels` (dict[str, LevelConfig]), `scanning` (ScanningConfig), and `output` (OutputConfig) fields. The `directories`, `spec`, `testing`, `ignore`, `graph`, `traceability`, `core`, and `associated` fields SHALL be removed. Version SHALL default to 3.

G. A repository's identifier configuration SHALL admit exactly one spelling of any given identifier, up to case. Two elements of an identifier configuration that differ only in case SHALL be rejected at configuration-validation time, naming both and the element they collide in.

H. `HierarchyConfig` SHALL contain only boolean flags (`allow_circular`, `allow_structural_orphans`, `allow_orphans`, `cross_repo_implements`). Per-level implement rules SHALL be defined in `LevelConfig.implements` instead. The model SHALL be strict (`extra="forbid"`).

I. [Removed - named a references section of the configuration that does not exist. Identifier grammar is configured under identifier patterns, and an identifier is admitted in one spelling only, per REQ-d00212-G.]

J. `ProjectConfig` SHALL contain only `namespace` and `name`. The `version` and `type` fields SHALL be removed.

K. `AssociateEntryConfig` SHALL define the fields an associate declaration is written in: `path` (str) and `namespace` (str), both required, together with the optional `git` remote and `color`. A declaration SHALL be admitted only where every field it carries is one this model defines.

L. A `TermsConfig` model SHALL define defined-terms configuration: `output_dir` (str, default "spec/_generated"), `markup_styles` (list[str], default ["*", "**"]), `exclude_files` (list[str], default []), and a nested `severity` field of type `TermsSeverityConfig`. `TermsSeverityConfig` SHALL define 6 severity fields: `duplicate` (default "error"), `undefined` (default "warning"), `unmarked` (default "warning"), `unused` (default "warning"), `bad_definition` (default "error"), `collection_empty` (default "warning"). `ElspaisConfig` SHALL include a `terms` field of type `TermsConfig` with factory default.

M. `FormatConfig` SHALL include a `no_traceability_severity` field (str | None, default None) to configure the severity of code/test files lacking *Traceability* markers.

N. A `_migrate_v3_to_v4` migration SHALL move flat `duplicate_severity`, `undefined_severity`, `unmarked_severity` from `[terms]` into `[terms.severity]` as `duplicate`, `undefined`, `unmarked`. Configs without `[terms]` SHALL pass through unchanged. Configs already having `[terms.severity]` SHALL NOT be double-migrated. `CURRENT_CONFIG_VERSION` SHALL be bumped to 4.

O. The configuration schema SHALL locate each rule setting under the concern it governs, such that a setting's position in the schema identifies which checks it affects.

P. The configuration schema SHALL make the severity of every health check configurable under a single consistent convention.

Q. The configuration schema SHALL express file selection for scanning through a single mechanism, such that exactly one configuration surface determines whether any given file is scanned.

R. An identifier SHALL resolve to a requirement only where it is spelled as the configuration of the repository owning that requirement admits, and case SHALL NOT decide whether it resolves. An identifier SHALL be rendered in the one casing that configuration names, on every surface.

S. Reading an identifier without regard to case SHALL NOT extend to any other difference. A spelling that differs from what the configuration admits in anything but case SHALL resolve to nothing, and SHALL NOT be repaired into one that resolves.

### Rationale

Most lettered entries inventory the v3/v4 model shapes; G and O–R state the organising invariants those shapes must converge on.

K carries the remote because a federation member is a git repository, and a member declared but absent from this machine is an ordinary situation rather than an error to be merely reported: the declaration is the one place that knows where the repository can be obtained. The remote never identifies a member — the path and the namespace do that, which is why it stays optional and why a declaration without one is complete. What a declaration may contain and what it must contain are one question, so the field list and the strictness that enforces it belong together rather than in separate assertions that could drift.

G, R and S hold within a single repository, not only where several meet. G fixes what the configuration admits; R fixes what an inadmissible spelling may do; S bounds how far R's tolerance reaches. The failure R forbids is not silence but a wrong answer: a spelling nobody wrote being repaired into one that resolves, so a reference lands on a requirement its author did not name. That is invisible in every report, because the reference looks satisfied.

Case is exempt from that, and the exemption is safe for a reason that has to be built rather than assumed. Reading without regard to case can only mislead where two admissible spellings differ in case alone — and G now forbids a configuration from holding such a pair at all, so the ambiguity has no way to arise. What remains is one identifier reachable by more than one casing, and a single casing in which it is written back. An author who types a label in the wrong case is naming a requirement that exists, unambiguously, and refusing them costs an edge to buy nothing; an author who mistypes a digit is naming a requirement that may not exist at all, which is why S keeps every other difference resolving to nothing.

The two obligations are therefore a pair rather than a compromise: matching relaxes exactly as far as the configuration guard makes safe, and no further. Rendering is what keeps the estate uniform regardless — an identifier read in any casing is stored and re-emitted in the one the configuration names, so a file rewritten by the tool converges on that casing rather than preserving whatever was typed.

Reporting is deliberately absent from R. Once an inadmissible spelling resolves to nothing, it is an unresolved reference like any other, and the existing obligations to record it and to report it at a project-chosen severity carry it the rest of the way. Stating the reporting again here would duplicate them and invite the two statements to drift apart.

R is a condition on resolving, never on writing, which is what keeps a reference authored ahead of its target legitimate. A requirement may be named before the repository owning it is declared, or before that requirement exists; the reference simply finds nothing yet, and how loudly that is reported is the project's decision. R also judges a spelling against the configuration of the repository owning the named requirement, not the one doing the writing — otherwise no reference could ever cross a repository boundary, since a neighbour's identifiers are foreign to the local grammar by construction. Rule settings have drifted into a layout where a setting's location no longer predicts what it governs, some check severities are configurable while others are hardcoded with no stated principle distinguishing them, and "why was this file (not) scanned" can have more than one configuration answer (per-kind skip lists alongside a global skip list, plus pattern lists). O–Q close those gaps as invariants only: candidate mechanisms discussed during design — splitting rules into concern sections such as `[rules.changelog]` and `[rules.status]`, or collapsing file selection into a unified `patterns` list — are proposals, not obligations, and deliberately absent from the assertions. Which existing semantics survive, and how existing configs migrate, is decided at implementation. Current schema shapes that contradict O–Q (including the dual file-selection surfaces described alongside B and C) are conformance-defect territory for later implementation tickets.

### Changelog

- 2026-08-15 | a11d15f9 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-15 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: case no longer decides whether an identifier resolves (R), a configuration holding two elements differing only in case is rejected (G), and S bounds the tolerance to case alone
- 2026-08-12 | da474c2a | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: sync changelog hash
- 2026-08-12 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: amend K to state the fields an associate declaration is written in, including the optional git remote, reconciling it with REQ-d00202-A/B
- 2026-08-12 | da474c2a | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | 52cce4c8 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | d2250c7d | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: retire I, which named a references section that does not exist
- 2026-08-10 | 3b50127c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | 92f8213c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | 9b2c6bea | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: G states one admitted spelling; R states reporting a malformed one
- 2026-08-10 | f2697393 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | 40849780 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-26: organising invariants for rule-setting location (O), severity configurability (P), and single file-selection mechanism (Q)
- 2026-07-31 | a0ea657d | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-03 | e4cda67b | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | db4ad28c | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | db4ad28c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms
- 2026-03-29 | c75b87f8 | - | Michael Lewis (<michael@anspar.org>) | Add assertion N for config migration v3 to v4

*End* *Config Schema v3 Models* | **Hash**: a11d15f9
---

## REQ-d00251: A Repository's Identifier Grammar

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

The `[id-patterns.component].style` configuration SHALL use an explicit case-convention vocabulary rather than a small set of "custom pattern with hidden default" modes. The `[id-patterns.assertions]` section SHALL gain a configurable separator that decouples the component-to-*Assertion* boundary from any character used inside component names, enabling kebab-case and snake_case component styles to work cleanly with numeric *Assertion* labels. The grammar these settings describe is one repository's own, and applies to that repository's identifiers alone.

### Assertions

A. `ComponentConfig.style` SHALL accept exactly six values: `numeric`, `camelCase`, `PascalCase`, `snake_case`, `kebab-case`, and `regex`. The legacy values `named` and `alphanumeric` SHALL be rejected at config validation time.

B. Each case-style SHALL have a fixed default regex: `camelCase` matches `[a-z][a-zA-Z0-9]+`; `PascalCase` matches `[A-Z][a-zA-Z0-9]+`; `snake_case` matches `[a-z][a-z0-9]*(?:_[a-z0-9]+)*`; `kebab-case` matches `[a-z][a-z0-9]*(?:-[a-z0-9]+)*`. The four case-style regexes SHALL NOT be overridable via `pattern`.

C. `style = "regex"` SHALL require a non-empty `pattern` field. Config validation SHALL fail when `style = "regex"` and `pattern` is empty.

D. Rejection of the legacy values `named` and `alphanumeric` SHALL produce a fix-it error message listing the four case styles, the `regex` escape hatch, and the literal pattern that reproduces the legacy default (`[A-Za-z][A-Za-z0-9]+` for `named`, `[A-Z0-9]+` for `alphanumeric`).

E. `AssertionConfig` SHALL include a `separator` field (str, default `"-"`) used (with `re.escape`) as the boundary between the component and the optional *Assertion* suffix in the canonical regex.

F. The *Assertion* separator SHALL NOT be a character that can legally appear in a component or in an *Assertion* label. A configuration that violates this SHALL be rejected at validation time, naming the offending character, the style that makes it legal, and a non-overlapping character to use instead.

G. [Removed - stated where the component sub-pattern is derived rather than an obligation the tool meets. What a configuration admits is REQ-d00212-G; that one repository's grammar governs only its own identifiers is L below.]

H. An *Assertion* label series SHALL be one of the alphabets a repository may configure, each having a first label, a successor for every label but its last, and a last label beyond which the series does not extend.

I. [Removed - enumerated one alphabet's order here. Which alphabets a repository may configure is a matter for the configuration surface; what any of them must be is H, and a series ends at its alphabet's last label rather than at a separately configured count.]

J. The multi-*Assertion* separator SHALL NOT be a character that can legally appear in an *Assertion* label.

K. The *Assertion* separator and the multi-*Assertion* separator SHALL each be exactly one character. A configuration declaring either as empty, or as longer than one character, SHALL be rejected at validation time.

L. A repository's identifier grammar SHALL be derived from that repository's own identifier configuration, so that a process holding several repositories at once applies each repository's grammar only to that repository.

M. Neither the *Assertion* separator nor the multi-*Assertion* separator SHALL be the character that divides one reference from the next within a list of references. A configuration that declares either as that character SHALL be rejected at validation time, naming the character, the role it already holds, and a character available instead.

### Rationale

An identifier is read left to right, so every boundary inside it has to be findable without knowing what follows. A separator drawn from the characters a component may itself contain destroys that boundary: the component absorbs the separator and the label after it, and the reference resolves to a different requirement rather than failing. The result is a wrong answer, not an error, which is why this is rejected at validation time rather than warned about later.

Restricting the rule to the punctuation a style happens to use internally would leave the same trap open elsewhere — a digit separator under a numeric component, a letter separator under a camelCase one. F and J are therefore stated over the whole legal character set of the part each separator bounds, which is derivable from the style and needs no enumeration here.

Uppercase *Assertion* labels do make a lowercase component mechanically unambiguous, and that exception was previously how an overlapping separator was tolerated. It is a subtlety every reader has to re-derive, and it silently changes which requirement a mis-cased reference names, so the tolerance is not worth its cost.

K is what makes F and J decidable. Both are stated over *a character*, which leaves a separator of some other length outside the rule rather than inside it: an empty separator marks no boundary at all, and a longer one is absorbed character by character exactly as a single legal character would be, so asking whether the whole string is legal answers a different question than the one F and J pose. Fixing the length at one keeps every boundary a single findable character and leaves F and J to say which character it may be.

The alphabets themselves are configuration rather than obligation: which ones a repository may choose belongs to the configuration surface, while H fixes what any of them must be — ordered, with a definite beginning and end, so that a label can be placed in it and the label after it named. That is what lets a label missing from the middle of a series be evidence of loss rather than of removal, and it is what ends a series without a separate count: a requirement runs out of labels when its alphabet does.

M extends F and J outward. Those two protect a boundary inside one reference; M protects the boundary between two of them. A list is divided before its items are read, so a separator that also divides references is spent on the outer boundary first: what reaches the identifier reader is a fragment ending where the list was cut, and a bare label with no requirement in front of it. Both halves fail quietly — the fragment resolves to the requirement it names without the labels the author attached, and the orphaned label resolves to nothing and is carried as an unresolved reference. As with F, the outcome is a wrong answer rather than an error, so the configuration is refused rather than tolerated. Stating the rule over the dividing character rather than over a particular punctuation mark keeps it true of whatever character holds that role.

### Changelog

- 2026-08-14 | 09f5a257 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-14 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: an assertion separator may not also be the character dividing two references (M)
- 2026-08-13 | d83f4fd6 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-13 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: repoint G's placeholder, which named a requirement that has since been retired itself
- 2026-08-12 | d6d44bc9 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-12 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: H states what any label alphabet must be, not which ones exist; retire I
- 2026-08-12 | c7541313 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | e4e4a5fc | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-12 | 0ba5e8b6 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | 534a01d7 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | 3632edb9 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: separators are exactly one character (K)
- 2026-08-08 | 7a2823ed | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-08 | 427d0f5f | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | 7857498c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | e04a4e37 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-05-11 | e04a4e37 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize term forms, update hash
- 2026-05-11 | - | - | Developer (<dev@example.com>) | Initial authoring: introduce explicit case-style vocabulary and configurable assertion separator.

*End* *A Repository's Identifier Grammar* | **Hash**: 09f5a257
---

## REQ-d00270: Single-Authority Identifier Grammar Derivation

**Level**: dev | **Status**: Superseded | **Implements**: REQ-p00002

This requirement stated an implementation structure rather than a property of the tool. Deriving the identifier grammar in one place is an engineering rule, and it lives with the other such rules rather than as an obligation the tool can be measured against. The one property it carried that is observable — that each repository's grammar applies only to that repository's identifiers — is REQ-d00251-L. Which strings a configuration admits, and what becomes of a string spelled any other way, are REQ-d00212-G and REQ-d00212-R.

### Assertions

A. [Removed - stated where a derivation lives rather than an obligation the tool meets. Single-authority derivation is an engineering rule and is recorded with the others; what a configuration admits is REQ-d00212-G.]

B. [Removed - an interface rule about the implementation, measurable only by reading it. The observable consequence is REQ-d00212-G.]

C. [Removed - prescribed how a surface obtains its patterns. What it must then answer is REQ-d00212-G, and what an inadmissible spelling may do is REQ-d00212-R.]

D. [Removed - one configuration admitting one spelling is REQ-d00212-G, which every deciding surface answers under alike.]

E. [Removed - carried by REQ-d00251-L.]

F. [Removed - a rule about an optimisation, not about an answer. A string an admitting configuration spells is resolvable under REQ-d00212-G however a surface narrows candidates first.]

G. [Removed - carried by REQ-d00212-R, which admits one spelling and lets any other resolve to nothing.]

### Changelog

- 2026-08-13 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: reduce the retired assertions to placeholders naming what carries each obligation now, and delete a Rationale arguing in the present tense for assertions that no longer oblige anything
- 2026-08-10 | d3233556 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-10 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: D scoped to deciding surfaces; add F (pre-filter contract) and G (component case is spelling)
- 2026-08-08 | 2e02bcf7 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: sync changelog hash
- 2026-08-09 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: single-authority derivation for the whole identifier grammar

*End* *Single-Authority Identifier Grammar Derivation* | **Hash**: c8cb35b9
---
