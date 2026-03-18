# Declarative Config Schema and Versioned Migration — Design

**Date:** 2026-03-17
**Status:** Approved
**Scope:** Full replacement of `ConfigLoader`/`DEFAULT_CONFIG`/argparse with a Pydantic-driven
declarative schema (config) and Tyro-driven CLI generation (commands). These two concerns are
strictly separated.

---

## Problem

Config fields are defined across three independent sources that drift:

- `DEFAULT_CONFIG` dict in `config/__init__.py`
- Hardcoded string template in `commands/init.py`
- `docs/configuration.md`

Consequences:
- Unknown config keys are silently ignored; typos go undetected
- Many fields used in code are absent from `DEFAULT_CONFIG` (e.g. `version`, `associated.prefix`,
  `core.path`, `directories.code`, `traceability.scan_patterns`)
- Cross-field constraints (e.g. status values must match `allowed_statuses`) are validated at
  runtime but not expressed in any schema or surfaced to users
- `_migrate_legacy_patterns()` is a temporary compat shim with no migration system behind it
- argparse setup is a 1000+ line monolith in `cli.py` with no auto-generated help

---

## Solution

Two strictly separated concerns, each with the right tool:

```text
Pydantic    ElspaisConfig schema
              -> validates .elspais.toml (unknown keys, types, cross-field constraints)
              -> model_json_schema() -> JSON Schema -> Taplo IDE autocomplete/validation
              -> drives elspais init template generation
              -> drives docs/configuration.md drift detection
              -> drives viewer UI selectors (status dropdowns, type pickers, etc.)

Tyro        CommandArgs dataclasses
              -> drives CLI --help (auto-updated when args change)
              -> generates subcommand structure

These never mix. Tyro never sees ElspaisConfig. Pydantic never sees CLI args.
TOML files are unchanged — plain human-authored .elspais.toml as today.
```

---

## Section 1: Schema Definition

### New file: `src/elspais/config/schema.py`

Pydantic `BaseModel` classes define every valid config field. Python naming uses underscores;
TOML hyphenated keys (e.g. `id-patterns`) are handled via Pydantic field aliases — no
normalization pass is needed (see Section 2).

```
ElspaisConfig (BaseModel)
  .version: int = 2
  .project: ProjectConfig
      .name: str
      .namespace: str
      .type: Literal["core", "associated"] | None = None
  .id_patterns: IdPatternsConfig
      .types: dict[str, TypeConfig]
      .assertions: AssertionConfig
      .component: ComponentConfig
  .spec: SpecConfig
      .directories: list[str]
      .patterns: list[str]
      .skip_dirs: list[str]
      .skip_files: list[str]
  .rules: RulesConfig
      .hierarchy: HierarchyConfig
          .allowed_implements: list[str]
      .format: FormatConfig
          .allowed_statuses: list[str]
          .status_roles: dict[str, str]
          .require_hash: bool
          .require_assertions: bool
          ... etc.
      .traceability: TraceabilityRulesConfig
      .naming: NamingConfig
  .testing: TestingConfig
  .references: ReferencesConfig
      .defaults: ReferenceDefaultsConfig
  .traceability: TraceabilityConfig
  .changelog: ChangelogConfig
  .directories: DirectoriesConfig
      .code: list[str]
      .docs: list[str]
      .ignore: list[str]
  .ignore: IgnoreConfig
  .associates: dict[str, AssociateConfig]
  .core: CoreConfig | None = None        # required when project.type = "associated"
  .associated: AssociatedConfig | None = None
```

Each field has:
- A Python default (replaces `DEFAULT_CONFIG`)
- A type annotation (structural validation)
- A `Field(alias=...)` for any TOML key that uses hyphens (e.g. `alias="id-patterns"`)
- `Field(description="...")` (drives generated `docs/configuration.md`)
- `field_validator` / `model_validator` for cross-field constraints

All models use:

```python
model_config = ConfigDict(
    extra="forbid",        # unknown keys -> ValidationError with field path
    frozen=True,           # immutable after load
    populate_by_name=True, # accept both "id_patterns" and "id-patterns"
)
```

Cross-field constraints expressed in schema (not in a separate post-validation pass):

```python
@model_validator(mode="after")
def check_associated_requires_core(self) -> "ElspaisConfig":
    if self.project.type == "associated" and self.core is None:
        raise ValueError("project.type='associated' requires a [core] section")
    return self

# FormatConfig:
@model_validator(mode="after")
def status_roles_match_allowed(self) -> "FormatConfig":
    unknown = set(self.status_roles) - set(self.allowed_statuses)
    if unknown:
        raise ValueError(f"status_roles references unknown statuses: {unknown}")
    return self
```

Because constraints are in the schema, they are:
- Validated at load time with clear error messages
- Reflected in the exported JSON Schema (where possible via `if/then/else`)
- Available for docs generation

### File layout

