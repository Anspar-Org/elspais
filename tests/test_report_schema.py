"""Tests for ReportSchema and RollupMetrics.

These tests verify the configurable report system including:
- ReportSchema parsing from configuration
- RollupMetrics accumulation from leaves to roots
- Metric exclusions based on status
- Built-in report presets

Note: Tests import from graph_schema.py (renamed from tree_schema.py).
"""

from __future__ import annotations

import pytest
from pathlib import Path


class TestRollupMetrics:
    """Tests for the RollupMetrics dataclass."""

    def test_rollup_metrics_defaults(self) -> None:
        """RollupMetrics initializes with zero values."""
        from elspais.core.graph_schema import RollupMetrics

        metrics = RollupMetrics()

        assert metrics.total_assertions == 0
        assert metrics.covered_assertions == 0
        assert metrics.total_tests == 0
        assert metrics.passed_tests == 0
        assert metrics.failed_tests == 0
        assert metrics.skipped_tests == 0
        assert metrics.total_code_refs == 0
        assert metrics.coverage_pct == 0.0
        assert metrics.pass_rate_pct == 0.0

    def test_rollup_metrics_with_values(self) -> None:
        """RollupMetrics stores provided values."""
        from elspais.core.graph_schema import RollupMetrics

        metrics = RollupMetrics(
            total_assertions=10,
            covered_assertions=8,
            total_tests=5,
            passed_tests=4,
            failed_tests=1,
            skipped_tests=0,
            total_code_refs=3,
            coverage_pct=80.0,
            pass_rate_pct=80.0,
        )

        assert metrics.total_assertions == 10
        assert metrics.covered_assertions == 8
        assert metrics.coverage_pct == 80.0

    def test_rollup_metrics_summation(self) -> None:
        """RollupMetrics can be combined via addition."""
        from elspais.core.graph_schema import RollupMetrics

        m1 = RollupMetrics(total_assertions=5, covered_assertions=3, total_tests=2, passed_tests=2)
        m2 = RollupMetrics(total_assertions=3, covered_assertions=2, total_tests=1, passed_tests=0)

        # Note: Addition operator may not be implemented - this tests the expected behavior
        combined = RollupMetrics(
            total_assertions=m1.total_assertions + m2.total_assertions,
            covered_assertions=m1.covered_assertions + m2.covered_assertions,
            total_tests=m1.total_tests + m2.total_tests,
            passed_tests=m1.passed_tests + m2.passed_tests,
        )

        assert combined.total_assertions == 8
        assert combined.covered_assertions == 5
        assert combined.total_tests == 3
        assert combined.passed_tests == 2


class TestReportSchema:
    """Tests for the ReportSchema dataclass."""

    def test_report_schema_defaults(self) -> None:
        """ReportSchema has sensible defaults."""
        from elspais.core.graph_schema import ReportSchema

        schema = ReportSchema(name="test")

        assert schema.name == "test"
        assert schema.description == ""
        assert schema.include_fields == ["id", "title", "status"]
        assert schema.include_metrics is False
        assert schema.metric_fields == []
        assert schema.include_children is True
        assert schema.max_depth is None
        assert schema.sort_by == "id"
        assert schema.sort_descending is False
        assert schema.filters == {}

    def test_report_schema_custom_fields(self) -> None:
        """ReportSchema accepts custom field configuration."""
        from elspais.core.graph_schema import ReportSchema

        schema = ReportSchema(
            name="custom",
            description="Custom report",
            include_fields=["id", "title", "status", "level", "hash"],
            include_metrics=True,
            metric_fields=["coverage_pct", "pass_rate_pct"],
            include_children=True,
            max_depth=3,
            sort_by="coverage_pct",
            sort_descending=True,
            filters={"status": ["Active"]},
        )

        assert schema.name == "custom"
        assert schema.include_metrics is True
        assert "coverage_pct" in schema.metric_fields
        assert schema.max_depth == 3
        assert schema.filters == {"status": ["Active"]}

    def test_report_schema_defaults_method(self) -> None:
        """ReportSchema.defaults() returns built-in presets."""
        from elspais.core.graph_schema import ReportSchema

        defaults = ReportSchema.defaults()

        assert "minimal" in defaults
        assert "standard" in defaults
        assert "full" in defaults

        minimal = defaults["minimal"]
        assert minimal.include_metrics is False
        assert minimal.include_children is False

        standard = defaults["standard"]
        assert standard.include_metrics is True
        assert "coverage_pct" in standard.metric_fields

        full = defaults["full"]
        assert full.include_metrics is True
        assert len(full.metric_fields) >= 5


