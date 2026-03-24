# Graph Configuration Development Requirements

## REQ-d00207: Declarative Config Schema Cleanup

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

All configuration defaults and validation SHALL be provided by the Pydantic `ElspaisConfig` schema. Legacy `DEFAULT_CONFIG` dict and `ConfigLoader` wrapper class SHALL be removed; all consumer code SHALL access configuration via plain dicts produced by `ElspaisConfig.model_dump()`.

## Assertions

A. `DEFAULT_CONFIG` dict SHALL be removed from `config/__init__.py`; all default values SHALL be defined as Pydantic field defaults in `config/schema.py`.

B. `ConfigLoader` class SHALL be removed; `load_config()` SHALL return a plain `dict[str, Any]` produced by `ElspaisConfig.model_validate()` + `model_dump(by_alias=True)`.

C. All consumer code that references `ConfigLoader` (type annotations, imports, `.from_dict()`, `.get_raw()`, `.get()`) SHALL be updated to use plain dicts directly.

*End* *Declarative Config Schema Cleanup* | **Hash**: 8d323813
---

## REQ-d00208: JSON Schema Export for IDE Autocomplete

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

The `ElspaisConfig` Pydantic model SHALL be exportable as a JSON Schema file for IDE autocomplete (e.g., Taplo). A CLI subcommand SHALL generate the schema on demand, and a committed schema file SHALL stay in sync with the model.

## Assertions

A. `elspais config schema` SHALL output the JSON Schema to stdout (or to a file with `--output`), generated from `ElspaisConfig.model_json_schema()`.

B. A committed `src/elspais/config/elspais-schema.json` SHALL match the output of `ElspaisConfig.model_json_schema()`. A CI test SHALL verify this.

C. The generated JSON Schema SHALL include `$schema` and `title` top-level keys.

*End* *JSON Schema Export for IDE Autocomplete* | **Hash**: 2b82ef02
---

## REQ-d00209: Schema-Driven Init Template Generation

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

The `elspais init` command SHALL generate `.elspais.toml` configuration files by walking the `ElspaisConfig` Pydantic model, ensuring generated templates are always in sync with the schema. Hardcoded template strings SHALL be replaced by a schema walker that produces valid TOML from field metadata and defaults.

## Assertions

A. `generate_config("core")` SHALL produce TOML that passes `ElspaisConfig.model_validate()` without error.

B. `generate_config("associated")` SHALL produce TOML that passes `ElspaisConfig.model_validate()` without error when given a valid prefix.

C. The generated TOML SHALL include all sections present in the current hardcoded templates (project, directories, id-patterns, rules, etc.).

D. The generated TOML SHALL include human-readable comments derived from Pydantic field descriptions or the current template comments.

*End* *Schema-Driven Init Template Generation* | **Hash**: 44aeb496
---

## REQ-d00210: Documentation Drift Detection

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

The `elspais doctor` command SHALL detect drift between `ElspaisConfig` Pydantic schema fields and `docs/configuration.md`. Undocumented schema fields and stale documentation sections SHALL be reported as health check findings.

## Assertions

A. `elspais doctor` SHALL include a `docs.config_drift` health check that compares schema top-level sections against documented sections.

B. The drift detection SHALL report undocumented sections (in schema but not in docs) and stale sections (in docs but not in schema).

C. The drift check SHALL pass when all schema sections are documented and no stale sections exist, and fail otherwise.

*End* *Documentation Drift Detection* | **Hash**: eb94434a
---

## REQ-d00211: Config-Driven Viewer UI Values

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

The viewer UI SHALL derive dropdown values and filter labels from `ElspaisConfig` rather than hardcoding them. The Flask template context SHALL include config-derived requirement types, allowed statuses, and user-selectable relationship kinds.

## Assertions

A. The Flask template context SHALL include a `config_types` variable containing requirement type definitions derived from `ElspaisConfig.id_patterns.types`.

B. The Flask template context SHALL include a `config_relationship_kinds` variable listing user-selectable relationship kinds (implements, refines, satisfies).

C. The Flask template context SHALL include a `config_statuses` variable containing allowed statuses from `ElspaisConfig.rules.format.allowed_statuses` when configured.

*End* *Config-Driven Viewer UI Values* | **Hash**: b322b22e
---

## REQ-d00212: Config Schema v3 Models

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002

The `ElspaisConfig` Pydantic schema SHALL be restructured to v3 shape with first-class level definitions, unified scanning configuration, simplified references, and cleaner changelog sub-models. New models SHALL be strict (`extra="forbid"`) and frozen by default.

## Assertions

A. A `LevelConfig` model SHALL define per-level properties: `rank` (int), `letter` (str), `display_name` (str, optional), and `implements` (list[str]). Unknown fields SHALL be rejected.

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

L. A `TermsConfig` model SHALL define defined-terms configuration: `output_dir` (str, default "spec/_generated"), `duplicate_severity` (str, default "error"), `undefined_severity` (str, default "warning"), `unmarked_severity` (str, default "warning"). `ElspaisConfig` SHALL include a `terms` field of type `TermsConfig` with factory default.

*End* *Config Schema v3 Models* | **Hash**: 0cee5e84
---
