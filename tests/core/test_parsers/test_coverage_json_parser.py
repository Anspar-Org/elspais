"""Tests for Python coverage.json parser."""

import json
from pathlib import Path

from elspais.graph.parsers.results.coverage_json import CoverageJsonParser


class TestCoverageJsonParserAggregate:
    """Aggregate parsing tests (no contexts)."""

    def test_parse_single_file(self):
        """Parses a single file entry with executed/missing lines."""
        data = {
            "meta": {"version": "7.6.10", "timestamp": "2024-01-01"},
            "files": {
                "src/foo.py": {
                    "executed_lines": [1, 2, 5, 10],
                    "missing_lines": [3, 4],
                    "excluded_lines": [],
                    "summary": {
                        "num_statements": 6,
                        "covered_lines": 4,
                        "missing_lines": 2,
                        "percent_covered": 66.67,
                    },
                }
            },
        }
        parser = CoverageJsonParser()
        result = parser.parse(json.dumps(data), "coverage.json")

        assert "src/foo.py" in result
        entry = result["src/foo.py"]
        assert entry["line_coverage"] == {1: 1, 2: 1, 5: 1, 10: 1, 3: 0, 4: 0}
        assert entry["executable_lines"] == 6
        assert entry["covered_lines"] == 4
        assert entry["contexts"] is None

    def test_parse_multiple_files(self):
        """Parses multiple file entries."""
        data = {
            "files": {
                "src/foo.py": {
                    "executed_lines": [1, 2],
                    "missing_lines": [3],
                    "summary": {
                        "num_statements": 3,
                        "covered_lines": 2,
                    },
                },
                "src/bar.py": {
                    "executed_lines": [10],
                    "missing_lines": [],
                    "summary": {
                        "num_statements": 1,
                        "covered_lines": 1,
                    },
                },
            }
        }
        parser = CoverageJsonParser()
        result = parser.parse(json.dumps(data), "coverage.json")

        assert len(result) == 2
        assert result["src/foo.py"]["executable_lines"] == 3
        assert result["src/bar.py"]["covered_lines"] == 1


class TestCoverageJsonParserContexts:
    """Per-context parsing tests."""

    def test_parse_with_contexts(self):
        """Parses file entries that include per-line test contexts."""
        data = {
            "files": {
                "src/foo.py": {
                    "executed_lines": [1, 2, 5],
                    "missing_lines": [3],
                    "contexts": {
                        "1": ["tests.test_foo.test_bar|run"],
                        "2": ["tests.test_foo.test_bar|run"],
                        "5": ["tests.test_foo.test_baz|run"],
                    },
                    "summary": {
                        "num_statements": 4,
                        "covered_lines": 3,
                    },
                }
            }
        }
        parser = CoverageJsonParser()
        result = parser.parse(json.dumps(data), "coverage.json")

        entry = result["src/foo.py"]
        assert entry["contexts"] is not None
        assert entry["contexts"][1] == ["tests.test_foo.test_bar|run"]
        assert entry["contexts"][5] == ["tests.test_foo.test_baz|run"]

    def test_contexts_keys_converted_to_int(self):
        """Context dict keys (strings in JSON) are converted to int line numbers."""
        data = {
            "files": {
                "src/foo.py": {
                    "executed_lines": [1],
                    "missing_lines": [],
                    "contexts": {"1": ["ctx"]},
                    "summary": {"num_statements": 1, "covered_lines": 1},
                }
            }
        }
        parser = CoverageJsonParser()
        result = parser.parse(json.dumps(data), "coverage.json")

        contexts = result["src/foo.py"]["contexts"]
        assert isinstance(list(contexts.keys())[0], int)


class TestCoverageJsonParserEdgeCases:
    """Edge case tests."""

    def test_empty_files_dict(self):
        """Empty files dict returns empty result."""
        data = {"files": {}}
        parser = CoverageJsonParser()
        result = parser.parse(json.dumps(data), "coverage.json")
        assert result == {}

    def test_missing_summary_computed_from_lines(self):
        """When summary is missing, values are computed from line lists."""
        data = {
            "files": {
                "src/foo.py": {
                    "executed_lines": [1, 2, 5],
                    "missing_lines": [3, 4],
                }
            }
        }
        parser = CoverageJsonParser()
        result = parser.parse(json.dumps(data), "coverage.json")

        entry = result["src/foo.py"]
        assert entry["executable_lines"] == 5  # 3 executed + 2 missing
        assert entry["covered_lines"] == 3

    def test_missing_summary_fields_computed(self):
        """When summary exists but lacks fields, values are computed."""
        data = {
            "files": {
                "src/foo.py": {
                    "executed_lines": [1, 2],
                    "missing_lines": [3],
                    "summary": {"percent_covered": 66.67},
                }
            }
        }
        parser = CoverageJsonParser()
        result = parser.parse(json.dumps(data), "coverage.json")

        entry = result["src/foo.py"]
        assert entry["executable_lines"] == 3
        assert entry["covered_lines"] == 2

    def test_invalid_json_returns_empty(self):
        """Invalid JSON content returns empty dict."""
        parser = CoverageJsonParser()
        result = parser.parse("not json at all", "coverage.json")
        assert result == {}

    def test_missing_files_key_returns_empty(self):
        """JSON without 'files' key returns empty dict."""
        parser = CoverageJsonParser()
        result = parser.parse(json.dumps({"meta": {}}), "coverage.json")
        assert result == {}


class TestCoverageJsonParserCanParse:
    """Tests for can_parse file detection."""

    def test_coverage_json(self):
        parser = CoverageJsonParser()
        assert parser.can_parse(Path("coverage.json")) is True

    def test_coverage_in_name_json(self):
        parser = CoverageJsonParser()
        assert parser.can_parse(Path("build/coverage-report.json")) is True

    def test_plain_json_without_coverage(self):
        parser = CoverageJsonParser()
        assert parser.can_parse(Path("config.json")) is False

    def test_non_json_file(self):
        parser = CoverageJsonParser()
        assert parser.can_parse(Path("coverage.xml")) is False

    def test_dot_coverage_json(self):
        parser = CoverageJsonParser()
        assert parser.can_parse(Path(".coverage.json")) is True


class TestCoverageJsonParserFactory:
    """Tests for the create_parser factory function."""

    def test_factory_creates_parser(self):
        from elspais.graph.parsers.results.coverage_json import create_parser

        parser = create_parser()
        assert isinstance(parser, CoverageJsonParser)
