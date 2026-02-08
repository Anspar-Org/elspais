"""Tests for DomainFile - File/directory deserializer."""

import pytest

from elspais.graph.deserializer import DomainFile
from elspais.graph.parsers import ParserRegistry
from elspais.graph.parsers.comments import CommentsParser
from elspais.graph.parsers.remainder import RemainderParser
from elspais.graph.parsers.requirement import RequirementParser
from elspais.utilities.patterns import PatternConfig


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

    def test_skip_dirs_filters_subdirectories(self, temp_spec_dir):
        """Test that skip_dirs excludes files in specified subdirectories."""
        # Create a roadmap subdirectory with a file
        roadmap_dir = temp_spec_dir / "roadmap"
        roadmap_dir.mkdir()
        roadmap_file = roadmap_dir / "future.md"
        roadmap_file.write_text("# Future\n\nSome future content.")

        # Without skip_dirs - should include roadmap file
        deserializer = DomainFile(temp_spec_dir, patterns=["*.md"], recursive=True)
        sources = list(deserializer.iterate_sources())
        source_paths = [ctx.source_id for ctx, _ in sources]
        assert any("roadmap" in s for s in source_paths), "Should include roadmap without skip"

        # With skip_dirs - should exclude roadmap file
        deserializer = DomainFile(
            temp_spec_dir, patterns=["*.md"], recursive=True, skip_dirs=["roadmap"]
        )
        sources = list(deserializer.iterate_sources())
        source_paths = [ctx.source_id for ctx, _ in sources]
        assert not any("roadmap" in s for s in source_paths), "Should exclude roadmap with skip"

    def test_skip_files_filters_specific_files(self, temp_spec_dir):
        """Test that skip_files excludes files with specified names."""
        # Create a README.md file
        readme = temp_spec_dir / "README.md"
        readme.write_text("# README\n\nThis is a readme.")

        # Without skip_files - should include README.md
        deserializer = DomainFile(temp_spec_dir, patterns=["*.md"])
        sources = list(deserializer.iterate_sources())
        source_paths = [ctx.source_id for ctx, _ in sources]
        assert any("README.md" in s for s in source_paths), "Should include README without skip"

        # With skip_files - should exclude README.md
        deserializer = DomainFile(temp_spec_dir, patterns=["*.md"], skip_files=["README.md"])
        sources = list(deserializer.iterate_sources())
        source_paths = [ctx.source_id for ctx, _ in sources]
        assert not any("README.md" in s for s in source_paths), "Should exclude README with skip"

    def test_skip_dirs_and_files_combined(self, temp_spec_dir):
        """Test that skip_dirs and skip_files work together."""
        # Create a roadmap subdirectory with files
        roadmap_dir = temp_spec_dir / "roadmap"
        roadmap_dir.mkdir()
        (roadmap_dir / "future.md").write_text("# Future")

        # Create INDEX.md
        (temp_spec_dir / "INDEX.md").write_text("# Index")

        deserializer = DomainFile(
            temp_spec_dir,
            patterns=["*.md"],
            recursive=True,
            skip_dirs=["roadmap"],
            skip_files=["INDEX.md"],
        )
        sources = list(deserializer.iterate_sources())
        source_paths = [ctx.source_id for ctx, _ in sources]

        # Should not contain roadmap or INDEX.md
        assert not any("roadmap" in s for s in source_paths)
        assert not any("INDEX.md" in s for s in source_paths)

        # But should contain the original prd.md and ops.md
        assert any("prd.md" in s for s in source_paths)
        assert any("ops.md" in s for s in source_paths)
