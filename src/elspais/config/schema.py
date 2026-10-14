"""Pydantic schema for .elspais.toml configuration."""

from __future__ import annotations

import posixpath
import re
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

# Hex-color and namespace patterns live in the utilities lib so all consumers
# share a single regex. See `utilities/color.py` and `utilities/patterns.py`.
from elspais.utilities.color import validate_hex_color as _validate_hex_color

# The severity vocabulary has ONE home (REQ-d00212-U): the schema admits exactly
# the values the resolver knows, so a setting cannot name a severity nothing can
# act on.
from elspais.utilities.findings import SeverityValue
from elspais.utilities.patterns import REF_LIST_SEPARATOR, RESERVED_IDENTIFIER_CHARACTERS
from elspais.utilities.patterns import validate_namespace as _validate_namespace

# Implements: REQ-p00014-S
# A node's identifier is written with `:` between its parts -- the prefix of a
# structural id, the namespace it names, the composite form joining a declaring
# requirement to a template's. A requirement identifier able to contain one is
# therefore ambiguous with the graph's own syntax, and the ambiguity surfaces
# far from the configuration that caused it. Every field that can put a `:`
# into a produced identifier excludes it, on the field rather than in a
# validator, so the exported JSON schema carries the same refusal an editor
# reads.
_RESERVED = "".join(RESERVED_IDENTIFIER_CHARACTERS)
_NO_COLON = rf"^[^{re.escape(_RESERVED)}]*$"
_NO_COLON_MESSAGE = "must not contain ':', which separates the parts of a node identifier"
# A run names a test target or group of another federation member by writing
# that member's namespace, a `:`, and the name. A namespace holds no `:`, so a
# target or group name holding none either is what keeps the two parts apart.
_NO_COLON_IN_SELECTOR_MESSAGE = (
    "must not contain ':', which separates a federation member's namespace from "
    "a target or group name that member declares"
)


# The statuses a project starts with, and what each one means. Read from here
# by both the schema default and the roles reader, which held their own copies
# of it and would have agreed until one of them was edited.
_DEFAULT_STATUS_ROLES: dict[str, list[str]] = {
    "active": ["Active"],
    "provisional": ["Draft", "Proposed"],
    "aspirational": ["Roadmap", "Future", "Idea"],
    "retired": ["Deprecated", "Superseded", "Rejected"],
}


class _StrictModel(BaseModel):
    # A field carrying an alias is written under that alias and no other: one
    # setting has one spelling, so a file cannot say the same thing two ways
    # and leave a reader to work out which one the tool read.
    model_config = ConfigDict(extra="forbid", frozen=True)


# Implements: REQ-d00212-Y
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


# Implements: REQ-d00251-D
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

    @field_validator("style", mode="before")
    @classmethod
    def _reject_legacy_styles(cls, value):
        if isinstance(value, str) and value in _LEGACY_STYLE_MIGRATION:
            raise ValueError(_legacy_style_message(value))
        return value


# Implements: REQ-d00251-E, REQ-d00251-K, REQ-d00251-M, REQ-d00081-B
class AssertionConfig(_StrictModel):
    label_style: str = "uppercase"
    max_count: int = 26
    zero_pad: bool = False
    # A boundary is a character (REQ-d00251-K). The length is constrained on
    # the field rather than in the model validator so the exported JSON schema
    # carries it too, and an editor rejects what the runtime would reject.
    separator: str = Field(default="-", min_length=1, max_length=1, pattern=_NO_COLON)
    multi_separator: str = Field(default="+", min_length=1, max_length=1, pattern=_NO_COLON)

    # Implements: REQ-d00251-M
    @model_validator(mode="after")
    def _separators_do_not_divide_references(self):
        # A list is divided before its items are read, so this character is
        # spent on the outer boundary first: what reaches the identifier
        # reader is a fragment cut short and a bare label with no
        # requirement in front of it, neither of which fails loudly.
        for field_name in ("separator", "multi_separator"):
            if getattr(self, field_name) == REF_LIST_SEPARATOR:
                raise ValueError(
                    f"id-patterns.assertions.{field_name} is "
                    f'"{REF_LIST_SEPARATOR}", which already divides one '
                    f"reference from the next in a list of references. Choose "
                    f'a character that holds no other role, such as "&".'
                )
        return self


class AssociatedPatternConfig(_StrictModel):
    enabled: bool = False
    position: str = "after_prefix"
    format: str = "uppercase"
    length: int = 3
    separator: str = "-"


_PRINTABLE = frozenset(chr(code) for code in range(0x21, 0x7F))


# Implements: REQ-d00251-F, REQ-d00251-J
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


# Implements: REQ-d00251-F, REQ-d00251-J
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


# Implements: REQ-d00251-F, REQ-d00251-J
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


# Implements: REQ-d00251-F, REQ-d00251-J
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
    from re import _parser as _regex_parser

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
    canonical: str = Field(default="{namespace}-{level.letter}{component}", pattern=_NO_COLON)
    aliases: dict[str, str] = Field(default_factory=lambda: {"short": "{level.letter}{component}"})
    component: ComponentConfig = Field(default_factory=ComponentConfig)
    assertions: AssertionConfig = Field(default_factory=AssertionConfig)
    associated: AssociatedPatternConfig = Field(default_factory=AssociatedPatternConfig)

    # Implements: REQ-p00014-S
    @model_validator(mode="after")
    def _validate_style_pattern_and_separator(self):
        # The two places a `:` can enter an identifier without any single
        # field spelling one: an alias template, whose values are a mapping
        # rather than a field, and a component pattern that ADMITS a colon
        # without containing one. The component's alphabet is read off its
        # own parse tree, the same way the separator suggestions are.
        for name, template in (self.aliases or {}).items():
            if ":" in template:
                raise ValueError(f'id-patterns.aliases.{name} {_NO_COLON_MESSAGE}: "{template}"')
        if self.component.style == "regex" and self.component.pattern:
            if ":" in _legal_chars(self.component.pattern):
                raise ValueError(
                    f"id-patterns.component.pattern admits ':', which separates the "
                    f'parts of a node identifier: "{self.component.pattern}"'
                )

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


