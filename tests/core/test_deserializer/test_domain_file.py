"""Tests for DomainFile - File/directory deserializer."""

import pytest
from pathlib import Path

from elspais.arch3.Graph.deserializer import DomainFile
from elspais.arch3.Graph.MDparser import ParserRegistry
from elspais.arch3.Graph.MDparser.comments import CommentsParser
from elspais.arch3.Graph.MDparser.remainder import RemainderParser
from elspais.arch3.Graph.MDparser.requirement import RequirementParser
from elspais.arch3.utilities.patterns import PatternConfig


@pytest.fixture
def hht_config():
    return PatternConfig(
        id_template="{prefix}-{type}{id}",
        prefix="REQ",
        types={
            "prd": {"id": "p", "name": "PRD", "level": 1},
            "ops": {"id": "o", "name": "OPS", "level": 2},
            "dev": {"id": "d", "name": "DEV", "level": 3},
        },
        id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
    )


@pytest.fixture
def parser_registry(hht_config):
    registry = ParserRegistry()
    registry.register(CommentsParser())
    registry.register(RequirementParser(hht_config))
    registry.register(RemainderParser())
    return registry


class TestDomainFile:
    """Tests for DomainFile deserializer."""

    def test_iterate_sources_single_file(self, temp_spec_dir):
        prd_file = temp_spec_dir / "prd.md"
        deserializer = DomainFile(prd_file)

        sources = list(deserializer.iterate_sources())

        assert len(sources) == 1
        ctx, content = sources[0]
        assert ctx.source_type == "file"
        assert "prd.md" in ctx.source_id
        assert "REQ-p00001" in content

    def test_iterate_sources_directory(self, temp_spec_dir):
        deserializer = DomainFile(temp_spec_dir, patterns=["*.md"])

        sources = list(deserializer.iterate_sources())

        assert len(sources) == 2
        source_ids = [ctx.source_id for ctx, _ in sources]
        assert any("prd.md" in s for s in source_ids)
        assert any("ops.md" in s for s in source_ids)

    def test_deserialize_produces_parsed_content(self, temp_spec_dir, parser_registry):
        deserializer = DomainFile(temp_spec_dir, patterns=["*.md"])

        results = list(deserializer.deserialize(parser_registry))

        # Should have parsed content from both files
        assert len(results) > 0

        # Find requirements
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) >= 2  # At least REQ-p00001 and REQ-p00002

        req_ids = [r.parsed_data["id"] for r in reqs]
        assert "REQ-p00001" in req_ids
        assert "REQ-p00002" in req_ids

    def test_deserialize_includes_file_context(self, temp_spec_dir, parser_registry):
        prd_file = temp_spec_dir / "prd.md"
        deserializer = DomainFile(prd_file)

        results = list(deserializer.deserialize(parser_registry))

        # All results should have source context
        for result in results:
            assert hasattr(result, "source_context")
            assert "prd.md" in result.source_context.source_id
