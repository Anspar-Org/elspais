# Verifies: REQ-p00014-T, REQ-d00251-L
"""One authority derives a repository's identifier grammar.

Several surfaces have to recognise an identifier: the resolver that parses
one, the lark grammar that finds one in a spec or a source file, the
reference matcher that expands a multi-assertion target, and the federation
probe that decides which repository of a federation claims one. When any of
them composes its own patterns the surfaces answer for different sets of
strings, and the reported severity of a broken reference depends on which
one was asked.

These tests hold the surfaces to the single derivation: that the fragments
are reachable publicly, that the consumers take them from there, and that
recognition and claiming agree. There is one notation, and a spelling
differing from it in anything but case and padding is a reference spelled
wrongly rather than a second rendering of the grammar (REQ-d00212-S).
"""

from __future__ import annotations

import pytest

from elspais.config.schema import ElspaisConfig
from elspais.graph.federated import FederatedGraph
from elspais.graph.parsers.lark import GrammarFactory
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
    """A configuration dictionary the shipped schema accepts.

    ``build_resolver`` takes a raw dictionary and never consults the config
    schema, so a fixture built here could describe a repository no config
    file can produce -- and pin behaviour no user can reach. Every fixture is
    therefore validated the way ``load_config`` validates a file on disk,
    before any resolver is built from it, so an unreachable one fails loudly
    at collection instead of quietly pinning unreachable behaviour.
    """
    config = {
        "project": {"namespace": namespace},
        "levels": {
            "prd": {"rank": 1, "letter": "p", "implements": ["prd"]},
            "dev": {"rank": 2, "letter": "d", "implements": ["dev", "prd"]},
        },
        "id-patterns": {
            "canonical": canonical,
            "component": component or {"style": "numeric", "digits": 5},
            "assertions": assertions or {},
        },
    }
    ElspaisConfig.model_validate(config)
    return config


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
    namespace_separator="-",
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


def test_lark_grammar_builder_takes_its_tokens_from_the_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Verifies: REQ-p00014-T
    resolver = build_resolver(_config())
    _stub_grammar(monkeypatch)

    tokens = GrammarFactory(resolver)._build_tokens()

    assert tokens["__ID_PATTERN__"] == _SENTINEL.identifier
    assert tokens["__NAMESPACE__"] == _SENTINEL.namespace
    assert tokens["__DIGITS_PATTERN__"] == _SENTINEL.component
    assert tokens["__ASSERTION_LABEL__"] == _SENTINEL.assertion_label


def test_the_namespace_claim_probe_takes_its_pattern_from_the_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Verifies: REQ-p00014-T
    """Which repository a broken item is attributed to reads one grammar.

    The probe deciding whether an item opens with this repository's
    namespace takes the namespace and the separator that ends it from the
    authority rather than assuming a ``-``. Composing them here instead
    would attribute every identifier of a repository configured otherwise
    to nobody at all, and the severity of a broken reference would depend
    on which surface was asked.
    """
    resolver = build_resolver(_config())
    _stub_grammar(monkeypatch)

    # The sentinel grammar is the only thing that claims this namespace, and
    # the only thing that stops the configured one being claimed.
    assert resolver.declares_namespace("ZQX-q0007"), "the probe did not use the derived grammar"
    assert not resolver.declares_namespace("REQ-d00001")


def test_reference_expansion_takes_its_pattern_from_the_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Verifies: REQ-d00081-D
    """A multi-*Assertion* reference is recognised through the one grammar.

    What expands to a set of individual references is settled by the
    authority's fragments -- the identifier, the assertion separator, the
    label alphabet and the multi-separator -- so the same reference expands
    the same way wherever it is written.
    """
    resolver = build_resolver(_config())
    _stub_grammar(monkeypatch)

    pattern = resolver.multi_assertion_reference_regex()

    assert pattern.fullmatch("ZQX-q0007-B"), "the expansion pattern did not use the authority"
    assert pattern.fullmatch("ZQX-q0007-A+B"), "and it must span every label of the reference"
    assert not pattern.fullmatch("REQ-d00001")


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
    assert federation._claim_for(probe) == ("LIB", "LIB-d00001")


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
    resolver = federation._resolver_for(federation.repo_for("LIB-d00001"))
    assert resolver is not None
    assert not resolver.is_local_id(probe), "probe must be one the owning resolver rejects"
    assert federation._claim_for(probe) is None


