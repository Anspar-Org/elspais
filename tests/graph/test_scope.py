# Verifies: REQ-d00279-A
"""The report-scope vocabulary and the one membership judgement (REQ-d00278).

Estates are built through ``GraphBuilder`` and wrapped in a real
``FederatedGraph``: the per-member resolution of REQ-d00278-I is only
observable where two members really do carry different vocabularies, and a
stand-in for the ownership map would be asserting against the stand-in.
"""

from pathlib import Path

import pytest

from elspais.config import config_defaults
from elspais.graph import scope as scope_mod
from elspais.graph.builder import GraphBuilder
from elspais.graph.federated import FederatedGraph, RepoEntry
from elspais.graph.GraphNode import NodeKind
from elspais.graph.parsers import ParsedContent
from elspais.graph.scope import (
    SCOPE_PROPERTIES,
    SCOPE_VALUE_SEPARATOR,
    ReportScope,
    ScopeProperty,
    carried_values,
    describe_scope,
    resolve_scope,
    satisfies,
    scope_from_params,
    scope_to_params,
    scoped_requirements,
)
from tests.core.graph_test_helpers import grammar_for

# ── Estate construction ──────────────────────────────────────────────────────


def _config(
    name: str,
    namespace: str,
    levels: tuple[str, ...],
    status_roles: dict[str, list[str]],
) -> dict:
    """A member's configuration, carrying its own levels and its own statuses."""
    cfg = config_defaults()
    cfg["project"] = {**cfg.get("project", {}), "name": name, "namespace": namespace}
    cfg["levels"] = {
        key: {"rank": rank, "letter": key[0], "implements": []}
        for rank, key in enumerate(levels, start=1)
    }
    rules = {**cfg.get("rules", {})}
    rules["format"] = {**rules.get("format", {}), "status_roles": status_roles}
    cfg["rules"] = rules
    return cfg


def _trace_graph(namespace: str, reqs: tuple[tuple[str, str, str], ...]):
    """A TraceGraph holding bare requirements carrying a level and a status.

    Built through GraphBuilder rather than ``make_requirement``, whose level
    validation is PRD/OPS/DEV-only -- these estates carry custom levels.
    """
    builder = GraphBuilder(namespace=namespace, resolver=grammar_for(namespace))
    for req_id, level, status in reqs:
        builder.add_parsed_content(
            ParsedContent(
                content_type="requirement",
                start_line=1,
                end_line=2,
                raw_text="",
                parsed_data={
                    "id": req_id,
                    "title": req_id,
                    "level": level,
                    "status": status,
                    "assertions": [],
                },
            )
        )
    return builder.build()


def _member(
    name: str,
    namespace: str,
    levels: tuple[str, ...],
    status_roles: dict[str, list[str]],
    reqs: tuple[tuple[str, str, str], ...],
) -> RepoEntry:
    return RepoEntry(
        name=name,
        graph=_trace_graph(namespace, reqs),
        config=_config(name, namespace, levels, status_roles),
        repo_root=Path(f"/tmp/{name}"),
    )


def _federation(*entries: RepoEntry) -> FederatedGraph:
    return FederatedGraph(list(entries), root_repo=entries[0].name)


ROOT_ROLES = {
    "active": ["Active"],
    "provisional": ["Draft", "Proposed"],
    "retired": ["Retired"],
}

# One estate, one member. REQ-d00003 carries a status the configuration never
# lists, which is what REQ-d00278-H is about.
ESTATE_REQS = (
    ("REQ-p00001", "prd", "Active"),
    ("REQ-o00001", "ops", "Active"),
    ("REQ-d00001", "dev", "Draft"),
    ("REQ-d00002", "dev", "Proposed"),
    ("REQ-d00003", "dev", "Bespoke"),
    ("REQ-d00004", "dev", "Active"),
)
ALL_DEV = {"REQ-d00001", "REQ-d00002", "REQ-d00003", "REQ-d00004"}


