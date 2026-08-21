# Verifies: REQ-d00279-B
"""The viewer's own scope membership rule against the authority's answer.

REQ-d00279-B grants the viewer a second evaluator, never a second semantics: it
filters client-side over ``/api/tree-data`` so it can answer as the reader
narrows, and what it owes in return is the set ``scoped_requirements`` yields for
the same scope over the same requirements. ``/api/scope`` is where the
authority's answer can be had, so the comparison is checkable rather than assumed.

The viewer's rule is reimplemented here in Python, faithfully enough to fail when
it drifts: ``_filter-group.js.j2``'s ``matches()`` (exact membership in the
group's on-set, a group with no buttons passing), ``_nav-tree.js.j2``'s AND
across groups, its ``level`` group (row level uppercased on the wire, mapped back
to the configured key spelling case-insensitively) and its ``status`` group
(lowercased throughout), plus the requirement tab's drop of rows carrying no
level and the dedupe a DAG forces -- ``/api/tree-data`` emits one row per path.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from elspais.config import get_status_roles
from elspais.graph.factory import build_graph
from elspais.graph.scope import ReportScope, scope_to_params
from elspais.server.app import create_app
from elspais.server.state import AppState

# ---------------------------------------------------------------------------
# A repository carrying several levels AND several statuses.
#
# The canonical hht-like fixture carries one status only, so no scope written
# over it can tell a status rule from a level rule -- a reimplementation that
# ignored status entirely would agree with the authority everywhere. This
# fixture is built so that every rule under test has something to decide:
# requirements matching a level but not a status and the reverse, an exclusion
# with something to refuse, a requirement reached by two parents (so tree-data
# emits it twice), and a journey (a row carrying no level).
# ---------------------------------------------------------------------------

CONFIG = """\
version = 3

[project]
name = "scope-fixture"
namespace = "REQ"

[levels.prd]
rank = 1
letter = "p"
implements = ["prd"]

[levels.ops]
rank = 2
letter = "o"
implements = ["prd"]

[levels.dev]
rank = 3
letter = "d"
implements = ["ops", "prd"]

[id-patterns]
canonical = "{namespace}-{level.letter}{component}"

