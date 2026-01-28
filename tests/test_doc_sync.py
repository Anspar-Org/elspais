"""Tests for documentation files and markdown renderer.

Ensures docs/cli/ files exist, have required sections, and that the
markdown renderer handles all expected patterns correctly.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from elspais.utilities.docs_loader import (
    TOPIC_ORDER,
    find_docs_dir,
    get_available_topics,
    load_all_topics,
    load_topic,
)
from elspais.utilities.md_renderer import MarkdownRenderer, render_markdown


class TestDocsExistence:
    """Test that all documentation files exist."""

    def test_docs_dir_found(self):
        """docs/cli directory should be locatable."""
        docs_dir = find_docs_dir()
        assert docs_dir is not None, "docs/cli directory not found"
        assert docs_dir.is_dir(), f"{docs_dir} is not a directory"

    @pytest.mark.parametrize("topic", TOPIC_ORDER)
    def test_topic_file_exists(self, topic: str):
        """Each topic should have a corresponding markdown file."""
        docs_dir = find_docs_dir()
        assert docs_dir is not None
        topic_file = docs_dir / f"{topic}.md"
        assert topic_file.is_file(), f"Missing documentation file: {topic}.md"

    def test_all_topics_available(self):
        """get_available_topics should return all expected topics."""
        available = get_available_topics()
        assert set(available) == set(TOPIC_ORDER), (
            f"Expected topics {TOPIC_ORDER}, got {available}"
        )


class TestDocsContent:
    """Test that documentation files have required content."""

    @pytest.mark.parametrize("topic", TOPIC_ORDER)
    def test_topic_has_heading(self, topic: str):
        """Each topic file should start with a level-1 heading."""
        content = load_topic(topic)
        assert content is not None, f"Could not load {topic}"
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        assert len(lines) > 0, f"{topic}.md is empty"
        assert lines[0].startswith("# "), f"{topic}.md should start with # heading"

    @pytest.mark.parametrize("topic", TOPIC_ORDER)
    def test_topic_has_subheadings(self, topic: str):
        """Each topic file should have at least one ## subheading."""
        content = load_topic(topic)
        assert content is not None
        assert "## " in content, f"{topic}.md should have at least one ## subheading"

    def test_quickstart_has_essential_sections(self):
        """quickstart.md should have initialize, validate, and next steps."""
        content = load_topic("quickstart")
        assert content is not None
        assert "Initialize" in content, "quickstart should mention initialization"
        assert "elspais init" in content, "quickstart should show init command"
        assert "elspais validate" in content, "quickstart should show validate command"

    def test_format_has_structure_section(self):
        """format.md should explain requirement structure."""
        content = load_topic("format")
        assert content is not None
        assert "REQ-" in content, "format should show REQ- ID pattern"
        assert "Level" in content, "format should explain Level field"
        assert "Hash" in content, "format should explain Hash"

    def test_hierarchy_has_levels(self):
        """hierarchy.md should explain PRD, OPS, DEV."""
        content = load_topic("hierarchy")
        assert content is not None
        assert "PRD" in content, "hierarchy should mention PRD"
        assert "OPS" in content, "hierarchy should mention OPS"
        assert "DEV" in content, "hierarchy should mention DEV"

    def test_assertions_has_keywords(self):
        """assertions.md should explain normative keywords."""
        content = load_topic("assertions")
        assert content is not None
        assert "SHALL" in content, "assertions should explain SHALL"
        assert "SHALL NOT" in content, "assertions should explain SHALL NOT"

    def test_commands_has_all_commands(self):
        """commands.md should document all CLI commands."""
        content = load_topic("commands")
        assert content is not None
        # Check for key commands
        for cmd in ["validate", "trace", "hash", "edit", "config", "init"]:
            assert f"## {cmd}" in content, f"commands should document {cmd}"
        # Check for global options
        assert "Global Options" in content, "commands should have global options"

    def test_all_topics_concatenation(self):
        """load_all_topics should return all topics concatenated."""
        all_content = load_all_topics()
        assert len(all_content) > 0, "load_all_topics returned empty"
        # Should contain content from all topics
        for topic in TOPIC_ORDER:
            topic_content = load_topic(topic)
            assert topic_content is not None
            # First heading from each topic should appear in all_content
            first_line = topic_content.strip().split("\n")[0]
            assert first_line in all_content, (
                f"all_topics missing content from {topic}"
            )


