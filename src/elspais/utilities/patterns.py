"""Patterns - Configurable requirement ID pattern matching.

Supports multiple ID formats:
- HHT style: REQ-p00001, REQ-CAL-d00001
- Type-prefix style: PRD-00001, OPS-00001, DEV-00001
- Jira style: PROJ-123
- Named: REQ-UserAuth

Ported from core/patterns.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# --- Shared regex patterns ---

# Matches 3+ consecutive newlines for cleanup (collapse to double-newline)
BLANK_LINE_CLEANUP_RE = re.compile(r"\n{3,}")


# --- New ID Pattern System (Tasks 1-4) ---


# Implements: REQ-p00002-A
@dataclass
class TypeDef:
    """Definition of a requirement type (e.g., prd, ops, dev)."""

    code: str
    level: int
    aliases: dict[str, str]


# Implements: REQ-p00002-A
@dataclass
class ComponentFormat:
    """Configuration for the component part of an ID."""

    style: str  # "numeric", "named", "alphanumeric"
    digits: int
    leading_zeros: bool
    pattern: str | None


# Implements: REQ-p00002-A
@dataclass
class AssertionFormat:
    """Configuration for assertion labels."""

    label_style: str  # "uppercase", "numeric", "alphanumeric", "numeric_1based"
    max_count: int
    zero_pad: bool
    multi_separator: str


# Implements: REQ-p00002-A
@dataclass
class IdPatternConfig:
    """Configuration for the ID pattern system.

    Parsed from [project].namespace + [id-patterns] config sections.
    """

    namespace: str
    canonical_template: str
    aliases: dict[str, str]
    types: dict[str, TypeDef]
    component: ComponentFormat
    assertions: AssertionFormat
    output_forms: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IdPatternConfig:
        """Create IdPatternConfig from a full configuration dictionary.

        Reads [project].namespace and [id-patterns] sections.
        """
        project = data.get("project", {})
        namespace = project.get("namespace", "REQ")

        patterns = data.get("id-patterns", {})
        canonical = patterns.get("canonical", "{namespace}-{type}{component}")
        aliases = dict(patterns.get("aliases", {}))

        # Parse types
        raw_types = patterns.get("types", {})
        types: dict[str, TypeDef] = {}
        for code, tdef in raw_types.items():
            if isinstance(tdef, dict):
                level = tdef.get("level", 1)
                type_aliases = dict(tdef.get("aliases", {}))
            else:
                level = 1
                type_aliases = {}
            types[code] = TypeDef(code=code, level=level, aliases=type_aliases)

        # Parse component format
        raw_comp = patterns.get("component", {})
        component = ComponentFormat(
            style=raw_comp.get("style", "numeric"),
            digits=raw_comp.get("digits", 5),
            leading_zeros=raw_comp.get("leading_zeros", True),
            pattern=raw_comp.get("pattern"),
        )

        # Parse assertion format
        raw_assert = patterns.get("assertions", {})
        assertions = AssertionFormat(
            label_style=raw_assert.get("label_style", "uppercase"),
            max_count=raw_assert.get("max_count", 26),
            zero_pad=raw_assert.get("zero_pad", False),
            multi_separator=(
                raw_assert.get("separator", {}).get("multi", "+")
                if isinstance(raw_assert.get("separator"), dict)
                else raw_assert.get("multi_separator", "+")
            ),
        )

        # Parse output forms
        output = data.get("output", {})
        output_forms = dict(output.get("id-patterns", {}))

        return cls(
            namespace=namespace,
            canonical_template=canonical,
            aliases=aliases,
            types=types,
            component=component,
            assertions=assertions,
            output_forms=output_forms,
        )


# Implements: REQ-p00002-A
@dataclass
class ParsedId:
    """Result of parsing a requirement ID string."""

    namespace: str
    type_code: str
    component: str
    assertions: list[str]
    fqn: str

    @property
    def kind(self) -> str:
        """Return 'assertion' if assertions present, else 'requirement'."""
        return "assertion" if self.assertions else "requirement"


# Implements: REQ-p00002-A
class IdResolver:
    """Single authority for parsing, normalizing, and rendering requirement IDs."""

    def __init__(self, config: IdPatternConfig):
        self.config = config
        # Build reverse alias lookup: {alias_name: {alias_value: canonical_type_code}}
        self._reverse_aliases: dict[str, dict[str, str]] = {}
        for type_code, tdef in config.types.items():
            for alias_name, alias_value in tdef.aliases.items():
                if alias_name not in self._reverse_aliases:
                    self._reverse_aliases[alias_name] = {}
                self._reverse_aliases[alias_name][alias_value] = type_code

        # Compile all forms: list of (form_name, compiled_regex, type_alias_name_or_None)
        # type_alias_name is the TypeDef alias name used in the template (e.g., "letter")
        self._forms: list[tuple[str, re.Pattern, str | None]] = []
        # canonical
        canonical_re = self._compile_regex(config.canonical_template)
        self._forms.append(("canonical", canonical_re, None))
        # aliases
        for form_name, form_template in config.aliases.items():
            type_alias_name = self._extract_type_alias_name(form_template)
            alias_re = self._compile_regex(form_template)
            self._forms.append((form_name, alias_re, type_alias_name))

        # Compile renderers: {form_name: template_string}
        self._renderers: dict[str, str] = {"canonical": config.canonical_template}
        self._renderers.update(config.aliases)

    @staticmethod
    def _extract_type_alias_name(template: str) -> str | None:
        """Extract the TypeDef alias name from a template (e.g., 'letter' from '{type.letter}')."""
        m = re.search(r"\{type\.(\w+)\}", template)
        return m.group(1) if m else None

    def _compile_regex(self, template: str) -> re.Pattern:
        """Compile a template string into a regex for parsing."""
        pattern = template

        # {namespace} -> literal match
        pattern = pattern.replace(
            "{namespace}", f"(?P<namespace>{re.escape(self.config.namespace)})"
        )

        # {type} -> alternation of canonical type codes
        type_codes = list(self.config.types.keys())
        if type_codes and "{type}" in pattern:
            type_alt = "|".join(re.escape(t) for t in type_codes)
            pattern = pattern.replace("{type}", f"(?P<type>{type_alt})")

        # {type.<alias_name>} -> alternation of alias values
        for match in re.finditer(r"\{type\.(\w+)\}", template):
            alias_name = match.group(1)
            if alias_name in self._reverse_aliases:
                values = list(self._reverse_aliases[alias_name].keys())
                val_alt = "|".join(re.escape(v) for v in values)
                pattern = pattern.replace(match.group(0), f"(?P<type>{val_alt})")

        # {component} -> based on component config
        comp = self.config.component
        if comp.style == "numeric":
            if comp.digits > 0:
                comp_pattern = rf"\d{{1,{comp.digits}}}"
            else:
                comp_pattern = r"\d+"
        elif comp.style == "named":
            comp_pattern = comp.pattern or r"[A-Za-z][A-Za-z0-9]+"
        elif comp.style == "alphanumeric":
            comp_pattern = comp.pattern or r"[A-Z0-9]+"
        else:
            comp_pattern = r"[A-Za-z0-9]+"
        pattern = pattern.replace("{component}", f"(?P<component>{comp_pattern})")

        # Assertion suffix (optional)
        assertion_suffix = self._build_assertion_suffix()
        pattern = f"^{pattern}{assertion_suffix}$"

        return re.compile(pattern)

    def _build_assertion_suffix(self) -> str:
        """Build optional assertion suffix regex."""
        af = self.config.assertions
        label_pat = self._assertion_label_regex_str()
        sep = re.escape(af.multi_separator) if af.multi_separator else r"\+"
        return rf"(?:-(?P<assertions>{label_pat}(?:{sep}{label_pat})*))?"

    def _assertion_label_regex_str(self) -> str:
        """Get regex for a single assertion label."""
        af = self.config.assertions
        style = af.label_style
        if style == "uppercase":
            return r"[A-Z]"
        elif style == "numeric":
            return r"[0-9]{2}" if af.zero_pad else r"[0-9]{1,2}"
        elif style == "alphanumeric":
            return r"[0-9A-Z]"
        elif style == "numeric_1based":
            return r"[0-9]{2}" if af.zero_pad else r"[1-9][0-9]?"
        return r"[A-Z]"

    def parse(self, raw_id: str) -> ParsedId | None:
        """Try all compiled forms. Returns ParsedId with canonical type_code."""
        # Reject composite IDs — callers must split on :: first
        if "::" in raw_id:
            return None
        for _form_name, regex, alias_used in self._forms:
            m = regex.match(raw_id)
            if m:
                return self._match_to_parsed_id(m, alias_used)
        return None

    def _match_to_parsed_id(self, m: re.Match, alias_used: str | None) -> ParsedId:
        """Convert regex match to ParsedId."""
        groups = m.groupdict()
        namespace = groups.get("namespace", self.config.namespace)
        raw_type = groups.get("type", "")
        component = groups.get("component", "")

        # Resolve type alias to canonical code
        if alias_used and alias_used in self._reverse_aliases:
            type_code = self._reverse_aliases[alias_used].get(raw_type, raw_type)
        else:
            type_code = raw_type

        # If type is empty (JIRA-style with no {type} in template), use first type
        if not type_code and self.config.types:
            type_code = next(iter(self.config.types))

        # Normalize component (zero-pad if needed)
        comp = self.config.component
        if comp.style == "numeric" and comp.digits > 0 and comp.leading_zeros:
            component = component.zfill(comp.digits)

        # Parse assertions
        assertions_str = groups.get("assertions", "")
        assertions: list[str] = []
        if assertions_str:
            af = self.config.assertions
            sep = af.multi_separator if af.multi_separator else "+"
            assertions = assertions_str.split(sep)

        # Render FQN (canonical form without assertion)
        fqn = self._render_template(self.config.canonical_template, namespace, type_code, component)

        return ParsedId(
            namespace=namespace,
            type_code=type_code,
            component=component,
            assertions=assertions,
            fqn=fqn,
        )

    def _render_template(
        self, template: str, namespace: str, type_code: str, component: str
    ) -> str:
        """Render a template with given values."""
        result = template.replace("{namespace}", namespace)
        result = result.replace("{type}", type_code)
        result = result.replace("{component}", component)

        # Handle {type.<alias>} tokens
        if "{type." in result:
            tdef = self.config.types.get(type_code)
            if tdef:
                for alias_name, alias_value in tdef.aliases.items():
                    result = result.replace(f"{{type.{alias_name}}}", alias_value)

        return result

    def to_canonical(self, raw_id: str) -> str | None:
        """Parse then render as canonical. Returns None if no form matches."""
        parsed = self.parse(raw_id)
        if parsed is None:
            return None
        result = parsed.fqn
        if parsed.assertions:
            af = self.config.assertions
            sep = af.multi_separator if af.multi_separator else "+"
            result += f"-{sep.join(parsed.assertions)}"
        return result

    def is_valid(self, raw_id: str) -> bool:
        """True if any form matches."""
        return self.parse(raw_id) is not None

    # --- Task 4: Rendering, expand, validation, assertion labels ---

    def render(self, parsed_id: ParsedId, form: str = "canonical") -> str:
        """Render a ParsedId using a named form."""
        if form not in self._renderers:
            raise KeyError(f"Unknown form: {form!r}. Available: {list(self._renderers.keys())}")
        template = self._renderers[form]
        result = self._render_template(
            template, parsed_id.namespace, parsed_id.type_code, parsed_id.component
        )
        if parsed_id.assertions:
            af = self.config.assertions
            sep = af.multi_separator if af.multi_separator else "+"
            result += f"-{sep.join(parsed_id.assertions)}"
        return result

    def render_canonical(self, parsed_id: ParsedId) -> str:
        """Shorthand for render(parsed_id, 'canonical')."""
        return self.render(parsed_id, "canonical")

    def output_form(self, context: str) -> str:
        """Look up [output.id-patterns] for context. Defaults to 'canonical'."""
        return self.config.output_forms.get(context, "canonical")

    def render_for(self, parsed_id: ParsedId, context: str) -> str:
        """render(parsed_id, output_form(context))."""
        return self.render(parsed_id, self.output_form(context))

    def expand(self, parsed_id: ParsedId) -> list[ParsedId]:
        """Expand multi-assertion into individual ParsedIds."""
        if len(parsed_id.assertions) <= 1:
            return [parsed_id]
        return [
            ParsedId(
                namespace=parsed_id.namespace,
                type_code=parsed_id.type_code,
                component=parsed_id.component,
                assertions=[label],
                fqn=parsed_id.fqn,
            )
            for label in parsed_id.assertions
        ]

    def is_valid_assertion_label(self, label: str) -> bool:
        """True if label matches configured assertion format."""
        pat = self._assertion_label_regex_str()
        return re.match(f"^{pat}$", label) is not None

    def format_assertion_label(self, index: int) -> str:
        """Convert zero-based index to label string."""
        af = self.config.assertions
        style = af.label_style
        zero_pad = af.zero_pad
        max_count = af.max_count

        if index < 0 or index >= max_count:
            raise ValueError(f"Index {index} out of range (0-{max_count - 1})")

        if style == "uppercase":
            return chr(ord("A") + index)
        elif style == "numeric":
            return f"{index:02d}" if zero_pad else str(index)
        elif style == "alphanumeric":
            if index < 10:
                return str(index)
            else:
                return chr(ord("A") + index - 10)
        elif style == "numeric_1based":
            return f"{index + 1:02d}" if zero_pad else str(index + 1)
        return chr(ord("A") + index)

    def parse_assertion_label_index(self, label: str) -> int:
        """Convert label string to zero-based index."""
        af = self.config.assertions
        style = af.label_style

        if style == "uppercase":
            if len(label) == 1 and label.isupper():
                return ord(label) - ord("A")
        elif style == "numeric":
            return int(label)
        elif style == "alphanumeric":
            if label.isdigit():
                return int(label)
            elif len(label) == 1 and label.isupper():
                return ord(label) - ord("A") + 10
        elif style == "numeric_1based":
            return int(label) - 1

        raise ValueError(f"Cannot parse assertion label: {label}")

    def resolve_level(self, raw_level: str) -> str | None:
        """Map raw level text to canonical type code."""
        lower = raw_level.lower()
        # Check type codes directly
        for code in self.config.types:
            if code.lower() == lower:
                return code
        # Check alias values
        for code, tdef in self.config.types.items():
            for alias_value in tdef.aliases.values():
                if alias_value.lower() == lower:
                    return code
        return None

    def canonical_regex(self) -> re.Pattern:
        """Compiled regex for the canonical form (anchored with ^...$)."""
        return self._forms[0][1]

    def search_regex(self) -> re.Pattern:
        """Unanchored regex for finding canonical IDs within longer text."""
        pat = self._forms[0][1].pattern
        # Strip ^ and $ anchors
        if pat.startswith("^"):
            pat = pat[1:]
        if pat.endswith("$"):
            pat = pat[:-1]
        return re.compile(pat)

    def all_type_codes(self) -> list[str]:
        """All canonical type codes."""
        return list(self.config.types.keys())


# Implements: REQ-p00002-A
def find_req_header(content: str, req_id: str) -> re.Match | None:
    """Find a requirement header line by ID.

    Matches any heading level: # REQ-xxx: Title, ## REQ-xxx: Title, etc.
    Group 1 = full header line, Group 2 = title text.

    Args:
        content: File content to search.
        req_id: Requirement ID to find.

    Returns:
        Match object or None if not found.
    """
    pattern = re.compile(
        rf"^(#+ {re.escape(req_id)}:\s*(.+?)\s*)$",
        re.MULTILINE,
    )
    return pattern.search(content)


@dataclass
class ParsedRequirement:
    """Result of parsing a requirement ID string."""

    full_id: str
    prefix: str
    associated: str | None
    type_code: str
    number: str
    assertion: str | None = None


@dataclass
# Implements: REQ-p00002-A
class PatternConfig:
    """Configuration for requirement ID patterns.

    Attributes:
        id_template: Template string with tokens {prefix}, {associated}, {type}, {id}
        prefix: Base prefix (e.g., "REQ")
        types: Dictionary of type definitions
        id_format: ID format configuration (style, digits, etc.)
        associated: Optional associated repo namespace configuration
        assertions: Optional assertion label format configuration
    """

    id_template: str
    prefix: str
    types: dict[str, dict[str, Any]]
    id_format: dict[str, Any]
    associated: dict[str, Any] | None = None
    assertions: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PatternConfig:
        """Create PatternConfig from configuration dictionary."""
        return cls(
            id_template=data.get("id_template", "{prefix}-{type}{id}"),
            prefix=data.get("prefix", "REQ"),
            types=data.get("types", {}),
            id_format=data.get("id_format", {"style": "numeric", "digits": 5}),
            associated=data.get("associated"),
            assertions=data.get("assertions"),
        )

    def get_type_by_id(self, type_id: str) -> dict[str, Any] | None:
        """Get type configuration by type ID."""
        for config in self.types.values():
            if config.get("id") == type_id:
                return config
        return None

    def resolve_level(self, raw_level: str) -> str | None:
        """Resolve raw level text to canonical type key.

        Case-insensitive match against config type keys.

        Args:
            raw_level: Raw level text from spec file (e.g., "Dev", "PRD", "ops").

        Returns:
            Canonical type key (e.g., "dev", "prd", "ops") or None if unrecognized.
        """
        lower = raw_level.lower()
        for key in self.types:
            if key.lower() == lower:
                return key
        return None

    def get_all_type_ids(self) -> list[str]:
        """Get list of all type IDs."""
        return [config.get("id", "") for config in self.types.values()]

    def get_assertion_label_pattern(self) -> str:
        """Get regex pattern for assertion labels based on configuration."""
        assertions = self.assertions or {}
        style = assertions.get("label_style", "uppercase")
        zero_pad = assertions.get("zero_pad", False)

        if style == "uppercase":
            return r"[A-Z]"
        elif style == "numeric":
            if zero_pad:
                return r"[0-9]{2}"
            return r"[0-9]{1,2}"
        elif style == "alphanumeric":
            return r"[0-9A-Z]"
        elif style == "numeric_1based":
            if zero_pad:
                return r"[0-9]{2}"
            return r"[1-9][0-9]?"
        else:
            return r"[A-Z]"

    def get_assertion_max_count(self) -> int:
        """Get maximum number of assertions allowed."""
        assertions = self.assertions or {}
        style = assertions.get("label_style", "uppercase")
        max_count = assertions.get("max_count")

        if max_count is not None:
            return int(max_count)

        if style == "uppercase":
            return 26
        elif style == "numeric":
            return 100
        elif style == "alphanumeric":
            return 36
        elif style == "numeric_1based":
            return 99
        return 26


# Implements: REQ-p00002-A
class PatternValidator:
    """Validates and parses requirement IDs against configured patterns."""

    def __init__(self, config: PatternConfig):
        """Initialize pattern validator.

        Args:
            config: Pattern configuration
        """
        self.config = config
        self._regex = self._build_regex()
        self._regex_with_assertion = self._build_regex(include_assertion=True)
        self._assertion_label_regex = re.compile(f"^{self.config.get_assertion_label_pattern()}$")

    def _build_regex(self, include_assertion: bool = False) -> re.Pattern:
        """Build regex pattern from configuration."""
        template = self.config.id_template

        # Build type alternatives
        type_ids = self.config.get_all_type_ids()
        type_pattern = "|".join(re.escape(t) for t in type_ids if t)

        # Build ID pattern based on format
        id_format = self.config.id_format
        style = id_format.get("style", "numeric")

        if style == "numeric":
            digits = int(id_format.get("digits", 5))
            leading_zeros = id_format.get("leading_zeros", True)
            if digits > 0 and leading_zeros:
                id_pattern = f"\\d{{{digits}}}"
            elif digits > 0:
                id_pattern = f"\\d{{1,{digits}}}"
            else:
                id_pattern = "\\d+"
        elif style == "named":
            pattern = id_format.get("pattern", "[A-Za-z][A-Za-z0-9]+")
            id_pattern = pattern
        elif style == "alphanumeric":
            pattern = id_format.get("pattern", "[A-Z0-9]+")
            id_pattern = pattern
        else:
            id_pattern = "[A-Za-z0-9]+"

        # Build associated pattern if enabled
        associated_config = self.config.associated or {}
        if associated_config.get("enabled"):
            length = associated_config.get("length", 3)
            sep = re.escape(associated_config.get("separator", "-"))
            if length:
                associated_pattern = f"(?P<associated>[A-Z]{{{length}}}){sep}"
            else:
                associated_pattern = f"(?P<associated>[A-Z]+){sep}"
        else:
            associated_pattern = "(?P<associated>)"

        # Build full regex from template
        pattern = template
        pattern = pattern.replace("{prefix}", f"(?P<prefix>{re.escape(self.config.prefix)})")

        if "{associated}" in pattern:
            pattern = pattern.replace("{associated}", f"(?:{associated_pattern})?")
        else:
            pattern = pattern.replace("{associated}", "")

        if type_pattern:
            pattern = pattern.replace("{type}", f"(?P<type>{type_pattern})")
        else:
            pattern = pattern.replace("{type}", "(?P<type>)")

        pattern = pattern.replace("{id}", f"(?P<id>{id_pattern})")

        if include_assertion:
            assertion_pattern = self.config.get_assertion_label_pattern()
            pattern = f"{pattern}(?:-(?P<assertion>{assertion_pattern}))?"

        return re.compile(f"^{pattern}$")

    def parse(self, id_string: str, allow_assertion: bool = False) -> ParsedRequirement | None:
        """Parse a requirement ID string into components.

        Args:
            id_string: The requirement ID to parse
            allow_assertion: If True, allow and parse assertion suffix

        Returns:
            ParsedRequirement if valid, None if invalid
        """
        regex = self._regex_with_assertion if allow_assertion else self._regex
        match = regex.match(id_string)
        if not match:
            return None

        groups = match.groupdict()
        return ParsedRequirement(
            full_id=id_string,
            prefix=groups.get("prefix", ""),
            associated=groups.get("associated") or None,
            type_code=groups.get("type", ""),
            number=groups.get("id", ""),
            assertion=groups.get("assertion") or None,
        )

    def is_valid(self, id_string: str, allow_assertion: bool = False) -> bool:
        """Check if an ID string is valid.

        Args:
            id_string: The requirement ID to validate
            allow_assertion: If True, allow assertion suffix

        Returns:
            True if valid, False otherwise
        """
        return self.parse(id_string, allow_assertion=allow_assertion) is not None

    def is_valid_assertion_label(self, label: str) -> bool:
        """Check if an assertion label is valid.

        Args:
            label: The assertion label to validate

        Returns:
            True if valid, False otherwise
        """
        return self._assertion_label_regex.match(label) is not None

    def format_assertion_label(self, index: int) -> str:
        """Format an assertion label from a zero-based index.

        Args:
            index: Zero-based index (0 = A or 00, 1 = B or 01, etc.)

        Returns:
            Formatted assertion label
        """
        assertions = self.config.assertions or {}
        style = assertions.get("label_style", "uppercase")
        zero_pad = assertions.get("zero_pad", False)

        if style == "uppercase":
            if index < 0 or index >= 26:
                raise ValueError(f"Index {index} out of range for uppercase labels (0-25)")
            return chr(ord("A") + index)
        elif style == "numeric":
            if zero_pad:
                return f"{index:02d}"
            return str(index)
        elif style == "alphanumeric":
            if index < 10:
                return str(index)
            elif index < 36:
                return chr(ord("A") + index - 10)
            else:
                raise ValueError(f"Index {index} out of range for alphanumeric labels (0-35)")
        elif style == "numeric_1based":
            if zero_pad:
                return f"{index + 1:02d}"
            return str(index + 1)
        else:
            return chr(ord("A") + index)

    def parse_assertion_label_index(self, label: str) -> int:
        """Parse an assertion label to get its zero-based index.

        Args:
            label: The assertion label

        Returns:
            Zero-based index
        """
        assertions = self.config.assertions or {}
        style = assertions.get("label_style", "uppercase")

        if style == "uppercase":
            if len(label) == 1 and label.isupper():
                return ord(label) - ord("A")
        elif style == "numeric":
            return int(label)
        elif style == "alphanumeric":
            if label.isdigit():
                return int(label)
            elif len(label) == 1 and label.isupper():
                return ord(label) - ord("A") + 10
        elif style == "numeric_1based":
            return int(label) - 1

        raise ValueError(f"Cannot parse assertion label: {label}")

    def format(self, type_code: str, number: int, associated: str | None = None) -> str:
        """Format a requirement ID from components.

        Args:
            type_code: The requirement type code
            number: The requirement number
            associated: Optional associated repo code

        Returns:
            Formatted requirement ID string
        """
        template = self.config.id_template
        id_format = self.config.id_format

        style = id_format.get("style", "numeric")
        if style == "numeric":
            digits = int(id_format.get("digits", 5))
            leading_zeros = id_format.get("leading_zeros", True)
            if digits > 0 and leading_zeros:
                formatted_number = str(number).zfill(digits)
            else:
                formatted_number = str(number)
        else:
            formatted_number = str(number)

        result = template
        result = result.replace("{prefix}", self.config.prefix)

        if associated and "{associated}" in result:
            associated_config = self.config.associated or {}
            sep = associated_config.get("separator", "-")
            result = result.replace("{associated}", f"{associated}{sep}")
        else:
            result = result.replace("{associated}", "")

        result = result.replace("{type}", type_code)
        result = result.replace("{id}", formatted_number)

        return result

    def extract_implements_ids(self, implements_str: str) -> list[str]:
        """Extract requirement IDs from an Implements field value.

        Args:
            implements_str: The Implements field value

        Returns:
            List of normalized requirement IDs
        """
        if not implements_str:
            return []

        parts = [p.strip() for p in implements_str.split(",")]
        result = []

        for part in parts:
            if not part:
                continue
            if self.is_valid(part):
                result.append(part)
            else:
                result.append(part)

        return result


# Implements: REQ-p00002-A
def normalize_req_id(
    req_id: str,
    prefix_or_validator: str | PatternValidator = "REQ",
) -> str:
    """Normalize ID to canonical format.

    Examples:
        'd00027' -> 'REQ-d00027'
        'REQ-d00027' -> 'REQ-d00027'

    Args:
        req_id: The requirement ID to normalize
        prefix_or_validator: Either a prefix string or a PatternValidator instance

    Returns:
        Normalized ID with prefix
    """
    if isinstance(prefix_or_validator, PatternValidator):
        prefix = prefix_or_validator.config.prefix
    else:
        prefix = prefix_or_validator

    if req_id.startswith(f"{prefix}-"):
        return req_id
    return f"{prefix}-{req_id}"