# Implements: REQ-d00212-Y
class HierarchyConfig(_StrictModel):
    cross_repo_implements: bool = False
    allow_structural_orphans: bool = False
    allow_circular: bool = False
    allow_orphans: bool = False


# Implements: REQ-d00212-Y
class FormatConfig(_StrictModel):
    require_hash: bool = False
    require_assertions: bool = False
    require_status: bool = False
    require_rationale: bool = False
    # Each of these three is a check that exists and works
    # (`validation/format.py`). Without the field a project cannot ask for
    # it, so the first two never ran and the third could not be turned off
    # -- and the health report described all three as configured.
    require_shall: bool = False
    labels_sequential: bool = False
    labels_unique: bool = True
    # A role maps to the LIST of status names in it. A bare string was
    # admitted here and silently discarded by the reader, so a project
    # writing `retired = "Deprecated"` was told nothing and kept treating
    # the status as active -- counted in coverage, reported as a gap.
    status_roles: dict[str, list[str]] = Field(default_factory=lambda: dict(_DEFAULT_STATUS_ROLES))
    no_assertions_severity: SeverityValue = "warning"
    no_traceability_severity: SeverityValue = "warning"

    @field_validator("status_roles")
    @classmethod
    def _v_status_role_values(cls, v: dict[str, Any]) -> dict[str, Any]:
        # Each status name listed here ends up as a key in `.status-badge.{name}`
        # CSS selectors, JS string literals, and `data-key` attributes — same
        # identifier shape as namespaces / level keys.
        from elspais.config.status_roles import StatusRole

        known = {r.value for r in StatusRole}
        for role, names in (v or {}).items():
            if role not in known:
                # Swallowed before, so a mistyped role name quietly assigned
                # nothing and the statuses under it kept whatever role they
                # had by default.
                raise ValueError(
                    f"rules.format.status_roles.{role} is not a role. "
                    f"The roles are: {', '.join(sorted(known))}."
                )
            for name in names:
                _validate_namespace(name)
        return v


class CoverageSeverityConfig(_StrictModel):
    """Severity mapping for a single coverage dimension's tier states.

    Each tier maps to a severity in the one vocabulary (REQ-d00212-U): 'off',
    'info', 'warning' or 'error'. Tiers are the unified vocabulary
    (REQ-d00258): full / partial / failing / missing. A tier mapped to 'off'
    is one this dimension says nothing about -- which is what a fully covered
    dimension has to say, and why `full` defaults to it.
    """

    full: SeverityValue = "off"
    partial: SeverityValue = "warning"
    failing: SeverityValue = "error"
    missing: SeverityValue = "error"


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
    # Implements: REQ-d00274-C
    # Evidence naming an assertion its dimension does not count -- a test on an
    # assertion nothing implements. An error by default because the condition
    # has only two explanations and both are defects: the implementation exists
    # and its `Implements:` reference was never written, or the test is aimed at
    # an assertion it does not exercise.
    uncredited_evidence: SeverityValue = "error"
    # Implements: REQ-d00276-C
    # A test that failed and reaches no requirement. A warning by default: a
    # repository legitimately carries tests for things it has written no
    # requirement for, so the condition is not always a defect -- but a failure
    # nobody can find through a requirement is one nobody will find at all.
    external_test_failure: SeverityValue = "warning"
    # Per-relationship label overrides (REQ-d00258). Keyed by relationship name
    # (implements/verifies/yields/validates/validated); resolved to dimension
    # labels via elspais.config.status_words.get_status_words().
    status_words: dict[str, str] = Field(default_factory=dict)


class ReferenceSeverityConfig(_StrictModel):
    """Severity for each class of reference fault, and for reference status.

    Severity is chosen per class because the classes differ in what would
    resolve them: configuring a missing repository answers one and answers
    nothing about a line that never read as an identifier (REQ-d00269-F).
    """

    retired: SeverityValue = "warning"
    provisional: SeverityValue = "info"
    aspirational: SeverityValue = "info"
    malformed: SeverityValue = "warning"
    unknown_namespace: SeverityValue = "info"
    unknown_requirement: SeverityValue = "error"
    unknown_assertion: SeverityValue = "error"
    forbidden: SeverityValue = "error"
    # Implements: REQ-d00272-G
    keyword_form: SeverityValue = "warning"
    # Implements: REQ-d00272-N
    identifier_form: SeverityValue = "warning"
    # Implements: REQ-d00272-O
    undeclared: SeverityValue = "warning"


# Implements: REQ-d00212-P, REQ-d00285-D, REQ-d00212-O
class RulesConfig(_StrictModel):
    hierarchy: HierarchyConfig = Field(default_factory=HierarchyConfig)
    format: FormatConfig = Field(default_factory=FormatConfig)
    coverage: CoverageConfig = Field(default_factory=CoverageConfig)
    references: ReferenceSeverityConfig = Field(default_factory=ReferenceSeverityConfig)
    # Severity for the checks that carry no setting of their own, keyed by the
    # name the check reports under: `"spec.parseable" = "off"`. A check reads
    # EITHER a named setting above OR an entry here -- never both, so a project
    # that sets the one it read about always sees it take effect. Which of the
    # two a given check reads is recorded in
    # `elspais.utilities.findings.REGISTRY`, and a name that registry does not
    # know is refused here rather than silently doing nothing.
    severity: dict[str, SeverityValue] = Field(default_factory=dict)
    content_rules: list[str] = Field(default_factory=list)
    protected_branches: list[str] = Field(default=["main", "master"])

    @field_validator("severity")
    @classmethod
    def _v_severity_names(cls, v: dict[str, Any]) -> dict[str, Any]:
        from elspais.utilities.findings import REGISTRY, WITHDRAWN_CHECKS

        for name in v or {}:
            rule = REGISTRY.get(name)
            if rule is None and name in WITHDRAWN_CHECKS:
                raise ValueError(
                    f"rules.severity.{name!r} names no check: the references it judged "
                    f"are reported by {WITHDRAWN_CHECKS[name]}. Remove the entry and "
                    f"set those instead."
                )
            if rule is None:
                raise ValueError(
                    f"rules.severity.{name!r} names no check. Run `elspais docs checks` "
                    f"for the checks this project runs."
                )
            if rule.path[:2] != ("rules", "severity"):
                raise ValueError(
                    f"rules.severity.{name!r} is configured under "
                    f"{'.'.join(rule.path)} instead. A check reads one setting, "
                    f"so setting it here would be read by nothing."
                )
        return v


