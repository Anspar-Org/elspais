# Verifies: REQ-d00212-G, REQ-p00014-T
"""One authority derives a repository's identifier grammar.

Several surfaces have to recognise an identifier: the resolver that parses
one, the lark grammar that finds one in a spec or a source file, the
reference matcher that expands a multi-assertion target, and the federation
probe that decides which repository of a federation claims one. When any of
them composes its own patterns the surfaces answer for different sets of
strings, and the reported severity of a broken reference depends on which
one was asked.

These tests hold the surfaces to the single derivation: that the fragments
are reachable publicly, that the consumers take them from there, that the
underscore spelling of an identifier is the same grammar in another
notation, and that recognition and claiming agree.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from elspais.graph.federated import FederatedGraph
from elspais.graph.parsers.lark import GrammarFactory
from elspais.graph.parsers.lark.transformers.reference import ReferenceTransformer
from elspais.utilities.patterns import (
    FederatedIdReader,
    IdGrammar,
    IdResolver,
    build_resolver,
)
from tests.federation_repos import make_repo


def _config(
    *,
    namespace: str = "REQ",
    canonical: str = "{namespace}-{level.letter}{component}",
    component: dict | None = None,
    assertions: dict | None = None,
) -> dict:
    """A minimal configuration dictionary for ``build_resolver``."""
    return {
        "project": {"namespace": namespace},
        "levels": {
            "prd": {"rank": 1, "letter": "p"},
            "dev": {"rank": 2, "letter": "d"},
        },
        "id-patterns": {
            "canonical": canonical,
            "component": component or {"style": "numeric", "digits": 5},
            "assertions": assertions or {},
        },
    }


KEBAB_SLASH = _config(
    canonical="{namespace}-{level.letter}-{component}",
    component={"style": "kebab-case", "digits": 0, "leading_zeros": False},
    assertions={"separator": "/"},
)

SNAKE_DASH = _config(
    canonical="{namespace}-{level.letter}-{component}",
    component={"style": "snake_case", "digits": 0, "leading_zeros": False},
    assertions={"separator": "-"},
)

KEBAB_DASH = _config(
    canonical="{namespace}-{level.letter}-{component}",
    component={"style": "kebab-case", "digits": 0, "leading_zeros": False},
)


# ---------------------------------------------------------------------------
# The matcher and the resolver answer for the same strings.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "config, probe",
    [
        # kebab-case component, "/" before the assertion labels.
        (KEBAB_SLASH, "REQ-p-widget"),
        (KEBAB_SLASH, "REQ-p-widget/A"),
        (KEBAB_SLASH, "REQ-p-widget/A+C"),
        (KEBAB_SLASH, "REQ-d-my-long-widget/B"),
        (KEBAB_SLASH, "REQ-p-Widget"),  # case-style violated
        (KEBAB_SLASH, "REQ-p-widget-A+C"),  # wrong assertion separator
        (KEBAB_SLASH, "REQ-p-my_widget/A"),  # wrong word separator
        (KEBAB_SLASH, "REQ-x-widget/A"),  # unknown level
        (KEBAB_SLASH, "PRD-p-widget/A"),  # foreign namespace
        # snake_case component, "-" before the assertion labels: the
        # component's own word separator and the assertion separator are
        # now different characters, so the boundary has to be found.
        (SNAKE_DASH, "REQ-p-widget"),
        (SNAKE_DASH, "REQ-p-my_widget"),
        (SNAKE_DASH, "REQ-p-my_widget-A+C"),
        (SNAKE_DASH, "REQ-d-widget-B"),
        (SNAKE_DASH, "REQ-p-My_Widget"),  # case-style violated
        (SNAKE_DASH, "REQ-p-my-widget"),  # wrong word separator
        (SNAKE_DASH, "REQ-p-widget/A"),  # wrong assertion separator
        (SNAKE_DASH, "PRD-p-widget-A"),  # foreign namespace
    ],
)
def test_matcher_and_resolver_recognise_the_same_strings(config: dict, probe: str) -> None:
    # Verifies: REQ-p00014-T
    # The probes are written in the case the configuration prescribes. The
    # matcher reads text tolerantly and hands what it finds to
    # ``normalize_ref`` before anything parses it, so a mis-cased namespace
    # is a reading tolerance rather than a second answer about which strings
    # are identifiers. What the two surfaces must agree on is the shape.
    resolver = build_resolver(config)
    matched = resolver.multi_assertion_reference_regex().fullmatch(probe) is not None
    accepted = resolver.is_local_id(probe)
    assert matched == accepted, (
        f"{probe!r}: the reference matcher says {matched} and the resolver says "
        f"{accepted}; a string only one of them recognises is a broken reference "
        f"whose severity depends on which surface was asked"
    )


# ---------------------------------------------------------------------------
# Consumers take their fragments from the public surface.
# ---------------------------------------------------------------------------


_SENTINEL = IdGrammar(
    namespace="ZQX",
    level="q",
    component="[0-9]{4}",
    identifier="ZQX[-_]q[0-9]{4}",
    assertion_label="[A-Z]",
    assertion_label_exact="(?-i:[A-Z])",
    assertion_separator="[-_]",
    multi_separator=r"\+",
)


def _stub_grammar(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the one authority answer with a grammar nothing else could invent."""
    monkeypatch.setattr(IdResolver, "grammar", lambda self, separator=None: _SENTINEL)


