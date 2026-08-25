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
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.graph.reference_faults import FaultClass, FaultCode, RefItem

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

# Implements: REQ-p00014-S, REQ-d00287-A
# The characters no identifier configuration may produce. `:` separates the
# parts of a node identifier, so configuration validation refuses any pattern
# element able to put one into an identifier -- which makes an item carrying
# one an item that was never written as an identifier, exactly as a space is.
# One definition: the schema's refusal and the reader's classification are two
# consequences of the same reservation, and a character reserved in one and
# not the other would leave an item both impossible to configure and reported
# as a name from a repository nobody configured.
RESERVED_IDENTIFIER_CHARACTERS = (":",)


# Implements: REQ-d00287-B
def default_comment_markers() -> tuple[str, ...]:
    """The markers that end a reference on a line that belongs to no language.

    A spec or journey metadata line is markdown, not source: it is not a
    comment in any language, so no language's comment pattern governs it and
    ``REQ-d00269-K`` -- which says where a keyword may be READ inside a
    comment -- has nothing to say about it.  What such a line still needs is
    an answer to a narrower question: an author who writes a note after a
    reference on a metadata line conventionally opens it with one of the
    three markers below, and that note must not be read as a further
    reference (REQ-d00287-B).

    A caller reading an actual source file does NOT come here.  It holds the
    file's path, asks ``comment_pattern_for_path`` for that language's one
    marker, and passes it to ``parse_ref_list``.

    Named from the one set of comment patterns rather than respelled here,
    so this convention and the languages cannot drift apart.
    """
    from elspais.graph.parsers.patterns import METADATA_COMMENT_MARKERS

    return METADATA_COMMENT_MARKERS


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
    namespace_separator: str
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


