# Verifies: REQ-d00085
"""Tests that health check functions populate findings with structured data.

Validates REQ-d00085-I: Each check function should produce HealthFinding instances
with appropriate message, node_id, file_path, and line fields when issues are detected.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.commands.health import (
    HealthFinding,
    check_reference_class,
    check_spec_format_rules,
    check_spec_hierarchy_levels,
    check_spec_hierarchy_undefined_levels,
    check_spec_implements_resolve,
    check_spec_no_duplicates,
    check_spec_refines_resolve,
    check_spec_undefined_levels,
    check_test_results,
    run_spec_checks,
)
from elspais.config import _merge_configs, config_defaults, get_config
from elspais.graph.builder import TraceGraph
from elspais.graph.factory import build_graph
from elspais.graph.federated import FederatedGraph
from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.parsers.lark.transformers.requirement import NO_DECLARED_LEVEL


def _fed(graph: TraceGraph, tmp_path: Path) -> FederatedGraph:
    """Hold a hand-built graph in the one federation the checks read through."""
    config = {"project": {"name": "test", "namespace": "REQ"}}
    return FederatedGraph.from_single(graph, config, tmp_path)


def _load_config(config_path: Path) -> dict:
    raw = get_config(config_path)
    return _merge_configs(config_defaults(), raw)


def _make_config(tmp_path: Path) -> Path:
    """Create a minimal .elspais.toml config and return its path."""
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text(
        """version = 5

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]
"""
    )
    return config_path


def _build(tmp_path: Path, config_path: Path, **kwargs):
    """Build a graph with common defaults."""
    defaults = {
        "spec_dirs": [tmp_path / "spec"],
        "config_path": config_path,
        "repo_root": tmp_path,
        "scan_code": False,
        "scan_tests": False,
    }
    defaults.update(kwargs)
    return build_graph(**defaults)


class TestCheckSpecNoDuplicatesFindings:
    """Findings should identify each duplicate requirement with node_id and file_path."""

    # Verifies: REQ-d00085-I
    def test_REQ_d00085_I_duplicates_have_findings(self, tmp_path: Path) -> None:
        # check_spec_no_duplicates now reads the build-time collision record
        # at graph._duplicate_req_ids (subsequent occurrences are stored under
        # synthetic IDs and the canonical-id index entry no longer reveals the
        # duplication). Populate the record directly to exercise the check.
        graph = TraceGraph()
        node_a = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            label="First Copy",
        )
        node_a.set_field("source_file", "spec/file_a.md")
        node_b = GraphNode(
            id="REQ-p00001#file_b",
            kind=NodeKind.REQUIREMENT,
            label="Second Copy",
        )
        node_b.set_field("source_file", "spec/file_b.md")
        node_b.set_field("is_duplicate", True)
        node_b.set_field("original_id", "REQ-p00001")
        graph._index["REQ-p00001"] = node_a
        graph._index["REQ-p00001#file_b"] = node_b
        # Populate the build-time collision record the check reads from.
        graph._duplicate_req_ids = {
            "REQ-p00001": ["spec/file_a.md", "spec/file_b.md"],
        }

        check = check_spec_no_duplicates(_fed(graph, tmp_path))

        assert not check.passed, "Expected check to fail with duplicate IDs"
        assert len(check.findings) > 0, "Expected findings for duplicates"
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.node_id is not None, "Finding should have node_id"
        assert "REQ-p00001" in (finding.node_id or "")


class TestCheckSpecImplementsResolveFindings:
    """Findings should identify each unresolved implements reference."""

    # Verifies: REQ-d00085-I
    def test_REQ_d00085_I_unresolved_implements_have_findings(self, tmp_path: Path) -> None:
        # The builder stores implements as pending edge links, not as a node
        # field. The check function reads node.get_field("implements", []),
        # so we construct the graph manually with the field set directly.
        graph = TraceGraph()
        node = GraphNode(
            id="REQ-d00001",
            kind=NodeKind.REQUIREMENT,
            label="Dev Requirement",
        )
        node.set_field("level", "DEV")
        node.set_field("status", "Active")
        node.set_field("implements", ["REQ-p99999"])
        graph._index["REQ-d00001"] = node

        check = check_spec_implements_resolve(_fed(graph, tmp_path))

        assert not check.passed, "Expected check to fail with unresolved implements"
        assert len(check.findings) > 0, "Expected findings for unresolved implements"
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.node_id is not None, "Finding should have node_id (the 'from' req)"
        assert "REQ-d00001" in (finding.node_id or "")
        assert finding.message, "Finding should have a message"


class TestCheckSpecRefinesResolveFindings:
    """Findings should identify each unresolved refines reference."""

    # Verifies: REQ-d00085-I
    def test_REQ_d00085_I_unresolved_refines_have_findings(self, tmp_path: Path) -> None:
        # Same issue as implements: the builder stores refines as pending
        # edge links, not as a node field. Construct manually.
        graph = TraceGraph()
        node = GraphNode(
            id="REQ-d00002",
            kind=NodeKind.REQUIREMENT,
            label="Dev Refines",
        )
        node.set_field("level", "DEV")
        node.set_field("status", "Active")
        node.set_field("refines", ["REQ-p88888"])
        graph._index["REQ-d00002"] = node

        check = check_spec_refines_resolve(_fed(graph, tmp_path))

        assert not check.passed, "Expected check to fail with unresolved refines"
        assert len(check.findings) > 0, "Expected findings for unresolved refines"
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.node_id is not None, "Finding should have node_id"
        assert "REQ-d00002" in (finding.node_id or "")
        assert finding.message, "Finding should have a message"


class TestCheckSpecHierarchyLevelsFindings:
    """Findings should identify each hierarchy level violation."""

    # Verifies: REQ-d00085-I
    def test_REQ_d00085_I_hierarchy_violations_have_findings(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            """version = 5

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[rules.severity]
"spec.hierarchy_levels" = "warning"

