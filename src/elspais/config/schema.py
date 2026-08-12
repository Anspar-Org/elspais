"""Pydantic schema for .elspais.toml configuration."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Hex-color and namespace patterns live in the utilities lib so all consumers
# share a single regex. See `utilities/color.py` and `utilities/patterns.py`.
from elspais.utilities.color import validate_hex_color as _validate_hex_color
from elspais.utilities.patterns import validate_namespace as _validate_namespace


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


# Implements: REQ-d00212-J
class ProjectConfig(_StrictModel):
    # Defaults below are sentinels for the no-config-file path (used by the
    # MCP server in degraded mode when invoked outside any elspais project).
    # `load_config()` rejects empty or missing `name` *and* `namespace` at the
    # TOML-parsing boundary, so these defaults only surface when `get_config()`
    # returns `config_defaults()` because no `.elspais.toml` was discoverable.
    # Keeping non-empty values here means callers that inline
    # `config["project"]["name"|"namespace"]` never see "" silently.
    namespace: str = "REQ"
    name: str = "example"
    color: str | None = None

    @field_validator("namespace")
    @classmethod
    def _v_namespace(cls, v):
        return _validate_namespace(v)

    @field_validator("color")
    @classmethod
    def _v_color(cls, v):
        return _validate_hex_color(v)


_LEGACY_STYLE_MIGRATION = {
    "named": "[A-Za-z][A-Za-z0-9]+",
    "alphanumeric": "[A-Z0-9]+",
}


def _legacy_style_message(legacy: str) -> str:
    """Build the migration error message for the deprecated style names.

    Mentions all four case styles, the regex escape hatch, and the literal
    pattern that reproduces the legacy default.
    """
    return (
        f'component.style "{legacy}" is no longer supported.\n\n'
        "Choose one of:\n"
        "  - camelCase  (userAuth)\n"
        "  - PascalCase (UserAuth)\n"
        "  - snake_case (user_auth)\n"
        "  - kebab-case (user-auth)\n"
        '  - regex      (custom — requires `pattern = "..."`)\n\n'
        "For your existing config, the equivalent is:\n"
        '  style = "regex"\n'
        f'  pattern = "{_LEGACY_STYLE_MIGRATION[legacy]}"'
    )


# Implements: REQ-d00251-A
class ComponentConfig(_StrictModel):
    style: Literal["numeric", "camelCase", "PascalCase", "snake_case", "kebab-case", "regex"] = (
        "numeric"
    )
    digits: int = 5
    leading_zeros: bool = True
    pattern: str = ""
    max_length: int = 0

    @field_validator("style", mode="before")
    @classmethod
    def _reject_legacy_styles(cls, value):
        if isinstance(value, str) and value in _LEGACY_STYLE_MIGRATION:
            raise ValueError(_legacy_style_message(value))
        return value


# Implements: REQ-d00251-E, REQ-d00251-K
class AssertionConfig(_StrictModel):
    label_style: str = "uppercase"
    max_count: int = 26
    zero_pad: bool = False
    # A boundary is a character (REQ-d00251-K). The length is constrained on
    # the field rather than in the model validator so the exported JSON schema
    # carries it too, and an editor rejects what the runtime would reject.
    separator: str = Field(default="-", min_length=1, max_length=1)
    multi_separator: str = Field(default="+", min_length=1, max_length=1)


class AssociatedPatternConfig(_StrictModel):
    enabled: bool = False
    position: str = "after_prefix"
    format: str = "uppercase"
    length: int = 3
    separator: str = "-"


_PRINTABLE = frozenset(chr(code) for code in range(0x21, 0x7F))


def _in_set_chars(items) -> set[str]:
    """The printable characters a parsed ``[...]`` set admits."""
    negated = False
    collected: set[str] = set()
    for op, av in items:
        name = str(op)
        if name == "NEGATE":
            negated = True
        elif name == "LITERAL":
            collected.add(chr(av))
        elif name == "RANGE":
            low, high = av
            collected.update(chr(code) for code in range(low, high + 1))
        elif name == "CATEGORY":
            collected |= _category_chars(str(av))
        elif name == "IN":  # nested set (character class union)
            collected |= _in_set_chars(av)
    collected &= _PRINTABLE
    return (_PRINTABLE - collected) if negated else collected


def _category_chars(category: str) -> set[str]:
    digits = set("0123456789")
    word = digits | set("abcdefghijklmnopqrstuvwxyz") | set("ABCDEFGHIJKLMNOPQRSTUVWXYZ") | {"_"}
    if category.endswith("CATEGORY_DIGIT"):
        return digits
    if category.endswith("CATEGORY_NOT_DIGIT"):
        return _PRINTABLE - digits
    if category.endswith("CATEGORY_WORD"):
        return word
    if category.endswith("CATEGORY_NOT_WORD"):
        return _PRINTABLE - word
    if category.endswith("CATEGORY_SPACE"):
        return set()  # no printable character in 0x21..0x7E is whitespace
    if category.endswith("CATEGORY_NOT_SPACE"):
        return set(_PRINTABLE)
    return set(_PRINTABLE)  # unknown category: assume it admits anything


def _walk_pattern(parsed, legal: set[str]) -> None:
    for op, av in parsed:
        name = str(op)
        if name == "LITERAL":
            legal.update(_PRINTABLE & {chr(av)})
        elif name == "NOT_LITERAL":
            legal.update(_PRINTABLE - {chr(av)})
        elif name == "IN":
            legal.update(_in_set_chars(av))
        elif name == "ANY":
            legal.update(_PRINTABLE)
        elif name in ("MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT"):
            _minimum, maximum, sub = av
            if maximum:
                _walk_pattern(sub, legal)
        elif name == "BRANCH":
            for branch in av[1]:
                _walk_pattern(branch, legal)
        elif name == "SUBPATTERN":
            _walk_pattern(av[-1], legal)
        elif name == "ATOMIC_GROUP":
            _walk_pattern(av, legal)
        elif name == "GROUPREF_EXISTS":
            for sub in av[1:]:
                if sub:
                    _walk_pattern(sub, legal)
        # ASSERT / ASSERT_NOT consume nothing, AT is an anchor, GROUPREF
        # repeats characters already collected -- none add to the alphabet.


def _legal_chars(pattern: str) -> set[str]:
    """The printable characters ``pattern`` can match at some position.

    A component style may be an arbitrary user-supplied regex, so the set
    is read off the pattern's own parse tree rather than guessed by trying
    sample strings against it: a probe can only speak for the positions and
    lengths it happens to cover, and every character that is legal only
    after the first position, or only in a match longer than the probe,
    would be missed and wrongly offered as a separator.
    """
    import re as _re

    try:  # Python 3.11+
        from re import _parser as _regex_parser
    except ImportError:  # pragma: no cover - Python 3.10
        import sre_parse as _regex_parser  # type: ignore[no-redef]

    _re.compile(pattern)  # reject a malformed pattern here, as before
    legal: set[str] = set()
    _walk_pattern(_regex_parser.parse(pattern), legal)
    return legal


_LABEL_STYLE_PATTERNS = {
    "uppercase": r"[A-Z]",
    "numeric": r"[0-9]{1,2}",
    "alphanumeric": r"[0-9A-Z]",
    "numeric_1based": r"[1-9][0-9]?",
}


# Implements: REQ-d00212-G, REQ-d00251-C, REQ-d00251-F, REQ-d00251-J, REQ-d00251-K
class IdPatternsConfig(_StrictModel):
    canonical: str = "{namespace}-{level.letter}{component}"
    aliases: dict[str, str] = Field(default_factory=lambda: {"short": "{level.letter}{component}"})
    component: ComponentConfig = Field(default_factory=ComponentConfig)
    assertions: AssertionConfig = Field(default_factory=AssertionConfig)
    associated: AssociatedPatternConfig = Field(default_factory=AssociatedPatternConfig)

    @model_validator(mode="after")
    def _validate_style_pattern_and_separator(self):
        # REQ-d00251-C: regex style requires non-empty pattern
        if self.component.style == "regex" and not self.component.pattern:
            raise ValueError(
                'component.style = "regex" requires a non-empty `pattern` field.\n'
                'Example: pattern = "[A-Z][a-zA-Z0-9]+"'
            )
        # REQ-d00251-F+J: a separator drawn from the characters the part
        # before it may itself contain is absorbed by that part, taking the
        # label with it -- the reference then resolves to a different
        # requirement instead of failing.
        from elspais.utilities.patterns import ComponentFormat, component_regex

        component_pattern = component_regex(
            ComponentFormat(
                style=self.component.style,
                digits=self.component.digits,
                leading_zeros=self.component.leading_zeros,
                pattern=self.component.pattern,
            )
        )
        label_pattern = _LABEL_STYLE_PATTERNS.get(self.assertions.label_style, r"[A-Z]")
        component_chars = _legal_chars(component_pattern)
        label_chars = _legal_chars(label_pattern)

        def _suggest(taken: set[str]) -> str:
            # ":" is deliberately absent: it is reserved out of every
            # configurable pattern element so "::" stays unambiguous as
            # the composite instance-ID joiner (REQ-p00014-S).
            for candidate in ("/", ".", "#", "|", "~"):
                if candidate not in taken:
                    return candidate
            return "/"

        # Both separators are exactly one character by field constraint
        # (REQ-d00251-K), so membership answers the overlap question directly.
        sep_taken = component_chars | label_chars
        separator = self.assertions.separator
        if separator in sep_taken:
            where = "a component" if separator in component_chars else "a label"
            raise ValueError(
                f'assertions.separator is "{separator}", which can '
                f"legally appear in {where} under "
                f'component.style = "{self.component.style}" / '
                f'label_style = "{self.assertions.label_style}".\n'
                f"The component would absorb the separator and the label after it, so "
                f"the reference would resolve to a different requirement rather than "
                f"fail.\n"
                f'Use a character neither can contain, e.g. "{_suggest(sep_taken)}".'
            )
        multi = self.assertions.multi_separator
        if multi in label_chars:
            raise ValueError(
                f'assertions.multi_separator is "{multi}", '
                f"which can legally appear in a label under label_style = "
                f'"{self.assertions.label_style}".\n'
                f"Two labels would run together with no findable boundary.\n"
                f'Use a character a label cannot contain, e.g. "{_suggest(label_chars)}".'
            )
        return self


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

    @field_validator("status_roles")
    @classmethod
    def _v_status_role_values(cls, v: dict[str, Any]) -> dict[str, Any]:
        # Each status name listed here ends up as a key in `.status-badge.{name}`
        # CSS selectors, JS string literals, and `data-key` attributes — same
        # identifier shape as namespaces / level keys.
        for _role, names in (v or {}).items():
            if isinstance(names, list):
                for name in names:
                    _validate_namespace(name)
            elif isinstance(names, str):
                _validate_namespace(names)
        return v


class CoverageSeverityConfig(_StrictModel):
    """Severity mapping for a single coverage dimension's tier states.

    Each tier maps to a severity: 'ok', 'info', 'warning', or 'error'. Tiers
    are the unified vocabulary (REQ-d00258): full / partial / failing / missing.
    """

    full: str = "ok"
    partial: str = "warning"
    failing: str = "error"
    missing: str = "error"


def _uat_severity() -> CoverageSeverityConfig:
    return CoverageSeverityConfig(missing="info")


class CoverageConfig(_StrictModel):
    """Coverage severity configuration for all 5 dimensions."""

    implemented: CoverageSeverityConfig = Field(default_factory=CoverageSeverityConfig)
    tested: CoverageSeverityConfig = Field(default_factory=CoverageSeverityConfig)
    verified: CoverageSeverityConfig = Field(
        default_factory=lambda: CoverageSeverityConfig(missing="warning")
    )
    uat_coverage: CoverageSeverityConfig = Field(default_factory=_uat_severity)
    uat_verified: CoverageSeverityConfig = Field(default_factory=_uat_severity)
    # When True (default), indirect coverage (REFINES-conducted, blanket, and
    # other transitive evidence) credits a dimension's badge/tier state -- the
    # generous footing (REQ-d00069-L). When False, ONLY direct coverage lifts a
    # state; indirect-only coverage reads `missing` (REQ-d00258, Phase 4).
    allow_indirect: bool = True
    # Per-relationship label overrides (REQ-d00258). Keyed by relationship name
    # (implements/verifies/yields/validates/validated); resolved to dimension
    # labels via elspais.config.status_words.get_status_words().
    status_words: dict[str, str] = Field(default_factory=dict)


class ReferenceSeverityConfig(_StrictModel):
    """Severity levels for the reference checks.

    ``unclaimed`` governs references whose target no configured repository
    claims. Noticing one is not the project's decision, but how loudly is:
    a repository may legitimately reference a requirement a sibling has not
    authored yet, and the same finding is advisory to one project and a
    build failure to another.
    """

    retired: str = "warning"
    provisional: str = "info"
    aspirational: str = "info"
    unclaimed: str = "info"


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
    color: str | None = None
    # When true, requirements at this level are expected to have UAT validation
    # (a USER_JOURNEY that Validates them). Absence is then a real gap: reported
    # by health `uat.coverage` + `gaps unvalidated` and rendered red in the
    # viewer. Default false -- absent UAT is neither flagged nor badged.
    expects_validation: bool = False

    @field_validator("color")
    @classmethod
    def _v_color(cls, v):
        return _validate_hex_color(v)


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


# Implements: REQ-d00254-C
class TestTargetConfig(_StrictModel):
    """One test target: how its results + coverage are produced and ingested."""

    __test__ = False  # not a pytest class

    name: str
    cwd: str = ""  # relative to repo root; empty = repo root
    command: str = ""  # optional; omitted in CI (tests already ran)
    reporter: str = ""  # registry format name (e.g. "flutter-machine", "junit", "pytest-json")
    results: str = (
        ""  # glob (relative to cwd) for file-channel reporters; unused for stdout reporters
    )
    coverage: str = ""  # lcov/coverage file (relative to cwd); empty = no coverage
    match: str = "source"  # "source" | "aggregate"
    credit_coverage: str = "off"  # "off" | "tested" | "verified" (lcov_tested dimension)
    min_coverage_fraction: float = 0.0  # [0.0, 1.0]

    @field_validator("match")
    @classmethod
    def _check_match(cls, v: str) -> str:
        if v not in ("source", "aggregate"):
            raise ValueError('match must be "source" or "aggregate"')
        return v

    @field_validator("credit_coverage")
    @classmethod
    def _check_credit(cls, v: str) -> str:
        if v not in ("off", "tested", "verified"):
            raise ValueError('credit_coverage must be "off", "tested", or "verified"')
        return v

    @field_validator("min_coverage_fraction")
    @classmethod
    def _check_frac(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("min_coverage_fraction must be in [0.0, 1.0]")
        return v

    @model_validator(mode="after")
    def _require_reporter(self) -> TestTargetConfig:
        if (self.command or self.results) and not self.reporter:
            raise ValueError("reporter is required when command or results is set")
        return self


class TestScanningConfig(ScanningKindConfig):
    __test__ = False  # Prevent pytest collection

    directories: list[str] = Field(default_factory=lambda: ["tests"])
    file_patterns: list[str] = Field(default_factory=lambda: ["test_*.py", "*_test.py"])
    enabled: bool = False
    prescan_command: str = ""
    reference_keyword: str = "Verifies"
    reference_patterns: list[str] = Field(default_factory=list)
    targets: list[TestTargetConfig] = Field(default_factory=list)


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
    color: str | None = None

    @field_validator("namespace")
    @classmethod
    def _v_namespace(cls, v):
        return _validate_namespace(v)

    @field_validator("color")
    @classmethod
    def _v_color(cls, v):
        return _validate_hex_color(v)


class StatusConfig(_StrictModel):
    """Optional per-status metadata. Keys match status names from status_roles."""

    color: str | None = None
    # None = derive from role (active-role -> True). Explicit value wins.
    expects_implementation: bool | None = None

    @field_validator("color")
    @classmethod
    def _v_color(cls, v):
        return _validate_hex_color(v)


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


# Implements: REQ-d00253-A
class FederationConfig(_StrictModel):
    """Controls how associate repos affect write/generate surfaces.

    Reads (checks/summary/cross-repo resolution) always federate; these flags
    govern only the write and generation surfaces.
    """

    write_associates: bool = False
    index_associates: bool = False


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
    federation: FederationConfig = Field(default_factory=FederationConfig)
    statuses: dict[str, StatusConfig] = Field(default_factory=dict)
    stats: str = Field(default="", description="File path for MCP tool usage statistics")

    @field_validator("levels")
    @classmethod
    def _v_level_keys(cls, v: dict[str, Any]) -> dict[str, Any]:
        # Level keys are interpolated into CSS attribute selectors, CSS class
        # names, and single-quoted JS string literals inside HTML attributes.
        # Restrict them to the same identifier shape as namespaces.
        for key in v or {}:
            _validate_namespace(key)
        return v

    @field_validator("statuses")
    @classmethod
    def _v_status_keys(cls, v: dict[str, Any]) -> dict[str, Any]:
        # Status keys flow into `.status-badge.{key|lower}` CSS class selectors,
        # JS string literals, and `data-key` attributes. Same identifier shape
        # as namespaces / levels.
        for key in v or {}:
            _validate_namespace(key)
        return v

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