class KeywordsSearchConfig(_StrictModel):
    min_length: int = 3


# Implements: REQ-d00324-A
def _retired_hash_mode_message(value: str) -> str:
    """Build the refusal for a hash mode the tool no longer offers."""
    return (
        f'[validation] hash_mode = "{value}" is no longer supported.\n\n'
        "A requirement's hash covers its Assertions alone, normalized as the\n"
        "Hash section of `elspais docs format` describes. No setting selects\n"
        "another digest.\n\n"
        "Remove the hash_mode line from [validation], or write:\n"
        '  hash_mode = "normalized-text"\n\n'
        "The next `elspais fix` then rewrites the stored hash of every\n"
        "requirement to the normalized digest. Commit that change on its own,\n"
        "so reviewers can tell it from an edit to what a requirement says."
    )


class ValidationConfig(_StrictModel):
    hash_mode: Literal["normalized-text"] = "normalized-text"
    hash_algorithm: str = "sha256"
    hash_length: int = 8

    @field_validator("hash_mode", mode="before")
    @classmethod
    def _refuse_retired_hash_mode(cls, value):
        if value == "full-text":
            raise ValueError(_retired_hash_mode_message(value))
        return value


# Implements: REQ-d00212-Y
class LevelConfig(_StrictModel):
    rank: int
    letter: str = Field(pattern=_NO_COLON)
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


# Implements: REQ-d00212-Q+W
# The patterns a kind selects by when its configuration declares none. They
# are the DEFAULTS of the one selection mechanism, not a second one: a kind
# always selects the files its `file_patterns` match, and these are what that
# setting holds until a project writes its own. An empty list means "the
# defaults", so a configuration written before the setting had a default
# still scans what it always scanned.
DEFAULT_SPEC_PATTERNS = ["*.md"]
DEFAULT_TEST_PATTERNS = ["test_*.py", "*_test.py"]
DEFAULT_JOURNEY_PATTERNS = ["*.md"]
DEFAULT_DOCS_PATTERNS = ["*.md"]

# Covers every language named in the comment-pattern table
# (``graph/parsers/patterns.py``), because a file whose language has a comment
# marker is a file a *Traceability* keyword can be written in.
#
# Jinja templates are included because a template is where a viewer's
# JavaScript is written -- the code is real, the annotations in it are real,
# and leaving the extension out meant every one of them was invisible while
# the requirements they implement read as unimplemented. A template is
# associated with the c-like comment pattern, whatever it renders to, like
# every other scannable file type is associated with exactly one
# (REQ-d00236-H): a `//` line reads in a `.js.j2` and in a `.css.j2` alike.
# Block comments carry no citation in a template any more than anywhere else.
#
# Container image files are included for the same reason a `.tf` file is: an
# image is where a deployment's configuration values are bound, so it is a
# normal place to cite a requirement from.
DEFAULT_CODE_PATTERNS = [
    "*.py",
    "*.js",
    "*.ts",
    "*.jsx",
    "*.tsx",
    "*.java",
    "*.c",
    "*.cpp",
    "*.h",
    "*.hpp",
    "*.go",
    "*.rs",
    "*.rb",
    "*.sh",
    "*.bash",
    "*.sql",
    "*.lua",
    "*.yml",
    "*.yaml",
    "*.dart",
    "*.swift",
    "*.kt",
    "*.css",
    "*.scss",
    "*.tf",
    "*.tfvars",
    "*.hcl",
    "*.j2",
    "Dockerfile",
    "*.Dockerfile",
    "Containerfile",
]


# Implements: REQ-d00212-Y
class ScanningKindConfig(_StrictModel):
    directories: list[str] = Field(default_factory=list)
    file_patterns: list[str] = Field(default_factory=list)
    skip_files: list[str] = Field(default_factory=list)
    skip_dirs: list[str] = Field(default_factory=list)


class SpecScanningConfig(ScanningKindConfig):
    directories: list[str] = Field(default_factory=lambda: ["spec"])
    file_patterns: list[str] = Field(default_factory=lambda: list(DEFAULT_SPEC_PATTERNS))
    index_file: str = ""


class CodeScanningConfig(ScanningKindConfig):
    directories: list[str] = Field(default_factory=lambda: ["src"])
    file_patterns: list[str] = Field(default_factory=lambda: list(DEFAULT_CODE_PATTERNS))
    source_roots: list[str] = Field(default_factory=lambda: ["src", ""])


# Implements: REQ-d00254-C
# Implements: REQ-d00283-B+C+J
# The tool defines these three group names. REQ-d00283-G requires a declared
# keyword to be unique among all group names, these included. Consequently, a
# project cannot declare any of them. `none` stands for no target.
# Consequently, no target may claim it either.
GROUP_ALL = "all"
GROUP_DEFAULT = "default"
GROUP_NONE = "none"
# Implements: REQ-d00316-E
# `last-run` stands for the targets the last recorded run executed. It is read
# from that run's record, so no target may claim it either.
GROUP_LAST_RUN = "last-run"
RESERVED_GROUPS = frozenset({GROUP_ALL, GROUP_DEFAULT, GROUP_NONE, GROUP_LAST_RUN})