```
src/elspais/config/
  schema.py        <- NEW: ElspaisConfig + all nested Pydantic models
  __init__.py      <- GUTTED: load_config() returns ElspaisConfig; migrations live here
                      parse_toml_document() PRESERVED (used by config_cmd, associate_cmd,
                      install_cmd for comment-preserving write-back)
  status_roles.py  <- unchanged
```

`DEFAULT_CONFIG` dict and `ConfigLoader` class are deleted.

---

## Section 2: Config Loading Pipeline

Replaces `load_config()` + `_merge_configs()` + `_apply_env_overrides()` +
`_migrate_legacy_patterns()`:

```text
1. tomlkit.load(.elspais.toml)
   tomlkit.load(.elspais.local.toml) if present
   -> deep_merge(base, local)                  tomlkit kept for write-back
                                               TOML hyphenated keys kept as-is

2. _apply_env_overrides(merged)               ELSPAIS_* env vars applied to dict
   (preserved, operates on raw hyphenated dict — no change in behaviour)

3. version = merged.get("version", 1)
   for v in range(version, CURRENT_VERSION):
       merged = MIGRATIONS[v](merged)          version-gated, sequential
   (see Section 3)

4. ElspaisConfig.model_validate(merged, by_alias=True)
                                               Pydantic resolves hyphens via aliases:
                                               "id-patterns" -> id_patterns field
                                               Validates:
                                               - unknown keys (extra="forbid")
                                               - wrong types
                                               - cross-field constraints
                                               -> ValidationError with field path on failure

5. return ElspaisConfig instance
```

No `normalize_section_keys()` step — Pydantic aliases handle hyphen/underscore translation
natively. `model_dump(by_alias=True)` returns hyphenated keys, preserving backward
compatibility for the Phase 1 shim (see Section 10).

`get_config()` per-command calls are removed. Config is loaded once in `main()` and passed
as a typed parameter to each command's `run(args, config)`.

---

## Section 3: Version-Gated Migration System

Replaces `_migrate_legacy_patterns()`:

```python
CURRENT_VERSION = 2

MIGRATIONS: dict[int, Callable[[dict], dict]] = {
    1: migrate_v1_to_v2,   # [patterns] -> [id_patterns] (current shim, formalized)
    # 2: migrate_v2_to_v3, # future migrations added here
}
```

Each migration is a pure `dict -> dict` function. Applied sequentially before Pydantic
validation. Adding a future migration = one new dict entry + one new function.

Configs without `version` are treated as v1 (current behaviour preserved).

---

## Section 4: CLI Architecture

All argparse setup in `cli.py` is replaced by Tyro. Tyro generates CLI and `--help` from
dataclass annotations and docstrings.

### Separation of concerns

```text
CLI args   = what operation to perform, how to perform it
TOML file  = what the graph looks like
```

These never cross. There is no `--set` flag, no CLI-to-config override path. If a user
needs a different config, they use `.elspais.local.toml` or `-C <directory>`.

Example: `elspais viewer --branch feature-x`
- `--branch` is a `ViewerArgs` field (Tyro) — tells the viewer which git context to show
- It is NOT a config override — the graph config still comes from `.elspais.toml`

### File layout

```
src/elspais/
  cli.py              <- REPLACED: tyro.cli(GlobalArgs) is the new main()
  commands/
    args.py           <- NEW: all subcommand dataclasses
    *.py              <- business logic unchanged; receives (args, config) parameters
```

### Args structure

```python
@dataclass
class GlobalArgs:
    """elspais — requirements traceability tool."""
    command: ValidateArgs | FixArgs | SummaryArgs | HealthArgs | ViewerArgs | ...
    config: Path = Path(".elspais.toml")
    directory: Path | None = None
    verbose: bool = False
    quiet: bool = False
```

### Command signature

```python
# Before:
def run(args: argparse.Namespace) -> int:
    config = get_config(args.config, overrides=args.config_overrides)
    ...

# After:
def run(args: ValidateArgs, config: ElspaisConfig) -> int:
    ...
```

Global flags (`-C`, `--config`, `--verbose`, `--quiet`) remain as Tyro fields in
`GlobalArgs` — they control which config file to load and operational behaviour, not graph
content.

### Deleted

- `--set key=value` flag (no replacement; use `.elspais.local.toml` for overrides)
- `config_overrides` threaded through argparse namespace

---

## Section 5: Init Template Generation

`generate_config()` in `commands/init.py` replaces its hardcoded string with a schema walker:

```text
walk ElspaisConfig Pydantic model:
  field name          -> TOML key (underscores back to hyphens where needed)
  field default       -> TOML value
  Field(description)  -> inline comment above the key
  nested model        -> TOML section header [section]
  Optional fields     -> commented-out in template
  Literal types       -> comment shows allowed values
```

`elspais init` is always in sync with the schema. No manual template maintenance.

---

## Section 6: JSON Schema Export + IDE Support

```python
schema = ElspaisConfig.model_json_schema()
# Write to: src/elspais/config/elspais-schema.json
```

This JSON Schema file enables:

- **Taplo** (TOML language server for VS Code, Neovim, Emacs, etc.) — hover docs, inline
  validation of `.elspais.toml` as the user types
