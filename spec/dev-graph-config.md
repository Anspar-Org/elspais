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

The viewer UI SHALL derive dropdown values and filter labels from `ElspaisConfig` rather than hardcoding them. The Flask template context SHALL include config-derived requirement types, allowed statuses, and user-selectable relationship kinds.

### Assertions

A. The Flask template context SHALL include a `config_types` variable containing requirement type definitions derived from `ElspaisConfig.id_patterns.types`.

B. The Flask template context SHALL include a `config_relationship_kinds` variable listing user-selectable relationship kinds (implements, refines, satisfies).

C. The Flask template context SHALL include a `config_statuses` variable containing allowed statuses from `ElspaisConfig.rules.format.allowed_statuses` when configured.

D. `StatusRolesConfig` SHALL provide a `sort_by_role()` method that orders a list of status strings by role priority (active first, then provisional, aspirational, and retired last), preserving original order within each role group; unknown statuses SHALL be treated as active.

### Changelog

- 2026-07-31 | 58192a4f | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | a9cc41d2 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-04-23 | a9cc41d2 | - | Developer (<dev@example.com>) | Auto-fix: add missing changelog section

*End* *Config-Driven Viewer UI Values* | **Hash**: 58192a4f
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

G. `IdPatternsConfig` SHALL have `separators` and `prefix_optional` fields (moved from `references.defaults`). The `types` and `associated` fields SHALL be removed. The canonical pattern SHALL use `{level.letter}` instead of `{type.letter}`.

H. `HierarchyConfig` SHALL contain only boolean flags (`allow_circular`, `allow_structural_orphans`, `allow_orphans`, `cross_repo_implements`). Per-level implement rules SHALL be defined in `LevelConfig.implements` instead. The model SHALL be strict (`extra="forbid"`).

I. `ReferencesConfig` SHALL contain only `enabled` (bool) and `case_sensitive` (bool). The `defaults` sub-model and `overrides` list SHALL be removed.

J. `ProjectConfig` SHALL contain only `namespace` and `name`. The `version` and `type` fields SHALL be removed.

K. `AssociateEntryConfig` SHALL contain `path` (str) and `namespace` (str). The `git` and `spec` fields SHALL be removed.

L. A `TermsConfig` model SHALL define defined-terms configuration: `output_dir` (str, default "spec/_generated"), `markup_styles` (list[str], default ["*", "**"]), `exclude_files` (list[str], default []), and a nested `severity` field of type `TermsSeverityConfig`. `TermsSeverityConfig` SHALL define 6 severity fields: `duplicate` (default "error"), `undefined` (default "warning"), `unmarked` (default "warning"), `unused` (default "warning"), `bad_definition` (default "error"), `collection_empty` (default "warning"). `ElspaisConfig` SHALL include a `terms` field of type `TermsConfig` with factory default.

M. `FormatConfig` SHALL include a `no_traceability_severity` field (str | None, default None) to configure the severity of code/test files lacking *Traceability* markers.

N. A `_migrate_v3_to_v4` migration SHALL move flat `duplicate_severity`, `undefined_severity`, `unmarked_severity` from `[terms]` into `[terms.severity]` as `duplicate`, `undefined`, `unmarked`. Configs without `[terms]` SHALL pass through unchanged. Configs already having `[terms.severity]` SHALL NOT be double-migrated. `CURRENT_CONFIG_VERSION` SHALL be bumped to 4.

O. The configuration schema SHALL locate each rule setting under the concern it governs, such that a setting's position in the schema identifies which checks it affects.

P. The configuration schema SHALL make the severity of every health check configurable under a single consistent convention.

Q. The configuration schema SHALL express file selection for scanning through a single mechanism, such that exactly one configuration surface determines whether any given file is scanned.

### Rationale

A–N inventory the v3/v4 model shapes; O–Q state the organising invariants those shapes must converge on. Rule settings have drifted into a layout where a setting's location no longer predicts what it governs, some check severities are configurable while others are hardcoded with no stated principle distinguishing them, and "why was this file (not) scanned" can have more than one configuration answer (per-kind skip lists alongside a global skip list, plus pattern lists). O–Q close those gaps as invariants only: candidate mechanisms discussed during design — splitting rules into concern sections such as `[rules.changelog]` and `[rules.status]`, or collapsing file selection into a unified `patterns` list — are proposals, not obligations, and deliberately absent from the assertions. Which existing semantics survive, and how existing configs migrate, is decided at implementation. Current schema shapes that contradict O–Q (including the dual file-selection surfaces described alongside B and C) are conformance-defect territory for later implementation tickets.

### Changelog

- 2026-07-31 | 40849780 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-26: organising invariants for rule-setting location (O), severity configurability (P), and single file-selection mechanism (Q)
- 2026-07-31 | a0ea657d | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-03 | e4cda67b | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | db4ad28c | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-03-30 | db4ad28c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: canonicalize term forms
- 2026-03-29 | c75b87f8 | - | Michael Lewis (<michael@anspar.org>) | Add assertion N for config migration v3 to v4

*End* *Config Schema v3 Models* | **Hash**: 40849780
---

## REQ-d00251: Component Style Vocabulary and Assertion Separator

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

The `[id-patterns.component].style` configuration SHALL use an explicit case-convention vocabulary rather than a small set of "custom pattern with hidden default" modes. The `[id-patterns.assertions]` section SHALL gain a configurable separator that decouples the component-to-*Assertion* boundary from any character used inside component names, enabling kebab-case and snake_case component styles to work cleanly with numeric *Assertion* labels.