class TestMarkdownRenderer:
    """Test markdown-to-ANSI rendering."""

    def test_render_heading(self):
        """Level-1 heading should render with box borders."""
        renderer = MarkdownRenderer(use_color=True)
        result = renderer.render("# My Title")
        assert "═" in result, "Heading should have box border"
        assert "My Title" in result

    def test_render_heading_no_color(self):
        """Heading without color should have no ANSI codes."""
        renderer = MarkdownRenderer(use_color=False)
        result = renderer.render("# My Title")
        assert "\033[" not in result, "Should have no ANSI codes"
        assert "My Title" in result

    def test_render_subheading(self):
        """Level-2 heading should render with underline."""
        renderer = MarkdownRenderer(use_color=True)
        result = renderer.render("## Subheading")
        assert "─" in result, "Subheading should have underline"
        assert "Subheading" in result

    def test_render_code_block(self):
        """Code blocks should be indented and dimmed."""
        renderer = MarkdownRenderer(use_color=True)
        result = renderer.render("```\ncode here\n```")
        # Code block content should be present
        assert "code here" in result
        # Should have DIM escape code when colors enabled
        assert "\033[2m" in result, "Code should be dimmed"

    def test_render_bold(self):
        """Bold text should use BOLD escape code."""
        renderer = MarkdownRenderer(use_color=True)
        result = renderer.render("This is **bold** text")
        assert "\033[1m" in result, "Bold should use BOLD code"
        assert "bold" in result

    def test_render_inline_code(self):
        """Inline code should use CYAN."""
        renderer = MarkdownRenderer(use_color=True)
        result = renderer.render("Use `command` here")
        assert "\033[36m" in result, "Inline code should be CYAN"
        assert "command" in result

    def test_render_command_with_comment(self):
        """Command lines with comments should have green $ and dim comment."""
        renderer = MarkdownRenderer(use_color=True)
        result = renderer.render("  $ elspais init  # Creates config")
        assert "\033[32m" in result, "$ should be green"
        assert "\033[2m" in result, "Comment should be dim"

    def test_convenience_function_auto_color(self):
        """render_markdown should auto-detect TTY."""
        # When forced off, should have no ANSI codes
        result = render_markdown("# Test", use_color=False)
        assert "\033[" not in result

    def test_render_preserves_blank_lines(self):
        """Blank lines in content should be preserved."""
        content = "# Title\n\nParagraph one.\n\nParagraph two."
        result = render_markdown(content, use_color=False)
        # Should have blank lines between content
        assert "\n\n" in result or result.count("\n") >= 4


class TestCLIIntegration:
    """Test CLI docs command integration."""

    def test_docs_quickstart(self):
        """elspais docs quickstart should succeed."""
        result = subprocess.run(
            [sys.executable, "-m", "elspais", "docs", "quickstart", "--plain"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "ELSPAIS" in result.stdout

    def test_docs_all(self):
        """elspais docs all should show all topics."""
        result = subprocess.run(
            [sys.executable, "-m", "elspais", "docs", "all", "--plain"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"Failed: {result.stderr}"
        # Should contain headings from multiple topics
        assert "QUICK START" in result.stdout
        assert "HIERARCHY" in result.stdout
        assert "CONFIGURATION" in result.stdout

    def test_docs_plain_no_ansi(self):
        """--plain should produce output without ANSI codes."""
        result = subprocess.run(
            [sys.executable, "-m", "elspais", "docs", "format", "--plain"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "\033[" not in result.stdout, "Plain output should have no ANSI codes"

    @pytest.mark.parametrize("topic", TOPIC_ORDER)
    def test_each_topic_loads(self, topic: str):
        """Each topic should be loadable via CLI."""
        result = subprocess.run(
            [sys.executable, "-m", "elspais", "docs", topic, "--plain"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"Failed for {topic}: {result.stderr}"
        assert len(result.stdout) > 100, f"{topic} output too short"