- **SchemaStore** — publish once, zero-config IDE support for all users
- **`elspais config schema`** — new command that prints the JSON Schema

The JSON Schema is generated at build time and committed to the repo. It is regenerated
automatically when the schema changes (enforced by a test that compares the committed file
to `model_json_schema()` output).

**Known limitation:** `dict[str, TypeConfig]` and `dict[str, AssociateConfig]` fields
(open-keyed dicts) produce a generic JSON Schema object — Taplo can validate the value
structure but cannot autocomplete user-defined keys (type codes, associate names). This is
acceptable: IDE key-completion for these sections is a future concern, not part of this
feature. Shell tab completion for CLI commands is handled separately by Tyro's built-in
completion support (replacing the existing `completion.py` argparse integration).

---

## Section 7: Viewer UI Integration

The loaded `ElspaisConfig` instance is the runtime source of truth for viewer UI elements.
No hardcoded value lists in frontend code:

```text
config.rules.format.allowed_statuses     -> status dropdown options
config.id_patterns.types.keys()          -> type selector options
config.rules.hierarchy.allowed_implements -> relationship type picker
config.changelog.allowed_author_ids      -> author selector (if configured)
```

If a project adds a custom status to `.elspais.toml`, the viewer dropdown updates
automatically. UI selections are always consistent with what validation will accept.

---

## Section 8: Docs Drift Detection

Added to `elspais doctor`:

```text
walk ElspaisConfig Pydantic model   -> set of all field paths + descriptions
scan docs/configuration.md          -> set of documented field paths
report: fields in schema but not in docs  (undocumented)
report: fields in docs but not in schema  (stale)
```

Enforced in CI. Docs remain hand-authored; the check prevents drift.
Docs are brought up to date before the CI check is enabled (not triggered by Phase 1).

---

## Section 9: Consumer Migration

138 `config.get()` call sites → typed attribute access, migrated in one pass:

```python
# Before
config.get("spec", {}).get("directories", [])
config.get("rules", {}).get("format", {})
config.get("id-patterns", {})

# After
config.spec.directories
config.rules.format
config.id_patterns
```

Helper functions `get_project_name()`, `get_spec_directories()`, `get_code_directories()`
become dead code and are deleted. Their callers are updated to use typed field access directly.

`build_graph()` signature: `config=raw_config` (dict) → `config=config` (ElspaisConfig).

---

## Section 10: Testing Strategy

**New dependency:** `pydantic>=2.0` added to `pyproject.toml` core dependencies.

The existing ~3000 tests are the primary safety net. Implementation proceeds in phases, with
the full suite run between each:

1. Add `schema.py` + new loader with temporary shim: `load_config()` returns `ElspaisConfig`
   but wraps it in a `ConfigLoader`-compatible adapter that calls `model_dump(by_alias=True)`
   to produce the hyphenated dict callers expect. All 138 `config.get("id-patterns", {})`
   calls continue to work unchanged → suite must pass
2. Migrate consumers (138 call sites) → unit tests catch per-command regressions
3. Replace CLI (argparse → Tyro) → e2e tests catch regressions
4. Delete `ConfigLoader`, `DEFAULT_CONFIG`, argparse setup, `--set` flag
5. Enable docs drift CI check (after docs are complete)

### New tests to add

- Unknown key in TOML → `ValidationError` with field path
- Type mismatch → `ValidationError` with field path
- Cross-field constraint violations (e.g. `status_roles` references unknown status)
- v1 → v2 migration roundtrip
- Schema → init template → re-parse roundtrip (generated config validates cleanly)
- JSON Schema committed file matches `model_json_schema()` output
- Docs drift detection: schema field not in docs → reported; stale doc field → reported
- Env override applied correctly to typed config

---

## Deleted artifacts

| Artifact | Replacement |
|----------|-------------|
| `DEFAULT_CONFIG` dict | Pydantic field defaults in `schema.py` |
| `ConfigLoader` class | `ElspaisConfig` Pydantic model |
| `_merge_configs()` | `deep_merge()` utility (preserved, internal) |
| `_migrate_legacy_patterns()` | `migrate_v1_to_v2()` in `MIGRATIONS` dict |
| `_apply_env_overrides()` | Preserved, applied to dict before `model_validate()` |
| `get_config()` per-command calls | `load_config()` once in `main()`, passed down |
| argparse setup in `cli.py` | `tyro.cli(GlobalArgs)` |
| `--set key=value` flag | `.elspais.local.toml` overlay files |
| Hardcoded init template string | Schema walker in `generate_config()` |
| `validate_project_config()` post-pass | `@model_validator` on `ElspaisConfig` |

## Preserved artifacts

| Artifact | Reason |
|----------|--------|
| `parse_toml_document()` | Used by `config_cmd`, `associate_cmd`, `install_cmd` for comment-preserving write-back |
| `tomlkit` dependency | Write-back path; also used for initial load |
| `_apply_env_overrides()` | Applied to dict before Pydantic validation |
| `status_roles.py` | Unchanged |