# Implements: REQ-d00251-B
def component_regex(component: ComponentFormat) -> str:
    """Resolve a ComponentFormat to its regex string.

    Sole authority for the style → regex mapping. No other code path may
    contain a component-style dispatch.
    """
    style = component.style
    if style == "numeric":
        # Implements: REQ-d00212-R, REQ-d00212-T
        # The configured digit count bounds the component's VALUE, not the
        # characters written: leading zeros carry no value, so they are
        # consumed separately and only the significant digits are counted.
        # `\d{1,N}` alone caps characters, which makes how many zeros an
        # author typed decide whether an identifier resolves.
        if component.digits > 0:
            return rf"0*\d{{1,{component.digits}}}"
        return r"\d+"
    if style == "camelCase":
        return r"[a-z][a-zA-Z0-9]+"
    if style == "PascalCase":
        return r"[A-Z][a-zA-Z0-9]+"
    if style in ("snake_case", "kebab-case"):
        sep = re.escape(STYLE_INTERNAL_SEPARATOR[style])
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

    def _compile_regex(
        self,
        template: str,
        *,
        unbounded_component: bool = False,
    ) -> re.Pattern:
        """Compile a template string into a regex for parsing.

        Args:
            unbounded_component: Drop the configured bound on a numeric
                component's value. Never used to admit a reference -- only to
                tell an item whose number is too large from one that is
                misspelled, so the report names the defect the input has
                (REQ-d00212-T).
        """
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

        # {type.<alias_name>} or {level.<alias_name>} -> alternation of alias values
        for match in re.finditer(r"\{(?:type|level)\.(\w+)\}", template):
            alias_name = match.group(1)
            if alias_name in self._reverse_aliases:
                values = list(self._reverse_aliases[alias_name].keys())
                val_alt = "|".join(re.escape(v) for v in values)
                pattern = pattern.replace(match.group(0), f"(?P<type>{val_alt})")

        # {component} -> resolved via the single style→regex helper
        component = self.config.component
        if unbounded_component and component.style == "numeric" and component.digits > 0:
            component = replace(component, digits=0)
        comp_pattern = component_regex(component)
        pattern = pattern.replace("{component}", f"(?P<component>{comp_pattern})")

        # Assertion suffix (optional)
        assertion_suffix = self._build_assertion_suffix()
        pattern = f"^{pattern}{assertion_suffix}$"

        return re.compile(pattern)

    # Implements: REQ-d00082-E
    def _build_assertion_suffix(self) -> str:
        """Build optional assertion suffix regex."""
        af = self.config.assertions
        label_pat = self._assertion_label_regex_str()
        sep = re.escape(af.separator)
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
    def grammar(self) -> IdGrammar:
        """The regex fragments of this repository's identifier grammar.

        Every consumer that has to recognise, parse or expand an identifier
        takes its patterns from here, so a repository's configuration is
        interpreted once and the surfaces cannot drift apart.  The fragments
        are uncompiled and unanchored so a caller can embed them in a larger
        grammar; the compiled, anchored form is ``canonical_regex``.

        There is one notation.  An identifier is spelled the way the
        configuration spells it, so a boundary written with another character
        is a reference spelled wrongly rather than the same reference in a
        second notation (REQ-d00212-S).
        """
        cfg = self.config
        namespace = re.escape(cfg.namespace)

        alias_values = self.all_type_alias_values()
        level = "|".join(re.escape(v) for v in alias_values) if alias_values else "[a-z]"

        component = component_regex(cfg.component)
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
            return re.escape(segment)

        parts = re.split(r"(\{[^}]+\})", cfg.canonical_template)
        identifier = "".join(placeholders[p] if p in placeholders else _literal(p) for p in parts)

        # The literal character the canonical template places right after
        # {namespace} -- the boundary declares_namespace() tests against,
        # taken from the same template the identifier fragment above is
        # built from rather than assumed to be "-".
        namespace_separator = ""
        for i, part in enumerate(parts):
            if part == "{namespace}" and i + 1 < len(parts):
                following = parts[i + 1]
                if following:
                    namespace_separator = following[0]
                break

        assertion_separator = re.escape(cfg.assertions.separator)

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
            namespace_separator=namespace_separator,
            level=level,
            component=component,
            identifier=identifier,
            assertion_label=assertion_label,
            assertion_label_exact=assertion_label_exact,
            assertion_separator=assertion_separator,
            multi_separator=re.escape(cfg.assertions.multi_separator),
        )

    # Implements: REQ-d00272-C
    def declares_namespace(self, item: str) -> bool:
        """Whether *item* opens with this repository's namespace.

        The boundary between the namespace and what follows comes from the
        grammar rather than from an assumed ``-``: a repository configured
        with another separator would otherwise have every one of its
        identifiers attributed elsewhere.
        """
        grammar = self.grammar()
        pattern = re.compile(
            rf"(?:{grammar.namespace})(?:{re.escape(grammar.namespace_separator)}|$)"
        )
        return bool(pattern.match(item))

    # Implements: REQ-d00272-E, REQ-d00287-E
    def opening_reference(self, item: str) -> tuple[str, str] | None:
        """*item* split into the reference it opens with and the rest of it,
        or None where it does not open with one.

        The identifier ends at the first character this repository's grammar
        does not admit, and no configuration can admit a space, so a space is
        always such a character.  That is the whole of the split: the head is
        an acceptable reference and the tail is content the grammar did not
        account for, which is exactly the pair a report of trailing content
        has to name (REQ-d00272-E).

        Splitting describes; it never binds.  The tail is content nobody
        wrote as part of an identifier, so an item with a non-empty tail is
        still an item that failed to read (REQ-d00287-E).
        """
        match = self.multi_assertion_reference_regex().match(item)
        if match is None or match.end() == 0:
            return None
        return item[: match.end()], item[match.end() :]

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

    # Implements: REQ-d00272-D
    def _canonical_assertion_sep(self, item: str) -> str:
        """Rewrite *item* as though its assertion separator were spelled
        with this repository's multi-*Assertion* separator by mistake.

        Only the boundary between the identifier and the first label is
        touched -- an author who reaches for the wrong character reaches for
        it once, at the one boundary that looks like a separator to type,
        and every label after it is still joined by whatever character the
        author used there. Returns *item* unchanged where the wrong-spelling
        shape does not match, so a caller testing the result against the
        strict grammar sees no false success.
        """
        g = self.grammar()
        label = g.assertion_label
        wrong = re.compile(
            rf"^({g.identifier}){g.multi_separator}({label}(?:{g.multi_separator}{label})*)$",
            re.IGNORECASE,
        )
        m = wrong.fullmatch(item)
        if not m:
            return item
        return f"{m.group(1)}{self.config.assertions.separator}{m.group(2)}"

    # Implements: REQ-d00272-D
    def _canonical_multi_sep(self, item: str) -> str:
        """Rewrite *item* as though its labels were joined with this
        repository's assertion separator by mistake, in place of the
        multi-*Assertion* separator.

        Requires at least two labels: with only one, nothing distinguishes
        "wrong multi-separator" from a correctly-formed single-label
        reference, so there is nothing here for this relaxation to name.
        Returns *item* unchanged where the wrong-spelling shape does not
        match.
        """
        g = self.grammar()
        label = g.assertion_label
        wrong = re.compile(
            rf"^({g.identifier}){g.assertion_separator}"
            rf"({label}(?:{g.assertion_separator}{label})+)$",
            re.IGNORECASE,
        )
        m = wrong.fullmatch(item)
        if not m:
            return item
        af = self.config.assertions
        labels = re.split(re.escape(af.separator), m.group(2))
        return f"{m.group(1)}{af.separator}{af.multi_separator.join(labels)}"

    # Implements: REQ-d00272-D, REQ-d00272-E, REQ-d00272-L
    def diagnose_item(self, item: str) -> tuple[str, ...]:
        """The smallest set of relaxations that makes *item* acceptable.

        Minimality is what bounds the diagnosis: a larger set that also
        succeeds contains a relaxation the input never asked for, and naming
        it describes a defect the author does not have.  Where two disjoint
        sets of equal size each succeed, the input admits two accounts and
        neither is issued (REQ-d00271-D): the item carries the generic code
        alone, which is already the report that nothing more specific is
        known (REQ-d00271-C).

        A relaxation never produces a reference.  It says what is wrong and
        stops (REQ-d00269-J).
        """
        import itertools

        from elspais.graph.reference_faults import FaultCode

        relaxations = {
            FaultCode.WRONG_ASSERTION_SEPARATOR: self._canonical_assertion_sep,
            FaultCode.WRONG_MULTI_SEPARATOR: self._canonical_multi_sep,
        }
        # The matcher already ignores case and numeric padding, so an item
        # differing only in those resolved and never reached this function.
        exact = self.multi_assertion_reference_regex()

        # An item that already fullmatches has nothing for a relaxation to
        # explain -- each relaxation is a no-op on a string its own "wrong"
        # shape does not match, and a no-op applied to an already-acceptable
        # item would otherwise register as a trivially succeeding combo at
        # every size, naming a defect an item that is not malformed at all
        # does not have.
        if exact.fullmatch(item):
            return ()

        for size in range(1, len(relaxations) + 1):
            succeeding = []
            for combo in itertools.combinations(relaxations, size):
                candidate = item
                for code in combo:
                    candidate = relaxations[code](candidate)
                if exact.fullmatch(candidate):
                    succeeding.append(frozenset(combo))
            if len(succeeding) == 1:
                return tuple(sorted(succeeding[0]))
            if len(succeeding) > 1:
                return ()

        prefix = exact.match(item)
        if prefix and prefix.end() < len(item):
            return (FaultCode.IDENTIFIER_WITH_TRAILING_TEXT,)
        return ()

    # Implements: REQ-d00212-T
    def component_out_of_range(self, item: str) -> bool:
        """Whether *item* is this repository's identifier but for a numeric
        component whose value the configuration cannot admit.

        A padding defect and an out-of-range value are different defects with
        different remedies: one is answered by rewriting the same number,
        the other by no spelling at all.  Telling them apart needs the value,
        so the item is re-read with the bound lifted and the number compared
        against what the configuration admits -- never to resolve it, only to
        say which defect it has.
        """
        component = self.config.component
        if component.style != "numeric" or component.digits <= 0:
            return False
        relaxed = self._compile_regex(self.config.canonical_template, unbounded_component=True)
        match = re.compile(relaxed.pattern, re.IGNORECASE).fullmatch(item)
        if match is None:
            return False
        value = match.groupdict().get("component")
        if not value or not value.isdigit():
            return False
        return int(value) >= 10**component.digits

    # Implements: REQ-d00272-D
    def label_position_defect(self, item: str) -> bool:
        """Whether *item* opens with a bare identifier immediately followed
        by this repository's own assertion separator.

        ``diagnose_item`` reports unaccounted trailing content generically
        (``IDENTIFIER_WITH_TRAILING_TEXT``); this narrows that to the one
        case worth naming more specifically -- the separator the author used
        is already correct, so what follows it occupies label position, and
        a defect there is about the label rather than about content the
        reference never reaches. A label outside the configured series is
        decided by the series itself, not by re-reading, so it is not one of
        ``diagnose_item``'s relaxations.
        """
        exact = self.multi_assertion_reference_regex()
        prefix = exact.match(item)
        if not prefix:
            return False
        trailing = item[prefix.end() :]
        return trailing.startswith(self.config.assertions.separator)

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

    def is_local_id(self, raw_id: str) -> bool:
        """Return True if raw_id matches this repo's ID pattern.

        Uses parse() to validate against all configured canonical forms and
        aliases. Returns False for IDs belonging to other repos (different
        namespace or format) and for INSTANCE IDs.
        """
        return self.parse(raw_id) is not None

    # Implements: REQ-d00212-R
    def _canonical_component(self, component: str) -> str:
        """The component's one canonical spelling.

        A numeric component's identity is its value, so the canonical form is
        that value written to the configured width -- reached by discarding
        the zeros the author wrote and re-padding, not by padding what was
        written. `zfill` alone leaves an over-padded component longer than the
        configuration names, and the identifier renders in a form that
        configuration does not.

        Every path that renders an identifier reaches padding through here.
        Settling it on the path that parses and not on the path that settles
        case leaves the canonical renderer emitting a non-canonical spelling
        for exactly the references that differ in both -- and `fix` writes
        what that renderer returns.
        """
        comp = self.config.component
        if comp.style != "numeric" or comp.digits <= 0:
            return component
        value = component.lstrip("0") or "0"
        return value.zfill(comp.digits) if comp.leading_zeros else value

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

        component = self._canonical_component(component)

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

    # Implements: REQ-d00082-G
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

    # Implements: REQ-d00212-R, REQ-d00212-S
    def _canonicalize_case(self, cleaned: str) -> str | None:
        """Rewrite a reference's level code and *Assertion* labels to canonical case.

        Case does not decide whether an identifier resolves (REQ-d00212-R):
        two case-spellings of a level code or label name the same identifier,
        and the configuration guard (REQ-d00212-G) keeps that reading safe by
        refusing a configuration that would let two case-spellings collide.
        Rendering stays canonical regardless of the case an author wrote, so
        this is what makes reading tolerant without making writing ambiguous.

        The component is deliberately not touched (REQ-d00212-S): under a
        case-style its case is its identity, so a mis-cased component is a
        different component, not the same one spelled differently, and it
        stays unresolved -- case tolerance reaches no further than case.
        """
        for _form_name, regex, alias_used in self._case_insensitive_forms():
            m = regex.match(cleaned)
            if not m:
                continue
            groups = m.groupdict()

            component = groups.get("component", "")
            if component and not re.fullmatch(component_regex(self.config.component), component):
                return None
            # Case and padding are settled together or the canonical renderer
            # emits a non-canonical spelling for a reference differing in both.
            component = self._canonical_component(component)

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

    # Implements: REQ-d00212-S
    def normalize_ref(self, raw_ref: str) -> str:
        """Normalize a raw reference string to canonical form.

        Case and digit-padding are the whole of what normalization settles,
        because they are the whole of what the configuration admits as a
        variant spelling.  A reference differing in anything else -- a
        boundary spelled with another character, punctuation the template
        does not place -- is left exactly as written, so it resolves to
        nothing and is reported rather than repaired into something that
        resolves.  The cleaned form is returned even where it matches no
        canonical pattern, so an unresolvable reference stays visible rather
        than disappearing.
        """
        cleaned = raw_ref
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