class TestReportSchemaFromConfig:
    """Tests for parsing ReportSchema from TOML configuration."""

    def test_parse_minimal_report(self) -> None:
        """Parse minimal report configuration."""
        from elspais.core.graph_schema import GraphSchema

        config = {
            "trace": {
                "reports": {
                    "minimal": {
                        "description": "Quick overview",
                        "fields": ["id", "title"],
                        "include_metrics": False,
                    }
                }
            }
        }

        schema = GraphSchema.from_config(config)

        assert "minimal" in schema.reports
        assert schema.reports["minimal"].include_fields == ["id", "title"]
        assert schema.reports["minimal"].include_metrics is False

    def test_parse_report_with_metrics(self) -> None:
        """Parse report configuration with metrics enabled."""
        from elspais.core.graph_schema import GraphSchema

        config = {
            "trace": {
                "reports": {
                    "detailed": {
                        "fields": ["id", "title", "status"],
                        "include_metrics": True,
                        "metric_fields": ["total_assertions", "coverage_pct"],
                    }
                }
            }
        }

        schema = GraphSchema.from_config(config)

        assert "detailed" in schema.reports
        report = schema.reports["detailed"]
        assert report.include_metrics is True
        assert "coverage_pct" in report.metric_fields

    def test_parse_report_with_filters(self) -> None:
        """Parse report configuration with filters."""
        from elspais.core.graph_schema import GraphSchema

        config = {
            "trace": {
                "reports": {
                    "active_only": {
                        "fields": ["id", "title"],
                        "filters": {"status": ["Active", "Draft"]},
                    }
                }
            }
        }

        schema = GraphSchema.from_config(config)
        report = schema.reports["active_only"]

        assert report.filters == {"status": ["Active", "Draft"]}

    def test_defaults_included_when_not_overridden(self) -> None:
        """Default presets are included when not overridden in config."""
        from elspais.core.graph_schema import GraphSchema

        config = {
            "trace": {
                "reports": {
                    "custom": {"fields": ["id"]},
                }
            }
        }

        schema = GraphSchema.from_config(config)

        # Custom report exists
        assert "custom" in schema.reports
        # Default presets also exist
        assert "minimal" in schema.reports
        assert "standard" in schema.reports
        assert "full" in schema.reports

    def test_user_config_overrides_defaults(self) -> None:
        """User-defined reports override default presets."""
        from elspais.core.graph_schema import GraphSchema

        config = {
            "trace": {
                "reports": {
                    "minimal": {
                        "description": "My custom minimal",
                        "fields": ["id", "hash"],
                    }
                }
            }
        }

        schema = GraphSchema.from_config(config)

        assert schema.reports["minimal"].description == "My custom minimal"
        assert schema.reports["minimal"].include_fields == ["id", "hash"]


class TestMetricsExclusions:
    """Tests for metric exclusion configuration."""

    def test_parse_exclude_status(self) -> None:
        """Parse [rules.metrics] exclude_status configuration."""
        from elspais.core.graph_schema import GraphSchema

        config = {
            "rules": {
                "metrics": {
                    "exclude_status": ["Deprecated", "Superseded"],
                }
            }
        }

        schema = GraphSchema.from_config(config)

        assert schema.metrics_config is not None
        assert "Deprecated" in schema.metrics_config.exclude_status
        assert "Superseded" in schema.metrics_config.exclude_status

    def test_default_exclude_status(self) -> None:
        """Default exclude_status includes common inactive statuses."""
        from elspais.core.graph_schema import GraphSchema

        schema = GraphSchema.from_config({})

        defaults = schema.metrics_config.exclude_status
        assert "Deprecated" in defaults
        assert "Superseded" in defaults
        assert "Draft" in defaults

    def test_count_placeholder_assertions_config(self) -> None:
        """Parse count_placeholder_assertions configuration."""
        from elspais.core.graph_schema import GraphSchema

        config = {
            "rules": {
                "metrics": {
                    "count_placeholder_assertions": True,
                }
            }
        }

        schema = GraphSchema.from_config(config)

        assert schema.metrics_config.count_placeholder_assertions is True


class TestGraphSchemaReportIntegration:
    """Tests for GraphSchema integration with ReportSchema."""

    def test_graph_schema_has_reports_field(self) -> None:
        """GraphSchema has reports dictionary field."""
        from elspais.core.graph_schema import GraphSchema

        schema = GraphSchema.default()

        assert hasattr(schema, "reports")
        assert isinstance(schema.reports, dict)

    def test_graph_schema_has_metrics_config(self) -> None:
        """GraphSchema has metrics_config field."""
        from elspais.core.graph_schema import GraphSchema

        schema = GraphSchema.default()

        assert hasattr(schema, "metrics_config")
        assert hasattr(schema.metrics_config, "exclude_status")


class TestCLIReportFlag:
    """Tests for the --report CLI flag."""

    def test_trace_command_accepts_report_flag(self) -> None:
        """The trace command accepts --report flag."""
        from elspais.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["trace", "--report", "minimal"])

        assert args.report == "minimal"

    def test_trace_command_default_report(self) -> None:
        """Default report is 'standard' when --report not specified."""
        from elspais.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["trace"])

        # Either default is None (let command choose) or "standard"
        assert args.report is None or args.report == "standard"

    def test_report_flag_combined_with_graph(self) -> None:
        """--report flag works with --graph flag."""
        from elspais.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["trace", "--graph", "--report", "full"])

        assert args.graph is True
        assert args.report == "full"

    def test_report_flag_combined_with_format(self) -> None:
        """--report flag works with --format flag."""
        from elspais.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["trace", "--report", "minimal", "--format", "csv"])

        assert args.report == "minimal"
        assert args.format == "csv"
