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
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.graph.reference_faults import RefItem

# --- Errors ---


class GrammarUnavailable(RuntimeError):
    """A caller must spell an identifier but holds no repository grammar.

    Deliberately not a ``ValueError``: the render layer catches that to mean
    "this node is not independently renderable", and a missing grammar
    swallowed by that catch would degrade output rather than stop it.
    """


# --- Constants ---

INSTANCE_SEPARATOR = "::"

# The character between two references of one list. One spelling, shared by
# every surface that reads a list of references, so a *Requirement*'s
# metadata line and a code annotation admit exactly the same target.
REF_LIST_SEPARATOR = ","

# --- Shared regex patterns ---

# Matches 3+ consecutive newlines for cleanup (collapse to double-newline)
BLANK_LINE_CLEANUP_RE = re.compile(r"\n{3,}")

# Pattern for `[project].namespace` and `[associates.*].namespace`.
# Namespaces appear in CSS attribute selectors, JS string literals, ID
# attributes, and URL paths; restricting them to a plain identifier shape
# means none of those surfaces ever needs special quoting or escaping.
NAMESPACE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


def validate_namespace(value: str) -> str:
    """Return ``value`` if it is a valid namespace string; raise ``ValueError``
    otherwise. Single authority for the namespace shape — pydantic field
    validators in `config/schema.py` reuse this so there's only one regex.
    """
    if not isinstance(value, str) or not NAMESPACE_RE.match(value):
        raise ValueError(
            f"namespace must start with a letter and contain only "
            f'letters/digits/"_"/"-" (got {value!r}). Restricting this avoids '
            "CSS-selector / URL / JS escaping bugs across UI surfaces."
        )
    return value


# --- New ID Pattern System (Tasks 1-4) ---


# Implements: REQ-p00002-A
@dataclass
class TypeDef:
    """Definition of a requirement type (e.g., prd, ops, dev)."""

    code: str
    level: int
    aliases: dict[str, str]


# Implements: REQ-p00002-A, REQ-d00251-A
@dataclass
class ComponentFormat:
    """Configuration for the component part of an ID."""

    style: str  # one of: numeric, camelCase, PascalCase, snake_case, kebab-case, regex
    digits: int
    leading_zeros: bool
    pattern: str | None


# Implements: REQ-p00002-A, REQ-d00251-E
@dataclass
class AssertionFormat:
    """Configuration for assertion labels."""

    label_style: str  # "uppercase", "numeric", "alphanumeric", "numeric_1based"
    max_count: int
    zero_pad: bool
    multi_separator: str
    separator: str = "-"


# Implements: REQ-d00251-L
def _schema_default_canonical() -> str:
    """The canonical identifier template a configuration defaults to."""
    from elspais.config.schema import IdPatternsConfig

    return IdPatternsConfig.model_fields["canonical"].default


def _schema_default_assertion(field_name: str) -> Any:
    """A default the assertion grammar takes when a raw dict omits the field.

    Read off the schema rather than spelled again here. The schema is where
    a configuration acquires its defaults, and a second copy of one is a
    second grammar the moment the two disagree.
    """
    from elspais.config.schema import AssertionConfig

    return AssertionConfig.model_fields[field_name].default


@dataclass(frozen=True)
class IdGrammar:
    """The regex fragments of one repository's identifier grammar.

    Uncompiled and unanchored, so a consumer can embed a fragment in a
    larger grammar without reconstructing it. Produced only by
    ``IdResolver.grammar()``.
    """

    namespace: str
    level: str
    component: str
    identifier: str
    assertion_label: str
    assertion_label_exact: str
    assertion_separator: str
    multi_separator: str


# Each case-style's own internal punctuation. A notation that cannot spell it
# substitutes its own character for it, so it is a parameter rather than a
# literal inside the pattern.
STYLE_INTERNAL_SEPARATOR = {"snake_case": "_", "kebab-case": "-"}


def _respell(segment: str, separator: str) -> str:
    """Rewrite a template's literal punctuation into *separator*'s notation.

    One rule, used wherever a notation is rendered: a notation spends its one
    character on every boundary the template spells with ``-`` or ``_``, and
    leaves everything else alone.
    """
    return "".join(separator if c in "-_" else c for c in segment)