# Implements: REQ-d00312-A
# The name of a target is also the name of its output area under the output root.
# Consequently, the name must be one path segment. The name cannot be hidden or relative.
_TARGET_FOLDER_NAME = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*")

# Implements: REQ-d00284-A
# The forms a target may declare for the name its results give the test that
# produced them. "python-module" reads the name as a dotted module path;
# "source-file" reads it as naming the test's source file.
CLASSNAME_FORMS = ("python-module", "source-file")

# Implements: REQ-d00294-C
# The sources a target may declare for the environment a result was recorded
# in. "results-path" reads the part of the path that the wildcard in the
# target's results glob matched; "suite-hostname" reads the `hostname`
# attribute of the `<testsuite>` that holds the result record.
ENVIRONMENT_SOURCES = ("results-path", "suite-hostname")

# Implements: REQ-d00327-A+B
# The origins a relative source path a reporter records may be read from.
# "repository-root" reads it from the root of the repository that owns the
# target; "working-directory" reads it from the target's `cwd`.
PATH_ORIGIN_ROOT = "repository-root"
PATH_ORIGIN_CWD = "working-directory"
PATH_ORIGINS = (PATH_ORIGIN_ROOT, PATH_ORIGIN_CWD)


# Implements: REQ-d00311-R
class EnvironmentProbeConfig(_StrictModel):
    """One part of a test target's environment, identified by what a command prints.

    The command runs in the target's ``cwd``. Its exit status and its standard
    output identify that part of the environment, such as the version of a
    toolchain or the packages installed for the target.
    """

    name: str
    command: str
    # Implements: REQ-d00333-K
    # Whether a change of this part of the environment executes every unit of
    # a target that declares units. False leaves the part out of each unit's
    # Dependency Evidence; the target is still stale when the part changes.
    affects_retention: bool = True

    @field_validator("name", "command")
    @classmethod
    def _check_present(cls, v: str, info: ValidationInfo) -> str:
        if not v.strip():
            raise ValueError(
                f"an environment probe needs a {info.field_name}: a probe is a table "
                f'such as {{ name = "python", command = "python --version" }}'
            )
        return v


#: The placeholder in a test target's command that the selected units replace.
SELECTION_PLACEHOLDER = "{selection}"

# Implements: REQ-d00249-O
# How a target's command receives the units a run selects. "placeholder"
# replaces `{selection}` in the command with them; "file" leaves the command
# as it is, and the command reads the list from the file $ELSPAIS_SELECTION
# names.
SELECTION_RECEIVERS = ("placeholder", "file")


# Implements: REQ-d00333-C, REQ-d00249-O
class UnitsConfig(_StrictModel):
    """The units of a test target: its test files, which a run may execute in part.

    ``dependencies`` names the source of each unit's *Dependency Evidence*
    (``source``) and holds the settings that source validates. ``observes``
    selects the files the source observes, read from the repository root;
    unset means the source's own default. ``tests`` selects, from the
    repository root, the scanned test files below the target's working
    directory that its command executes; unset means all of them.
    ``receives`` says how the command receives the selected units.
    ``full_selection`` is what ``{selection}`` becomes on a run of every unit.
    """

    dependencies: dict[str, Any]
    observes: ScanningKindConfig | None = None
    tests: ScanningKindConfig | None = None
    receives: str = "placeholder"
    full_selection: str = ""

    @field_validator("receives")
    @classmethod
    def _check_receives(cls, v: str) -> str:
        if v not in SELECTION_RECEIVERS:
            names = ", ".join(f'"{r}"' for r in SELECTION_RECEIVERS)
            raise ValueError(f"units.receives must be one of {names}")
        return v

    @model_validator(mode="after")
    def _check_source(self) -> UnitsConfig:
        from elspais.graph.dependencies import source_names

        name = self.dependencies.get("source")
        if not isinstance(name, str) or not name:
            known = ", ".join(f'"{n}"' for n in source_names())
            raise ValueError(
                f"units.dependencies needs a source, one of {known}, such as "
                f'dependencies = {{ source = "declared" }}'
            )
        try:
            self.source_settings()
        except KeyError as exc:
            raise ValueError(str(exc.args[0])) from exc
        except ValidationError as exc:
            raise ValueError(
                f"units.dependencies does not suit the {name!r} source: {exc}"
            ) from exc
        return self

    def source_name(self) -> str:
        """The name of the dependency source."""
        return str(self.dependencies["source"])

    def source_settings(self) -> BaseModel:
        """The source's own settings: the keys beside ``source``, validated by its model."""
        from elspais.graph.dependencies import validate_settings

        return validate_settings(
            self.source_name(), {k: v for k, v in self.dependencies.items() if k != "source"}
        )


