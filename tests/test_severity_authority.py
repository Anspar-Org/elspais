"""The one severity vocabulary and the one authority that applies it.

Validates REQ-d00212-U+V: the values a severity setting admits are fixed by
the schema, and a value outside them is refused when the configuration is
read rather than surviving to decide nothing at report time.

Validates REQ-d00212-P: the severity of every health check is configurable,
under one convention -- a setting of the check's own where it has one, and
the general ``[rules.severity]`` table keyed by check name where it does not.

Validates REQ-d00285-D+E: every finding falls in a category whose severity a
project can configure, and one authority (`severity_for`) decides a finding's
severity from that category.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from elspais.commands.health import HealthCheck, check_term_duplicates, check_unlinked_code
from elspais.config import CURRENT_CONFIG_VERSION, load_config
from elspais.utilities.findings import REGISTRY, SEVERITY_VALUES, severity_for

_MINIMAL_PROJECT = '[project]\nname = "test"\nnamespace = "REQ"\n'


def _write_config(tmp_path: Path, body: str, version: int = CURRENT_CONFIG_VERSION) -> Path:
    path = tmp_path / ".elspais.toml"
    path.write_text(f"version = {version}\n\n{_MINIMAL_PROJECT}\n{body}", encoding="utf-8")
    return path


# =============================================================================
# The vocabulary the schema admits
# =============================================================================


class TestAdmittedSeverityValues:
    """REQ-d00212-U/V: four words, fixed by the schema."""

    # Verifies: REQ-d00212-V
    @pytest.mark.parametrize(
        "body",
        [
            '[rules.references]\nmalformed = "banana"\n',
            '[terms.severity]\nduplicate = "banana"\n',
            '[rules.coverage.tested]\nfull = "banana"\n',
            '[rules.format]\nno_assertions_severity = "banana"\n',
            '[rules.severity]\n"spec.parseable" = "banana"\n',
        ],
        ids=["references", "terms", "coverage-tier", "format", "general-table"],
    )
    def test_REQ_d00212_V_an_unadmitted_value_is_refused_at_read_time(
        self, tmp_path: Path, body: str
    ) -> None:
        """A severity nothing can act on is refused where it was written.

        Accepted and ignored, the project would believe it had said something
        about how loudly a condition is reported and be told nothing when the
        condition never moved.
        """
        with pytest.raises(ValidationError):
            load_config(_write_config(tmp_path, body))

    # Verifies: REQ-d00212-U
    @pytest.mark.parametrize("value", SEVERITY_VALUES)
    def test_REQ_d00212_U_every_admitted_value_loads_at_a_severity_setting(
        self, tmp_path: Path, value: str
    ) -> None:
        """The four words are admitted everywhere a severity is written -- the
        named settings and the general table read the same vocabulary, so a
        project does not have to learn which word each place accepts."""
        config = load_config(
            _write_config(
                tmp_path,
                f'[rules.references]\nmalformed = "{value}"\n'
                f'[terms.severity]\nduplicate = "{value}"\n'
                f'[rules.coverage.tested]\nfull = "{value}"\n'
                f'[rules.severity]\n"spec.parseable" = "{value}"\n',
            )
        )

        assert config["rules"]["references"]["malformed"] == value
        assert config["terms"]["severity"]["duplicate"] == value
        assert config["rules"]["coverage"]["tested"]["full"] == value
        assert config["rules"]["severity"]["spec.parseable"] == value

    # Verifies: REQ-d00212-U
    def test_REQ_d00212_U_the_retired_word_is_no_longer_admitted(self, tmp_path: Path) -> None:
        """``ok`` named a fifth behaviour -- pass the check but list the
        findings anyway -- that no longer exists. A v5 config writing it is
        refused rather than quietly read as one of the four."""
        with pytest.raises(ValidationError):
            load_config(_write_config(tmp_path, '[rules.references]\nmalformed = "ok"\n'))


# =============================================================================
# The migration off the retired word
# =============================================================================


class TestMigrationOfTheRetiredWord:
    """REQ-d00212-U: an existing configuration written `ok` still loads."""

    # Verifies: REQ-d00212-U
    def test_REQ_d00212_U_ok_is_rewritten_to_off_and_the_version_moves(
        self, tmp_path: Path
    ) -> None:
        """A v4 configuration is carried forward: every severity setting
        written ``ok`` reads ``off``, at a named setting and at a coverage
        tier alike, and the file is left at the current version."""
        config = load_config(
            _write_config(
                tmp_path,
                '[rules.references]\nmalformed = "ok"\nunknown_requirement = "error"\n'
                '[rules.coverage.tested]\nfull = "ok"\npartial = "warning"\n',
                version=4,
            )
        )

        assert config["version"] == CURRENT_CONFIG_VERSION
        assert config["rules"]["references"]["malformed"] == "off"
        assert config["rules"]["coverage"]["tested"]["full"] == "off"
        # Settings that never said "ok" are left exactly as written.
        assert config["rules"]["references"]["unknown_requirement"] == "error"
        assert config["rules"]["coverage"]["tested"]["partial"] == "warning"

    # Verifies: REQ-d00212-U
    def test_REQ_d00212_U_a_word_that_is_not_a_severity_is_left_alone(self, tmp_path: Path) -> None:
        """The migration rewrites the enumerated severity settings and nothing
        else. A blind walk would rewrite any string reading "ok" -- a project
        name, a status word -- and corrupt settings it knows nothing about."""
        path = tmp_path / ".elspais.toml"
        path.write_text(
            "version = 4\n\n"
            "[project]\n"
            'name = "ok"\n'
            'namespace = "REQ"\n'
            "\n"
            "[rules.format]\n"
            'status_roles = { active = ["ok"] }\n'
            "\n"
            "[rules.references]\n"
            'malformed = "ok"\n',
            encoding="utf-8",
        )

        config = load_config(path)

        assert config["project"]["name"] == "ok"
        assert config["rules"]["format"]["status_roles"]["active"] == ["ok"]
        # ...while the setting that IS a severity did move.
        assert config["rules"]["references"]["malformed"] == "off"


# =============================================================================
# The one authority
# =============================================================================


class TestSeverityFor:
    """REQ-d00285-E: one function decides a finding's severity."""

    # Verifies: REQ-d00285-E
    @pytest.mark.parametrize(
        "check_name,configured,expected_default,expected_configured",
        [
            # A check with a legacy setting of its own.
            (
                "terms.duplicates",
                {"terms": {"severity": {"duplicate": "warning"}}},
                "error",
                "warning",
            ),
            # A check configured under the general table.
            (
                "spec.parseable",
                {"rules": {"severity": {"spec.parseable": "error"}}},
                "warning",
                "error",
            ),
        ],
        ids=["legacy-named-path", "general-table-path"],
    )
    def test_REQ_d00285_E_the_registered_default_stands_until_the_config_speaks(
        self,
        check_name: str,
        configured: dict[str, Any],
        expected_default: str,
        expected_configured: str,
    ) -> None:
        """Both kinds of check are answered by the same call: the registered
        default where the project says nothing, the written value where it
        does. The two differ, so the last assertion can only pass because the
        path the registry names was the one read."""
        assert severity_for(check_name, None) == expected_default
        assert severity_for(check_name, {}) == expected_default

        assert expected_configured != expected_default
        assert severity_for(check_name, configured) == expected_configured

    # Verifies: REQ-d00285-E
    def test_REQ_d00285_E_a_setting_belonging_to_another_check_moves_nothing(self) -> None:
        """A check reads ONE path. Writing a severity at a path some other
        check owns must not reach this one, or a project would silence a
        condition it never named."""
        config = {"terms": {"severity": {"undefined": "off"}}}

        assert severity_for("terms.duplicates", config) == REGISTRY["terms.duplicates"].default
        assert severity_for("terms.undefined", config) == "off"

    # Verifies: REQ-d00285-D
    def test_REQ_d00285_D_an_unregistered_check_name_is_refused(self) -> None:
        """A finding outside the registry is a finding whose severity no
        project can configure, so asking for one is an error rather than a
        quiet default."""
        with pytest.raises(KeyError, match="not a registered check"):
            severity_for("spec.invented_condition", {})

    # Verifies: REQ-d00212-P
    def test_REQ_d00212_P_every_registered_check_reads_one_reachable_path(self) -> None:
        """One convention: a check either owns a named setting or is keyed by
        its own name under ``[rules.severity]`` -- never both, and never
        neither. A registered default outside the vocabulary would be a
        severity the resolver hands back that the schema would refuse."""
        for name, rule in REGISTRY.items():
            assert rule.default in SEVERITY_VALUES, f"{name} defaults to {rule.default!r}"
            assert rule.path, f"{name} names no configuration path"
            general = rule.path[:2] == ("rules", "severity")
            assert general is (rule.path == ("rules", "severity", name)), (
                f"{name} is keyed under [rules.severity] by something other than its name"
            )