[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true

[scanning.spec]
directories = ["spec"]

[scanning.journey]
directories = ["spec"]

[rules.format]
require_hash = false
require_rationale = false
require_assertions = true
require_status = true

[rules.format.status_roles]
active = ["Active"]
provisional = ["Draft", "Proposed"]
aspirational = ["Roadmap"]
retired = ["Deprecated"]
"""

# (id, title, level, status, implements)
REQUIREMENTS: tuple[tuple[str, str, str, str, str], ...] = (
    ("REQ-p00001", "Signed Records", "PRD", "Active", ""),
    ("REQ-p00002", "Record Retention", "PRD", "Draft", ""),
    ("REQ-p00003", "Operator Training", "PRD", "Proposed", ""),
    ("REQ-o00001", "Record Store", "OPS", "Active", "REQ-p00001"),
    # Two parents: tree-data emits this requirement once per path.
    ("REQ-o00002", "Retention Sweep", "OPS", "Draft", "REQ-p00001, REQ-p00002"),
    ("REQ-o00003", "Training Register", "OPS", "Deprecated", "REQ-p00003"),
    ("REQ-d00001", "Signature Block", "DEV", "Active", "REQ-o00001"),
    ("REQ-d00002", "Sweep Schedule", "DEV", "Roadmap", "REQ-o00002"),
    ("REQ-d00003", "Register Export", "DEV", "Draft", "REQ-o00003"),
)

JOURNEY = """\
# Journeys

### JNY-SIGN-01: Operator signs a record

**Actor**: Operator | **Goal**: Sign a record

## Steps

1. The operator opens a record.
2. The operator signs it.
"""


def _spec_text(entries: Iterable[tuple[str, str, str, str, str]]) -> str:
    blocks = ["# Requirements", ""]
    for req_id, title, level, status, implements in entries:
        meta = f"**Level**: {level} | **Status**: {status}"
        if implements:
            meta += f" | **Implements**: {implements}"
        blocks.extend(
            [
                "---",
                "",
                f"### {req_id}: {title}",
                "",
                meta,
                "",
                f"The system SHALL provide {title.lower()}.",
                "",
                "## Assertions",
                "",
                f"A. The system SHALL provide {title.lower()}.",
                "",
                f"*End* *{title}*",
                "",
            ]
        )
    return "\n".join(blocks)


@pytest.fixture(scope="module")
def scope_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("scope-equivalence")
    (root / "spec").mkdir()
    (root / ".elspais.toml").write_text(CONFIG)
    (root / "spec" / "requirements.md").write_text(_spec_text(REQUIREMENTS))
    (root / "spec" / "journeys.md").write_text(JOURNEY)
    return root


@pytest.fixture(scope="module")
def served(scope_repo: Path) -> tuple[TestClient, dict[str, Any]]:
    """A serving process over the fixture, and the configuration it serves."""
    federated = build_graph(repo_root=scope_repo)
    config = federated._repos[federated._root_repo].config
    state = AppState(graph=federated, repo_root=scope_repo, config=config)
    return TestClient(create_app(state, mount_mcp=False)), config


@pytest.fixture(scope="module")
def scope_client(served) -> TestClient:
    return served[0]


@pytest.fixture(scope="module")
def repo_config(served) -> dict[str, Any]:
    return served[1]


@pytest.fixture(scope="module")
def tree_rows(scope_client: TestClient) -> list[dict[str, Any]]:
    response = scope_client.get("/api/tree-data")
    assert response.status_code == 200
    return response.json()


# ---------------------------------------------------------------------------
# The viewer's rule, in Python.
# ---------------------------------------------------------------------------


def _level_button_keys(config: Mapping[str, Any]) -> tuple[str, ...]:
    """The keys the viewer's level group carries.

    ``build_levels()`` fills that group from the configuration's level table, so
    the button key is the spelling the project wrote.
    """
    return tuple(config.get("levels") or {})


def _status_button_keys(rows: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """The keys the viewer's status group carries.

    The template lowercases each button key, and the candidates are the statuses
    the estate actually carries rather than the configured list.
    """
    return tuple(sorted({(r.get("status") or "").lower() for r in rows if r.get("status")}))


def _level_matches(row: Mapping[str, Any], on: set[str], buttons: Sequence[str]) -> bool:
    """``filterGroups.level``: matchFn, then exact membership in the on-set."""
    if not buttons:
        return True  # A group with no buttons is disabled and passes everything.
    value = (row.get("level") or "").upper()
    resolved = value
    for key in buttons:
        if key.upper() == value:
            resolved = key
            break
    return resolved in on


def _status_matches(row: Mapping[str, Any], on: set[str], buttons: Sequence[str]) -> bool:
    """``filterGroups.status``: lowercased row value against the on-set."""
    if not buttons:
        return True
    return (row.get("status") or "").lower() in on


def viewer_membership(
    rows: Sequence[Mapping[str, Any]],
    *,
    levels_on: set[str],
    statuses_on: set[str],
    level_buttons: Sequence[str],
    status_buttons: Sequence[str],
) -> set[str]:
    """The requirements the viewer shows, deciding membership for itself.

    Every group not under test is left with all of its buttons on, which is the
    viewer's unconstrained state.
    """
    selected: set[str] = set()
    seen: set[str] = set()
    for row in rows:
        node_id = row["id"]
        if node_id in seen:
            continue
        seen.add(node_id)
        # The requirement tab keeps rows carrying a level; a journey carries none.
        if not row.get("level"):
            continue
        # AND across groups -- one refusal is a refusal.
        if not _level_matches(row, levels_on, level_buttons):
            continue
        if not _status_matches(row, statuses_on, status_buttons):
            continue
        selected.add(node_id)
    return selected


def on_sets_for_scope(
    scope: ReportScope,
    config: Mapping[str, Any],
    level_buttons: Sequence[str],
    status_buttons: Sequence[str],
) -> tuple[set[str], set[str]]:
    """The button state a reader would leave behind having narrowed to ``scope``.

    A property the scope requires turns everything else off; a property it
    refuses turns those buttons off and leaves the rest on. Where a named status
    stands for its role, the reader turns on every status sharing that role --
    which is what the ``status_roles`` mapping shipped into the template is for.
    """
    roles = get_status_roles(dict(config))

    def _required(buttons: Sequence[str], wanted: Sequence[str], widen: bool) -> set[str]:
        folded = {v.strip().lower() for v in wanted}
        if widen:
            targets = {roles.role_of(v.strip()) for v in wanted}
            folded |= {b for b in buttons if roles.role_of(b) in targets}
        return {b for b in buttons if b.lower() in folded}

    def _refused(buttons: Sequence[str], unwanted: Sequence[str], widen: bool) -> set[str]:
        return set(buttons) - _required(buttons, unwanted, widen)

    levels_on = set(level_buttons)
    if scope.include.get("level"):
        levels_on = _required(level_buttons, scope.include["level"], False)
    if scope.exclude.get("level"):
        levels_on &= _refused(level_buttons, scope.exclude["level"], False)

    widen = scope.match_status_roles
    statuses_on = set(status_buttons)
    if scope.include.get("status"):
        statuses_on = _required(status_buttons, scope.include["status"], widen)
    if scope.exclude.get("status"):
        statuses_on &= _refused(status_buttons, scope.exclude["status"], widen)

    return levels_on, statuses_on


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


# Verifies: REQ-d00279-B
def test_authority_and_viewer_judge_the_same_requirements(tree_rows, scope_client):
    """The obligation is over the SAME requirement set, so first check it is.

    A membership comparison between two populations proves nothing: were the
    viewer never shown a requirement, it could hide it and still agree.
    """
    response = scope_client.get("/api/scope")
    assert response.status_code == 200
    authority = response.json()

    shown = {r["id"] for r in tree_rows if r.get("level")}
    assert shown == set(authority["ids"])
    assert authority["population"] == len(shown)
    assert len(tree_rows) > len(shown), "fixture must exercise dedupe and the journey drop"


SCOPES: dict[str, ReportScope] = {
    "one-level": ReportScope(include={"level": ("prd",)}),
    "several-levels": ReportScope(include={"level": ("ops", "dev")}),
    "one-status": ReportScope(include={"status": ("Draft",)}),
    "several-statuses": ReportScope(include={"status": ("Draft", "Active")}),
    "status-excluded": ReportScope(exclude={"status": ("Draft",)}),
    "level-excluded": ReportScope(exclude={"level": ("prd",)}),
    "level-and-status": ReportScope(include={"level": ("ops",), "status": ("Draft",)}),
    "level-included-status-excluded": ReportScope(
        include={"level": ("dev", "ops")}, exclude={"status": ("Deprecated", "Roadmap")}
    ),
    "status-stands-for-its-role": ReportScope(
        include={"status": ("Draft",)}, match_status_roles=True
    ),
    "selects-nothing": ReportScope(include={"level": ("prd",), "status": ("Deprecated",)}),
    "unconstrained": ReportScope(),
}


# Verifies: REQ-d00279-B
@pytest.mark.parametrize("case", sorted(SCOPES))
def test_viewer_rule_yields_the_authoritys_membership(case, scope_client, tree_rows, repo_config):
    """A second evaluator, never a second semantics."""
    scope = SCOPES[case]

    response = scope_client.get("/api/scope", params=scope_to_params(scope))
    assert response.status_code == 200
    authority = set(response.json()["ids"])

    level_buttons = _level_button_keys(repo_config)
    status_buttons = _status_button_keys(tree_rows)
    levels_on, statuses_on = on_sets_for_scope(scope, repo_config, level_buttons, status_buttons)
    viewer = viewer_membership(
        tree_rows,
        levels_on=levels_on,
        statuses_on=statuses_on,
        level_buttons=level_buttons,
        status_buttons=status_buttons,
    )

    assert viewer == authority


# Verifies: REQ-d00279-B
def test_selecting_nothing_is_an_answer_not_an_empty_estate(scope_client):
    """REQ-d00278-L: an empty answer over a populated estate says so.

    The viewer showing an empty tree and the authority reporting nothing selected
    have to be the same event, or a reader takes an empty report for a report of
    nothing to report.
    """
    scope = SCOPES["selects-nothing"]
    body = scope_client.get("/api/scope", params=scope_to_params(scope)).json()
    assert body["ids"] == []
    assert body["population"] > 0
    assert body["selected_nothing"] is True


# Verifies: REQ-d00279-B
def test_the_scopes_under_test_divide_the_estate(scope_client, tree_rows):
    """Guard the comparison above: a scope selecting all or none decides nothing.

    Were every scope here to select the whole estate, the equivalence would hold
    for a rule that read no property at all.
    """
    population = len({r["id"] for r in tree_rows if r.get("level")})
    sizes = {
        case: len(scope_client.get("/api/scope", params=scope_to_params(scope)).json()["ids"])
        for case, scope in SCOPES.items()
        if case not in ("unconstrained", "selects-nothing")
    }
    partial = {c: n for c, n in sizes.items() if 0 < n < population}
    assert partial == sizes, f"scopes deciding nothing: {set(sizes) - set(partial)}"