[levels.prd]
rank = 1
letter = "p"
implements = []

[levels.ops]
rank = 2
letter = "o"
implements = ["prd"]

[levels.dev]
rank = 3
letter = "d"
implements = ["ops", "prd"]
"""
        )

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        # PRD implementing PRD is a violation (prd has no allowed parents)
        (spec_dir / "reqs.md").write_text(
            """# REQ-p00001: Parent PRD

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL exist.

*End* *Parent PRD* | **Hash**: eeee5555

# REQ-p00002: Child PRD

**Level**: PRD | **Status**: Active
**Implements**: REQ-p00001

## Assertions

A. The system SHALL also exist.

*End* *Child PRD* | **Hash**: ffff6666
"""
        )

        graph = _build(tmp_path, config_path)
        config = _load_config(config_path)
        check = check_spec_hierarchy_levels(graph, config)

        assert not check.passed, "Expected check to fail with hierarchy violations"
        assert len(check.findings) > 0, "Expected findings for hierarchy violations"
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.node_id is not None, "Finding should have node_id"


_HIERARCHY_PROJECT = """version = 5

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[levels.prd]
rank = 1
letter = "p"
implements = []

[levels.ops]
rank = 2
letter = "o"
implements = ["prd"]

[levels.dev]
rank = 3
letter = "d"
implements = ["ops", "prd"]
"""

_PRD_IMPLEMENTS_PRD = """# REQ-p00001: Parent PRD

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL exist.

*End* *Parent PRD* | **Hash**: eeee5555

# REQ-p00002: Child PRD

**Level**: PRD | **Status**: Active
**Implements**: REQ-p00001

## Assertions

A. The system SHALL also exist.

