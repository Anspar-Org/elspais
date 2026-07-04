"""Tests for DomainDeserializer base infrastructure."""

from __future__ import annotations

from collections.abc import Iterator

from elspais.graph.deserializer import (
    DomainContext,
    DomainDeserializer,
    DomainStdio,
    ParsedContentWithContext,
)
from elspais.graph.parsers import ParseContext, ParsedContent, ParserRegistry


class FakeClaimingParser:
    """A minimal LineClaimingParser that claims only lines whose text is in
    `claimable`. Used to drive DomainStdio.deserialize() without pulling in
    the full Lark grammar.
    """

    def __init__(self, claimable: set[str], priority: int = 10) -> None:
        self.claimable = claimable
        self._priority = priority
        self.captured_lines: list[tuple[int, str]] | None = None

    @property
    def priority(self) -> int:
        return self._priority

    def claim_and_parse(
        self,
        lines: list[tuple[int, str]],
        context: ParseContext,
    ) -> Iterator[ParsedContent]:
        # Record exactly what we were handed so tests can inspect line
        # numbering/content passed through by the caller.
        self.captured_lines = list(lines)
        for line_no, text in lines:
            if text in self.claimable:
                yield ParsedContent(
                    content_type="fake",
                    start_line=line_no,
                    end_line=line_no,
                    raw_text=text,
                    parsed_data={"text": text},
                )


class TestDomainContext:
    """Tests for DomainContext dataclass."""

    # Verifies: REQ-o00072-A
    def test_metadata_default_not_shared_between_instances(self):
        """Each DomainContext must get its own metadata dict.

        If `metadata` were declared as a plain mutable default (e.g.
        `metadata: dict = {}`) instead of `field(default_factory=dict)`,
        every instance would share the same dict object and mutating one
        instance's metadata would leak into all others.
        """
        ctx1 = DomainContext(source_type="file", source_id="a.md")
        ctx2 = DomainContext(source_type="file", source_id="b.md")

        assert ctx1.metadata is not ctx2.metadata

        ctx1.metadata["key"] = "value"

        assert "key" not in ctx2.metadata


class TestParsedContentWithContext:
    """Tests for ParsedContentWithContext dataclass."""

    # Verifies: REQ-o00072-A
    def test_source_context_defaults_to_none(self):
        parsed = ParsedContentWithContext(
            content_type="requirement",
            start_line=1,
            end_line=3,
            raw_text="text",
        )

        assert parsed.source_context is None

    # Verifies: REQ-o00072-A
    def test_carries_real_domain_context(self):
        ctx = DomainContext(source_type="stdin", source_id="<stdin>")

        parsed = ParsedContentWithContext(
            content_type="requirement",
            start_line=1,
            end_line=3,
            raw_text="text",
            source_context=ctx,
        )

        assert parsed.source_context is ctx
        assert parsed.source_context.source_type == "stdin"

    # Verifies: REQ-o00072-B
    def test_inherits_line_count_computation(self):
        """ParsedContentWithContext must genuinely inherit ParsedContent's
        computed line_count property, not merely have the same field names.
        """
        parsed = ParsedContentWithContext(
            content_type="requirement",
            start_line=5,
            end_line=9,
            raw_text="text",
        )

        # 5,6,7,8,9 -> 5 lines. Verify the actual arithmetic, not just
        # "it doesn't raise".
        assert parsed.line_count == 5


class TestDomainDeserializerProtocol:
    """Tests for the DomainDeserializer runtime-checkable Protocol."""

    # Verifies: REQ-o00072-C
    def test_domain_file_satisfies_protocol(self):
        from elspais.graph.deserializer import DomainFile

        deserializer = DomainFile("some/path.md")

        assert isinstance(deserializer, DomainDeserializer)

    # Verifies: REQ-o00072-C
    def test_domain_stdio_satisfies_protocol(self):
        deserializer = DomainStdio("some content")

        assert isinstance(deserializer, DomainDeserializer)

    # Verifies: REQ-o00072-C
    def test_unrelated_duck_typed_object_satisfies_protocol(self):
        """The Protocol is structural: any object exposing both required
        methods conforms, regardless of its class hierarchy.
        """

        class DuckDeserializer:
            def iterate_sources(self):
                yield DomainContext(source_type="cli", source_id="args"), "content"

            def deserialize(self, registry):
                yield from ()

        assert isinstance(DuckDeserializer(), DomainDeserializer)

    # Verifies: REQ-o00072-C
    def test_object_missing_a_method_does_not_satisfy_protocol(self):
        """An object missing one of the two required methods must NOT be
        recognized as a DomainDeserializer -- proves the protocol actually
        enforces its contract rather than trivially matching anything.
        """

        class IncompleteDeserializer:
            def iterate_sources(self):
                yield DomainContext(source_type="cli", source_id="args"), "content"

            # deliberately no deserialize()

        assert not isinstance(IncompleteDeserializer(), DomainDeserializer)