@pytest.fixture(scope="module")
def estate_config() -> dict:
    return _config("host", "REQ", ("prd", "ops", "dev"), ROOT_ROLES)


@pytest.fixture(scope="module")
def estate() -> FederatedGraph:
    return _federation(_member("host", "REQ", ("prd", "ops", "dev"), ROOT_ROLES, ESTATE_REQS))


@pytest.fixture(scope="module")
def empty_estate() -> FederatedGraph:
    return _federation(_member("host", "REQ", ("prd", "ops", "dev"), ROOT_ROLES, ()))


@pytest.fixture(scope="module")
def federation() -> FederatedGraph:
    """Two members whose levels and statuses have nothing in common."""
    root = _member(
        "root",
        "REQ",
        ("prd", "dev"),
        {"active": ["Active"], "provisional": ["Draft"]},
        (("REQ-p00001", "prd", "Active"), ("REQ-d00001", "dev", "Draft")),
    )
    assoc = _member(
        "assoc",
        "FDA",
        ("safety", "quality"),
        {"active": ["Approved"], "provisional": ["Pending"]},
        (("FDA-s00001", "safety", "Approved"), ("FDA-q00001", "quality", "Pending")),
    )
    return _federation(root, assoc)


def _ids(graph, scope, config=None) -> set[str]:
    return set(scoped_requirements(graph, scope, config).ids)


# ── The properties a scope selects on ────────────────────────────────────────


class TestSelectableProperties:
    # Verifies: REQ-d00278-A+B
    @pytest.mark.parametrize(
        ("prop", "values", "expected"),
        [
            ("level", ("dev",), ALL_DEV),
            ("level", ("prd",), {"REQ-p00001"}),
            ("status", ("Active",), {"REQ-p00001", "REQ-o00001", "REQ-d00004"}),
            ("status", ("Draft",), {"REQ-d00001"}),
        ],
    )
    def test_level_and_status_each_select(self, estate, estate_config, prop, values, expected):
        """Level (A) and status (B) are both properties a scope selects on."""
        assert _ids(estate, ReportScope(include={prop: values}), estate_config) == expected

    # Verifies: REQ-d00278-C
    @pytest.mark.parametrize(
        ("include", "exclude", "expected"),
        [
            ({}, {"level": ("dev",)}, {"REQ-p00001", "REQ-o00001"}),
            (
                {"level": ("dev",), "status": ("Draft", "Proposed")},
                {},
                {"REQ-d00001", "REQ-d00002"},
            ),
            (
                {"level": ("prd", "dev")},
                {"status": ("Bespoke",)},
                {"REQ-p00001", "REQ-d00001", "REQ-d00002", "REQ-d00004"},
            ),
            ({"status": ("Active",)}, {"level": ("prd", "ops")}, {"REQ-d00004"}),
            ({"level": ("dev",)}, {"level": ("dev",)}, set()),
        ],
    )
    def test_any_combination_of_properties_and_values_is_expressible(
        self, estate, estate_config, include, exclude, expected
    ):
        """Properties and values combine freely, in either place."""
        scope = ReportScope(include=include, exclude=exclude)
        assert _ids(estate, scope, estate_config) == expected

    def test_a_further_property_does_not_move_an_existing_scope(
        self, estate, estate_config, monkeypatch
    ):
        """Admitting a property must cost only the scopes that name it."""
        level_only = ReportScope(include={"level": ("dev",)})
        before = _ids(estate, level_only, estate_config)

        monkeypatch.setitem(
            scope_mod.SCOPE_PROPERTIES,
            "owner",
            ScopeProperty(
                name="owner",
                read=lambda node: node.get_field("owner") or "",
                configured=lambda config: {str(o) for o in (config or {}).get("owners", ())},
            ),
        )
        # The property really is admitted now -- a scope naming it is read
        # against its vocabulary rather than refused as no property at all.
        named = resolve_scope(
            ReportScope(include={"owner": ("platform",)}), estate_config, repo="host"
        )
        assert [(u.prop, u.value) for u in named.unadmitted] == [("owner", "platform")]
        assert "owner" in carried_values(estate.nodes_by_kind(NodeKind.REQUIREMENT))

        assert _ids(estate, level_only, estate_config) == before