### Assertions

A. `ComponentConfig.style` SHALL accept exactly six values: `numeric`, `camelCase`, `PascalCase`, `snake_case`, `kebab-case`, and `regex`. The legacy values `named` and `alphanumeric` SHALL be rejected at config validation time.

B. Each case-style SHALL have a fixed default regex: `camelCase` matches `[a-z][a-zA-Z0-9]+`; `PascalCase` matches `[A-Z][a-zA-Z0-9]+`; `snake_case` matches `[a-z][a-z0-9]*(?:_[a-z0-9]+)*`; `kebab-case` matches `[a-z][a-z0-9]*(?:-[a-z0-9]+)*`. The four case-style regexes SHALL NOT be overridable via `pattern`.

C. `style = "regex"` SHALL require a non-empty `pattern` field. Config validation SHALL fail when `style = "regex"` and `pattern` is empty.

D. Rejection of the legacy values `named` and `alphanumeric` SHALL produce a fix-it error message listing the four case styles, the `regex` escape hatch, and the literal pattern that reproduces the legacy default (`[A-Za-z][A-Za-z0-9]+` for `named`, `[A-Z0-9]+` for `alphanumeric`).

E. `AssertionConfig` SHALL include a `separator` field (str, default `"-"`) used (with `re.escape`) as the boundary between the component and the optional *Assertion* suffix in the canonical regex.

F. Ambiguous combinations SHALL be rejected at config validation time: `style = "snake_case"` with `separator = "_"` plus a non-uppercase `label_style`; `style = "kebab-case"` with `separator = "-"` plus a non-uppercase `label_style`. The error message SHALL suggest changing `separator` to a non-overlapping character.

G. [Removed - superseded by REQ-d00268, which extends single-authority derivation from the component sub-pattern to the whole identifier grammar]

H. An *Assertion* label series SHALL be one of two ordered alphabets: `uppercase`, running A to Z; and `numeric`, running 0 upward. Each SHALL have a first label, a successor for every label but its last, and a last label beyond which the series does not extend.

I. An *Assertion* label series configured as `alphanumeric` SHALL run 0 to 9 and then A to Z, giving thirty-six labels in that order.

### Changelog

- 2026-08-10 | e4e4a5fc | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-08-08 | 427d0f5f | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-07-31 | 7857498c | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: update hash
- 2026-05-11 | e04a4e37 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize section header depth
- 2026-05-11 | e04a4e37 | - | Developer (<dev@example.com>) | Auto-fix: canonicalize term forms, update hash
- 2026-05-11 | - | - | Developer (<dev@example.com>) | Initial authoring: introduce explicit case-style vocabulary and configurable assertion separator.

*End* *Component Style Vocabulary and Assertion Separator* | **Hash**: e4e4a5fc
---

## REQ-d00268: Single-Authority Identifier Grammar Derivation

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

A repository's identifier grammar is derived in one place. The canonical identifier pattern, the component sub-pattern, the *Assertion* label pattern, the boundary between component and *Assertion* suffix, and the expansion of a multi-*Assertion* reference all come from one authority reading that repository's identifier configuration, so that every surface which recognises, parses, or expands an identifier answers for exactly the same set of strings.

### Assertions

A. One derivation authority SHALL produce, from a repository's identifier configuration, every regex fragment of that repository's identifier grammar: the canonical identifier pattern, the component sub-pattern, the *Assertion* label pattern, the boundary between the component and the *Assertion* suffix, and the pattern that expands a multi-*Assertion* reference.

B. The derivation authority SHALL expose every fragment it produces through its public interface, and a consumer SHALL obtain a fragment only through that interface.

C. A surface that recognises, parses, or expands an identifier SHALL derive its patterns from the derivation authority rather than compose them.

D. For a given identifier configuration, every surface that recognises an identifier SHALL recognise the same set of strings as an identifier, including the surface that decides which repository of a federation claims an identifier.

E. The derivation authority SHALL derive a repository's identifier grammar from that repository's own identifier configuration, so that a process holding several repositories at once applies each repository's grammar only to that repository.

### Rationale

Federation puts several repositories, each with its own identifier configuration, in one process at once. A surface that treats an identifier as recognised while another treats it as foreign produces a broken reference whose reported severity depends on which surface was asked, and the opportunities for that disagreement grow with every repository a dependency chain pulls in. D is therefore the load-bearing assertion: A, B and C are the structure that makes it hold, and E is what keeps single-authority derivation from collapsing into single configuration — federated repositories occupy disjoint identifier spaces and keep their own configurations.

The governed surfaces are the identifier resolver, the lark grammar builder that recognises identifiers in spec and code, the reference matcher that expands multi-*Assertion* targets, and the federation claim probe that splits a hard broken reference from a presumed-foreign one. B exists because a fragment reachable only as a private internal is an interface by accident: consumers that reach for one are as coupled as consumers that copy it, and neither survives a change to the derivation. The single-authority rule for the component sub-pattern alone is folded into A rather than kept alongside it, so one rule covers the whole grammar.

### Changelog

- 2026-08-08 | 2e02bcf7 | - | Michael Lewis (<michael@anspar.org>) | Auto-fix: sync changelog hash
- 2026-08-09 | - | - | Michael Lewis (<michael@anspar.org>) | TOOL-58: single-authority derivation for the whole identifier grammar

*End* *Single-Authority Identifier Grammar Derivation* | **Hash**: 2e02bcf7
---
