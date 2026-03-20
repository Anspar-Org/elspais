"""Tests for MDparser base infrastructure - LineClaimingParser protocol."""

from elspais.graph.parsers import (
    ParseContext,
    ParsedContent,
    ParserRegistry,
)


class TestParsedContent:
    """Tests for ParsedContent dataclass."""

    # Implements: REQ-d00054-A
    def test_create_minimal_defaults(self):
        """Non-obvious default: parsed_data defaults to empty dict."""
        content = ParsedContent(
            content_type="requirement",
            start_line=10,
            end_line=25,
            raw_text="Some text",
        )
        assert content.parsed_data == {}

    # Implements: REQ-d00054-A
    def test_line_count(self):
        content = ParsedContent(
            content_type="comment",
            start_line=5,
            end_line=10,
            raw_text="",
        )
        assert content.line_count == 6  # 5, 6, 7, 8, 9, 10


class TestParserRegistry:
    """Tests for ParserRegistry - manages parser priority ordering."""

    # Implements: REQ-d00128-G
    def test_empty_registry(self):
        registry = ParserRegistry()
        assert registry.parsers == []

    # Implements: REQ-d00128-G
    def test_register_parser(self):
        registry = ParserRegistry()

        class MockParser:
            priority = 50

            def claim_and_parse(self, lines, context):
                return iter([])

        parser = MockParser()
        registry.register(parser)
        assert len(registry.parsers) == 1

    # Implements: REQ-d00128-G
    def test_parsers_sorted_by_priority(self):
        registry = ParserRegistry()

        class LowPriority:
            priority = 100

            def claim_and_parse(self, lines, context):
                return iter([])

        class HighPriority:
            priority = 10

            def claim_and_parse(self, lines, context):
                return iter([])

        class MidPriority:
            priority = 50

            def claim_and_parse(self, lines, context):
                return iter([])

        registry.register(LowPriority())
        registry.register(HighPriority())
        registry.register(MidPriority())

        priorities = [p.priority for p in registry.get_ordered()]
        assert priorities == [10, 50, 100]

    # Implements: REQ-d00128-G
    def test_parse_all_calls_parsers_in_order(self):
        registry = ParserRegistry()
        call_order = []

        class Parser1:
            priority = 10

            def claim_and_parse(self, lines, context):
                call_order.append(1)
                # Claim lines 1-2
                return iter(
                    [
                        ParsedContent(
                            content_type="test",
                            start_line=1,
                            end_line=2,
                            raw_text="",
                        )
                    ]
                )

        class Parser2:
            priority = 20

            def claim_and_parse(self, lines, context):
                call_order.append(2)
                return iter([])

        registry.register(Parser1())
        registry.register(Parser2())

        lines = [(1, "line1"), (2, "line2"), (3, "line3")]
        ctx = ParseContext(file_path="test.md")

        list(registry.parse_all(lines, ctx))

        assert call_order == [1, 2]

    # Implements: REQ-d00128-G
    def test_claimed_lines_not_passed_to_later_parsers(self):
        registry = ParserRegistry()
        lines_seen_by_parser2 = []

        class Parser1:
            priority = 10

            def claim_and_parse(self, lines, context):
                # Claim line 2
                yield ParsedContent(
                    content_type="claimed",
                    start_line=2,
                    end_line=2,
                    raw_text="",
                )

        class Parser2:
            priority = 20

            def claim_and_parse(self, lines, context):
                lines_seen_by_parser2.extend([ln for ln, _ in lines])
                return iter([])

        registry.register(Parser1())
        registry.register(Parser2())

        lines = [(1, "line1"), (2, "line2"), (3, "line3")]
        ctx = ParseContext(file_path="test.md")

        list(registry.parse_all(lines, ctx))

        # Parser2 should NOT see line 2 (it was claimed)
        assert 2 not in lines_seen_by_parser2
        assert 1 in lines_seen_by_parser2
        assert 3 in lines_seen_by_parser2