# ── What a requirement must and must not carry ───────────────────────────────


class TestMembership:
    # Verifies: REQ-d00278-D
    def test_every_named_property_must_be_satisfied(self, estate, estate_config):
        """Properties named together are conditions met at once, not alternatives."""
        by_level = ReportScope(include={"level": ("dev",)})
        both = ReportScope(include={"level": ("dev",), "status": ("Active",)})
        assert "REQ-d00001" in _ids(estate, by_level, estate_config)
        # REQ-d00001 is dev, but Draft: the second property refuses it, and the
        # answer is not the union of the two properties either.
        assert _ids(estate, both, estate_config) == {"REQ-d00004"}

    # Verifies: REQ-d00278-E
    def test_any_required_value_satisfies_its_property(self, estate, estate_config):
        """Values named for one property are alternatives."""
        scope = ReportScope(include={"status": ("Draft", "Proposed", "Bespoke")})
        assert _ids(estate, scope, estate_config) == {
            "REQ-d00001",
            "REQ-d00002",
            "REQ-d00003",
        }

    # Verifies: REQ-d00278-F
    @pytest.mark.parametrize(
        ("include", "exclude", "expected"),
        [
            # An exclusion alone refuses what carries the value.
            ({"level": ("dev",)}, {"status": ("Draft",)}, ALL_DEV - {"REQ-d00001"}),
            (
                {"level": ("dev",)},
                {"status": ("Draft", "Bespoke")},
                {"REQ-d00002", "REQ-d00004"},
            ),
            # Where one property both requires and refuses a value, the
            # refusal decides the overlap.
            (
                {"status": ("Draft", "Proposed")},
                {"status": ("Draft",)},
                {"REQ-d00002"},
            ),
        ],
    )
    def test_an_excluded_value_refuses_the_requirement(
        self, estate, estate_config, include, exclude, expected
    ):
        scope = ReportScope(include=include, exclude=exclude)
        assert _ids(estate, scope, estate_config) == expected

    # Verifies: REQ-d00279-A
    def test_an_absent_scope_selects_the_whole_population(self, estate, estate_config):
        """A caller need not branch on whether a scope was given."""
        whole = {req_id for req_id, _lv, _st in ESTATE_REQS}
        for scope in (None, ReportScope(), ReportScope(include={"level": ()})):
            result = scoped_requirements(estate, scope, estate_config)
            assert set(result.ids) == whole
            assert result.population == len(whole)
            assert result.unadmitted == ()


# ── Vocabulary ───────────────────────────────────────────────────────────────


