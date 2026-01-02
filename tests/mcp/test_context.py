"""
Tests for elspais.mcp.context module.
"""

import pytest
from pathlib import Path


class TestWorkspaceContext:
    """Tests for WorkspaceContext class."""

    def test_from_directory(self, hht_like_fixture):
        """Test creating context from directory."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)

        assert ctx.working_dir == hht_like_fixture
        assert ctx.config is not None
        assert ctx.config["project"]["name"] == "hht-like-fixture"

    def test_get_requirements(self, hht_like_fixture):
        """Test getting requirements from context."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        requirements = ctx.get_requirements()

        assert len(requirements) > 0
        assert "REQ-p00001" in requirements

    def test_get_requirements_cached(self, hht_like_fixture):
        """Test that requirements are cached."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        req1 = ctx.get_requirements()
        req2 = ctx.get_requirements()

        assert req1 is req2  # Same object (cached)

    def test_get_requirements_force_refresh(self, hht_like_fixture):
        """Test force refresh of requirements."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        req1 = ctx.get_requirements()
        req2 = ctx.get_requirements(force_refresh=True)

        assert req1 is not req2  # Different objects

    def test_get_requirement(self, hht_like_fixture):
        """Test getting a single requirement."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        req = ctx.get_requirement("REQ-p00001")

        assert req is not None
        assert req.id == "REQ-p00001"

    def test_get_requirement_not_found(self, hht_like_fixture):
        """Test getting a non-existent requirement."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        req = ctx.get_requirement("REQ-p99999")

        assert req is None

    def test_get_content_rules(self, tmp_path):
        """Test getting content rules."""
        from elspais.mcp.context import WorkspaceContext

        # Create config with content rules
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text("""
[project]
name = "test"

[rules]
content_rules = ["AI-AGENT.md"]
""")
        (tmp_path / "AI-AGENT.md").write_text("""---
title: AI Guidelines
---
# Guidelines
""")
        (tmp_path / "spec").mkdir()

        ctx = WorkspaceContext.from_directory(tmp_path)
        rules = ctx.get_content_rules()

        assert len(rules) == 1
        assert rules[0].title == "AI Guidelines"

    def test_invalidate_cache(self, hht_like_fixture):
        """Test cache invalidation."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        _ = ctx.get_requirements()
        assert ctx._requirements_cache is not None

        ctx.invalidate_cache()
        assert ctx._requirements_cache is None

    def test_search_requirements(self, hht_like_fixture):
        """Test searching requirements."""
        from elspais.mcp.context import WorkspaceContext

        ctx = WorkspaceContext.from_directory(hht_like_fixture)
        results = ctx.search_requirements("Product", field="title")

        assert len(results) > 0
        # All results should have "Product" in their title
        for req in results:
            assert "Product" in req.title or "product" in req.title.lower()