*End* *Child PRD* | **Hash**: ffff6666
"""


def _hierarchy_project(
    tmp_path: Path,
    spec: str,
    severity: str | None,
    severities: dict[str, str] | None = None,
) -> tuple:
    """A project holding `spec`, with the hierarchy check's severity set to
    `severity` under [rules.severity], or left unwritten where it is None.
    `severities` writes further [rules.severity] entries, keyed by check name."""
    text = _HIERARCHY_PROJECT
    entries = dict(severities or {})
    if severity is not None:
        entries["spec.hierarchy_levels"] = severity
    if entries:
        text += "\n[rules.severity]\n" + "".join(f'"{k}" = "{v}"\n' for k, v in entries.items())
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text(text)
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "reqs.md").write_text(spec)
    return _build(tmp_path, config_path), _load_config(config_path)


class TestCheckSpecHierarchyLevelsSeverity:
    """The hierarchy check takes its severity from [rules.severity] alone."""

    # Verifies: REQ-d00285-E
    @pytest.mark.parametrize("severity", ["info", "warning", "error"])
    def test_REQ_d00285_E_configured_severity_reaches_the_check(
        self, tmp_path: Path, severity: str
    ) -> None:
        graph, config = _hierarchy_project(tmp_path, _PRD_IMPLEMENTS_PRD, severity)

        check = check_spec_hierarchy_levels(graph, config)

        assert check.severity == severity
        assert not check.passed
        assert [f.node_id for f in check.findings] == ["REQ-p00002"]

    # Verifies: REQ-d00285-E
    def test_REQ_d00285_E_off_withholds_the_violation(self, tmp_path: Path) -> None:
        graph, config = _hierarchy_project(tmp_path, _PRD_IMPLEMENTS_PRD, "off")

        check = check_spec_hierarchy_levels(graph, config)

        assert check.passed
        assert check.severity == "info"
        assert check.findings == []
        assert "not reported (severity=off)" in check.message

    # Verifies: REQ-d00285-E
    def test_REQ_d00285_E_unconfigured_severity_is_info(self, tmp_path: Path) -> None:
        graph, config = _hierarchy_project(tmp_path, _PRD_IMPLEMENTS_PRD, None)

        check = check_spec_hierarchy_levels(graph, config)

        assert check.severity == "info"
        assert not check.passed
        assert [f.node_id for f in check.findings] == ["REQ-p00002"]


class TestCheckSpecHierarchyLevelsSatisfies:
    """A requirement's parents are the ones it declares with Implements: or
    Refines:, so a Satisfies: instance is judged by neither."""

    # Verifies: REQ-p00061-A
    def test_REQ_p00061_A_satisfies_instance_is_not_a_hierarchy_deviation(
        self, tmp_path: Path
    ) -> None:
        spec = """# REQ-p00001: Cross-Cutting Template

**Level**: PRD | **Status**: Active | **Template**

## Assertions

A. The system SHALL log every change.

*End* *Cross-Cutting Template* | **Hash**: eeee5555

# REQ-d00001: Dev Module

**Level**: DEV | **Status**: Active
**Satisfies**: REQ-p00001

## Assertions

A. The module SHALL write a log record.

*End* *Dev Module* | **Hash**: ffff6666
"""
        graph, config = _hierarchy_project(tmp_path, spec, "error")
        assert graph.find_by_id("REQ-d00001::REQ-p00001") is not None, (
            "the Satisfies: instance this test judges was not cloned"
        )

        check = check_spec_hierarchy_levels(graph, config)

        assert [f.node_id for f in check.findings if "::" in (f.node_id or "")] == []
        assert check.passed


_UNDEFINED_LEVEL_PARENT = """# REQ-p00001: Parent PRD

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL exist.

*End* *Parent PRD* | **Hash**: eeee5555

# REQ-d00003: Quality Child

**Level**: QA | **Status**: Active
**Implements**: REQ-p00001

## Assertions

A. The system SHALL be checked.

*End* *Quality Child* | **Hash**: abcd1234
"""

# A defined-level deviation (PRD implementing PRD, where prd implements
# nothing) beside a relationship whose child carries an undefined level.
_DEFINED_AND_UNDEFINED = (
    _PRD_IMPLEMENTS_PRD
    + """
