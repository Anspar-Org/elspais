# Verifies: REQ-p00019-A, REQ-p00002-A
"""Tests for the split of the overloaded ``--status`` option into two
distinctly named, opposite-direction status selectors.

A single option name cannot honestly mean both "widen the counted set" and
"narrow the report", which is what ``--status`` means today depending on
which command it is attached to. The split is:

``--treat-active <S...>``
    Treat the named statuses as committed/active-like. WIDENS the counted
    set. Offered ONLY on the six coverage commands (``checks``, ``gaps``,
    ``uncovered``, ``untested``, ``unvalidated``, ``failing``), where an
    active-vs-excluded distinction exists.

``--only-status <S...>``
    Restrict the report to exactly the named statuses. NARROWS. Offered on
    all seven commands (the six coverage commands plus ``errors``).

``--status`` must no longer exist on any of those seven commands. (The
unrelated ``elspais edit --status``, which sets a requirement's Status
value, is out of scope here and is neither tested nor asserted about.)

The engine-compatible compute functions carry the same split in their
``params`` dicts: ``params["treat_active"]`` and ``params["only_status"]``
replace ``params["status"]``.
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Fixture project
# ─────────────────────────────────────────────────────────────────────────────

# require_hash is stated explicitly so the format rule definitely fires on
# every requirement in the fixture (none of them carry a hash). Changelog
# enforcement is off so the hash defect is the only violation in play.
CONFIG_TOML = """\
version = 3

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = false

[rules.format]
require_hash = true
"""

# Three requirements spanning the three role classes that matter here:
# Active (counted by default), Draft (PROVISIONAL — excluded from coverage
# by default, promotable by the widening option) and Deprecated (RETIRED —
# excluded by default and NOT promoted by naming Draft).
#
# The assertion counts deliberately differ (1 / 2 / 3). The assertion total
# is therefore a fingerprint of exactly WHICH requirements were counted,
# which is what separates "widened to include Draft" (Active + Draft) from
# "narrowed to Draft alone" — two selections that happen to share the same
# requirement count.
ACTIVE_ID = "REQ-d00001"
DRAFT_ID = "REQ-d00002"
DEPRECATED_ID = "REQ-d00003"

SPEC_MD = """\
# REQ-d00001: Active Requirement

**Level**: DEV | **Status**: Active | **Implements**: -

Body text.

## Assertions

A. The system shall do the active thing.

*End* *Active Requirement*
---

# REQ-d00002: Draft Requirement

**Level**: DEV | **Status**: Draft | **Implements**: -

Body text.

## Assertions

A. The system shall do the first draft thing.

B. The system shall do the second draft thing.

*End* *Draft Requirement*
---

# REQ-d00003: Deprecated Requirement

**Level**: DEV | **Status**: Deprecated | **Implements**: -

Body text.

## Assertions

A. The system shall do the first deprecated thing.

B. The system shall do the second deprecated thing.

C. The system shall do the third deprecated thing.

*End* *Deprecated Requirement*
---
"""


def _make_project(tmp_path: Path) -> Path:
    """Create a minimal on-disk project holding the three-status spec file."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".elspais.toml").write_text(CONFIG_TOML)
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "requirements.md").write_text(SPEC_MD)
    return tmp_path


@pytest.fixture
def project(tmp_path):
    """The on-disk project root."""
    return _make_project(tmp_path)


@pytest.fixture
def built(project):
    """(graph, config) built from the fixture project, cwd pinned to it."""
    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    old_cwd = os.getcwd()
    os.chdir(project)
    try:
        config = get_config(project / ".elspais.toml")
        graph = build_graph(
            spec_dirs=[project / "spec"],
            config_path=project / ".elspais.toml",
            repo_root=project,
            scan_code=False,
            scan_tests=False,
        )
        yield graph, config
    finally:
        os.chdir(old_cwd)


def _implemented_counts(graph, config, params: dict[str, str]) -> tuple[int, float]:
    """Run the checks compute path and return the Implemented dimension's
    (requirement count, assertion count) — the counted denominator.
    """
    from elspais.commands.health import compute_checks

    report = compute_checks(graph, config, params)
    for check in report["checks"]:
        if check["name"] == "code.implemented":
            details = check["details"]
            return details["total_requirements"], details["total_assertions"]
    raise AssertionError(
        "compute_checks produced no 'code.implemented' check; got "
        f"{[c['name'] for c in report['checks']]}"
    )


def _error_req_ids(result: dict) -> list[str]:
    """Requirement IDs carrying a format error in a compute_errors result."""
    return sorted({e["req_id"] for e in result["format_errors"]})


# ─────────────────────────────────────────────────────────────────────────────
# Surface: which options each command offers
# ─────────────────────────────────────────────────────────────────────────────

COVERAGE_ARG_CLASSES = [
    "ChecksArgs",
    "GapsArgs",
    "UncoveredArgs",
    "UntestedArgs",
    "UnvalidatedArgs",
    "FailingArgs",
]


