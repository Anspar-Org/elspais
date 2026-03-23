"""Tests for LCOV coverage report parser."""

from pathlib import Path

from elspais.graph.parsers.results.lcov import LcovParser


class TestLcovParserBasic:
    """Basic parsing tests for LcovParser."""

    def test_parse_single_file_record(self):
        """Parses a single file record with DA/LF/LH lines."""
        content = """\
SF:lib/src/foo.dart
DA:10,1
DA:11,0
DA:12,3
LF:3
LH:2
end_of_record
"""
        parser = LcovParser()
        result = parser.parse(content, "coverage/lcov.info")

        assert "lib/src/foo.dart" in result
        entry = result["lib/src/foo.dart"]
        assert entry["line_coverage"] == {10: 1, 11: 0, 12: 3}
        assert entry["executable_lines"] == 3
        assert entry["covered_lines"] == 2

    def test_parse_multiple_file_records(self):
        """Parses multiple file records in one LCOV file."""
        content = """\
SF:lib/src/foo.dart
DA:10,1
DA:11,0
DA:12,3
LF:3
LH:2
end_of_record
SF:lib/src/bar.dart
DA:5,2
DA:6,0
LF:2
LH:1
end_of_record
"""
        parser = LcovParser()
        result = parser.parse(content, "coverage/lcov.info")

        assert len(result) == 2
        assert "lib/src/foo.dart" in result
        assert "lib/src/bar.dart" in result

        foo = result["lib/src/foo.dart"]
        assert foo["line_coverage"] == {10: 1, 11: 0, 12: 3}
        assert foo["executable_lines"] == 3
        assert foo["covered_lines"] == 2

        bar = result["lib/src/bar.dart"]
        assert bar["line_coverage"] == {5: 2, 6: 0}
        assert bar["executable_lines"] == 2
        assert bar["covered_lines"] == 1

    def test_parse_missing_lf_lh_computed_from_da(self):
        """When LF/LH are absent, values are computed from DA lines."""
        content = """\
SF:lib/src/baz.dart
DA:1,5
DA:2,0
DA:3,1
end_of_record
"""
        parser = LcovParser()
        result = parser.parse(content, "lcov.info")

        entry = result["lib/src/baz.dart"]
        assert entry["executable_lines"] == 3  # 3 DA lines
        assert entry["covered_lines"] == 2  # lines 1 and 3 have hit > 0

    def test_parse_empty_content(self):
        """Empty content returns empty dict."""
        parser = LcovParser()
        result = parser.parse("", "lcov.info")
        assert result == {}

    def test_parse_file_with_no_da_lines(self):
        """File record with SF + end_of_record but no DA lines."""
        content = """\
SF:lib/src/empty.dart
end_of_record
"""
        parser = LcovParser()
        result = parser.parse(content, "lcov.info")

        assert "lib/src/empty.dart" in result
        entry = result["lib/src/empty.dart"]
        assert entry["line_coverage"] == {}
        assert entry["executable_lines"] == 0
        assert entry["covered_lines"] == 0

    def test_parse_high_hit_counts(self):
        """DA lines with high hit counts are parsed as ints correctly."""
        content = """\
SF:lib/src/hot.dart
DA:100,999999
DA:101,0
DA:102,1234567890
LF:3
LH:2
end_of_record
"""
        parser = LcovParser()
        result = parser.parse(content, "lcov.info")

        entry = result["lib/src/hot.dart"]
        assert entry["line_coverage"][100] == 999999
        assert entry["line_coverage"][102] == 1234567890

    def test_ignores_unknown_prefixes(self):
        """Lines with FN, FNDA, BRDA, BRF, BRH prefixes are ignored."""
        content = """\
TN:test_name
SF:lib/src/foo.dart
FN:10,myFunction
FNDA:5,myFunction
BRDA:15,0,0,1
BRF:4
BRH:2
DA:10,1
DA:11,0
LF:2
LH:1
end_of_record
"""
        parser = LcovParser()
        result = parser.parse(content, "lcov.info")

        entry = result["lib/src/foo.dart"]
        assert entry["line_coverage"] == {10: 1, 11: 0}
        assert entry["executable_lines"] == 2
        assert entry["covered_lines"] == 1

    def test_tolerates_whitespace_and_empty_lines(self):
        """Whitespace and empty lines between records are tolerated."""
        content = """\
SF:lib/src/a.dart
DA:1,1
LF:1
LH:1
end_of_record


SF:lib/src/b.dart
DA:2,0
LF:1
LH:0
end_of_record
"""
        parser = LcovParser()
        result = parser.parse(content, "lcov.info")

        assert len(result) == 2
        assert "lib/src/a.dart" in result
        assert "lib/src/b.dart" in result


class TestLcovParserCanParse:
    """Tests for can_parse file detection."""

    def test_info_extension(self):
        parser = LcovParser()
        assert parser.can_parse(Path("coverage/lcov.info")) is True

    def test_lcov_in_filename(self):
        parser = LcovParser()
        assert parser.can_parse(Path("lcov-report.txt")) is True

    def test_unrelated_file(self):
        parser = LcovParser()
        assert parser.can_parse(Path("test_results.xml")) is False

    def test_lcov_dat_file(self):
        parser = LcovParser()
        assert parser.can_parse(Path("lcov.dat")) is True


class TestLcovParserFactory:
    """Tests for the create_parser factory function."""

    def test_factory_creates_parser(self):
        from elspais.graph.parsers.results.lcov import create_parser

        parser = create_parser()
        assert isinstance(parser, LcovParser)