class TestTargetConfig(_StrictModel):
    """One test target: how its results + coverage are produced and ingested."""

    __test__ = False  # not a pytest class

    name: str
    # Relative to repo root; empty = repo root. The command runs here, and a
    # relative source path is read from here wherever the origin that applies
    # is the working directory.
    cwd: str = ""
    command: str = ""  # optional; omitted in CI (tests already ran)
    reporter: str = ""  # registry format name (e.g. "flutter-machine", "junit", "pytest-json")
    # Glob relative to the target's output folder naming the files a
    # results reporter reads.
    results: str = ""
    # lcov/coverage file relative to the target's output folder; empty = no coverage.
    coverage: str = ""
    # Implements: REQ-d00254-C
    # The format of the file `coverage` names: the name of a coverage reporter.
    # Required wherever `coverage` is set.
    coverage_format: str = ""

    # Implements: REQ-d00312-A
    # A file whose name begins `.elspais-` in an output area is written by
    # elspais itself, so a target's own results or coverage never names one.
    @field_validator("results", "coverage")
    @classmethod
    def _check_not_elspais_file(cls, v: str, info: ValidationInfo) -> str:
        if any(part.startswith(".elspais-") for part in v.replace("\\", "/").split("/")):
            raise ValueError(
                f"{info.field_name} {v!r} names a file elspais writes in the output "
                f"area; name the file the target's command writes"
            )
        return v

    match: str = "source"  # "source" | "aggregate"
    # Implements: REQ-d00283-A+C+F
    # The groups this target belongs to. Empty means the target claims none,
    # which REQ-d00283-C places in `default`; `all` is claimable but conveys
    # nothing, since REQ-d00283-B already holds every target.
    groups: list[str] = Field(default_factory=list)
    # Implements: REQ-d00284-A
    # How this target's results name the test that produced them. Empty means
    # the form its reporter declares.
    classname: str = ""
    # Implements: REQ-d00294-C
    # Where the environment a result was recorded in is read from. Empty
    # means the source its reporter declares, and where that is empty too
    # the results of this target carry no environment.
    environment: str = ""
    credit_coverage: str = "off"  # "off" | "tested" | "verified" (lcov_tested dimension)
    min_coverage_fraction: float = 0.0  # [0.0, 1.0]
    # Implements: REQ-d00254-O
    # The origin this target's reporter counts lines from, when the producer
    # departs from the format's convention. Unset means the reporter's own
    # declared origin.
    line_base: int | None = None
    # Implements: REQ-d00327-B
    # Where a relative source path in this target's results, and in its
    # coverage data, is read from, when the producer departs from its format's
    # convention. They are declared apart because the two are usually written
    # by different tools. Empty means the origin the reporter declares.
    results_origin: str = ""
    coverage_origin: str = ""
    # Implements: REQ-d00314-F
    # The shared resources this target uses. Two targets naming a common
    # resource never run at the same time.
    resources: list[str] = Field(default_factory=list)
    # Implements: REQ-d00311-J+K+L
    # inputs selects the files that the results of this target depend on.
    # inputs uses the same file-selection settings as a scan. Directories and
    # file patterns include files. Skipped directories and files exclude files.
    # If inputs is empty, then every file in the repository is an input.
    inputs: ScanningKindConfig = Field(default_factory=ScanningKindConfig)
    # Implements: REQ-d00329-A
    # Whether the exit status of this target's command is the result of each
    # test file the target scans. It stands beside the reporter rather than in
    # its place, so one target can hold per-test results and file-level ones.
    file_results: bool = False
    # Implements: REQ-d00311-R
    # The parts of the environment this target's outcomes depend on beyond the
    # files of the repository. Each probe is an input of the target, recorded
    # under its own name.
    environment_probes: list[EnvironmentProbeConfig] = Field(default_factory=list)
    # Implements: REQ-d00333-C, REQ-d00249-O
    # The units of this target and where their Dependency Evidence comes from.
    # Unset, the target is one unit and every run executes all of it.
    units: UnitsConfig | None = None

    # Implements: REQ-d00249-O, REQ-d00333-C
    @model_validator(mode="after")
    def _check_units(self) -> TestTargetConfig:
        named = f'test target "{self.name}"'
        holds = SELECTION_PLACEHOLDER in self.command
        if self.units is None:
            if holds:
                raise ValueError(
                    f"{named}: its command holds {SELECTION_PLACEHOLDER}, which only a "
                    f"target declaring units replaces; declare "
                    f"[scanning.test.targets.units] or remove {SELECTION_PLACEHOLDER}"
                )
            return self
        if not self.command:
            raise ValueError(f"{named}: units need a command for a run to execute them")
        if self.units.receives == "placeholder" and not holds:
            raise ValueError(
                f"{named}: its units are received through {SELECTION_PLACEHOLDER}, and "
                f"its command does not hold it; put {SELECTION_PLACEHOLDER} where the "
                f'test files go, or set units.receives = "file" for a command that reads '
                f"the list from $ELSPAIS_SELECTION"
            )
        if self.units.receives == "file" and holds:
            raise ValueError(
                f'{named}: units.receives = "file" reads the selection from '
                f"$ELSPAIS_SELECTION, so {SELECTION_PLACEHOLDER} would reach the shell "
                f"as written; remove it from the command"
            )
        if not self.results:
            raise ValueError(
                f"{named}: units need a results pattern, because a run reads each "
                f"unit's outcome from the files the command writes into "
                f"$ELSPAIS_TARGET_OUTPUT"
            )
        if self.file_results:
            raise ValueError(
                f"{named}: units cannot stand with file_results = true, because after a "
                f"run of some units the exit status speaks for those units alone"
            )
        from elspais.graph.dependencies import get_source, observes_required

        if self.units.observes is None:
            if observes_required(get_source(self.units.source_name())):
                raise ValueError(
                    f"{named}: the {self.units.source_name()!r} dependency source observes "
                    f"what the project declares; set units.observes to the files its "
                    f"evidence covers"
                )
        return self

    # Implements: REQ-d00311-R
    @model_validator(mode="after")
    def _check_probe_names(self) -> TestTargetConfig:
        seen: dict[str, str] = {}
        for probe in self.environment_probes:
            key = probe.name.strip().lower()
            if key in seen:
                raise ValueError(
                    f'test target "{self.name}" declares environment probes '
                    f'"{seen[key]}" and "{probe.name}", which differ only in case or '
                    f"spacing; each probe names one part of the environment, so give "
                    f"each a distinct name"
                )
            seen[key] = probe.name
        return self

    # Implements: REQ-d00283-X
    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        if any(ch in v for ch in RESERVED_IDENTIFIER_CHARACTERS):
            raise ValueError(f'test target name "{v}" {_NO_COLON_IN_SELECTOR_MESSAGE}')
        return v

    @field_validator("line_base")
    @classmethod
    def _check_line_base(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1):
            raise ValueError("line_base must be 0 or 1")
        return v

    @field_validator("match")
    @classmethod
    def _check_match(cls, v: str) -> str:
        if v not in ("source", "aggregate"):
            raise ValueError('match must be "source" or "aggregate"')
        return v

    @field_validator("classname")
    @classmethod
    def _check_classname(cls, v: str) -> str:
        if v and v not in CLASSNAME_FORMS:
            forms = ", ".join(f'"{f}"' for f in CLASSNAME_FORMS)
            raise ValueError(f"classname must be empty or one of {forms}")
        return v

    @field_validator("environment")
    @classmethod
    # Implements: REQ-d00294-C
    def _check_environment(cls, v: str) -> str:
        if v and v not in ENVIRONMENT_SOURCES:
            sources = ", ".join(f'"{s}"' for s in ENVIRONMENT_SOURCES)
            raise ValueError(f"environment must be empty or one of {sources}")
        return v

    @field_validator("results_origin", "coverage_origin")
    @classmethod
    # Implements: REQ-d00327-B
    def _check_origin(cls, v: str, info: ValidationInfo) -> str:
        if v and v not in PATH_ORIGINS:
            origins = ", ".join(f'"{o}"' for o in PATH_ORIGINS)
            raise ValueError(f"{info.field_name} must be empty or one of {origins}")
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

    # Implements: REQ-d00329-A
    @model_validator(mode="after")
    def _require_reporter(self) -> TestTargetConfig:
        # A target whose command's exit status is its files' result has a
        # verdict with no reporter. A results pattern always names files a
        # reporter must read.
        if self.results and not self.reporter:
            raise ValueError("reporter is required when results is set")
        # Implements: REQ-d00254-C
        # A coverage file is read in the format the project names for it.
        from elspais.graph.parsers.results.registry import REPORTER_REGISTRY

        formats = sorted(n for n, s in REPORTER_REGISTRY.items() if s.kind == "coverage")
        if self.coverage and not self.coverage_format:
            raise ValueError(
                f"coverage = {self.coverage!r} is set without coverage_format; set "
                f"coverage_format to the format of that file: {', '.join(formats)}"
            )
        if self.coverage_format and self.coverage_format not in formats:
            raise ValueError(
                f"coverage_format {self.coverage_format!r} is not a coverage format; "
                f"use one of {', '.join(formats)}"
            )
        if self.command and not self.reporter and not self.file_results:
            raise ValueError(
                "reporter is required when command is set, unless file_results = true "
                "makes the command's exit status the result of each test file the "
                "target scans"
            )
        return self


