"""Pydantic schema for .elspais.toml configuration."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class ProjectConfig(_StrictModel):
    namespace: str = "REQ"
    name: str | None = None
    version: str | None = None
    type: Literal["core", "associated"] | None = None


class TypeAliases(_StrictModel):
    letter: str


class TypeConfig(_StrictModel):
    level: int
    aliases: TypeAliases


class ComponentConfig(_StrictModel):
    style: str = "numeric"
    digits: int = 5
    leading_zeros: bool = True
    pattern: str | None = None


class AssertionConfig(_StrictModel):
    label_style: str = "uppercase"
    max_count: int = 26
    zero_pad: bool | None = None
    multi_separator: str | None = None


class IdPatternsConfig(_StrictModel):
    canonical: str = "{namespace}-{type.letter}{component}"
    aliases: dict[str, str] = Field(default_factory=lambda: {"short": "{type.letter}{component}"})
    types: dict[str, TypeConfig] = Field(
        default_factory=lambda: {
            "prd": TypeConfig(level=1, aliases=TypeAliases(letter="p")),
            "ops": TypeConfig(level=2, aliases=TypeAliases(letter="o")),
            "dev": TypeConfig(level=3, aliases=TypeAliases(letter="d")),
        }
    )
    component: ComponentConfig = Field(default_factory=ComponentConfig)
    assertions: AssertionConfig = Field(default_factory=AssertionConfig)
    associated: dict[str, Any] | None = None


class SpecConfig(_StrictModel):
    directories: list[str] = Field(default_factory=lambda: ["spec"])
    patterns: list[str] = Field(default_factory=lambda: ["*.md"])
    skip_files: list[str] = Field(default_factory=list)
    skip_dirs: list[str] = Field(default_factory=list)
    index_file: str | None = None


class HierarchyConfig(_StrictModel):
    dev: list[str] = Field(default_factory=lambda: ["ops", "prd"])
    ops: list[str] = Field(default_factory=lambda: ["prd"])
    prd: list[str] = Field(default_factory=list)
    cross_repo_implements: bool | None = None
    allow_structural_orphans: bool | None = None
    allow_circular: bool | None = None
    allow_orphans: bool | None = None
    model_config = ConfigDict(extra="allow", frozen=True, populate_by_name=True)


class FormatConfig(_StrictModel):
    require_hash: bool | None = None
    require_assertions: bool | None = None
    require_status: bool | None = None
    require_rationale: bool | None = None
    allowed_statuses: list[str] | None = None
    status_roles: dict[str, list[str] | str] | None = None
    model_config = ConfigDict(extra="allow", frozen=True, populate_by_name=True)


class RulesConfig(_StrictModel):
    hierarchy: HierarchyConfig = Field(default_factory=HierarchyConfig)
    format: FormatConfig = Field(default_factory=FormatConfig)
    content_rules: list[str] | None = None
    model_config = ConfigDict(extra="allow", frozen=True, populate_by_name=True)


class TestingConfig(_StrictModel):
    enabled: bool = False
    test_dirs: list[str] = Field(default_factory=lambda: ["tests"])
    skip_dirs: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=lambda: ["test_*.py", "*_test.py"])
    result_files: list[str] = Field(default_factory=list)
    run_meta_file: str = ""
    reference_patterns: list[str] = Field(default_factory=list)
    reference_keyword: str = "Verifies"
    prescan_command: str = ""


class IgnoreSchemaConfig(_StrictModel):
    global_: list[str] = Field(
        alias="global",
        default_factory=lambda: [
            "node_modules",
            ".git",
            "__pycache__",
            "*.pyc",
            ".venv",
            ".env",
        ],
    )
    spec: list[str] = Field(default_factory=lambda: ["README.md", "INDEX.md"])
    code: list[str] = Field(default_factory=lambda: ["*_test.py", "conftest.py", "test_*.py"])
    test: list[str] = Field(default_factory=lambda: ["fixtures/**", "__snapshots__"])


class KeywordsConfig(_StrictModel):
    implements: list[str] = Field(default_factory=lambda: ["Implements", "IMPLEMENTS"])
    verifies: list[str] = Field(default_factory=lambda: ["Verifies", "VERIFIES"])
    refines: list[str] = Field(default_factory=lambda: ["Refines", "REFINES"])
    satisfies: list[str] = Field(default_factory=lambda: ["Satisfies", "SATISFIES"])


class ReferenceDefaultsConfig(_StrictModel):
    separators: list[str] = Field(default_factory=lambda: ["-", "_"])
    case_sensitive: bool = False
    prefix_optional: bool = False
    comment_styles: list[str] = Field(default_factory=lambda: ["#", "//", "--"])
    keywords: KeywordsConfig = Field(default_factory=KeywordsConfig)
    multi_assertion_separator: str | None = None


class ReferencesConfig(_StrictModel):
    defaults: ReferenceDefaultsConfig = Field(default_factory=ReferenceDefaultsConfig)
    overrides: list[dict[str, Any]] = Field(default_factory=list)


class KeywordsSearchConfig(_StrictModel):
    min_length: int = 3


class ValidationConfig(_StrictModel):
    hash_mode: str = "normalized-text"
    allow_unresolved_cross_repo: bool = False
    strict_hierarchy: bool | None = None


class GraphConfig(_StrictModel):
    satellite_kinds: list[str] = Field(default_factory=lambda: ["assertion", "result"])


class ChangelogConfig(_StrictModel):
    enforce: bool = True
    require_present: bool = False
    id_source: str = "gh"
    date_format: str = "iso"
    require_change_order: bool = False
    require_reason: bool = True
    require_author_name: bool = True
    require_author_id: bool = True
    author_id_format: str = "email"
    allowed_author_ids: str | list[str] = "all"


class DirectoriesConfig(_StrictModel):
    spec: list[str] | str | None = None
    code: list[str] | str = Field(default_factory=lambda: ["src"])
    docs: list[str] | str = Field(default_factory=lambda: ["docs"])
    ignore: list[str] = Field(default_factory=list)


class TraceabilityConfig(_StrictModel):
    scan_patterns: list[str] = Field(default_factory=list)
    source_roots: list[str] | None = None


class AssociateEntryConfig(_StrictModel):
    path: str
    git: str | None = None
    spec: str | None = None


class CoreConfig(_StrictModel):
    path: str
    spec: str | None = None


class AssociatedConfig(_StrictModel):
    prefix: str | None = None
    id_range: list[int] | None = None
    enabled: bool | None = None
    position: str | None = None
    format: str | None = None
    length: int | None = None
    separator: str | None = None
    model_config = ConfigDict(extra="allow", frozen=True, populate_by_name=True)


class ElspaisConfig(_StrictModel):
    version: int = 2
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    id_patterns: IdPatternsConfig = Field(alias="id-patterns", default_factory=IdPatternsConfig)
    spec: SpecConfig = Field(default_factory=SpecConfig)
    rules: RulesConfig = Field(default_factory=RulesConfig)
    testing: TestingConfig = Field(default_factory=TestingConfig)
    ignore: IgnoreSchemaConfig = Field(default_factory=IgnoreSchemaConfig)
    references: ReferencesConfig = Field(default_factory=ReferencesConfig)
    keywords: KeywordsSearchConfig = Field(default_factory=KeywordsSearchConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    changelog: ChangelogConfig = Field(default_factory=ChangelogConfig)
    directories: DirectoriesConfig = Field(default_factory=DirectoriesConfig)
    traceability: TraceabilityConfig = Field(default_factory=TraceabilityConfig)
    associates: dict[str, AssociateEntryConfig] = Field(default_factory=dict)
    core: CoreConfig | None = None
    associated: AssociatedConfig | None = None
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    @model_validator(mode="after")
    def check_associated_requires_core(self) -> ElspaisConfig:
        if self.project.type == "associated" and self.core is None:
            raise ValueError(
                "project.type='associated' requires a [core] section "
                "with 'path' to the core repository"
            )
        return self