class TestVocabulary:
    # Verifies: REQ-d00278-G
    @pytest.mark.parametrize(
        ("match_roles", "expected"),
        [
            (False, {"REQ-d00001"}),
            (True, {"REQ-d00001", "REQ-d00002"}),
        ],
    )
    def test_a_named_status_can_stand_for_its_role(
        self, estate, estate_config, match_roles, expected
    ):
        """Draft and Proposed are both provisional in this project's mapping."""
        scope = ReportScope(include={"status": ("Draft",)}, match_status_roles=match_roles)
        assert _ids(estate, scope, estate_config) == expected

    # Verifies: REQ-d00278-G
    def test_role_widening_reaches_only_the_role_that_was_named(self, estate, estate_config):
        """Widening a status to its role does not widen it to every status."""
        scope = ReportScope(include={"status": ("Active",)}, match_status_roles=True)
        assert _ids(estate, scope, estate_config) == {
            "REQ-p00001",
            "REQ-o00001",
            "REQ-d00004",
        }

    # Verifies: REQ-d00278-H
    def test_a_carried_value_the_configuration_never_listed_is_nameable(
        self, estate, estate_config
    ):
        """The vocabulary is what is configured together with what is carried."""
        assert "Bespoke" not in scope_mod._configured_statuses(estate_config)
        scope = ReportScope(include={"status": ("Bespoke",)})
        result = scoped_requirements(estate, scope, estate_config)
        assert set(result.ids) == {"REQ-d00003"}
        assert result.unadmitted == ()

    # Verifies: REQ-d00278-H
    def test_a_value_neither_configured_nor_carried_is_not_nameable(self, estate_config):
        """The union has two halves: without the carried half the name is unknown."""
        scope = ReportScope(include={"status": ("Bespoke",)})
        unresolved = resolve_scope(scope, estate_config, carried=None, repo="host")
        assert [u.value for u in unresolved.unadmitted] == ["Bespoke"]

        resolved = resolve_scope(scope, estate_config, carried={"status": {"Bespoke"}}, repo="host")
        assert resolved.unadmitted == ()
        assert resolved.include["status"] == frozenset({"bespoke"})

    # Verifies: REQ-d00278-H
    @pytest.mark.parametrize(
        ("prop", "value", "expected"),
        [
            ("level", "DEV", ALL_DEV),
            ("level", "Dev", ALL_DEV),
            ("status", "draft", {"REQ-d00001"}),
            ("status", "BESPOKE", {"REQ-d00003"}),
        ],
    )
    def test_a_spelling_differing_only_in_case_still_resolves(
        self, estate, estate_config, prop, value, expected
    ):
        scope = ReportScope(include={prop: (value,)})
        result = scoped_requirements(estate, scope, estate_config)
        assert result.unadmitted == ()
        assert set(result.ids) == expected


# ── Per-member resolution ────────────────────────────────────────────────────


class TestPerMemberResolution:
    # Verifies: REQ-d00278-I
    @pytest.mark.parametrize(
        ("prop", "value", "expected_ids", "owner", "stranger", "stranger_vocab"),
        [
            ("level", "dev", {"REQ-d00001"}, "root", "assoc", ("quality", "safety")),
            ("level", "safety", {"FDA-s00001"}, "assoc", "root", ("dev", "prd")),
            ("status", "Draft", {"REQ-d00001"}, "root", "assoc", ("Approved", "Pending")),
            ("status", "Approved", {"FDA-s00001"}, "assoc", "root", ("Active", "Draft")),
        ],
    )
    def test_a_name_is_read_only_in_the_owning_members_vocabulary(
        self, federation, prop, value, expected_ids, owner, stranger, stranger_vocab
    ):
        """No member's configuration decides what another member's requirements are.

        The vocabulary reported against the member that does not admit the name
        is the assertion: a merged vocabulary would have admitted it there too.
        """
        result = scoped_requirements(federation, ReportScope(include={prop: (value,)}))
        assert set(result.ids) == expected_ids
        assert [(u.repo, u.value, u.vocabulary) for u in result.unadmitted] == [
            (stranger, value, stranger_vocab)
        ]
        assert owner not in {u.repo for u in result.unadmitted}

    # Verifies: REQ-d00278-I
    def test_role_widening_uses_the_owning_members_roles(self, federation):
        """Each member assigns its own statuses to roles."""
        scope = ReportScope(include={"status": ("Draft", "Approved")}, match_status_roles=True)
        result = scoped_requirements(federation, scope)
        # Draft is provisional in root and unknown in assoc; Approved is active
        # in assoc and unknown in root. Neither widening crosses the boundary,
        # so Pending (assoc's provisional) is not reached by root's Draft.
        assert set(result.ids) == {"REQ-d00001", "FDA-s00001"}


# ── Honesty about what a scope did not select ────────────────────────────────


