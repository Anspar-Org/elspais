"""Pydantic schema for .elspais.toml configuration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


# Implements: REQ-d00212-J
class ProjectConfig(_StrictModel):
    namespace: str = "REQ"
    name: str | None = None


class ComponentConfig(_StrictModel):
    style: str = "numeric"
    digits: int = 5
    leading_zeros: bool = True
    pattern: str | None = None
    max_length: int | None = None


class AssertionConfig(_StrictModel):
    label_style: str = "uppercase"
    max_count: int = 26
    zero_pad: bool | None = None
    multi_separator: str | None = None


# Implements: REQ-d00212-G
class IdPatternsConfig(_StrictModel):
    canonical: str = "{namespace}-{level.letter}{component}"
    aliases: dict[str, str] = Field(default_factory=lambda: {"short": "{level.letter}{component}"})
    component: ComponentConfig = Field(default_factory=ComponentConfig)
    assertions: AssertionConfig = Field(default_factory=AssertionConfig)
    separators: list[str] = Field(default_factory=lambda: ["-", "_"])
    prefix_optional: bool = False


# Implements: REQ-d00212-H
class HierarchyConfig(_StrictModel):
    cross_repo_implements: bool | None = None
    allow_structural_orphans: bool | None = None
    allow_circular: bool | None = None
    allow_orphans: bool | None = None


class FormatConfig(_StrictModel):
    require_hash: bool | None = None
    require_assertions: bool | None = None
    require_status: bool | None = None
    require_rationale: bool | None = None
    allowed_statuses: list[str] | None = None
    status_roles: dict[str, list[str] | str] | None = None


class RulesConfig(_StrictModel):
    hierarchy: HierarchyConfig = Field(default_factory=HierarchyConfig)
    format: FormatConfig = Field(default_factory=FormatConfig)
    content_rules: list[str] | None = None


class KeywordsSearchConfig(_StrictModel):
    min_length: int = 3


class ValidationConfig(_StrictModel):
    hash_mode: str = "normalized-text"
    hash_algorithm: str | None = None
    hash_length: int | None = None
    allow_unresolved_cross_repo: bool = False
    strict_hierarchy: bool | None = None


# Implements: REQ-d00212-A
class LevelConfig(_StrictModel):
    rank: int
    letter: str
    display_name: str | None = None
    implements: list[str]


# Implements: REQ-d00212-B
class ScanningKindConfig(_StrictModel):
    directories: list[str] = Field(default_factory=list)
    file_patterns: list[str] = Field(default_factory=list)
    skip_files: list[str] = Field(default_factory=list)
    skip_dirs: list[str] = Field(default_factory=list)


class SpecScanningConfig(ScanningKindConfig):
    directories: list[str] = Field(default_factory=lambda: ["spec"])
    file_patterns: list[str] = Field(default_factory=lambda: ["*.md"])
    index_file: str | None = None


class CodeScanningConfig(ScanningKindConfig):
    directories: list[str] = Field(default_factory=lambda: ["src"])
    source_roots: list[str] | None = None


class TestScanningConfig(ScanningKindConfig):
    __test__ = False  # Prevent pytest collection

    directories: list[str] = Field(default_factory=lambda: ["tests"])
    file_patterns: list[str] = Field(default_factory=lambda: ["test_*.py", "*_test.py"])
    enabled: bool = False
    prescan_command: str = ""
    reference_keyword: str = "Verifies"
    reference_patterns: list[str] = Field(default_factory=list)


class ResultScanningConfig(ScanningKindConfig):
    run_meta_file: str = ""


class JourneyScanningConfig(ScanningKindConfig):
    directories: list[str] = Field(default_factory=lambda: ["spec"])
    file_patterns: list[str] = Field(default_factory=lambda: ["*.md"])


class DocsScanningConfig(ScanningKindConfig):
    directories: list[str] = Field(default_factory=lambda: ["docs"])
    file_patterns: list[str] = Field(default_factory=lambda: ["*.md"])


# Implements: REQ-d00212-C
class ScanningConfig(_StrictModel):
    skip: list[str] = Field(default_factory=list)
    spec: SpecScanningConfig = Field(default_factory=SpecScanningConfig)
    code: CodeScanningConfig = Field(default_factory=CodeScanningConfig)
    test: TestScanningConfig = Field(default_factory=TestScanningConfig)
    result: ResultScanningConfig = Field(default_factory=ResultScanningConfig)
    journey: JourneyScanningConfig = Field(default_factory=JourneyScanningConfig)
    docs: DocsScanningConfig = Field(default_factory=DocsScanningConfig)


# Implements: REQ-d00212-D
class OutputConfig(_StrictModel):
    formats: list[str] = Field(default_factory=list)
    dir: str = ""


# Implements: REQ-d00212-E
class ChangelogRequireConfig(_StrictModel):
    reason: bool = True
    author_name: bool = True
    author_id: bool = True
    change_order: bool = False


class ChangelogConfig(_StrictModel):
    hash_current: bool = True
    present: bool = False
    id_source: str = "gh"
    date_format: str = "iso"
    author_id_format: str = "email"
    allowed_author_ids: str | list[str] = "all"
    require: ChangelogRequireConfig = Field(default_factory=ChangelogRequireConfig)


# Implements: REQ-d00212-K
class AssociateEntryConfig(_StrictModel):
    path: str
    namespace: str


# Implements: REQ-d00212-F
class ElspaisConfig(_StrictModel):
    version: int = 3
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    id_patterns: IdPatternsConfig = Field(alias="id-patterns", default_factory=IdPatternsConfig)
    levels: dict[str, LevelConfig] = Field(
        default_factory=lambda: {
            "prd": LevelConfig(rank=1, letter="p", display_name="Product", implements=["prd"]),
            "ops": LevelConfig(
                rank=2, letter="o", display_name="Operations", implements=["ops", "prd"]
            ),
            "dev": LevelConfig(
                rank=3,
                letter="d",
                display_name="Development",
                implements=["dev", "ops", "prd"],
            ),
        }
    )
    scanning: ScanningConfig = Field(default_factory=ScanningConfig)
    rules: RulesConfig = Field(default_factory=RulesConfig)
    keywords: KeywordsSearchConfig = Field(default_factory=KeywordsSearchConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    changelog: ChangelogConfig = Field(default_factory=ChangelogConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    associates: dict[str, AssociateEntryConfig] = Field(default_factory=dict)
    # Implements: REQ-d00208-C
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        json_schema_extra={"$schema": "https://json-schema.org/draft/2020-12/schema"},
    )