# ---------------------------------------------------------------------------
# Normalization settles the case and padding the matcher reads tolerantly.
# ---------------------------------------------------------------------------
#
# The reference matcher recognises an identifier without regard to case or to
# a numeric component's leading zeros, so a reference differing in either
# reaches normalization. Whatever normalization hands on is then parsed
# strictly. Every part whose case the grammar does not treat as significant --
# the namespace, the level code, the assertion labels -- and the width of a
# numeric component are therefore settled here, or the reference arrives at
# the resolver as a string no repository claims and a local typo is reported
# as belonging to another repository (REQ-d00212-R).
#
# Case and padding are settled on different paths -- one runs while an
# identifier parses, the other repairs a spelling that did not -- so a
# reference differing in BOTH travels only one of them. That is the quadrant
# a fix to either path alone leaves behind, and the table below covers all
# four rather than the two that are easy to reach.
#
# The component is the exception in the other direction. Under a case-style
# its case is its identity, so a mis-cased component names a different
# component and must stay unresolved.

NUMERIC = _config()


def _matcher_recognises(resolver: IdResolver, text: str) -> bool:
    """Whether a reference matcher would pick ``text`` out of a source file.

    One grammar, compiled case-insensitively, so a reference the matcher
    hands to normalization may be mis-cased but is otherwise spelled as the
    configuration admits.
    """
    return resolver.multi_assertion_reference_regex().fullmatch(text) is not None


@pytest.mark.parametrize(
    "config, raw, expected, local",
    [
        # -- Settled: case, padding, and the two together (REQ-d00212-R) --
        # Neither differs: the control the rows below are read against.
        (NUMERIC, "REQ-p00001-A", "REQ-p00001-A", True),
        # Case only.
        (NUMERIC, "REQ-p00001-a", "REQ-p00001-A", True),  # label case
        (NUMERIC, "req-D00001-A", "REQ-d00001-A", True),  # namespace and level case
        # Padding only.
        (NUMERIC, "REQ-p1-A", "REQ-p00001-A", True),
        # Both at once -- the quadrant reachable on neither path alone.
        (NUMERIC, "REQ-p1-a", "REQ-p00001-A", True),
        (NUMERIC, "req-p1-a", "REQ-p00001-A", True),
        # Both, carrying a multi-assertion suffix.
        (NUMERIC, "REQ-p1-a+b", "REQ-p00001-A+B", True),
        # Both, over-padded rather than under-padded: the value is the
        # identity, so it is re-padded to the configured width rather than
        # having zeros prepended to what was written.
        (NUMERIC, "REQ-p0001-a", "REQ-p00001-A", True),
        # -- Not settled: every other difference (REQ-d00212-S) ------------
        # Punctuation is neither case nor padding, so an underscore spelling
        # is left exactly as written and stays unresolved.
        (NUMERIC, "REQ_d00001_a", "REQ_d00001_a", False),
        (NUMERIC, "XXX-d00001-a", "XXX-d00001-a", False),  # foreign namespace
        # kebab-case component: the component's own case is load-bearing.
        (KEBAB_SLASH, "REQ-p-widget/A", "REQ-p-widget/A", True),
        (KEBAB_SLASH, "REQ-p-Widget/A", "REQ-p-Widget/A", False),
    ],
)
def test_normalize_ref_settles_case_and_padding_and_nothing_further(
    config: dict, raw: str, expected: str, local: bool
) -> None:
    # Verifies: REQ-d00212-R, REQ-d00212-S, REQ-p00014-T
    """One rule read from both ends: what normalization settles, and what it
    must leave alone.

    Case and padding decide nothing about whether a reference resolves
    (REQ-d00212-R), and every other difference decides it absolutely
    (REQ-d00212-S). Both halves fail silently and in opposite directions: a
    tolerance that stops working turns a valid citation into a broken
    reference attributed to another repository, and a tolerance that reaches
    too far builds an edge its author never spelled.

    The rendered spelling is asserted too, not merely that the reference
    resolves. A reference may resolve while rendering in a form the
    configuration does not name, and `fix` writes what the renderer returns.
    """
    resolver = build_resolver(config)

    normalized = resolver.normalize_ref(raw)

    assert normalized == expected, (
        f"{raw!r} normalized to {normalized!r}; the one spelling the "
        f"configuration names is {expected!r}"
    )
    assert resolver.is_local_id(normalized) is local