# Implements: REQ-d00333-F
class BaselineConfig(_StrictModel):
    """Where a *Baseline Run* comes from.

    ``fetch_command`` fills the directory that ``{dest}`` names with one archive
    that ``elspais baseline pack`` wrote. The project's command decides which
    run to fetch and how to reach it; elspais knows no host.
    """

    fetch_command: str = ""

    @field_validator("fetch_command")
    @classmethod
    def _check_dest(cls, v: str) -> str:
        if v.strip() and "{dest}" not in v:
            raise ValueError(
                f"scanning.test.baseline.fetch_command {v!r} does not name {{dest}}. "
                f"Write {{dest}} where the command takes the empty directory it fills "
                f"with a packed baseline, such as "
                f'"tools/fetch-baseline.sh {{dest}}"; elspais substitutes it shell-quoted'
            )
        return v


class TestScanningConfig(ScanningKindConfig):
    __test__ = False  # Prevent pytest collection

    directories: list[str] = Field(default_factory=lambda: ["tests"])
    file_patterns: list[str] = Field(default_factory=lambda: list(DEFAULT_TEST_PATTERNS))
    enabled: bool = False
    prescan_command: str = ""
    reference_keyword: str = "Verifies"
    reference_patterns: list[str] = Field(default_factory=list)
    # Implements: REQ-d00283-G
    # Each declared group binds a keyword to a description of what the group
    # is for. The description is required: a group named `slow` says nothing
    # about whether a change should have run it, and this is the only place
    # that explanation has to live.
    groups: dict[str, str] = Field(default_factory=dict)
    # Implements: REQ-d00314-E
    # Each declared shared resource binds a name to a description of what the
    # resource is: a database, a network port, a device, a local service stack.
    resources: dict[str, str] = Field(default_factory=dict)
    # Implements: REQ-d00314-A+B
    # The maximum number of targets one run executes at the same time. One
    # runs them one at a time, in declaration order.
    concurrency: int = 1
    targets: list[TestTargetConfig] = Field(default_factory=list)
    # Implements: REQ-d00312-B
    # output_root names the directory that holds the output area of each target.
    # The path is relative to the repository root.
    output_root: str = ".results"
    # Implements: REQ-d00333-F
    # How `elspais baseline fetch` obtains a packed Baseline Run.
    baseline: BaselineConfig = Field(default_factory=BaselineConfig)

    # Implements: REQ-d00312-B
    @field_validator("output_root")
    @classmethod
    def _check_output_root(cls, v: str) -> str:
        normalized = posixpath.normpath(v.strip().replace("\\", "/")) if v.strip() else ""
        if (
            not normalized
            or normalized in (".", "..")
            or normalized.startswith("../")
            or posixpath.isabs(normalized)
        ):
            raise ValueError(
                f"output_root {v!r} must name a directory inside the repository, "
                f'relative to its root, such as ".results"'
            )
        return normalized

    # Implements: REQ-d00314-A
    @field_validator("concurrency")
    @classmethod
    def _check_concurrency(cls, v: int) -> int:
        if v < 1:
            raise ValueError(
                f"concurrency {v} must be a whole number of targets, 1 or more; "
                f"1 runs the targets one at a time"
            )
        return v

    # Implements: REQ-d00314-E+F+G
    @model_validator(mode="after")
    def _check_resources(self) -> TestScanningConfig:
        seen: dict[str, str] = {}
        for name, description in self.resources.items():
            key = name.strip().lower()
            if not key:
                raise ValueError("a declared shared resource must have a name")
            if key in seen:
                raise ValueError(
                    f'shared resources "{seen[key]}" and "{name}" differ only in case or spacing'
                )
            if not str(description).strip():
                raise ValueError(f'shared resource "{name}" must have a description')
            seen[key] = name
        for target in self.targets:
            for named in target.resources:
                if named.strip().lower() not in seen:
                    declared = ", ".join(sorted(seen.values())) or "none"
                    raise ValueError(
                        f'test target "{target.name}" names undeclared shared resource '
                        f'"{named}"; declare it under [scanning.test.resources] with a '
                        f"description. Declared resources: {declared}"
                    )
        return self

    # Implements: REQ-d00322-J
    # evidence names the directory that holds the project's Evidence Snapshot,
    # relative to the repository root. Empty names none.
    evidence: str = ""

    # Implements: REQ-d00322-J
    @field_validator("evidence")
    @classmethod
    def _check_evidence(cls, v: str) -> str:
        if not v.strip():
            return ""
        normalized = posixpath.normpath(v.strip().replace("\\", "/"))
        if normalized in (".", "..") or normalized.startswith("../") or posixpath.isabs(normalized):
            raise ValueError(
                f"scanning.test.evidence {v!r} must name a directory inside the repository, "
                f'relative to its root, such as "test-evidence"'
            )
        return normalized

    # Implements: REQ-d00283-F+G
    @model_validator(mode="after")
    def _check_groups(self) -> TestScanningConfig:
        seen: dict[str, str] = {}
        for name, description in self.groups.items():
            key = name.strip().lower()
            if not key:
                raise ValueError("a declared test group must have a keyword")
            # Implements: REQ-d00283-X
            if any(ch in key for ch in RESERVED_IDENTIFIER_CHARACTERS):
                raise ValueError(f'test group "{name}" {_NO_COLON_IN_SELECTOR_MESSAGE}')
            if key in RESERVED_GROUPS:
                raise ValueError(
                    f'test group "{name}" is reserved and cannot be declared; '
                    f"the reserved groups are {', '.join(sorted(RESERVED_GROUPS))}"
                )
            if key in seen:
                raise ValueError(
                    f'test groups "{seen[key]}" and "{name}" differ only in case or spacing'
                )
            if not str(description).strip():
                raise ValueError(f'test group "{name}" must have a description')
            seen[key] = name

        known = set(seen) | RESERVED_GROUPS
        for target in self.targets:
            for claimed in target.groups:
                # Implements: REQ-d00283-J
                if claimed.strip().lower() == GROUP_NONE:
                    raise ValueError(
                        f'test target "{target.name}" claims the group "{claimed}", '
                        f"which stands for no target; remove it from the target's groups"
                    )
                # Implements: REQ-d00316-E
                if claimed.strip().lower() == GROUP_LAST_RUN:
                    raise ValueError(
                        f'test target "{target.name}" claims the group "{claimed}", '
                        f"which stands for the targets the last recorded run executed; "
                        f"remove it from the target's groups"
                    )
                if claimed.strip().lower() not in known:
                    raise ValueError(
                        f'test target "{target.name}" claims undeclared group "{claimed}"; '
                        f"declared groups are {', '.join(sorted(known))}"
                    )

        # Implements: REQ-d00283-G
        # A group is an alias for a set of targets and is named where a target
        # is named, so the two share one namespace: a name meaning a target to
        # one reader and a group to another cannot be resolved, and a run would
        # execute a different set according to which the tool looked up first.
        # Refused here rather than resolved by precedence -- a precedence rule
        # is a thing every reader of the configuration would have to know.
        for target in self.targets:
            key = target.name.strip().lower()
            if key in known:
                kind = "reserved" if key in RESERVED_GROUPS else "declared"
                raise ValueError(
                    f'test target "{target.name}" has the same name as a {kind} test '
                    f"group; a run names targets and groups alike, so one name cannot "
                    f"mean both. Rename the target or the group."
                )
        return self

    # Implements: REQ-d00312-A+C
    @model_validator(mode="after")
    def _check_target_folders(self) -> TestScanningConfig:
        for target in self.targets:
            if not _TARGET_FOLDER_NAME.fullmatch(target.name):
                raise ValueError(
                    f'test target "{target.name}" cannot name a folder: a target name '
                    f"is written with letters, digits, '-', '_' and '.', and does not "
                    f"start with '.'"
                )
            folder = posixpath.join(self.output_root, target.name)
            for setting in ("results", "coverage"):
                declared = getattr(target, setting)
                if not declared:
                    continue
                written = declared.replace("\\", "/")
                normalized = posixpath.normpath(written)
                if (
                    posixpath.isabs(written)
                    or normalized == ".."
                    or normalized.startswith("../")
                    or normalized == "."
                ):
                    raise ValueError(
                        f'test target "{target.name}" declares {setting} {declared!r}, '
                        f'which is outside its folder "{folder}". A results or '
                        f"coverage path names a file inside that folder, relative to "
                        f'it, such as "junit.xml"; the target\'s command finds the '
                        f"folder in the ELSPAIS_TARGET_OUTPUT environment variable."
                    )
        return self