class TestOptionSurface:
    """Pins which status selector each command's CLI dataclass exposes."""

    @pytest.mark.parametrize("class_name", COVERAGE_ARG_CLASSES)
    def test_coverage_commands_expose_both_status_options(self, class_name):
        """Every coverage command offers BOTH directions — ``treat_active``
        (widen) and ``only_status`` (narrow) — and no longer offers the
        ambiguous ``status``.
        """
        from elspais.commands import args as args_mod

        cls = getattr(args_mod, class_name)
        fields = {f.name for f in dataclasses.fields(cls)}

        assert "treat_active" in fields, (
            f"{class_name} must offer --treat-active (widening selector); fields were "
            f"{sorted(fields)}"
        )
        assert "only_status" in fields, (
            f"{class_name} must offer --only-status (narrowing selector); fields were "
            f"{sorted(fields)}"
        )
        assert "status" not in fields, (
            f"{class_name} must no longer offer the ambiguous --status; fields were "
            f"{sorted(fields)}"
        )

    def test_errors_exposes_only_status_and_not_treat_active(self):
        """``errors`` has no active-vs-excluded baseline to widen, so it
        offers the narrowing selector alone — and not ``status``.
        """
        from elspais.commands.args import ErrorsArgs

        fields = {f.name for f in dataclasses.fields(ErrorsArgs)}

        assert (
            "only_status" in fields
        ), f"ErrorsArgs must offer --only-status; fields were {sorted(fields)}"
        assert "treat_active" not in fields, (
            "ErrorsArgs must NOT offer --treat-active: errors reports every status, "
            f"so there is nothing to promote; fields were {sorted(fields)}"
        )
        assert (
            "status" not in fields
        ), f"ErrorsArgs must no longer offer --status; fields were {sorted(fields)}"


# ─────────────────────────────────────────────────────────────────────────────
# Semantics: errors — narrowing only
# ─────────────────────────────────────────────────────────────────────────────


class TestErrorsNarrowing:
    """Pins compute_errors' status selection through ``params``."""

    def test_errors_lists_every_status_by_default(self, built):
        """With no selector, ``errors`` reports format violations on every
        requirement regardless of status — a format defect is a defect on a
        Draft or Deprecated requirement too.
        """
        from elspais.commands.errors import compute_errors

        graph, config = built
        result = compute_errors(graph, config, {})

        assert _error_req_ids(result) == sorted([ACTIVE_ID, DRAFT_ID, DEPRECATED_ID]), (
            "compute_errors' default must exclude nothing; got " f"{_error_req_ids(result)}"
        )

    def test_errors_only_status_restricts_to_named(self, built):
        """``params['only_status']`` NARROWS the listing to exactly the
        named statuses — it is the sole selector ``errors`` reads.
        """
        from elspais.commands.errors import compute_errors

        graph, config = built
        result = compute_errors(graph, config, {"only_status": "Draft"})

        assert _error_req_ids(result) == [DRAFT_ID], (
            "only_status=Draft must restrict the listing to the Draft requirement; got "
            f"{_error_req_ids(result)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Semantics: coverage — widening vs narrowing
# ─────────────────────────────────────────────────────────────────────────────


class TestCoverageStatusSelectors:
    """Pins the two opposite directions on the coverage compute path."""

    def test_treat_active_widens_the_counted_set(self, built):
        """``params['treat_active']`` promotes the named status to
        active-like, so the counted denominator GROWS by exactly those
        requirements — Active alone becomes Active + Draft, while the
        still-retired Deprecated requirement stays out.
        """
        graph, config = built

        baseline = _implemented_counts(graph, config, {})
        widened = _implemented_counts(graph, config, {"treat_active": "Draft"})

        assert baseline == (1, 1), (
            "Default coverage footing must count the Active requirement only "
            f"(1 REQ, 1 assertion); got {baseline}"
        )
        assert widened == (2, 3), (
            "treat_active=Draft must add the Draft requirement to the counted set "
            f"(2 REQs, 1+2 assertions) and nothing else; got {widened}"
        )

    def test_only_status_restricts_the_counted_set(self, built):
        """``params['only_status']`` NARROWS the same compute path to
        exactly the named statuses — the Draft requirement's two assertions
        are counted and the Active requirement's is not.
        """
        graph, config = built

        narrowed = _implemented_counts(graph, config, {"only_status": "Draft"})

        assert narrowed == (1, 2), (
            "only_status=Draft must count the Draft requirement alone "
            "(1 REQ, 2 assertions) — an assertion total of 1 means the Active "
            f"requirement was counted instead; got {narrowed}"
        )

    def test_treat_active_and_only_status_are_independent(self, built):
        """The two selectors are not aliases: on the same compute path with
        the same status name, widening and narrowing must reach different
        counted sets. Wiring both option names to one implementation fails
        here.
        """
        graph, config = built

        widened = _implemented_counts(graph, config, {"treat_active": "Draft"})
        narrowed = _implemented_counts(graph, config, {"only_status": "Draft"})

        assert widened != narrowed, (
            "treat_active and only_status point in opposite directions and must not "
            f"produce the same counted set; both gave {widened}"
        )