# REQ-d00003: Quality Child

**Level**: QA | **Status**: Active
**Implements**: REQ-p00001

## Assertions

A. The system SHALL be checked.

*End* *Quality Child* | **Hash**: abcd1234
"""
)


class TestCheckSpecHierarchyUndefinedLevels:
    """A declared parent relationship involving a level the configuration does
    not define is its own condition, reported apart from the hierarchy check."""

    # Verifies: REQ-d00281-F
    def test_REQ_d00281_F_undefined_level_relationship_is_a_warning(self, tmp_path: Path) -> None:
        graph, config = _hierarchy_project(tmp_path, _UNDEFINED_LEVEL_PARENT, None)

        check = check_spec_hierarchy_undefined_levels(graph, config)

        assert check.name == "spec.hierarchy_undefined_levels"
        assert check.severity == "warning"
        assert not check.passed
        assert [f.node_id for f in check.findings] == ["REQ-d00003"]
        finding = check.findings[0]
        assert finding.related == ["REQ-p00001"]
        assert "'QA'" in finding.message
        assert "[levels] in .elspais.toml" in finding.message

    # Verifies: REQ-d00285-E
    @pytest.mark.parametrize("severity", ["off", "info", "warning", "error"])
    def test_REQ_d00285_E_undefined_level_severity_through_its_own_key(
        self, tmp_path: Path, severity: str
    ) -> None:
        graph, config = _hierarchy_project(
            tmp_path,
            _UNDEFINED_LEVEL_PARENT,
            None,
            severities={"spec.hierarchy_undefined_levels": severity},
        )

        check = check_spec_hierarchy_undefined_levels(graph, config)

        if severity == "off":
            assert check.passed
            assert check.severity == "info"
            assert check.findings == []
            assert "not reported (severity=off)" in check.message
        else:
            assert check.severity == severity
            assert not check.passed
            assert [f.node_id for f in check.findings] == ["REQ-d00003"]

    # Verifies: REQ-d00281-F
    def test_REQ_d00281_F_silencing_the_hierarchy_check_leaves_it_reported(
        self, tmp_path: Path
    ) -> None:
        graph, config = _hierarchy_project(tmp_path, _UNDEFINED_LEVEL_PARENT, "off")

        silenced = check_spec_hierarchy_levels(graph, config)
        check = check_spec_hierarchy_undefined_levels(graph, config)

        assert silenced.findings == []
        assert check.severity == "warning"
        assert not check.passed
        assert [f.node_id for f in check.findings] == ["REQ-d00003"]

    # Verifies: REQ-d00281-G
    def test_REQ_d00281_G_only_defined_levels_are_judged_by_the_hierarchy(
        self, tmp_path: Path
    ) -> None:
        graph, config = _hierarchy_project(tmp_path, _DEFINED_AND_UNDEFINED, "warning")

        hierarchy = check_spec_hierarchy_levels(graph, config)
        undefined = check_spec_hierarchy_undefined_levels(graph, config)

        assert [(f.node_id, f.related) for f in hierarchy.findings] == [
            ("REQ-p00002", ["REQ-p00001"])
        ]
        assert [(f.node_id, f.related) for f in undefined.findings] == [
            ("REQ-d00003", ["REQ-p00001"])
        ]

    # Verifies: REQ-d00281-F
    def test_REQ_d00281_F_spec_checks_report_the_undefined_level(self, tmp_path: Path) -> None:
        graph, config = _hierarchy_project(tmp_path, _UNDEFINED_LEVEL_PARENT, None)

        checks = [
            c for c in run_spec_checks(graph, config) if c.name == "spec.hierarchy_undefined_levels"
        ]

        assert len(checks) == 1
        assert [f.node_id for f in checks[0].findings] == ["REQ-d00003"]
        assert checks[0].severity == "warning"

    # Verifies: REQ-d00281-F
    def test_REQ_d00281_F_a_requirement_without_a_level_is_named_as_declaring_none(
        self, tmp_path: Path
    ) -> None:
        spec = """# REQ-p00001: Parent PRD

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL exist.