class TestUnadmittedNames:
    # Verifies: REQ-d00278-J
    def test_an_unadmitted_value_is_reported_with_its_vocabulary(self, estate, estate_config):
        scope = ReportScope(include={"status": ("Shipped",)})
        result = scoped_requirements(estate, scope, estate_config)
        assert len(result.unadmitted) == 1
        reported = result.unadmitted[0]
        assert (reported.prop, reported.value, reported.repo) == ("status", "Shipped", "host")
        assert set(reported.vocabulary) == {
            "Active",
            "Draft",
            "Proposed",
            "Retired",
            "Bespoke",
        }
        assert "Shipped" in reported.describe()
        assert "Draft" in reported.describe()

    # Verifies: REQ-d00278-J
    def test_an_unadmitted_property_reports_the_selectable_properties(self, estate, estate_config):
        result = scoped_requirements(
            estate, ReportScope(include={"phase": ("beta",)}), estate_config
        )
        assert len(result.unadmitted) == 1
        reported = result.unadmitted[0]
        assert reported.prop == "phase"
        assert reported.vocabulary == tuple(sorted(SCOPE_PROPERTIES))
        assert "phase" in reported.describe()

    # Verifies: REQ-d00278-J
    def test_an_excluded_value_the_vocabulary_refuses_is_reported_too(self, estate, estate_config):
        scope = ReportScope(include={"level": ("dev",)}, exclude={"status": ("Shipped",)})
        result = scoped_requirements(estate, scope, estate_config)
        assert [(u.prop, u.value) for u in result.unadmitted] == [("status", "Shipped")]

    # Verifies: REQ-d00278-K
    def test_an_unadmitted_value_selects_nothing_rather_than_everything(
        self, estate, estate_config
    ):
        """The regression this guards: dropping the constraint hands back the estate."""
        scope = ReportScope(include={"status": ("Shipped",)})
        resolved = resolve_scope(
            scope,
            estate_config,
            carried=carried_values(estate.nodes_by_kind(NodeKind.REQUIREMENT)),
            repo="host",
        )
        assert resolved.include["status"] == frozenset()
        assert _ids(estate, scope, estate_config) == set()

    # Verifies: REQ-d00278-K
    def test_an_unadmitted_value_leaves_the_rest_of_the_scope_selecting(self, federation):
        """A level only one member defines is a legitimate cross-member scope."""
        result = scoped_requirements(federation, ReportScope(include={"level": ("dev",)}))
        # assoc admits no 'dev' and so contributes nothing -- but it must not
        # contribute everything, and root must go on selecting.
        assert set(result.ids) == {"REQ-d00001"}
        assert {u.repo for u in result.unadmitted} == {"assoc"}

    # Verifies: REQ-d00278-K
    def test_an_unadmitted_property_selects_nothing(self, estate, estate_config):
        """A requirement cannot be shown to carry what nothing can read."""
        scope = ReportScope(include={"phase": ("beta",), "level": ("dev",)})
        resolved = resolve_scope(scope, estate_config, repo="host")
        assert resolved.selects_nothing is True
        node = next(iter(estate.nodes_by_kind(NodeKind.REQUIREMENT)))
        assert satisfies(node, resolved) is False
        assert _ids(estate, scope, estate_config) == set()

    # Verifies: REQ-d00278-K
    def test_an_unadmitted_exclusion_refuses_nothing(self, estate, estate_config):
        """Refusing a value nothing carries is what omitting it already means."""
        scope = ReportScope(include={"level": ("dev",)}, exclude={"status": ("Shipped",)})
        assert _ids(estate, scope, estate_config) == ALL_DEV

    # Verifies: REQ-d00278-L
    def test_an_empty_selection_is_told_apart_from_an_empty_estate(
        self, estate, empty_estate, estate_config
    ):
        scope = ReportScope(include={"level": ("prd",), "status": ("Draft",)})

        populated = scoped_requirements(estate, scope, estate_config)
        assert populated.ids == frozenset()
        assert populated.population == len(ESTATE_REQS)
        assert populated.selected_nothing_from_a_populated_estate is True

        barren = scoped_requirements(empty_estate, scope, estate_config)
        assert barren.ids == frozenset()
        assert barren.population == 0
        assert barren.selected_nothing_from_a_populated_estate is False

    # Verifies: REQ-d00278-L
    def test_an_answering_scope_is_not_reported_as_an_empty_selection(self, estate, estate_config):
        result = scoped_requirements(
            estate, ReportScope(include={"level": ("dev",)}), estate_config
        )
        assert result.selected_nothing_from_a_populated_estate is False
        assert result.scope.include == {"level": ("dev",)}


