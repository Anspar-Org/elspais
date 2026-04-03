"""Pydantic schema for .elspais.toml configuration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


# Implements: REQ-d00212-J
class ProjectConfig(_StrictModel):
    namespace: str = "REQ"
    name: str = ""


class ComponentConfig(_StrictModel):
    style: str = "numeric"
    digits: int = 5
    leading_zeros: bool = True
    pattern: str = ""
    max_length: int = 0


class AssertionConfig(_StrictModel):
    label_style: str = "uppercase"
    max_count: int = 26
    zero_pad: bool = False
    multi_separator: str = "+"


class AssociatedPatternConfig(_StrictModel):
    enabled: bool = False
    position: str = "after_prefix"
    format: str = "uppercase"
    length: int = 3
    separator: str = "-"


# Implements: REQ-d00212-G
class IdPatternsConfig(_StrictModel):
    canonical: str = "{namespace}-{level.letter}{component}"
    aliases: dict[str, str] = Field(default_factory=lambda: {"short": "{level.letter}{component}"})
    component: ComponentConfig = Field(default_factory=ComponentConfig)
    assertions: AssertionConfig = Field(default_factory=AssertionConfig)
    associated: AssociatedPatternConfig = Field(default_factory=AssociatedPatternConfig)
    separators: list[str] = Field(default_factory=lambda: ["-", "_"])
    prefix_optional: bool = False


# Implements: REQ-d00212-H
class HierarchyConfig(_StrictModel):
    cross_repo_implements: bool = False
    allow_structural_orphans: bool = False
    allow_circular: bool = False
    allow_orphans: bool = False


# Implements: REQ-d00212-M
class FormatConfig(_StrictModel):
    require_hash: bool = False
    require_assertions: bool = False
    require_status: bool = False
    require_rationale: bool = False
    status_roles: dict[str, list[str] | str] = Field(
        default_factory=lambda: {
            "active": ["Active"],
            "provisional": ["Draft", "Proposed"],
            "aspirational": ["Roadmap", "Future", "Idea"],
            "retired": ["Deprecated", "Superseded", "Rejected"],
        }
    )
    no_assertions_severity: str = "warning"
    no_traceability_severity: str = "warning"


class CoverageSeverityConfig(_StrictModel):
    """Severity mapping for a single coverage dimension's tier states.

    Each tier maps to a severity: 'ok', 'info', 'warning', or 'error'.
    """

    full_direct: str = "ok"
    full_indirect: str = "info"
    partial: str = "warning"
    none: str = "error"
    failing: str = "error"


def _uat_severity() -> CoverageSeverityConfig:
    return CoverageSeverityConfig(none="info", partial="info")


class CoverageConfig(_StrictModel):
    """Coverage severity configuration for all 5 dimensions."""

    implemented: CoverageSeverityConfig = Field(default_factory=CoverageSeverityConfig)
    tested: CoverageSeverityConfig = Field(default_factory=CoverageSeverityConfig)
    verified: CoverageSeverityConfig = Field(
        default_factory=lambda: CoverageSeverityConfig(none="warning")
    )
    uat_coverage: CoverageSeverityConfig = Field(default_factory=_uat_severity)
    uat_verified: CoverageSeverityConfig = Field(default_factory=_uat_severity)


class ReferenceSeverityConfig(_StrictModel):
    """Severity levels for status-based reference checks."""

    retired: str = "warning"
    provisional: str = "info"
    aspirational: str = "info"


class RulesConfig(_StrictModel):
    hierarchy: HierarchyConfig = Field(default_factory=HierarchyConfig)
    format: FormatConfig = Field(default_factory=FormatConfig)
    coverage: CoverageConfig = Field(default_factory=CoverageConfig)
    references: ReferenceSeverityConfig = Field(default_factory=ReferenceSeverityConfig)
    content_rules: list[str] = Field(default_factory=list)
    protected_branches: list[str] = Field(default=["main", "master"])


class KeywordsSearchConfig(_StrictModel):
    min_length: int = 3


class ValidationConfig(_StrictModel):
    hash_mode: str = "normalized-text"
    hash_algorithm: str = "sha256"
    hash_length: int = 8
    allow_unresolved_cross_repo: bool = False
    strict_hierarchy: bool = False


# Implements: REQ-d00212-A
class LevelConfig(_StrictModel):
    rank: int
    letter: str
    display_name: str = ""
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
    index_file: str = ""


class CodeScanningConfig(ScanningKindConfig):
    directories: list[str] = Field(default_factory=lambda: ["src"])
    source_roots: list[str] = Field(default_factory=lambda: ["src", ""])


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


class CoverageScanningConfig(ScanningKindConfig):
    """Configuration for code coverage report scanning."""

    directories: list[str] = Field(default_factory=lambda: ["."])


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
    coverage: CoverageScanningConfig = Field(default_factory=CoverageScanningConfig)
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


# Implements: REQ-d00212-L
class TermsSeverityConfig(_StrictModel):
    """Severity levels for defined-terms health checks."""

    duplicate: str = "error"
    undefined: str = "warning"
    unmarked: str = "warning"
    unused: str = "warning"
    bad_definition: str = "error"
    collection_empty: str = "warning"
    canonical_form: str = "warning"
    changed: str = "warning"  # definitions changed with unresolved review


# Implements: REQ-d00212-L
class TermsConfig(_StrictModel):
    """Configuration for defined terms feature."""

    output_dir: str = "spec/_generated"
    markup_styles: list[str] = Field(default_factory=lambda: ["*", "**"])
    exclude_files: list[str] = Field(default_factory=list)
    severity: TermsSeverityConfig = Field(default_factory=TermsSeverityConfig)


# Implements: REQ-d00212-F
class ElspaisConfig(_StrictModel):
    version: int = 4
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
    terms: TermsConfig = Field(default_factory=TermsConfig)
    associates: dict[str, AssociateEntryConfig] = Field(default_factory=dict)
    stats: str = Field(default="", description="File path for MCP tool usage statistics")
    cli_ttl: int = Field(
        default=30,
        description="CLI daemon TTL in minutes (>0=auto-start, 0=disabled, <0=no timeout)",
    )
    # Implements: REQ-d00208-C
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        json_schema_extra={"$schema": "https://json-schema.org/draft/2020-12/schema"},
    )
