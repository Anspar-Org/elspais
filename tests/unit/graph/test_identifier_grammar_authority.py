# Verifies: REQ-d00268-A, REQ-d00268-B, REQ-d00268-C, REQ-d00268-D
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
from elspais.utilities.patterns import IdGrammar, IdResolver, build_resolver
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
    # Verifies: REQ-d00268-D
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
    assertion_separator="[-_]",
    multi_separator=r"\+",
)


def _stub_grammar(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the one authority answer with a grammar nothing else could invent."""
    monkeypatch.setattr(IdResolver, "grammar", lambda self, separator=None: _SENTINEL)


def test_grammar_fragments_are_reachable_through_the_public_interface() -> None:
    # Verifies: REQ-d00268-B
    resolver = build_resolver(_config())
    grammar = resolver.grammar()
    for name in (
        "namespace",
        "level",
        "component",
        "identifier",
        "assertion_label",
        "assertion_separator",
        "multi_separator",
    ):
        fragment = getattr(grammar, name)
        assert isinstance(fragment, str) and fragment, f"{name} fragment is empty"
        re.compile(fragment)  # every fragment is usable on its own


def test_lark_grammar_builder_takes_its_tokens_from_the_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Verifies: REQ-d00268-C
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
    # Verifies: REQ-d00268-C
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
    # Verifies: REQ-d00268-C
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
    # Verifies: REQ-d00268-A
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
    # Verifies: REQ-d00268-A
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
    # Verifies: REQ-d00268-D
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
    # Verifies: REQ-d00268-D
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
    # Verifies: REQ-d00268-D
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
    # Verifies: REQ-d00268-D
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
    # Verifies: REQ-d00268-D
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
    # Verifies: REQ-d00268-D
    """A multi-assertion reference is a list of labels, each one settled."""
    resolver = build_resolver(NUMERIC)

    assert resolver.normalize_ref(raw) == expected