# ── Disclosure and transport ─────────────────────────────────────────────────


class TestDescribeScope:
    # Verifies: REQ-p00084-D
    @pytest.mark.parametrize("scope", [None, ReportScope(), ReportScope(include={"level": ()})])
    def test_an_unconstrained_scope_describes_the_whole_estate(self, scope):
        assert describe_scope(scope) == "every requirement"

    # Verifies: REQ-p00084-D
    def test_a_scope_describes_the_properties_and_values_it_names(self):
        described = describe_scope(
            ReportScope(
                include={"level": ("dev", "ops")},
                exclude={"status": ("Retired",)},
            )
        )
        # "excluding", not "not ... or not ...": the refused values are all
        # refused at once, and a disjunction of negations would describe a
        # condition every requirement meets.
        for fragment in ("level", "dev", "ops", "status", "Retired", "excluding"):
            assert fragment in described
        # Properties are described in a stable order, whatever order they were
        # written in, so two spellings of one scope disclose alike.
        assert described.index("level") < described.index("status")

    # Verifies: REQ-p00084-D
    def test_the_role_widening_is_disclosed(self):
        scope = ReportScope(include={"status": ("Draft",)}, match_status_roles=True)
        assert "role" in describe_scope(scope)
        assert "role" not in describe_scope(ReportScope(include={"status": ("Draft",)}))


class TestScopeParams:
    # Verifies: REQ-d00279-C
    @pytest.mark.parametrize(
        "scope",
        [
            ReportScope(include={"level": ("dev",)}),
            ReportScope(include={"level": ("dev", "ops"), "status": ("Draft",)}),
            ReportScope(include={"level": ("dev",)}, exclude={"status": ("Retired", "Draft")}),
            ReportScope(exclude={"level": ("prd",)}),
            ReportScope(include={"status": ("Draft",)}, match_status_roles=True),
            ReportScope(
                include={"level": ("dev",)},
                exclude={"status": ("Retired",)},
                match_status_roles=True,
            ),
        ],
    )
    def test_a_scope_survives_the_trip_to_a_serving_process(self, scope):
        rebuilt = scope_from_params(scope_to_params(scope))
        assert rebuilt is not None
        assert {k: tuple(v) for k, v in rebuilt.include.items()} == dict(scope.include)
        assert {k: tuple(v) for k, v in rebuilt.exclude.items()} == dict(scope.exclude)
        assert rebuilt.match_status_roles == scope.match_status_roles

    # Verifies: REQ-d00279-C
    def test_a_transported_scope_selects_what_it_selected(self, estate, estate_config):
        scope = ReportScope(
            include={"level": ("dev",), "status": ("Draft", "Proposed")},
            exclude={"status": ("Proposed",)},
        )
        rebuilt = scope_from_params(scope_to_params(scope))
        assert _ids(estate, rebuilt, estate_config) == _ids(estate, scope, estate_config)

    # Verifies: REQ-d00279-C
    @pytest.mark.parametrize("scope", [None, ReportScope(), ReportScope(exclude={"level": ()})])
    def test_an_unconstrained_scope_carries_no_parameters(self, scope):
        assert scope_to_params(scope) == {}
        assert scope_from_params({}) is None

    # Verifies: REQ-d00279-C
    def test_parameters_a_scope_did_not_write_are_left_alone(self):
        params = {
            "format": "json",
            "scope_level": f"dev{SCOPE_VALUE_SEPARATOR}ops",
            "scope_not_status": "Retired",
            "scope_status": "",
        }
        rebuilt = scope_from_params(params)
        assert rebuilt is not None
        assert dict(rebuilt.include) == {"level": ("dev", "ops")}
        assert dict(rebuilt.exclude) == {"status": ("Retired",)}