# Implements: REQ-d00269-C, REQ-d00251-L, REQ-d00275-B
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
        self._extra_item_regexes: dict[tuple[str, ...], tuple[re.Pattern[str], ...]] = {}
        self._comment_regexes: dict[tuple[str, ...], re.Pattern[str]] = {}

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

    # Implements: REQ-d00082-E
    def _classify(self, raw_ref: str) -> tuple[str, bool]:
        """Normalize *raw_ref* under the grammar of the member that claims it,
        and say whether some member actually confirmed it as its own.

        A member's grammar is more than its canonical spelling -- an alias
        reads whole too, and a mis-cased label is still recognised (case is
        repaired for a label, never for a component, since a component's
        case is its identity). ``normalize_ref`` already applies both; this
        additionally reports whether the result was a member's own
        identifier rather than merely handed back cleaned up and unclaimed.
        """
        for resolver in self._resolvers:
            candidate = resolver.normalize_ref(raw_ref)
            if resolver.is_local_id(candidate):
                return candidate, True
        return self.own.normalize_ref(raw_ref), False

    def normalize(self, raw_ref: str) -> str:
        """Normalize *raw_ref* under the grammar of the member that claims it.

        Falls back to the scanned repository's own resolver when no member
        claims the reference, which keeps an unresolvable reference visible
        rather than discarding it.
        """
        return self._classify(raw_ref)[0]

    # Implements: REQ-d00272-E, REQ-d00272-C
    def opening_reference(self, item: str) -> tuple[str, str] | None:
        """*item* split into the reference it opens with and the rest of it,
        under the grammar of whichever member reads furthest into it.

        Longest head, not the first member that matches: the members are
        scanned own-repo-first, so a first-match pick would read
        ``REQ-ALP-p00001 gloss`` as the ``REQ-`` member's ``REQ`` plus a tail
        starting ``-ALP``, attributing it to a repository that does not own
        it -- the misattribution REQ-d00272-C exists to prevent, arriving
        through the diagnosis rather than through the binding.
        """
        best: tuple[str, str] | None = None
        for resolver in self._resolvers:
            split = resolver.opening_reference(item)
            if split is not None and (best is None or len(split[0]) > len(best[0])):
                best = split
        return best

    def _comment_pattern(self, markers: tuple[str, ...]) -> re.Pattern[str]:
        """Match a comment opening: whitespace, then one of *markers*.

        The whitespace is required.  Without it a marker's characters are
        just characters an identifier may hold or abut, and ``REQ-d00001--A``
        would be read as a requirement plus a comment rather than as the
        separator defect it is.  A space before the marker is what no
        identifier can contain, so it is what makes the boundary decidable.
        """
        compiled = self._comment_regexes.get(markers)
        if compiled is None:
            longest_first = sorted(markers, key=len, reverse=True)
            alternation = "|".join(re.escape(m) for m in longest_first)
            compiled = re.compile(rf"\s(?:{alternation})")
            self._comment_regexes[markers] = compiled
        return compiled

    # Implements: REQ-d00287-B
    def _without_comment(self, text: str, markers: tuple[str, ...]) -> str:
        """*text* with a trailing comment removed, where one opens after a
        reference.

        The comment is taken off before the list is divided, because a
        comment may hold the character that divides one: splitting first
        would shred a prose remainder into items and report each fragment as
        a reference nobody wrote.

        A marker only opens a comment where what precedes it is a reference,
        so the item ending at the marker must open with one.  The earliest
        such marker wins -- everything after it is prose, marker characters
        in that prose included.
        """
        if not markers:
            return text
        for match in self._comment_pattern(markers).finditer(text):
            head = text[: match.start()]
            last_item = head.rsplit(REF_LIST_SEPARATOR, 1)[-1].strip()
            if last_item and self.opening_reference(last_item) is not None:
                return head.rstrip()
        return text

    def _extra_patterns(self, extra_items: Sequence[str]) -> tuple[re.Pattern[str], ...]:
        key = tuple(extra_items)
        compiled = self._extra_item_regexes.get(key)
        if compiled is None:
            compiled = tuple(re.compile(p, re.IGNORECASE) for p in key)
            self._extra_item_regexes[key] = compiled
        return compiled

    # Implements: REQ-d00287-A, REQ-d00272-C, REQ-d00272-E
    def classify_unmatched(self, candidate: str) -> tuple[FaultClass, tuple[FaultCode, ...]]:
        """How far reading *candidate* got, for an item no grammar accepted.

        Two tests, in order, and neither is a judgement about what an
        identifier looks like.  A character no configuration can put in an
        identifier is what no identifier contains, so an item holding one was
        not written as an identifier and must not be described as naming a
        repository -- a space is such a character whichever one it is, and so
        is a character reserved out of every identifier pattern
        (REQ-d00287-A).  Past that, whether some member *declares* the
        namespace the item opens with is a fact the federation holds, and it
        separates an identifier of this estate spelled wrongly from a name
        belonging outside it.

        A space decides that the item does not *bind*, and that is all it
        decides.  Where the item nonetheless opens with an acceptable
        reference, what it is worth telling the author is which reference was
        found and what followed it, so such an item is diagnosed the same way
        an unspaced one is (REQ-d00272-E) -- it still resolves to nothing,
        and it is still never described as naming a repository, because the
        member whose grammar read the head is the member that reports it.
        """
        from elspais.graph.reference_faults import FaultClass, FaultCode

        if any(ch in RESERVED_IDENTIFIER_CHARACTERS for ch in candidate):
            return FaultClass.MALFORMED, (FaultCode.NOT_AN_IDENTIFIER,)
        spaced = any(ch.isspace() for ch in candidate)
        if spaced and self.opening_reference(candidate) is None:
            return FaultClass.MALFORMED, (FaultCode.NOT_AN_IDENTIFIER,)
        declaring = [r for r in self._resolvers if r.declares_namespace(candidate)]
        if declaring:
            # Longest matching namespace, not first: `self._resolvers` is
            # own-repo-first, so a first-match pick would attribute
            # `REQ-ALP-p00001` to a member declaring plain `REQ` whenever
            # that member is scanned, reintroducing the misattribution this
            # function exists to prevent (REQ-d00272-C).
            owner = max(declaring, key=lambda r: len(r.config.namespace))
            # Implements: REQ-d00212-T
            # An out-of-range value is read as an identifier with trailing
            # digits by the bounded grammar, which names a defect the author
            # does not have: no repadding makes the number fit, so the value
            # is what is wrong and the value is what is reported.
            if owner.component_out_of_range(candidate):
                return FaultClass.MALFORMED, (FaultCode.COMPONENT_OUT_OF_RANGE,)
            codes = owner.diagnose_item(candidate)
            if codes == (FaultCode.IDENTIFIER_WITH_TRAILING_TEXT,) and owner.label_position_defect(
                candidate
            ):
                codes = (FaultCode.LABEL_OUT_OF_SERIES,)
            return FaultClass.MALFORMED, codes
        # Implements: REQ-d00287-A
        # No member claims the namespace this item opens with. An item
        # holding a space is not an identifier at all, so saying it names a
        # repository nobody configured would be the misattribution the space
        # test exists to prevent -- it is reported as what it is instead.
        if spaced:
            return FaultClass.MALFORMED, (FaultCode.NOT_AN_IDENTIFIER,)
        return FaultClass.UNKNOWN_NAMESPACE, ()

    # Implements: REQ-d00269-G, REQ-p00014-T
    def parse_ref_list(
        self,
        text: str,
        *,
        extra_items: Sequence[str] = (),
        comment_markers: Sequence[str] | None = None,
    ) -> list[RefItem]:
        """The items *text* spells as a separated list, each with its verdict.

        The one place a list of references is divided into its items.  A
        *Traceability* keyword introduces a list and nothing else, so each
        item is matched whole against a member's grammar rather than searched
        for inside the item.  Searching would read ``XREQ-d00001`` as
        ``REQ-d00001`` -- an edge to a requirement the author never named, and
        one nothing reports, since a reference that resolved is a reference
        that looked fine.

        Each item is judged on its own.  An item the grammar accounts for
        produces its reference; one it does not is returned carrying the class
        it reached, so the caller reports it rather than losing it.  A defect
        in one item is evidence about that item and not about the list
        (REQ-d00269-G).

        Args:
            text: The content a keyword introduced, with the keyword and its
                colon already removed.
            extra_items: Patterns for items belonging to a grammar this
                reader does not own -- a journey step, say -- which are
                accepted verbatim rather than normalized.
            comment_markers: The markers that open a comment in the language
                *text* was written in.  Defaults to the markers the
                reference grammar accepts, which is the answer available
                until the caller carries the file's kind; passing an empty
                sequence says the language has none.

        Returns:
            A ``RefItem`` per item, never ``None``.  An empty list means the
            content was empty.
        """
        from elspais.graph.reference_faults import FaultClass, FaultCode, RefItem

        stripped = text.strip()
        if not stripped:
            return []
        # Implements: REQ-d00287-B
        # A comment ends the reference before it, so it is taken off before
        # the list is divided -- prose may hold the dividing character, and
        # dividing first would report each fragment of a sentence as a
        # reference its author never wrote.
        markers = default_comment_markers() if comment_markers is None else tuple(comment_markers)
        stripped = self._without_comment(stripped, markers)
        extras = self._extra_patterns(extra_items)
        parts = stripped.split(REF_LIST_SEPARATOR)
        last_index = len(parts) - 1
        results: list[RefItem] = []
        for index, part in enumerate(parts):
            candidate = part.strip()
            if not candidate:
                # Implements: REQ-d00269-H
                # An empty final item means the separator that introduced it
                # had nothing to introduce -- a dangling separator, not a
                # gap between two named items -- so it is reported as one
                # and the other, never both, by its position in the list.
                code = FaultCode.TRAILING_SEPARATOR if index == last_index else FaultCode.EMPTY_ITEM
                results.append(
                    RefItem(
                        raw="",
                        index=index,
                        fault_class=FaultClass.MALFORMED,
                        codes=(code,),
                    )
                )
                continue
            # Whole-item membership, not a merged regex: a member's grammar
            # is more than its canonical form (an alias reads whole too, and
            # a mis-cased label is still recognised), and ``_classify`` is
            # anchored both ends throughout, so this is exactly the match a
            # single identifier gets, never a search inside a larger string.
            ref, matched = self._classify(candidate)
            if not matched and any(extra.fullmatch(candidate) for extra in extras):
                ref = candidate
                matched = True
            if matched:
                results.append(RefItem(raw=candidate, index=index, resolved=ref))
            else:
                fault_class, codes = self.classify_unmatched(candidate)
                results.append(
                    RefItem(raw=candidate, index=index, fault_class=fault_class, codes=codes)
                )

        # Implements: REQ-d00272-K
        # A repeated target is a list its author has lost track of. Every
        # instance is reported and none resolves -- keeping the first would
        # hide the very thing worth reporting. Detection is on the resolved
        # (normalized) target, so two spellings of one identifier count as a
        # repeat; an item that never resolved names no target and so cannot
        # collide with anything.
        target_counts: dict[str, int] = {}
        for item in results:
            if item.resolved is not None:
                target_counts[item.resolved] = target_counts.get(item.resolved, 0) + 1
        for i, item in enumerate(results):
            if item.resolved is not None and target_counts[item.resolved] > 1:
                results[i] = RefItem(
                    raw=item.raw,
                    index=item.index,
                    fault_class=FaultClass.FORBIDDEN,
                    codes=(FaultCode.DUPLICATE_ITEM,),
                )
        return results


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