# =============================================================================
# `off` withholds the condition
# =============================================================================


class TestOffProducesASkippedCheck:
    """REQ-d00212-P: a check configured off reports as skipped, not as clean."""

    @staticmethod
    def _duplicate_terms() -> list[tuple]:
        from elspais.graph.terms import TermEntry

        first = TermEntry(
            term="Electronic Record",
            definition="A record stored electronically.",
            defined_in="REQ-p00010",
            defined_at_line=5,
            namespace="REQ",
        )
        second = TermEntry(
            term="Electronic Record",
            definition="An electronic storage of data.",
            defined_in="REQ-d00042",
            defined_at_line=18,
            namespace="REQ",
        )
        return [(first, second)]

    @staticmethod
    def _graph_with_an_unmarked_code_file():
        from elspais.graph.builder import TraceGraph
        from elspais.graph.GraphNode import FileType, GraphNode, NodeKind

        graph = TraceGraph()
        node = GraphNode(id="file:src/orphan.py", kind=NodeKind.FILE, label="orphan.py")
        node.set_field("file_type", FileType.CODE)
        node.set_field("relative_path", "src/orphan.py")
        graph._index["file:src/orphan.py"] = node
        graph._roots.append(node)
        return graph

    # Verifies: REQ-d00212-P
    def test_REQ_d00212_P_a_legacy_configured_check_set_off_is_skipped(self) -> None:
        """`[terms.severity] duplicate = "off"` -- the same input that fails
        the check under the default severity is not reported at all."""
        duplicates = self._duplicate_terms()

        reported = check_term_duplicates(duplicates, config={})
        assert reported.passed is False
        assert reported.findings, "input no longer exercises the check"

        check = check_term_duplicates(
            duplicates, config={"terms": {"severity": {"duplicate": "off"}}}
        )

        assert check.passed is True
        assert check.severity == "info"
        assert check.findings == []
        assert check.details["skipped"] is True

    # Verifies: REQ-d00212-P
    def test_REQ_d00212_P_a_generally_configured_check_set_off_is_skipped(self) -> None:
        """`[rules.severity] "code.unlinked" = "off"` -- a check with no
        setting of its own is turned off through the general table, and the
        graph that produced a finding produces none."""
        graph = self._graph_with_an_unmarked_code_file()

        reported = check_unlinked_code(graph, {})
        assert reported.passed is False
        assert reported.findings, "graph no longer exercises the check"

        check = check_unlinked_code(graph, {"rules": {"severity": {"code.unlinked": "off"}}})

        assert check.passed is True
        assert check.severity == "info"
        assert check.findings == []
        assert check.details["skipped"] is True

    # Verifies: REQ-d00285-D
    def test_REQ_d00285_D_a_skipped_check_keeps_its_registered_category(self) -> None:
        """A skipped check is still filed where its findings would have been,
        so a reader looking at the category sees the withholding rather than
        an absence."""
        check = check_unlinked_code(
            self._graph_with_an_unmarked_code_file(),
            {"rules": {"severity": {"code.unlinked": "off"}}},
        )

        assert check.category == REGISTRY["code.unlinked"].category