def component_regex(component: ComponentFormat, internal_separator: str | None = None) -> str:
    """Resolve a ComponentFormat to its regex string.

    Sole authority for the style → regex mapping. No other code path may
    contain a component-style dispatch.

    Args:
        internal_separator: Spell a case-style's internal punctuation with
            this character instead of its own. A Python test name can write
            ``data-export`` only as ``data_export``, and a pattern still
            demanding the hyphen would match nothing.
    """
    style = component.style
    if style == "numeric":
        if component.digits > 0:
            return rf"\d{{1,{component.digits}}}"
        return r"\d+"
    if style == "camelCase":
        return r"[a-z][a-zA-Z0-9]+"
    if style == "PascalCase":
        return r"[A-Z][a-zA-Z0-9]+"
    if style in ("snake_case", "kebab-case"):
        sep = re.escape(internal_separator or STYLE_INTERNAL_SEPARATOR[style])
        return rf"[a-z][a-z0-9]*(?:{sep}[a-z0-9]+)*"
    if style == "regex":
        return component.pattern or r"[A-Za-z][A-Za-z0-9]+"
    # Defensive: schema validation already rejects unknown values, but
    # if a non-validated path constructs ComponentFormat directly we
    # fall back to a permissive default rather than crashing.
    return r"[A-Za-z][A-Za-z0-9]+"


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
        # The schema's default, not a second copy of it. This one had drifted
        # to a token the schema stopped using, so a caller reaching here
        # without a canonical template got a different grammar than any
        # configuration file produces.
        canonical = patterns.get("canonical") or _schema_default_canonical()
        aliases = dict(patterns.get("aliases", {}))

        # Levels are declared in the top-level [levels] section. An
        # `id-patterns.types` table is not part of the configuration the
        # schema admits, so reading one here would build a grammar from a
        # shape no config file can hold -- and would go on answering for
        # callers that hand-build one instead of loading a config.
        raw_types: dict[str, Any] = {}
        for code, ldef in data.get("levels", {}).items():
            if isinstance(ldef, dict):
                raw_types[code] = {
                    "level": ldef.get("rank", 1),
                    "aliases": {"letter": ldef.get("letter", code[0])},
                }
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
            label_style=raw_assert.get("label_style", _schema_default_assertion("label_style")),
            max_count=raw_assert.get("max_count", _schema_default_assertion("max_count")),
            zero_pad=raw_assert.get("zero_pad", _schema_default_assertion("zero_pad")),
            separator=raw_assert.get("separator", _schema_default_assertion("separator")),
            multi_separator=raw_assert.get(
                "multi_separator", _schema_default_assertion("multi_separator")
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

        self._ci_forms: list[tuple[str, re.Pattern, str | None]] | None = None
        # The same forms rendered in an alternate notation, keyed by the
        # notation's character. Compiled on first use.
        self._notation_forms_cache: dict[str, list[tuple[str, re.Pattern, str | None]]] = {}
        # Compile all forms: list of (form_name, compiled_regex, type_alias_name_or_None)
        # type_alias_name is the TypeDef alias name used in the template (e.g., "letter")
        self._forms: list[tuple[str, re.Pattern, str | None]] = []
        # canonical
        canonical_alias = self._extract_type_alias_name(config.canonical_template)
        canonical_re = self._compile_regex(config.canonical_template)
        self._forms.append(("canonical", canonical_re, canonical_alias))
        # aliases
        for form_name, form_template in config.aliases.items():
            type_alias_name = self._extract_type_alias_name(form_template)
            alias_re = self._compile_regex(form_template)
            self._forms.append((form_name, alias_re, type_alias_name))

        # Compile renderers: {form_name: template_string}
        self._renderers: dict[str, str] = {"canonical": config.canonical_template}
        self._renderers.update(config.aliases)

        # Loose detection regex used by quick "does this text contain a
        # REQ-id?" pre-filters such as the heredoc-claim detector. Matches
        # any token starting with the configured namespace OR any
        # configured type code, followed by `-` or `_` and word chars.
        prefixes: set[str] = {config.namespace, *config.types.keys()} - {""}
        if prefixes:
            alt = "|".join(re.escape(p) for p in sorted(prefixes, key=len, reverse=True))
            self._loose_id_regex: re.Pattern = re.compile(rf"\b(?:{alt})[-_]\w+", re.IGNORECASE)
        else:
            # No prefixes configured -- never match (parser will not claim).
            self._loose_id_regex = re.compile(r"(?!)")

    def contains_id_reference(self, text: str) -> bool:
        """Return True if ``text`` contains any token shaped like a configured REQ id.

        Used as a fast pre-filter by parsers that need to decide whether a
        chunk of text (e.g. an embedded heredoc) is worth claiming. Does
        not validate the id beyond the prefix and shape; full validation
        happens in ``parse()``.
        """
        return self._loose_id_regex.search(text) is not None

    @staticmethod
    def _extract_type_alias_name(template: str) -> str | None:
        """Extract alias name from template.

        E.g., 'letter' from '{type.letter}' or '{level.letter}'.
        """
        m = re.search(r"\{(?:type|level)\.(\w+)\}", template)
        return m.group(1) if m else None

    def _compile_regex(self, template: str, separator: str | None = None) -> re.Pattern:
        """Compile a template string into a regex for parsing.

        Args:
            separator: Compile the template in an alternate notation, where
                every boundary -- the template's own literals, the component's
                internal punctuation and the *Assertion* separator -- is
                spelled with this character. A Python test name can spell them
                only as ``_``; that is one grammar in two notations, so the
                notation is a parameter here rather than a second derivation.
        """
        pattern = template
        if separator is not None:
            parts = re.split(r"(\{[^}]+\})", template)
            pattern = "".join(
                part if part.startswith("{") else _respell(part, separator) for part in parts
            )

        # {namespace} -> literal match
        pattern = pattern.replace(
            "{namespace}", f"(?P<namespace>{re.escape(self.config.namespace)})"
        )

        # {type} -> alternation of canonical type codes
        type_codes = list(self.config.types.keys())
        if type_codes and "{type}" in pattern:
            type_alt = "|".join(re.escape(t) for t in type_codes)
            pattern = pattern.replace("{type}", f"(?P<type>{type_alt})")

        # {type.<alias_name>} or {level.<alias_name>} -> alternation of alias values
        for match in re.finditer(r"\{(?:type|level)\.(\w+)\}", template):
            alias_name = match.group(1)
            if alias_name in self._reverse_aliases:
                values = list(self._reverse_aliases[alias_name].keys())
                val_alt = "|".join(re.escape(v) for v in values)
                pattern = pattern.replace(match.group(0), f"(?P<type>{val_alt})")

        # {component} -> resolved via the single style→regex helper
        comp_pattern = component_regex(self.config.component, internal_separator=separator)
        pattern = pattern.replace("{component}", f"(?P<component>{comp_pattern})")

        # Assertion suffix (optional)
        assertion_suffix = self._build_assertion_suffix(separator)
        pattern = f"^{pattern}{assertion_suffix}$"

        return re.compile(pattern)

    def _build_assertion_suffix(self, separator: str | None = None) -> str:
        """Build optional assertion suffix regex.

        The multi-*Assertion* separator is not a boundary the notation has to
        respell -- it is not punctuation an identifier can be embedded behind
        -- so it stays as configured, matching ``grammar()``.
        """
        af = self.config.assertions
        label_pat = self._assertion_label_regex_str()
        sep = re.escape(separator if separator is not None else af.separator)
        multi = re.escape(af.multi_separator)
        return rf"(?:{sep}(?P<assertions>{label_pat}(?:{multi}{label_pat})*))?"

    @property
    def assertion_label_pattern(self) -> str:
        """Regex matching one assertion label under the configured style.

        Public counterpart of the suffix builder's label class, for callers
        that compose their own reference regex (reference extraction) and
        must recognize labels exactly as ``parse()`` does.
        """
        return self._assertion_label_regex_str()

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

    # Implements: REQ-d00251-L
    def grammar(self, separator: str | None = None) -> IdGrammar:
        """The regex fragments of this repository's identifier grammar.

        Every consumer that has to recognise, parse or expand an identifier
        takes its patterns from here, so a repository's configuration is
        interpreted once and the surfaces cannot drift apart.  The fragments
        are uncompiled and unanchored so a caller can embed them in a larger
        grammar; the compiled, anchored form is ``canonical_regex``.

        Args:
            separator: Render the same grammar with this character wherever
                the identifier's own punctuation appears.  Test function
                names spell ``REQ-d00001-A`` as ``REQ_d00001_A``; that is one
                grammar in two notations, not two grammars, so the notation
                is a parameter here rather than a second derivation
                elsewhere.
        """
        cfg = self.config
        namespace = re.escape(cfg.namespace)

        alias_values = self.all_type_alias_values()
        level = "|".join(re.escape(v) for v in alias_values) if alias_values else "[a-z]"

        component = component_regex(cfg.component, internal_separator=separator)
        if cfg.component.style in ("camelCase", "PascalCase", "snake_case", "kebab-case"):
            # A case-style says case is what distinguishes a component from
            # anything else, so the fragment stays case-sensitive even when a
            # consumer embeds it in a case-insensitive pattern. Without this a
            # kebab component swallows the uppercase assertion label that
            # follows it, and `REQ-p-widget-A+C` loses its second label.
            component = f"(?-i:{component})"

        placeholders = {
            "{namespace}": namespace,
            "{component}": component,
            "{level}": f"(?:{level})",
        }
        type_codes = list(cfg.types.keys())
        if type_codes:
            placeholders["{type}"] = "(?:" + "|".join(re.escape(t) for t in type_codes) + ")"
        for match in re.finditer(r"\{(?:type|level)\.(\w+)\}", cfg.canonical_template):
            alias_vals = self._reverse_aliases.get(match.group(1), {})
            if alias_vals:
                placeholders[match.group(0)] = (
                    "(?:" + "|".join(re.escape(v) for v in alias_vals) + ")"
                )

        def _literal(segment: str) -> str:
            if separator is None:
                return re.escape(segment)
            return re.escape(_respell(segment, separator))

        parts = re.split(r"(\{[^}]+\})", cfg.canonical_template)
        identifier = "".join(placeholders[p] if p in placeholders else _literal(p) for p in parts)

        assertion_separator = re.escape(
            separator if separator is not None else cfg.assertions.separator
        )

        assertion_label = self._assertion_label_regex_str()
        # The same alphabet, written so that it cannot match another case
        # inside a case-insensitive consumer. A label alphabet that names a
        # case has one to preserve; a digit alphabet does not.
        assertion_label_exact = (
            f"(?-i:{assertion_label})"
            if cfg.assertions.label_style in ("uppercase", "alphanumeric")
            else assertion_label
        )

        return IdGrammar(
            namespace=namespace,
            level=level,
            component=component,
            identifier=identifier,
            assertion_label=assertion_label,
            assertion_label_exact=assertion_label_exact,
            assertion_separator=assertion_separator,
            multi_separator=re.escape(cfg.assertions.multi_separator),
        )

    # Implements: REQ-d00081-D
    def multi_assertion_reference_regex(self) -> re.Pattern[str]:
        """Compile the pattern matching an identifier with its assertion suffix.

        Matches ``REQ-d00001`` and ``REQ-d00001-A+B`` alike, so a reference
        naming several *Assertion* labels is captured whole rather than
        truncated at the first label.
        """
        g = self.grammar()
        label = g.assertion_label
        suffix = rf"(?:{g.assertion_separator}{label}(?:{g.multi_separator}{label})*)?"
        return re.compile(f"{g.identifier}{suffix}", re.IGNORECASE)

    def parse(self, raw_id: str) -> ParsedId | None:
        """Try all compiled forms. Returns ParsedId with canonical type_code.

        Does not handle INSTANCE IDs (containing '::').
        Use ``is_instance_id()`` to detect them and ``get_template_id()``
        to extract the template part, which can then be passed to ``parse()``.
        """
        # Reject composite IDs — callers must split on :: first
        if "::" in raw_id:
            return None
        for _form_name, regex, alias_used in self._forms:
            m = regex.match(raw_id)
            if m:
                return self._match_to_parsed_id(m, alias_used)
        return None

    def _notation_forms(self, separator: str) -> list[tuple[str, re.Pattern, str | None]]:
        """This repository's forms, compiled in *separator*'s notation."""
        forms = self._notation_forms_cache.get(separator)
        if forms is None:
            templates = [("canonical", self.config.canonical_template)]
            templates.extend(self.config.aliases.items())
            forms = [
                (
                    name,
                    self._compile_regex(template, separator),
                    self._extract_type_alias_name(template),
                )
                for name, template in templates
            ]
            self._notation_forms_cache[separator] = forms
        return forms

    def _parse_notation(self, raw_id: str, separator: str) -> ParsedId | None:
        """``parse`` for an identifier spelled in *separator*'s notation.

        The parts come back in the configured spelling, so the result renders
        canonically without any further rewriting.
        """
        if "::" in raw_id:
            return None
        for _form_name, regex, alias_used in self._notation_forms(separator):
            m = regex.match(raw_id)
            if m:
                return self._match_to_parsed_id(m, alias_used, separator=separator)
        return None

    def is_local_id(self, raw_id: str) -> bool:
        """Return True if raw_id matches this repo's ID pattern.

        Uses parse() to validate against all configured canonical forms and
        aliases. Returns False for IDs belonging to other repos (different
        namespace or format) and for INSTANCE IDs.
        """
        return self.parse(raw_id) is not None

    def _match_to_parsed_id(
        self, m: re.Match, alias_used: str | None, separator: str | None = None
    ) -> ParsedId:
        """Convert regex match to ParsedId.

        Args:
            separator: The notation the match was read in. A case-style
                component's own punctuation was spelled with it, so it is
                spelled back before anything is rendered from the component.
        """
        groups = m.groupdict()
        namespace = groups.get("namespace", self.config.namespace)
        raw_type = groups.get("type", "")
        component = groups.get("component", "")

        # Resolve type alias to canonical code
        if alias_used and alias_used in self._reverse_aliases:
            type_code = self._reverse_aliases[alias_used].get(raw_type, raw_type)
        else:
            type_code = raw_type

        # The type group is absent exactly when the matched form's template
        # names no type token. Where the CANONICAL template is also typeless,
        # the substituted type is never rendered back out -- it exists only
        # to satisfy the membership check below -- and every shipped and
        # fixture configuration of that shape declares exactly one level, so
        # "the first declared" is "the only one".
        #
        # Nothing enforces that condition. Beside a TYPED canonical, or with
        # more than one level declared, this invents a level, and which one
        # depends on the order the levels appear in the TOML rather than on
        # anything about the identifier. `type_code` also reaches next-ID
        # allocation, which a wrong level mis-scopes.
        if not type_code and self.config.types:
            type_code = next(iter(self.config.types))

        # Normalize component (zero-pad if needed)
        comp = self.config.component
        internal = STYLE_INTERNAL_SEPARATOR.get(comp.style)
        if separator is not None and internal is not None and component:
            component = component.replace(separator, internal)
        if comp.style == "numeric" and comp.digits > 0 and comp.leading_zeros:
            component = component.zfill(comp.digits)

        # Parse assertions
        assertions_str = groups.get("assertions", "")
        assertions: list[str] = []
        if assertions_str:
            af = self.config.assertions
            sep = af.multi_separator
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

        # Handle {type.<alias>} and {level.<alias>} tokens
        tdef = self.config.types.get(type_code)
        if tdef:
            for alias_name, alias_value in tdef.aliases.items():
                result = result.replace(f"{{type.{alias_name}}}", alias_value)
                result = result.replace(f"{{level.{alias_name}}}", alias_value)

        return result

    def to_canonical(self, raw_id: str) -> str | None:
        """Parse then render as canonical. Returns None if no form matches."""
        parsed = self.parse(raw_id)
        if parsed is None:
            return None
        result = parsed.fqn
        if parsed.assertions:
            af = self.config.assertions
            multi = af.multi_separator
            result += f"{af.separator}{multi.join(parsed.assertions)}"
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
            multi = af.multi_separator
            result += f"{af.separator}{multi.join(parsed_id.assertions)}"
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

    def all_type_codes(self) -> list[str]:
        """All canonical type codes."""
        return list(self.config.types.keys())

    # --- DRY convenience methods ---

    def split_assertion_ref(self, raw_id: str) -> tuple[str, str] | None:
        """Split an assertion reference into (parent_fqn, assertion_labels_str).

        For example, ``"REQ-p00044-E"`` returns ``("REQ-p00044", "E")``.
        Returns None if *raw_id* is a plain requirement ID (no assertion)
        or does not match any known form.
        """
        parsed = self.parse(raw_id)
        if parsed is None or not parsed.assertions:
            return None
        return (parsed.fqn, self.config.assertions.multi_separator.join(parsed.assertions))

    def make_assertion_id(self, req_id: str, label: str) -> str:
        """Compose an assertion node ID from a requirement ID and label.

        Uses the configured assertion separator so the graph index keys
        match the user-facing canonical form (e.g. ``EVS-PRD-foo/A`` when
        ``separator="/"``). Internal == display — no second form to convert.
        """
        return f"{req_id}{self.config.assertions.separator}{label}"

    def make_assertion_ref(self, req_id: str, labels: list[str]) -> str:
        """Compose a multi-assertion reference like ``REQ-X-A+B+C``.

        Uses both the configured ``separator`` (between requirement and the
        first label) and ``multi_separator`` (between successive labels).
        With a single label this is identical to ``make_assertion_id``.
        """
        af = self.config.assertions
        return f"{req_id}{af.separator}{af.multi_separator.join(labels)}"

    def all_type_alias_values(self) -> list[str]:
        """All unique type alias values (or canonical codes if no aliases).

        Used for building regex alternations that match type identifiers
        as they appear in ID strings (e.g., ``["PRD", "OPS", "DEV"]``).
        """
        values: set[str] = set()
        for code, tdef in self.config.types.items():
            if tdef.aliases:
                for alias_val in tdef.aliases.values():
                    values.add(alias_val)
            else:
                values.add(code)
        return sorted(values)

    def _case_insensitive_forms(self) -> list[tuple[str, re.Pattern, str | None]]:
        """The compiled forms again, ignoring case. Built once, on demand."""
        if self._ci_forms is None:
            self._ci_forms = [
                (name, re.compile(regex.pattern, regex.flags | re.IGNORECASE), alias)
                for name, regex, alias in self._forms
            ]
        return self._ci_forms

    # Implements no requirement. Repairing a mis-spelled reference is an
    # unspecified stop-gap: it contradicts the rule that an identifier
    # resolves only in the one spelling its configuration admits, and it
    # goes when test annotations stop depending on it.
    def _canonicalize_case(self, cleaned: str) -> str | None:
        """Rewrite a reference's level code and *Assertion* labels to canonical case.

        A reference is recognised case-insensitively but parsed case-sensitively,
        so without this a mis-cased label reads as an identifier no repository
        claims -- reported as foreign rather than as the typo it is.

        The component is deliberately not touched. Under a case-style its case
        is its identity, so a mis-cased component is a different component, not
        the same one spelled differently, and it stays unresolved.
        """
        for _form_name, regex, alias_used in self._case_insensitive_forms():
            m = regex.match(cleaned)
            if not m:
                continue
            groups = m.groupdict()

            component = groups.get("component", "")
            if component and not re.fullmatch(component_regex(self.config.component), component):
                return None

            raw_type = groups.get("type", "")
            type_code = raw_type
            if alias_used and alias_used in self._reverse_aliases:
                by_lower = {k.lower(): v for k, v in self._reverse_aliases[alias_used].items()}
                type_code = by_lower.get(raw_type.lower(), raw_type)
            # Same substitution, same unenforced condition, as the plain
            # parse above: absent only for a typeless template, harmless
            # only while such a configuration declares one level.
            if not type_code and self.config.types:
                type_code = next(iter(self.config.types))
            if type_code not in self.config.types:
                return None

            af = self.config.assertions
            labels = [
                label.upper() if af.label_style in ("uppercase", "alphanumeric") else label
                for label in (groups.get("assertions") or "").split(af.multi_separator)
                if label
            ]
            return self.render_canonical(
                ParsedId(
                    namespace=self.config.namespace,
                    type_code=type_code,
                    component=component,
                    assertions=labels,
                    fqn="",
                )
            )
        return None

    def _fold_notation(self, raw_ref: str) -> str:
        """Rewrite an alternate notation onto the configured punctuation.

        A reference embedded in a Python identifier can spell every boundary
        only as ``_``. Folding restores the configured characters, each where
        it belongs: the template's own literals between the parts, the
        component's own punctuation inside it, and the *Assertion* separator
        where a label follows. Which underscore is which cannot be read off
        the string, so the notation is parsed by the same grammar rendered in
        it rather than guessed at by substitution -- a component style whose
        punctuation is already ``_`` would otherwise leave every boundary
        unfolded and the reference unclaimable.
        """
        if "_" not in raw_ref:
            return raw_ref
        sep = self.config.assertions.separator
        multi = self.config.assertions.multi_separator

        parsed = self._parse_notation(raw_ref, "_")
        if parsed is not None:
            return self.render_canonical(parsed)

        # Otherwise some suffix of the parts are labels. The notation spends
        # its one punctuation character on every boundary, so the split has to
        # be found rather than read: take the longest head that parses as a
        # requirement, and the rest are labels joined by the multi-separator.
        notation_parts = raw_ref.split("_")
        for cut in range(len(notation_parts) - 1, 0, -1):
            head = "_".join(notation_parts[:cut])
            labels = notation_parts[cut:]
            parsed_head = self._parse_notation(head, "_")
            if parsed_head is None or parsed_head.assertions:
                # A head that already carries labels is not the boundary --
                # it would leave the remaining labels stranded behind the
                # wrong separator.
                continue
            if all(self.is_valid_assertion_label(label) for label in labels):
                return self.render_canonical(parsed_head) + sep + multi.join(labels)

        # Nothing parses in either notation. Respell what punctuation can be
        # placed without a parse, so a reference whose case is what stops it
        # parsing still reaches case canonicalization downstream.
        internal = STYLE_INTERNAL_SEPARATOR.get(self.config.component.style, "-")
        all_internal = raw_ref.replace("_", internal)
        if self.parse(all_internal) is not None:
            # Every underscore was the component's own punctuation.
            return all_internal

        # The same split search over the respelled string, for a component
        # style that spells its own punctuation outside what the notation
        # rendering can express.
        parts = raw_ref.split("_")
        for cut in range(len(parts) - 1, 0, -1):
            head = internal.join(parts[:cut])
            labels = parts[cut:]
            parsed_head = self.parse(head)
            if parsed_head is None or parsed_head.assertions:
                # A head that already carries labels is not the boundary --
                # it would leave the remaining labels stranded behind the
                # wrong separator.
                continue
            if all(self.is_valid_assertion_label(label) for label in labels):
                return head + sep + multi.join(labels)
        return all_internal

    def normalize_ref(self, raw_ref: str) -> str:
        """Normalize a raw reference string to canonical form.

        Handles underscore-to-dash conversion and case normalization of every
        part whose case the grammar does not treat as significant. Returns the
        cleaned form even if it doesn't match any known canonical pattern, so
        an unresolvable reference stays visible rather than disappearing.
        """
        cleaned = self._fold_notation(raw_ref)
        # Fix namespace case before parsing (parse() is case-sensitive)
        prefix = self.config.namespace
        if cleaned.lower().startswith(prefix.lower() + "-"):
            cleaned = prefix + cleaned[len(prefix) :]
        result = self.to_canonical(cleaned)
        if result is None:
            result = self._canonicalize_case(cleaned)
        return result if result is not None else cleaned

    def build_instance_id(self, prefix: str, template_id: str) -> str:
        """Build a unique INSTANCE node ID.

        INSTANCE nodes are copies of template nodes created by the
        ``Satisfies:`` relationship. The *prefix* provides uniqueness
        (typically the declaring requirement's ID). The *template_id*
        identifies which template node was copied.
        """
        return f"{prefix}{INSTANCE_SEPARATOR}{template_id}"

    def is_instance_id(self, raw_id: str) -> bool:
        """True if raw_id is an INSTANCE node ID."""
        return INSTANCE_SEPARATOR in raw_id

    def get_template_id(self, instance_id: str) -> str | None:
        """Extract the template ID from an INSTANCE node ID.

        Returns the template ID, or None if *instance_id* is not an instance.
        """
        if INSTANCE_SEPARATOR not in instance_id:
            return None
        return instance_id.split(INSTANCE_SEPARATOR, 1)[1]

    def get_instance_prefix(self, instance_id: str) -> str | None:
        """Extract the uniqueness prefix from an INSTANCE node ID.

        Returns the prefix string, or None if *instance_id* is not an instance.
        """
        if INSTANCE_SEPARATOR not in instance_id:
            return None
        return instance_id.split(INSTANCE_SEPARATOR, 1)[0]


# Implements: REQ-d00269-C, REQ-d00251-L
class FederatedIdReader:
    """Reads the identifiers of every repository in one federation.

    A repository's code and tests routinely name a requirement another
    member of the same federation owns.  Recognising such a reference needs
    every member's grammar; normalizing it needs the grammar of the member
    that *claims* it, because the scanning repository's own resolver would
    rewrite a foreign identifier under rules that do not govern it.

    Each fragment still comes from one member's own ``IdResolver.grammar()``.
    This type alternates those fragments and probes the members in order; it
    never merges configurations, and it derives nothing itself.

    A reader over a single repository produces exactly that repository's own
    fragments, so a repository built alone is grammatically unchanged.
    """

    def __init__(self, own: IdResolver, others: Sequence[IdResolver] = ()) -> None:
        resolvers = [own]
        seen = {own.config.namespace}
        for other in others:
            namespace = other.config.namespace
            if namespace not in seen:
                seen.add(namespace)
                resolvers.append(other)
        self._resolvers: tuple[IdResolver, ...] = tuple(resolvers)
        self._ref_regex: re.Pattern[str] | None = None
        self._item_regex: re.Pattern[str] | None = None
        self._extra_item_regexes: dict[tuple[str, ...], tuple[re.Pattern[str], ...]] = {}

    @property
    def own(self) -> IdResolver:
        """The resolver of the repository being scanned."""
        return self._resolvers[0]

    @property
    def resolvers(self) -> tuple[IdResolver, ...]:
        """Every member's resolver, the scanned repository's first."""
        return self._resolvers

    @staticmethod
    def _alternate(fragments: Sequence[str]) -> str:
        """Join member fragments into one alternation.

        A lone member yields its fragment verbatim, so a repository outside
        any federation embeds the same pattern text it always did.
        """
        if len(fragments) == 1:
            return fragments[0]
        return "(?:" + "|".join(fragments) + ")"

    def namespace_pattern(self) -> str:
        """A pattern matching any member's namespace."""
        return self._alternate([r.grammar().namespace for r in self._resolvers])

    def identifier_pattern(self) -> str:
        """A pattern matching any member's canonical identifier."""
        return self._alternate([r.grammar().identifier for r in self._resolvers])

    def _reference_regex(self) -> re.Pattern[str]:
        if self._ref_regex is None:
            self._ref_regex = re.compile(
                self._alternate(
                    [r.multi_assertion_reference_regex().pattern for r in self._resolvers]
                ),
                re.IGNORECASE,
            )
        return self._ref_regex

    def normalize(self, raw_ref: str) -> str:
        """Normalize *raw_ref* under the grammar of the member that claims it.

        Falls back to the scanned repository's own resolver when no member
        claims the reference, which keeps an unresolvable reference visible
        rather than discarding it.
        """
        for resolver in self._resolvers:
            candidate = resolver.normalize_ref(raw_ref)
            if resolver.is_local_id(candidate):
                return candidate
        return self.own.normalize_ref(raw_ref)

    def extract_refs(self, text: str) -> list[str]:
        """Every member's identifiers named in *text*, in the order written."""
        refs: list[str] = []
        for match in self._reference_regex().finditer(text):
            ref = self.normalize(match.group(0))
            if ref not in refs:
                refs.append(ref)
        return refs

    def _item_pattern(self) -> re.Pattern[str]:
        """One member reference, matched whole rather than searched for."""
        if self._item_regex is None:
            self._item_regex = re.compile(
                "(?:"
                + "|".join(r.multi_assertion_reference_regex().pattern for r in self._resolvers)
                + ")",
                re.IGNORECASE,
            )
        return self._item_regex

    def _extra_patterns(self, extra_items: Sequence[str]) -> tuple[re.Pattern[str], ...]:
        key = tuple(extra_items)
        compiled = self._extra_item_regexes.get(key)
        if compiled is None:
            compiled = tuple(re.compile(p, re.IGNORECASE) for p in key)
            self._extra_item_regexes[key] = compiled
        return compiled

    # Implements: REQ-d00269-G, REQ-p00014-T
    def parse_ref_list(
        self,
        text: str,
        *,
        extra_items: Sequence[str] = (),
        on_unmatched: str = "reject",
    ) -> list[RefItem]:
        """The items *text* spells as a separated list, each with its verdict.

        The one place a list of references is divided into its items.  A
        *Traceability* keyword introduces a list and nothing else, so each
        item is matched whole against a member's grammar rather than searched
        for inside the item.  Searching would read ``XREQ-d00001`` as
        ``REQ-d00001`` -- an edge to a requirement the author never named, and
        one nothing reports, since a reference that resolved is a reference
        that looked fine.

        What becomes of an item no grammar accounts for is the caller's
        policy, and the only thing that varies between surfaces:

        ``reject``
            None for the whole text.  A scanned annotation is found in the
            wild rather than authored as data, so a target the grammar can
            only partly account for is a target read wrongly, and the caller
            reports the line rather than keeping whichever items parsed.
        ``keep``
            The item is carried through as written.  A reference authored in
            a spec file is data, and a wrong one has to survive being read in
            order to be reported as a broken reference; dropping the line
            would retire the diagnostic along with the typo.

        Args:
            text: The content a keyword introduced, with the keyword and its
                colon already removed.
            extra_items: Patterns for items belonging to a grammar this
                reader does not own -- a journey step, say -- which are
                accepted verbatim rather than normalized.
            on_unmatched: ``"reject"`` or ``"keep"``, as above.

        Returns:
            A ``RefItem`` per item, never ``None``.  An empty list means the
            content was empty.
        """
        from elspais.graph.reference_faults import FaultClass, FaultCode, RefItem

        if on_unmatched not in ("reject", "keep"):
            raise ValueError(f"on_unmatched must be 'reject' or 'keep', got {on_unmatched!r}")
        stripped = text.strip()
        if not stripped:
            return []
        item = self._item_pattern()
        extras = self._extra_patterns(extra_items)
        results: list[RefItem] = []
        seen: set[str] = set()
        for index, part in enumerate(stripped.split(REF_LIST_SEPARATOR)):
            candidate = part.strip()
            if not candidate:
                results.append(
                    RefItem(
                        raw="",
                        index=index,
                        fault_class=FaultClass.MALFORMED,
                        codes=(FaultCode.EMPTY_ITEM,),
                    )
                )
                continue
            if item.fullmatch(candidate):
                ref = self.normalize(candidate)
            elif any(extra.fullmatch(candidate) for extra in extras):
                ref = candidate
            else:
                results.append(
                    RefItem(
                        raw=candidate,
                        index=index,
                        fault_class=FaultClass.MALFORMED,
                        codes=(),
                    )
                )
                continue
            if ref in seen:
                continue
            seen.add(ref)
            results.append(RefItem(raw=candidate, index=index, resolved=ref))
        return results

    def extract_underscored_ref(self, text: str) -> str | None:
        """The first identifier *text* spells in underscore notation, or None.

        A Python test function name can spell every boundary only as ``_``,
        so each member's grammar is re-rendered in that notation rather than
        composed a second time.  A trailing lowercase run continues the
        function name rather than labelling an *Assertion*, so
        ``test_REQ_p00001_validates`` must not read its ``_v`` as a label.

        Only the first label is read tolerantly of case.  Past it the
        notation has spent its distinguishing punctuation -- the separator
        between the component and the labels and the separator between two
        labels are both ``_`` -- so case is all that is left to tell a second
        label from the next word of the name, and
        ``test_REQ_p00001_A_and_so_on`` names one label rather than two.
        """
        best: tuple[int, str] | None = None
        for resolver in self._resolvers:
            g = resolver.grammar(separator="_")
            head = rf"(?:{g.assertion_separator}{g.assertion_label}(?![a-z]))"
            tail = rf"(?:{g.assertion_separator}{g.assertion_label_exact}(?![a-z]))*"
            suffix = head + tail
            pattern = re.compile(rf"(?P<ref>{g.identifier}(?:{suffix})?)", re.IGNORECASE)
            match = pattern.search(text)
            if match and (best is None or match.start() < best[0]):
                best = (match.start(), resolver.normalize_ref(match.group("ref")))
        return best[1] if best else None


def build_resolver(config: dict[str, Any]) -> IdResolver:
    """Create an IdResolver from a full configuration dictionary.

    Convenience function that reads ``[project].namespace`` and
    ``[id-patterns]`` sections from *config*.
    """
    return IdResolver(IdPatternConfig.from_dict(config))


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