class TestDomainStdio:
    """Tests for DomainStdio deserializer."""

    # Verifies: REQ-o00072-A
    def test_iterate_sources_yields_single_tuple_with_defaults(self):
        deserializer = DomainStdio("hello\nworld")

        sources = list(deserializer.iterate_sources())

        assert len(sources) == 1
        ctx, content = sources[0]
        assert ctx.source_type == "stdin"
        assert ctx.source_id == "<stdin>"
        assert content == "hello\nworld"

    # Verifies: REQ-o00072-A
    def test_iterate_sources_honors_custom_source_id(self):
        deserializer = DomainStdio("content", source_id="custom-id")

        ctx, _content = next(deserializer.iterate_sources())

        assert ctx.source_id == "custom-id"

    # Verifies: REQ-o00072-B
    def test_deserialize_splits_content_into_1_indexed_lines(self):
        parser = FakeClaimingParser(claimable=set())
        registry = ParserRegistry()
        registry.register(parser)

        deserializer = DomainStdio("first\nsecond\nthird")
        list(deserializer.deserialize(registry))

        assert parser.captured_lines == [
            (1, "first"),
            (2, "second"),
            (3, "third"),
        ]

    # Verifies: REQ-o00072-A
    def test_deserialize_attaches_same_context_used_in_iteration(self):
        parser = FakeClaimingParser(claimable={"claim-me"})
        registry = ParserRegistry()
        registry.register(parser)

        deserializer = DomainStdio("claim-me", source_id="ctx-check")
        results = list(deserializer.deserialize(registry))

        assert len(results) == 1
        result = results[0]
        assert isinstance(result.source_context, DomainContext)
        assert result.source_context.source_type == "stdin"
        assert result.source_context.source_id == "ctx-check"

    # Verifies: REQ-o00072-B
    def test_deserialize_passes_through_underlying_parsed_content_fields(self):
        parser = FakeClaimingParser(claimable={"claim-me"})
        registry = ParserRegistry()
        registry.register(parser)

        deserializer = DomainStdio("claim-me")
        (result,) = list(deserializer.deserialize(registry))

        assert result.content_type == "fake"
        assert result.raw_text == "claim-me"
        assert result.parsed_data == {"text": "claim-me"}
        assert result.start_line == 1
        assert result.end_line == 1

    # Verifies: REQ-o00072-B
    def test_deserialize_yields_nothing_for_unclaimed_lines(self):
        """Lines the fake parser does not claim must produce no output --
        DomainStdio.deserialize only emits what parse_all yields, so
        unclaimed content is silently dropped, not passed through raw.
        """
        parser = FakeClaimingParser(claimable={"claim-me"})
        registry = ParserRegistry()
        registry.register(parser)

        deserializer = DomainStdio("claim-me\nignore-me\nalso-ignore-me")
        results = list(deserializer.deserialize(registry))

        assert len(results) == 1
        assert results[0].raw_text == "claim-me"

    # Verifies: REQ-o00072-B
    def test_deserialize_on_empty_content_does_not_raise(self):
        """ "".split("\n") yields [""], i.e. one empty line, not zero lines.
        Confirm DomainStdio handles this without crashing and that an
        unclaiming parser correctly yields nothing for it.
        """
        parser = FakeClaimingParser(claimable=set())
        registry = ParserRegistry()
        registry.register(parser)

        deserializer = DomainStdio("")
        results = list(deserializer.deserialize(registry))

        assert results == []
        assert parser.captured_lines == [(1, "")]