# =============================================================================
# The general table admits only names it can answer for
# =============================================================================


class TestGeneralSeverityTable:
    """REQ-d00285-D: `[rules.severity]` is keyed by check name."""

    # Verifies: REQ-d00285-D
    def test_REQ_d00285_D_an_unknown_check_name_is_refused(self, tmp_path: Path) -> None:
        """A key naming no check could only sit there doing nothing, which
        reads to the project exactly like a setting that took effect."""
        with pytest.raises(ValidationError, match="names no check"):
            load_config(
                _write_config(tmp_path, '[rules.severity]\n"spec.invented_condition" = "off"\n')
            )

    # Verifies: REQ-d00285-D
    @pytest.mark.parametrize(
        "check_name", ["terms.duplicates", "references.malformed", "spec.no_assertions"]
    )
    def test_REQ_d00285_D_a_check_owning_a_named_setting_is_refused_here(
        self, tmp_path: Path, check_name: str
    ) -> None:
        """A check reads one path. Naming one here that is answered elsewhere
        would be read by nothing, so the refusal says where the setting lives
        instead of accepting a second place to write it."""
        with pytest.raises(ValidationError, match="is configured under"):
            load_config(_write_config(tmp_path, f'[rules.severity]\n"{check_name}" = "off"\n'))