*End* *Parent PRD* | **Hash**: eeee5555

# REQ-d00004: Levelless Child

**Status**: Active
**Implements**: REQ-p00001

## Assertions

A. The system SHALL be described.

*End* *Levelless Child* | **Hash**: abcd5678
"""
        graph, config = _hierarchy_project(tmp_path, spec, None)
        child = graph.find_by_id("REQ-d00004")
        assert child is not None
        assert child.level == NO_DECLARED_LEVEL, "the child was expected to declare no level"

        check = check_spec_hierarchy_undefined_levels(graph, config)
        hierarchy = check_spec_hierarchy_levels(graph, config)

        assert len(check.findings) == 1
        finding = check.findings[0]
        assert finding.node_id == "REQ-d00004"
        assert finding.related == ["REQ-p00001"]
        assert "REQ-d00004 declares no level" in finding.message
        assert "(no level)" in finding.message
        assert "unknown" not in finding.message.lower()
        assert "[levels] in .elspais.toml" in finding.message
        assert [f.node_id for f in hierarchy.findings if f.node_id == "REQ-d00004"] == []


class TestCheckSpecUndefinedLevelsFindings:
    """REQ-d00281-D: a requirement carrying a level this configuration does not
    define is reported together with the level it carries.

    The check never fails -- an undefined level is a disclosure, since the
    requirement is still counted and still grouped (REQ-d00281-A+C). What it
    cannot do is pass silently, so the findings are the whole discriminator.
    """

    # Verifies: REQ-d00281-D
    def test_undefined_level_is_reported_with_the_spelling_it_carries(self, tmp_path: Path) -> None:
        config_path = _make_config(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "reqs.md").write_text(
            """# REQ-p00001: Defined Level

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL exist.

*End* *Defined Level* | **Hash**: eeee5555

# REQ-p00002: Undefined Level

**Level**: ArchTier | **Status**: Active

## Assertions

A. The system SHALL also exist.

*End* *Undefined Level* | **Hash**: ffff6666
"""
        )

        graph = _build(tmp_path, config_path)
        config = _load_config(config_path)
        check = check_spec_undefined_levels(graph, config)

        assert check.name == "spec.undefined_levels"
        assert check.category == "spec"
        assert check.severity == "info"
        assert check.passed, "an undefined level is disclosed, not a failure"
        # Only the requirement whose level the configuration lacks is named.
        assert [f.node_id for f in check.findings] == ["REQ-p00002"]
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert "ArchTier" in finding.message, "the level carried must be named"
        assert "REQ-p00002" in finding.message

    # Verifies: REQ-d00281-D
    def test_every_level_defined_reports_no_findings(self, tmp_path: Path) -> None:
        config_path = _make_config(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "reqs.md").write_text(
            """# REQ-p00001: A Product Requirement

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL exist.

*End* *A Product Requirement* | **Hash**: eeee5555

# REQ-d00001: A Dev Requirement

**Level**: DEV | **Status**: Active
**Implements**: REQ-p00001

## Assertions

A. The system SHALL also exist.

*End* *A Dev Requirement* | **Hash**: ffff6666
"""
        )

        graph = _build(tmp_path, config_path)
        config = _load_config(config_path)
        check = check_spec_undefined_levels(graph, config)

        assert check.passed
        assert check.findings == [], "every level here is configured"
        assert "Every requirement" in check.message


class TestCheckBrokenReferencesFindings:
    """Findings should identify each broken reference."""

    # Verifies: REQ-d00085-I
    def test_REQ_d00085_I_broken_refs_have_findings(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            """version = 5

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]
"""
        )
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        (spec_dir / "reqs.md").write_text(
            """# REQ-p00001: Real Requirement

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL exist.