@pytest.mark.parametrize(
    "variant",
    [
        "REQ-d00001-A",  # already canonical
        "REQ-d00001-a",
        "req-d00001-a",
        "REQ-D00001-A",
        "rEq-D00001-a",
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
        f"{variant!r} is not a case variant the matcher recognises, so it cannot test the agreement"
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
        (KEBAB_SLASH, "REQ-p-Widget/A"),
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
    "config, raw, expected",
    [
        # A label alphabet that names a case settles that case, so a
        # mis-cased label is a mis-cased label rather than a second answer
        # about what an identifier is.
        (UPPERCASE_LABELS, "REQ-p00001-A", "REQ-p00001-A"),
        (UPPERCASE_LABELS, "REQ-p00001-a", "REQ-p00001-A"),
        (UPPERCASE_LABELS, "REQ-p00001", "REQ-p00001"),
        # An alphabet that admits digits still names a case for its letters.
        (ALPHANUMERIC_LABELS, "REQ-p00001-a", "REQ-p00001-A"),
        # Digits have no case to preserve, so a digit label reads unchanged.
        (ALPHANUMERIC_LABELS, "REQ-p00001-3", "REQ-p00001-3"),
        (NUMERIC_LABELS, "REQ-p00001-2", "REQ-p00001-2"),
        (NUMERIC_LABELS, "REQ-p00001", "REQ-p00001"),
    ],
)
def test_a_label_alphabet_settles_the_case_it_names(config: dict, raw: str, expected: str) -> None:
    # Verifies: REQ-p00014-T
    """What the matcher reads tolerantly, the resolver must still accept.

    The reference matcher recognises a label without regard to case, and the
    resolver parses case-sensitively; normalization is the only place the
    two can be reconciled. Where a label alphabet names a case, an alphabet
    that failed to settle it would hand the resolver a string no repository
    claims, and a local typo would be reported as a reference belonging to
    another repository.
    """
    resolver = build_resolver(config)

    normalized = resolver.normalize_ref(raw)

    assert normalized == expected
    assert resolver.is_local_id(normalized), (
        f"normalization produced {normalized!r} from {raw!r} and the resolver "
        f"refuses it, so the two surfaces answer for different sets of strings"
    )


# ---------------------------------------------------------------------------
# A component style's own punctuation is not the template's.
# ---------------------------------------------------------------------------
#
# A component style has punctuation of its own, and it is not always the
# punctuation the canonical template spells its boundaries with. Under a
# snake_case component the two are `_` and `-`, and each has to be read where
# it belongs: the template's literals between the parts, the component's own
# inside it. Reading tolerantly settles case and padding and extends to no
# further difference (REQ-d00212-S), so swapping one of those characters for
# the other names a component this repository does not have -- and is left as
# written rather than repaired into one it does.


@pytest.mark.parametrize(
    "config, raw, local",
    [
        # snake_case component: its own `_` stays inside the component while
        # the template's boundaries stay `-`.
        (SNAKE_DASH, "REQ-p-data_export-A", True),
        (SNAKE_DASH, "REQ-p-widget", True),
        # The template's character written inside the component: a component
        # that does not exist, not "data_export" spelled differently.
        (SNAKE_DASH, "REQ-p-data-export-A", False),
        # kebab-case control: here the component's own character equals the
        # template's, and the assertion separator is what parts them.
        (KEBAB_SLASH, "REQ-p-data-export/A", True),
        (KEBAB_SLASH, "REQ-p-widget", True),
        (KEBAB_SLASH, "REQ-p-data_export/A", False),
        # Every boundary spelled `_`: a difference of punctuation, so it is
        # neither claimed nor repaired, under either style.
        (SNAKE_DASH, "REQ_p_data_export_A", False),
        (KEBAB_SLASH, "REQ_p_data_export_A", False),
    ],
)
def test_a_case_style_components_punctuation_is_read_where_it_belongs(
    config: dict, raw: str, local: bool
) -> None:
    # Verifies: REQ-p00014-T, REQ-d00212-S
    """Which character belongs to the component and which to the template is
    one question the authority answers, and normalization may not blur it.

    A repository whose component and whose template use different characters
    is where the two can be told apart at all. Rewriting one into the other
    would claim an identifier under a spelling its author did not write --
    silently, since the rewritten string resolves.
    """
    resolver = build_resolver(config)

    normalized = resolver.normalize_ref(raw)

    assert normalized == raw, (
        f"{raw!r} came back as {normalized!r}; nothing past case and padding may be rewritten"
    )
    assert resolver.is_local_id(normalized) is local


# ---------------------------------------------------------------------------
# A federated reader reads each identifier under its owner's grammar.
# ---------------------------------------------------------------------------
#
# The two members below disagree about every part of the grammar a reference
# passes through: the namespace, whether a dash separates the level letter
# from the component, how wide the component is, the character that opens the
# assertion labels, and the character that joins two of them. Neither
# member's grammar can spell the other's identifier, so reading one under the
# invoking repository's rules is not a stricter reading -- it is no reading
# at all, and the reference comes back in whatever spelling it was written.

FED_ALPHA = _config(
    namespace="ALP",
    canonical="{namespace}-{level.letter}{component}",
    component={"style": "numeric", "digits": 5, "leading_zeros": True},
    assertions={"label_style": "uppercase", "separator": "-", "multi_separator": "+"},
)

FED_BETA = _config(
    namespace="BET",
    canonical="{namespace}-{level.letter}-{component}",
    component={"style": "numeric", "digits": 3, "leading_zeros": True},
    assertions={"label_style": "uppercase", "separator": "/", "multi_separator": "&"},
)


@pytest.mark.parametrize(
    "written, canonical",
    [
        # ALPHA's own, in a spelling only ALPHA's grammar repairs.
        ("alp-d00001-a", "ALP-d00001-A"),
        ("ALP-d00001-a+b", "ALP-d00001-A+B"),
        # BETA's own, spelled with the separators only BETA configures.
        ("bet-p-007/c", "BET-p-007/C"),
        ("BET-p-007/a&b", "BET-p-007/A&B"),
    ],
)
def test_an_identifier_reads_the_same_from_either_member_of_the_federation(
    written: str, canonical: str
) -> None:
    # Verifies: REQ-d00275-B
    """The owner's grammar settles a reference, not the invoking repository's.

    The same federation is read twice, once from each member, and the pair of
    answers is compared with the spelling the owning repository's own resolver
    produces. A reader that applied its own member's grammar would leave the
    foreign reference exactly as written -- its label uncased, its multi-
    assertion separator unread -- so the two invocations would disagree about
    what one estate calls one requirement.
    """
    alpha, beta = build_resolver(FED_ALPHA), build_resolver(FED_BETA)
    owner = next(r for r in (alpha, beta) if r.is_local_id(r.normalize_ref(written)))

    from_alpha = FederatedIdReader(alpha, [beta]).normalize(written)
    from_beta = FederatedIdReader(beta, [alpha]).normalize(written)

    assert owner.normalize_ref(written) == canonical
    assert from_alpha == canonical, (
        f"{written!r} read from the ALPHA side came back as {from_alpha!r}; "
        f"its owner spells it {canonical!r}"
    )
    assert from_beta == canonical, (
        f"{written!r} read from the BETA side came back as {from_beta!r}; "
        f"its owner spells it {canonical!r}"
    )