# =============================================================================
# The registry accounts for every check the tool emits
# =============================================================================


def _check_names_emitted_by(module_path: Path) -> set[str]:
    """Every literal check name a module builds a check under.

    Names composed at runtime (the reference checks pass one in) are invisible
    to a static read; those are covered by the resolver refusing an
    unregistered name at the moment it is asked.
    """
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if called not in ("HealthCheck", "skipped_check"):
            continue
        supplied: ast.expr | None = None
        for kw in node.keywords:
            if kw.arg == "name":
                supplied = kw.value
        if supplied is None and node.args:
            supplied = node.args[0]
        if isinstance(supplied, ast.Constant) and isinstance(supplied.value, str):
            names.add(supplied.value)
    return names


# Verifies: REQ-d00285-D
def test_REQ_d00285_D_every_check_the_tool_emits_is_registered() -> None:
    """Every finding must fall in a category whose severity a project can
    configure. A check built under a name the registry does not carry reports
    a condition no project can turn off, soften or make fatal -- and the
    registry is where that reach is declared, so this walks what the code
    actually emits rather than trusting the two lists to have been kept in
    step by hand.
    """
    import elspais.commands.doctor as doctor_module
    import elspais.commands.health as health_module

    emitted: set[str] = set()
    for module in (health_module, doctor_module):
        emitted |= _check_names_emitted_by(Path(module.__file__))

    assert emitted, "found no check names; the walk no longer reads these modules"

    unregistered = sorted(name for name in emitted if name not in REGISTRY)
    assert unregistered == [], (
        f"checks emitted under unregistered names: {unregistered}. "
        f"Register each in elspais.utilities.findings.REGISTRY."
    )


# =============================================================================
# A severity outside the reported set can never reach the counting
# =============================================================================


class TestHealthCheckRefusesUnreportableSeverities:
    """REQ-d00212-U: the report counts three severities and only three."""

    # Verifies: REQ-d00212-U
    @pytest.mark.parametrize("severity", ["off", "ok", "banana", "", "ERROR"])
    def test_REQ_d00212_U_a_check_cannot_carry_an_unreportable_severity(
        self, severity: str
    ) -> None:
        """A severity outside {info, warning, error} matched none of the
        branches that count a check, so the check was neither failed, warned
        nor skipped and the run reported healthy. ``off`` is the pointed case:
        it is a legitimate thing to WRITE in a configuration and never a
        legitimate thing to REPORT, because a check resolving to it is emitted
        as a skipped `info` check instead.
        """
        with pytest.raises(ValueError, match="not a severity a check can be reported at"):
            HealthCheck(
                name="spec.parseable",
                passed=True,
                message="whatever",
                category="spec",
                severity=severity,
            )

    # Verifies: REQ-d00212-U
    @pytest.mark.parametrize("severity", ["info", "warning", "error"])
    def test_REQ_d00212_U_each_reported_severity_lands_in_exactly_one_count(
        self, severity: str
    ) -> None:
        """The report's four counts partition its checks: a check contributes
        to one of them and no more, so nothing can be reported and counted
        nowhere."""
        from elspais.commands.health import HealthReport

        report = HealthReport()
        report.add(
            HealthCheck(
                name="spec.parseable",
                passed=False,
                message="something",
                category="spec",
                severity=severity,
            )
        )

        counts = [report.passed, report.failed, report.warnings, report.skipped]
        assert sum(counts) == 1, f"{severity} lands in {sum(counts)} counts"