*End* *Real Requirement* | **Hash**: gggg7777
"""
        )

        # Create a code file referencing a non-existent requirement to create broken ref
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "orphan.py").write_text(
            """# Implements: REQ-d99999
def orphan_func():
    pass
"""
        )

        from elspais.graph.reference_faults import FaultClass

        graph = _build(tmp_path, config_path, scan_code=True)
        check = check_reference_class(
            graph,
            None,
            FaultClass.UNKNOWN_REQUIREMENT,
            "references.unknown_requirement",
            "name a requirement its repository does not hold",
        )

        assert not check.passed, "Expected check to fail with broken references"
        assert len(check.findings) > 0, "Expected findings for broken references"
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.node_id is not None, "Finding should have node_id"


class TestCheckSpecFormatRulesFindings:
    """Findings should identify each format violation."""

    # Verifies: REQ-d00085-I
    def test_REQ_d00085_I_format_violations_have_findings(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            """version = 5

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[rules.format]
require_hash = true
require_assertions = true
"""
        )

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        # Requirement with no hash and no assertions triggers format violations
        (spec_dir / "reqs.md").write_text(
            """# REQ-p00010: No Hash No Assertions

**Level**: PRD | **Status**: Active

This requirement has no assertions section and no hash.

*End* *No Hash No Assertions*
"""
        )

        graph = _build(tmp_path, config_path)
        config = _load_config(config_path)
        check = check_spec_format_rules(graph, config)

        assert not check.passed, "Expected check to fail with format violations"
        assert len(check.findings) > 0, "Expected findings for format violations"
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.node_id is not None, "Finding should have node_id"
        assert "REQ-p00010" in (finding.node_id or "")


class TestCheckTestResultsFindings:
    """Findings should identify test failures."""

    # Verifies: REQ-d00085-I
    def test_REQ_d00085_I_test_failures_have_findings(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            """version = 5

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = true
directories = ["tests"]

[[scanning.test.targets]]
name = "unit"
reporter = "junit"
results = "junit.xml"
match = "source"
"""
        )

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        (spec_dir / "reqs.md").write_text(
            """# REQ-p00001: Real Requirement

**Level**: PRD | **Status**: Active

## Assertions

A. The system SHALL do something.

*End* *Real Requirement* | **Hash**: jjjj0000
"""
        )

        # Create a JUnit XML with a failed test
        results_dir = tmp_path / ".results" / "unit"
        results_dir.mkdir(parents=True)
        (results_dir / "junit.xml").write_text(
            """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="tests" tests="2" failures="1">
    <testcase classname="tests.test_thing" name="test_REQ_p00001_pass" time="0.01"/>
    <testcase classname="tests.test_thing" name="test_REQ_p00001_fail" time="0.02">
      <failure message="AssertionError">assert False</failure>
    </testcase>
  </testsuite>