class JourneyScanningConfig(ScanningKindConfig):
    directories: list[str] = Field(default_factory=lambda: ["spec"])
    file_patterns: list[str] = Field(default_factory=lambda: list(DEFAULT_JOURNEY_PATTERNS))
    # Where UAT results are read from. The health check has always read this
    # setting and the shipped docs have always described it; only the field
    # was missing, so the path was fixed at its default and a project that
    # configured another one was refused.
    results_file: str = "uat-results.csv"


class DocsScanningConfig(ScanningKindConfig):
    directories: list[str] = Field(default_factory=lambda: ["docs"])
    file_patterns: list[str] = Field(default_factory=lambda: list(DEFAULT_DOCS_PATTERNS))


# Implements: REQ-d00212-Y
class ScanningConfig(_StrictModel):
    skip: list[str] = Field(default_factory=list)
    spec: SpecScanningConfig = Field(default_factory=SpecScanningConfig)
    code: CodeScanningConfig = Field(default_factory=CodeScanningConfig)
    test: TestScanningConfig = Field(default_factory=TestScanningConfig)
    journey: JourneyScanningConfig = Field(default_factory=JourneyScanningConfig)
    docs: DocsScanningConfig = Field(default_factory=DocsScanningConfig)


# Implements: REQ-d00212-Y
class OutputConfig(_StrictModel):
    formats: list[str] = Field(default_factory=list)
    dir: str = ""