def test_grammar_fragments_are_reachable_through_the_public_interface() -> None:
    # Verifies: REQ-d00212-G
    resolver = build_resolver(_config())
    grammar = resolver.grammar()
    for name in (
        "namespace",
        "level",
        "component",
        "identifier",
        "assertion_label",
        "assertion_label_exact",
        "assertion_separator",
        "multi_separator",
    ):
        fragment = getattr(grammar, name)
        assert isinstance(fragment, str) and fragment, f"{name} fragment is empty"
        re.compile(fragment)  # every fragment is usable on its own


def test_lark_grammar_builder_takes_its_tokens_from_the_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Verifies: REQ-d00212-G
    resolver = build_resolver(_config())
    _stub_grammar(monkeypatch)

    tokens = GrammarFactory(resolver)._build_tokens()

    assert tokens["__ID_PATTERN__"] == _SENTINEL.identifier
    assert tokens["__NAMESPACE__"] == _SENTINEL.namespace
    assert tokens["__DIGITS_PATTERN__"] == _SENTINEL.component
    assert tokens["__ASSERTION_LABEL__"] == _SENTINEL.assertion_label


class _Token:
    """The one shape ``_handle_test_name_ref`` reads off a parse tree."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.line = 1

    def __str__(self) -> str:
        return self._text


def test_test_function_matcher_takes_its_pattern_from_the_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Verifies: REQ-d00212-G
    resolver = build_resolver(_config())
    transformer = ReferenceTransformer(resolver, "test_ref")
    _stub_grammar(monkeypatch)

    # The sentinel grammar is the only thing that can recognise this name.
    node = SimpleNamespace(children=[_Token("def test_thing_ZQX_q0007_B")])
    parsed = transformer._handle_test_name_ref(node)

    assert parsed is not None, "the matcher did not use the derived grammar"
    assert parsed.parsed_data["verifies"] == ["ZQX-q0007-B"]


def test_reference_expansion_takes_its_pattern_from_the_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Verifies: REQ-d00212-G
    resolver = build_resolver(_config())
    transformer = ReferenceTransformer(resolver, "code_ref")
    sentinel_re = re.compile(r"ZQX-q[0-9]{4}")
    monkeypatch.setattr(IdResolver, "multi_assertion_reference_regex", lambda self: sentinel_re)

    assert transformer._extract_ids("Implements: ZQX-q0007, REQ-d00001") == ["ZQX-q0007"]


# ---------------------------------------------------------------------------
# The underscore spelling is the same grammar in another notation.
# ---------------------------------------------------------------------------


def _reference_regex(grammar: IdGrammar) -> re.Pattern[str]:
    """Identifier plus an optional single assertion label, in one notation."""
    return re.compile(
        rf"{grammar.identifier}(?:{grammar.assertion_separator}{grammar.assertion_label})?"
    )


@pytest.mark.parametrize(
    "hyphen_spelling",
    [
        "REQ-d00001",
        "REQ-p1",
        "REQ-d00001-A",
        "REQ-p00042-Z",
        "REQ-x00001",  # unknown level
        "REQ-d000001",  # component too long
        "REQ-d00001-a",  # lowercase label
        "PRD-d00001",  # foreign namespace
        "REQd00001",  # missing punctuation
    ],
)
def test_underscore_notation_matches_the_same_identifiers(hyphen_spelling: str) -> None:
    # Verifies: REQ-d00212-G
    resolver = build_resolver(_config())
    hyphen = _reference_regex(resolver.grammar())
    underscore = _reference_regex(resolver.grammar(separator="_"))

    underscore_spelling = hyphen_spelling.replace("-", "_")
    assert (hyphen.fullmatch(hyphen_spelling) is not None) == (
        underscore.fullmatch(underscore_spelling) is not None
    ), (
        f"{hyphen_spelling!r} and {underscore_spelling!r} are one identifier in "
        f"two notations and must be recognised alike"
    )


def test_underscore_notation_rejects_the_hyphen_spelling() -> None:
    # Verifies: REQ-d00212-G
    """The notation is rendered, not merely tolerated alongside the default."""
    resolver = build_resolver(_config())
    underscore = _reference_regex(resolver.grammar(separator="_"))

    assert underscore.fullmatch("REQ_d00001_A") is not None
    assert underscore.fullmatch("REQ-d00001-A") is None


# ---------------------------------------------------------------------------
# The federation claim probe claims exactly what the resolver accepts.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def federation(tmp_path_factory) -> FederatedGraph:
    """A root repository with one associate occupying a disjoint namespace."""
    from elspais.config import load_config
    from elspais.graph.factory import build_graph

    base = tmp_path_factory.mktemp("claim_probe")
    make_repo(base, "lib", namespace="LIB", req_id="LIB-d00001")
    root = make_repo(
        base,
        "root",
        namespace="REQ",
        associates={"lib": "../lib"},
        associate_namespaces={"lib": "LIB"},
    )
    return build_graph(config=load_config(root / ".elspais.toml"), repo_root=root)


@pytest.mark.parametrize(
    "probe",
    [
        "LIB-d00001",  # canonical
        "LIB-d1",  # unpadded -- the resolver normalises it
    ],
)
def test_claim_probe_claims_what_the_resolver_accepts(
    federation: FederatedGraph, probe: str
) -> None:
    # Verifies: REQ-p00014-T
    assert federation._claim_for(probe) == ("lib", "LIB-d00001")


@pytest.mark.parametrize(
    "probe",
    [
        "LIB-widget",  # no level letter, no numeric component
        "LIB-d00001x",  # trailing junk
        "lib-d00001",  # namespace in the wrong case
        "LIB",  # namespace alone
    ],
)
def test_claim_probe_refuses_what_the_resolver_rejects(
    federation: FederatedGraph, probe: str
) -> None:
    # Verifies: REQ-p00014-T
    resolver = federation._resolver_for(federation._repos["lib"])
    assert resolver is not None
    assert not resolver.is_local_id(probe), "probe must be one the owning resolver rejects"
    assert federation._claim_for(probe) is None


# ---------------------------------------------------------------------------
# Normalization settles the case the matcher reads tolerantly.
# ---------------------------------------------------------------------------
#
# The reference matcher recognises an identifier without regard to case, so a
# mis-cased reference reaches normalization. Whatever normalization hands on is
# then parsed case-sensitively. Every part whose case the grammar does not
# treat as significant -- the namespace, the level code, the assertion labels
# -- is therefore settled here, or the reference arrives at the resolver as a
# string no repository claims and a local typo is reported as belonging to
# another repository.
#
# The component is the exception. Under a case-style its case is its identity,
# so a mis-cased component names a different component and must stay
# unresolved. Note KEBAB_DASH is not exercised with a lowercase assertion
# label: with a kebab-case component and "-" separating the labels, "-a" is
# absorbed by the component, which is the separate ambiguity REQ-d00251-F
# governs.

NUMERIC = _config()


def _matcher_recognises(resolver: IdResolver, text: str) -> bool:
    """Whether a reference matcher would pick ``text`` out of a source file.

    Two notations are rendered from the one grammar, and text is read
    tolerantly of case in both, so a reference the matcher hands to
    normalization may be spelled either way.
    """
    if resolver.multi_assertion_reference_regex().fullmatch(text) is not None:
        return True
    underscore = _reference_regex(resolver.grammar(separator="_"))
    return re.fullmatch(underscore.pattern, text, re.IGNORECASE) is not None


@pytest.mark.parametrize(
    "config, raw, expected, local",
    [
        # Numeric component, "letter" level alias, uppercase labels.
        (NUMERIC, "REQ-d00001-a", "REQ-d00001-A", True),  # label case
        (NUMERIC, "req-D00001-A", "REQ-d00001-A", True),  # namespace and level case
        (NUMERIC, "REQ_d00001_a", "REQ-d00001-A", True),  # underscore notation
        (NUMERIC, "REQ-d00001-a+b", "REQ-d00001-A+B", True),  # multi-assertion
        (NUMERIC, "XXX-d00001-a", "XXX-d00001-a", False),  # foreign namespace
        # kebab-case component: the component's own case is load-bearing.
        (KEBAB_DASH, "REQ-p-widget-A", "REQ-p-widget-A", True),
        (KEBAB_DASH, "REQ-p-Widget-A", "REQ-p-Widget-A", False),
    ],
)
def test_normalize_ref_settles_case_the_grammar_does_not_own(
    config: dict, raw: str, expected: str, local: bool
) -> None:
    # Verifies: REQ-p00014-T
    resolver = build_resolver(config)

    normalized = resolver.normalize_ref(raw)

    assert normalized == expected
    assert resolver.is_local_id(normalized) is local


@pytest.mark.parametrize(
    "variant",
    [
        "REQ-d00001-A",  # already canonical
        "REQ-d00001-a",
        "req-d00001-a",
        "REQ-D00001-A",
        "rEq-D00001-a",
        "REQ_d00001_a",  # underscore notation, as a test function name spells it
        "req_D00001_A",
    ],
)
def test_matcher_and_resolver_agree_after_normalization(variant: str) -> None:
    # Verifies: REQ-p00014-T
    """Whatever the matcher recognises, the resolver claims once normalized.

    The matcher compiles case-insensitively and the resolver parses
    case-sensitively. Normalization is the only place that difference can be
    reconciled, so a string the matcher recognises must survive it as one the
    resolver accepts. Otherwise the two surfaces answer for different sets of
    strings and the severity of a broken reference depends on which was asked.
    """
    resolver = build_resolver(NUMERIC)
    assert _matcher_recognises(resolver, variant), (
        f"{variant!r} is not a case variant the matcher recognises, so it cannot "
        f"test the agreement"
    )

    normalized = resolver.normalize_ref(variant)

    assert resolver.is_local_id(normalized), (
        f"the matcher recognises {variant!r} but the resolver refuses its "
        f"normalized form {normalized!r}, so a local typo is reported as a "
        f"reference belonging to another repository"
    )


@pytest.mark.parametrize(
    "config, raw",
    [
        # A case-style component's case is its identity: this names a
        # component that does not exist, not "widget" spelled differently.
        (KEBAB_DASH, "REQ-p-Widget-A"),
        # Another repository's namespace: not this resolver's to rewrite.
        (NUMERIC, "XXX-d00001-a"),
    ],
)
def test_normalize_ref_leaves_what_it_cannot_claim_untouched(config: dict, raw: str) -> None:
    # Verifies: REQ-p00014-T
    resolver = build_resolver(config)

    normalized = resolver.normalize_ref(raw)

    assert normalized == raw, "an unclaimable reference is passed through, not rewritten"
    assert not resolver.is_local_id(normalized), "and it stays unresolved"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("REQ-d00001-a+b+c", "REQ-d00001-A+B+C"),
        ("REQ-d00001-A+b+C", "REQ-d00001-A+B+C"),
        ("REQ-d00001-a+B+c", "REQ-d00001-A+B+C"),
    ],
)
def test_every_assertion_label_is_canonicalized(raw: str, expected: str) -> None:
    # Verifies: REQ-p00014-T
    """A multi-assertion reference is a list of labels, each one settled."""
    resolver = build_resolver(NUMERIC)

    assert resolver.normalize_ref(raw) == expected


# ---------------------------------------------------------------------------
# A label alphabet that names a case keeps that case wherever it is embedded.
# ---------------------------------------------------------------------------


UPPERCASE_LABELS = _config(assertions={"label_style": "uppercase"})
ALPHANUMERIC_LABELS = _config(assertions={"label_style": "alphanumeric"})
NUMERIC_LABELS = _config(assertions={"label_style": "numeric"})


@pytest.mark.parametrize(
    "config, function_name, expected",
    [
        # A single lowercase word after a genuine label: the following word
        # of a function name, not a second label.
        (UPPERCASE_LABELS, "test_REQ_p00001_A_b_and_more", "REQ-p00001-A"),
        (UPPERCASE_LABELS, "test_REQ_p00001_A_and_then_some", "REQ-p00001-A"),
        (UPPERCASE_LABELS, "test_REQ_p00001_validates_something", "REQ-p00001"),
        # The shape that mints a broken reference out of a test's own name:
        # a real label followed by a single-letter word.
        (UPPERCASE_LABELS, "test_REQ_d00269_E_a_demoted_line_survives", "REQ-d00269-E"),
        # A lowercase *first* label is still a mis-cased label, not a word.
        (UPPERCASE_LABELS, "test_REQ_p00001_a_lower", "REQ-p00001-A"),
        # An alphabet that admits digits still names a case for its letters.
        (ALPHANUMERIC_LABELS, "test_REQ_p00001_A_b_and_more", "REQ-p00001-A"),
        (ALPHANUMERIC_LABELS, "test_REQ_p00001_3_more", "REQ-p00001-3"),
        # A lowercase *first* label is a mis-cased label the separator still
        # marks out, so it is read and canonicalized rather than dropped.
        (ALPHANUMERIC_LABELS, "test_REQ_p00001_a_lower", "REQ-p00001-A"),
        # Digits have no case to preserve, so a digit label reads unchanged.
        (NUMERIC_LABELS, "test_REQ_p00001_2_b_more", "REQ-p00001-2"),
        (NUMERIC_LABELS, "test_REQ_p00001_a_lower", "REQ-p00001"),
    ],
)
def test_a_test_function_name_yields_an_identifier_the_resolver_accepts(
    config: dict, function_name: str, expected: str
) -> None:
    # Verifies: REQ-p00014-T
    """What the reader picks out of a name must be one the resolver parses.

    A test function name spells every boundary as an underscore, so the
    trailing words of the name sit exactly where a label would. Reading one
    of them as a label produces a string the resolver rejects -- the two
    surfaces then disagree about what an identifier is, and the disagreement
    surfaces as a broken reference minted out of a test's own name.
    """
    resolver = build_resolver(config)
    reader = FederatedIdReader(resolver)

    extracted = reader.extract_underscored_ref(function_name)

    assert extracted == expected
    assert resolver.is_local_id(extracted), (
        f"the reader picked {extracted!r} out of {function_name!r} but the "
        f"resolver refuses it, so a test name mints a broken reference to a "
        f"requirement nothing declares"
    )


def test_case_tolerance_of_a_label_ends_where_the_notation_runs_out() -> None:
    # Verifies: REQ-p00014-T
    """Only a second label needs its case to be told from a following word.

    Both notations separate the component from the first label with a
    character of their own, so a lowercase first label is a mis-cased label
    and normalization settles it -- in either notation. It is the *second*
    label that the underscore notation cannot punctuate distinctly, because
    the separator between two labels is the same ``_``; there case is the
    only thing left, and reading a following word as a label yields a string
    the resolver refuses.
    """
    resolver = build_resolver(NUMERIC)
    reader = FederatedIdReader(resolver)

    assert _matcher_recognises(resolver, "req-d00001-a")
    assert resolver.is_local_id(resolver.normalize_ref("req-d00001-a"))

    assert _matcher_recognises(resolver, "REQ_d00001_a")
    assert reader.extract_underscored_ref("test_REQ_d00001_a") == "REQ-d00001-A"

    assert reader.extract_underscored_ref("test_REQ_d00001_A_note") == "REQ-d00001-A"


# ---------------------------------------------------------------------------
# The underscore notation folds back onto the template's own literals.
# ---------------------------------------------------------------------------
#
# A component style has punctuation of its own, and it is not always the
# punctuation the canonical template spells its boundaries with. Under a
# snake_case component the two are `_` and `-`; a fold that rewrites every
# underscore into the component's character therefore rewrites nothing, and
# the name the matcher recognised arrives at the resolver unchanged and
# unclaimed. Folding has to restore each character where it belongs: the
# template's literals between the parts, the component's own inside it.


@pytest.mark.parametrize(
    "config, function_name, expected",
    [
        # snake_case component: the component keeps its `_`, the template's
        # boundaries go back to `-`.
        (SNAKE_DASH, "test_REQ_p_data_export_A", "REQ-p-data_export-A"),
        (SNAKE_DASH, "test_REQ_d_my_long_widget_B", "REQ-d-my_long_widget-B"),
        (SNAKE_DASH, "test_REQ_p_widget", "REQ-p-widget"),
        # kebab-case control: here the component's own character happens to
        # equal the template's, and the component must still be spelled with
        # it rather than left in the notation it was read in.
        (KEBAB_DASH, "test_REQ_p_data_export_A", "REQ-p-data-export-A"),
        (KEBAB_DASH, "test_REQ_p_widget", "REQ-p-widget"),
    ],
)
def test_a_component_style_folds_onto_the_templates_own_separators(
    config: dict, function_name: str, expected: str
) -> None:
    # Verifies: REQ-p00014-T
    """A test name under a case-style component yields an identifier that parses.

    The reader recognises the name through the grammar re-rendered in
    underscore notation. If normalization cannot spell the result back in the
    configured punctuation the resolver refuses it, and the test's own name
    mints a broken reference to a requirement nothing declares.
    """
    resolver = build_resolver(config)
    reader = FederatedIdReader(resolver)

    extracted = reader.extract_underscored_ref(function_name)

    assert extracted == expected
    assert resolver.is_local_id(extracted), (
        f"the reader picked {extracted!r} out of {function_name!r} but the " f"resolver refuses it"
    )


@pytest.mark.parametrize(
    "config, raw, expected",
    [
        (SNAKE_DASH, "REQ_p_data_export_A", "REQ-p-data_export-A"),
        (SNAKE_DASH, "REQ-p-data_export-A", "REQ-p-data_export-A"),
        (KEBAB_DASH, "REQ_p_data_export_A", "REQ-p-data-export-A"),
    ],
)
def test_normalize_ref_folds_a_case_style_component(config: dict, raw: str, expected: str) -> None:
    # Verifies: REQ-p00014-T
    resolver = build_resolver(config)

    normalized = resolver.normalize_ref(raw)

    assert normalized == expected
    assert resolver.is_local_id(normalized)


def test_underscore_notation_still_reads_two_labels() -> None:
    # Verifies: REQ-p00014-T
    """The notation spells both boundaries as `_`, so the split is searched for.

    A head that already carries a label is not the boundary; the longest head
    that parses without one is, and the remainder are labels joined by the
    configured multi-separator.
    """
    resolver = build_resolver(NUMERIC)

    assert resolver.normalize_ref("REQ_d00001_A_B") == "REQ-d00001-A+B"
    assert resolver.is_local_id(resolver.normalize_ref("REQ_d00001_A_B"))


@pytest.mark.parametrize(
    "style, expected_spelling",
    [
        ("snake_case", "data_export"),
        ("kebab-case", "data_export"),
    ],
)
def test_component_regex_honours_an_alternate_internal_separator(
    style: str, expected_spelling: str
) -> None:
    # Verifies: REQ-d00212-G
    """A case-style's internal punctuation is a parameter of the one authority.

    A notation that cannot spell the style's own character substitutes its
    own, and the pattern has to follow it there rather than being composed a
    second time by the caller.
    """
    from elspais.utilities.patterns import ComponentFormat, component_regex

    comp = ComponentFormat(style=style, digits=0, leading_zeros=False, pattern=None)

    assert re.fullmatch(component_regex(comp, internal_separator="_"), expected_spelling)
    assert re.fullmatch(component_regex(comp, internal_separator="/"), "data/export")
    if style == "kebab-case":
        # Without the parameter the style's own character is what is demanded.
        assert re.fullmatch(component_regex(comp), "data-export")
        assert not re.fullmatch(component_regex(comp), "data_export")