</testsuites>
"""
        )

        graph = _build(tmp_path, config_path, scan_tests=True)
        check = check_test_results(graph)

        assert not check.passed, "Expected check to fail with test failures"
        assert len(check.findings) > 0, "Expected findings for test failures"
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.message, "Finding should have a message"


class TestCheckSpecNoDuplicateRefinesFindings:
    """Findings should identify requirements with redundant refs detected at parse time.

    Validates REQ-d00085-I: check_spec_needs_rewrite must produce HealthFinding
    instances with node_id when a requirement has parse_dirty=True (set by the builder
    when has_redundant_refs was True in parsed_data).
    """

    def test_REQ_d00085_I_duplicate_refines_have_findings(self, tmp_path: Path) -> None:
        # Verifies: REQ-d00085-I
        """A requirement with parse_dirty=True should produce a finding.

        parse_dirty is set by the builder when the parser detected duplicate refs
        (has_redundant_refs=True in parsed_data). The check reads parse_dirty instead
        of counting **Refines**: occurrences in body_text, since multiple Refines lines
        are now valid — only true duplicate refs should be flagged.
        """
        from elspais.commands.health import check_spec_needs_rewrite

        graph = TraceGraph()
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            label="Corrupted Requirement",
        )
        # Simulate what the builder sets when has_redundant_refs=True
        node.set_field("parse_dirty", True)
        node.set_field("body_text", "**Refines**: REQ-p00002\n\n**Refines**: REQ-p00002")
        node.set_field("level", "PRD")
        node.set_field("status", "Active")
        graph._index["REQ-p00001"] = node

        check = check_spec_needs_rewrite(_fed(graph, tmp_path))

        assert not check.passed, "Expected check to fail with parse_dirty=True"
        assert len(check.findings) > 0, "Expected findings for parse_dirty requirement"
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.node_id is not None, "Finding should have node_id"
        assert "REQ-p00001" in (finding.node_id or "")
        assert finding.message, "Finding should have a message"

    def test_REQ_d00085_I_single_refines_passes(self, tmp_path: Path) -> None:
        # Verifies: REQ-d00085-I
        """A requirement with a single distinct **Refines**: line (parse_dirty not set) passes."""
        from elspais.commands.health import check_spec_needs_rewrite

        graph = TraceGraph()
        node = GraphNode(
            id="REQ-p00002",
            kind=NodeKind.REQUIREMENT,
            label="Single Refines Requirement",
        )
        # parse_dirty is NOT set — no redundant refs were detected
        node.set_field("body_text", "**Refines**: REQ-p00001")
        node.set_field("level", "PRD")
        node.set_field("status", "Active")
        graph._index["REQ-p00002"] = node

        check = check_spec_needs_rewrite(_fed(graph, tmp_path))

        assert check.passed, "Expected check to pass when parse_dirty is not set"
        assert len(check.findings) == 0, "Expected no findings when parse_dirty is absent"

    def test_REQ_d00085_I_no_refines_passes(self, tmp_path: Path) -> None:
        # Verifies: REQ-d00085-I
        """A requirement with no parse_dirty should pass the check."""
        from elspais.commands.health import check_spec_needs_rewrite

        graph = TraceGraph()
        node = GraphNode(
            id="REQ-p00003",
            kind=NodeKind.REQUIREMENT,
            label="No Refines Requirement",
        )
        # parse_dirty is NOT set
        node.set_field("body_text", "This requirement has no Refines metadata.")
        node.set_field("level", "PRD")
        node.set_field("status", "Active")
        graph._index["REQ-p00003"] = node

        check = check_spec_needs_rewrite(_fed(graph, tmp_path))

        assert check.passed, "Expected check to pass when parse_dirty is not set"
        assert len(check.findings) == 0, "Expected no findings when parse_dirty is absent"

    def test_REQ_d00085_I_multiple_refines_without_duplicates_passes(self, tmp_path: Path) -> None:
        # Verifies: REQ-d00085-I
        """Multiple distinct **Refines**: lines (parse_dirty not set) should pass the check.

        This confirms the new behaviour: multiple Refines lines are valid as long as
        no duplicate refs were detected (parse_dirty remains unset).
        """
        from elspais.commands.health import check_spec_needs_rewrite

        graph = TraceGraph()
        node = GraphNode(
            id="REQ-p00004",
            kind=NodeKind.REQUIREMENT,
            label="Multi Refines No Duplicates",
        )
        # Two distinct Refines lines — parse_dirty is NOT set because no duplicates
        node.set_field("body_text", "**Refines**: REQ-p00001\n\n**Refines**: REQ-p00002")
        node.set_field("level", "PRD")
        node.set_field("status", "Active")
        # parse_dirty deliberately not set
        graph._index["REQ-p00004"] = node

        check = check_spec_needs_rewrite(_fed(graph, tmp_path))

        assert check.passed, (
            "Expected check to pass when multiple distinct Refines lines exist "
            "but parse_dirty is not set"
        )
        assert len(check.findings) == 0