# Implements: REQ-d00212-Y
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


# Implements: REQ-d00212-Y, REQ-d00202-Q
class AssociateEntryConfig(_StrictModel):
    # The committed configuration may name an associate without saying where
    # it is; the machine-local configuration then supplies the path.
    path: str | None = None
    namespace: str
    # Where the repository can be obtained by someone who does not have it.
    # The path and the namespace identify the member; the remote never does,
    # so a declaration without one is complete.
    git: str | None = None
    color: str | None = None

    @field_validator("namespace")
    @classmethod
    def _v_namespace(cls, v):
        return _validate_namespace(v)

    @field_validator("color")
    @classmethod
    def _v_color(cls, v):
        return _validate_hex_color(v)


# Implements: REQ-d00280-A
class ReportScopeConfig(_StrictModel):
    """A scope a project declares under a name, for reports to be produced under.

    A scope spelled out at the moment a report is run is known only to whoever
    spelled it; declared here it is versioned beside the requirements it selects
    over, and a reader holding a committed report can look up what produced it.

    One name carries both halves of what an audience reads: the requirements a
    report is about and the facts it states about them (REQ-d00280-C). The two
    stay independent choices -- a declaration naming no values constrains none,
    and naming values selects no requirements.
    """

    level: list[str] = Field(default_factory=list)
    not_level: list[str] = Field(default_factory=list)
    status: list[str] = Field(default_factory=list)
    not_status: list[str] = Field(default_factory=list)
    match_status_roles: bool = False
    # Value keys, not the words a project displays them under (REQ-d00282-J).
    # A measure is keyed beneath its dimension: "implemented.immediate_direct".
    # Not judged here: a name the report does not offer is refused where the
    # report is produced (REQ-d00282-F), which is the only place that knows
    # what is on offer.
    values: list[str] = Field(default_factory=list)


class StatusConfig(_StrictModel):
    """Optional per-status metadata. Keys match status names from status_roles."""

    color: str | None = None
    # None = derive from role (active-role -> True). Explicit value wins.
    expects_implementation: bool | None = None

    @field_validator("color")
    @classmethod
    def _v_color(cls, v):
        return _validate_hex_color(v)


# Implements: REQ-d00212-Y
class TermsSeverityConfig(_StrictModel):
    """Severity levels for defined-terms health checks."""

    duplicate: SeverityValue = "error"
    undefined: SeverityValue = "warning"
    unmarked: SeverityValue = "warning"
    unused: SeverityValue = "warning"
    bad_definition: SeverityValue = "error"
    collection_empty: SeverityValue = "warning"
    canonical_form: SeverityValue = "warning"


# Implements: REQ-d00212-Y
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


# Implements: REQ-d00212-Y
class ElspaisConfig(_StrictModel):
    version: int = 5
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
    scopes: dict[str, ReportScopeConfig] = Field(default_factory=dict)
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

    # Implements: REQ-d00212-G
    @model_validator(mode="after")
    def _v_levels_letter_case_collision(self):
        # An identifier's level code is matched case-insensitively
        # (REQ-d00212-R): two levels whose letter differs only in case would
        # make that tolerance ambiguous -- an identifier written in one
        # level's case could equally be the other's typo. Case-insensitive
        # matching is safe only because this pair is refused before either
        # level's identifiers are ever read, the same guard shape as
        # REQ-d00251-F/K for the separator characters.
        seen: dict[str, tuple[str, str]] = {}
        for key, level in (self.levels or {}).items():
            folded = level.letter.lower()
            prior = seen.get(folded)
            if prior is not None and prior[1] != level.letter:
                prior_key, prior_letter = prior
                raise ValueError(
                    f'levels.{key}.letter "{level.letter}" and '
                    f'levels.{prior_key}.letter "{prior_letter}" differ only in '
                    f"case. A repository's identifier configuration must admit "
                    f"exactly one spelling of any given identifier, up to case; "
                    f"give one level a letter the other's case cannot be "
                    f"mistaken for."
                )
            seen.setdefault(folded, (key, level.letter))
        return self

    @field_validator("statuses")
    @classmethod
    def _v_status_keys(cls, v: dict[str, Any]) -> dict[str, Any]:
        # Status keys flow into `.status-badge.{key|lower}` CSS class selectors,
        # JS string literals, and `data-key` attributes. Same identifier shape
        # as namespaces / levels.
        for key in v or {}:
            _validate_namespace(key)
        return v

    @field_validator("scopes")
    @classmethod
    def _v_scope_keys(cls, v: dict[str, Any]) -> dict[str, Any]:
        # A scope name is written on a command line and read back out of a
        # report's disclosure, so it takes the same identifier shape as the
        # other names a project declares.
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
        json_schema_extra={"$schema": "https://json-schema.org/draft/2020-12/schema"},
    )
