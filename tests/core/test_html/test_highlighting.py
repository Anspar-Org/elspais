# Validates REQ-p00006-A: Syntax highlighting for file viewer
"""Tests for the highlighting utility module.

Validates:
- REQ-p00006-A: Syntax highlighting with Pygments and graceful fallback
"""

from __future__ import annotations

from unittest.mock import patch

from elspais.html.highlighting import (
    MAX_FILE_SIZE,
    get_pygments_css,
    highlight_file_content,
)


class TestHighlightFileContent:
    """Validates REQ-p00006-A: highlight_file_content() core behavior."""

    def test_REQ_p00006_A_returns_highlighted_html_spans(self):
        """Python content returns lines with Pygments HTML spans."""
        result = highlight_file_content("test.py", "def foo():\n    pass\n")
        assert "lines" in result
        assert "language" in result
        assert "raw" in result
        # Pygments wraps keywords in <span> tags
        assert any("<span" in line for line in result["lines"])

    def test_REQ_p00006_A_detects_python_language(self):
        """Python files are detected as 'python'."""
        result = highlight_file_content("test.py", "x = 1\n")
        assert result["language"] == "python"

    def test_REQ_p00006_A_detects_markdown_language(self):
        """Markdown files are detected correctly."""
        result = highlight_file_content("README.md", "# Hello\n")
        # Pygments may report 'markdown' or similar
        assert result["language"] != ""

    def test_REQ_p00006_A_detects_javascript_language(self):
        """JavaScript files are detected correctly."""
        result = highlight_file_content("app.js", "const x = 1;\n")
        assert "javascript" in result["language"].lower() or "js" in result["language"].lower()

    def test_REQ_p00006_A_unknown_extension_falls_back_to_text(self):
        """Unknown file extensions fall back to text lexer."""
        result = highlight_file_content("data.xyz123", "some content\n")
        assert result["language"] == "text"

    def test_REQ_p00006_A_preserves_raw_content(self):
        """Raw content is preserved unchanged in the result."""
        raw = "def foo():\n    return 42\n"
        result = highlight_file_content("test.py", raw)
        assert result["raw"] == raw

    def test_REQ_p00006_A_line_count_matches(self):
        """Number of highlighted lines matches raw line count."""
        raw = "line1\nline2\nline3\n"
        result = highlight_file_content("test.txt", raw)
        # raw.split("\n") gives ["line1", "line2", "line3", ""]
        # trailing empty removed, so 3 lines
        assert len(result["lines"]) == 3

    def test_REQ_p00006_A_empty_content(self):
        """Empty content returns empty lines list."""
        result = highlight_file_content("test.py", "")
        assert result["lines"] == [] or result["lines"] == [""]
        assert result["raw"] == ""

    def test_REQ_p00006_A_multiline_tokens_preserved(self):
        """Multi-line tokens like docstrings are highlighted correctly."""
        raw = '"""\nA docstring\n"""\nx = 1\n'
        result = highlight_file_content("test.py", raw)
        assert len(result["lines"]) >= 4


class TestHighlightFileContentFallback:
    """Validates REQ-p00006-A: graceful degradation without Pygments."""

    def test_REQ_p00006_A_fallback_without_pygments(self):
        """When Pygments is unavailable, falls back to HTML-escaped text."""
        with patch.dict("sys.modules", {"pygments": None}):
            # Force re-import behavior by patching the import inside the function
            import importlib

            import elspais.html.highlighting as mod

            importlib.reload(mod)

            result = mod.highlight_file_content("test.py", "<script>alert(1)</script>\n")
            assert result["language"] == "text"
            assert "&lt;script&gt;" in result["lines"][0]

            # Restore module
            importlib.reload(mod)

    def test_REQ_p00006_A_fallback_escapes_html_entities(self):
        """Fallback properly escapes HTML special characters."""
        with (
            patch(
                "elspais.html.highlighting.pygments_highlight",
                side_effect=ImportError("mocked"),
            )
            if False
            else patch.dict(
                "sys.modules",
                {"pygments": None, "pygments.formatters": None, "pygments.lexers": None},
            )
        ):
            import importlib

            import elspais.html.highlighting as mod

            importlib.reload(mod)

            result = mod.highlight_file_content("test.html", "<div>&amp;</div>\n")
            assert "&lt;div&gt;" in result["lines"][0]
            assert "&amp;amp;" in result["lines"][0]

            importlib.reload(mod)


class TestGetPygmentsCss:
    """Validates REQ-p00006-A: get_pygments_css() CSS generation."""

    def test_REQ_p00006_A_returns_scoped_css(self):
        """Default call returns CSS scoped under .highlight."""
        css = get_pygments_css()
        assert ".highlight" in css
        assert "color" in css.lower() or "background" in css.lower()

    def test_REQ_p00006_A_custom_scope(self):
        """Custom scope parameter is applied to CSS."""
        css = get_pygments_css(scope=".my-scope")
        assert ".my-scope" in css

    def test_REQ_p00006_A_monokai_style(self):
        """Monokai style generates valid CSS."""
        css = get_pygments_css(style="monokai")
        assert ".highlight" in css
        assert len(css) > 0

    def test_REQ_p00006_A_dark_theme_scope(self):
        """Dark theme CSS scoped under .dark-theme .highlight."""
        css = get_pygments_css(style="monokai", scope=".dark-theme .highlight")
        assert ".dark-theme .highlight" in css

    def test_REQ_p00006_A_returns_empty_without_pygments(self):
        """Returns empty string when Pygments is unavailable."""
        with patch.dict(
            "sys.modules",
            {"pygments": None, "pygments.formatters": None},
        ):
            import importlib

            import elspais.html.highlighting as mod

            importlib.reload(mod)

            css = mod.get_pygments_css()
            assert css == ""

            importlib.reload(mod)


class TestMaxFileSize:
    """Validates REQ-p00006-A: MAX_FILE_SIZE constant."""

    def test_REQ_p00006_A_max_file_size_is_512k(self):
        """MAX_FILE_SIZE is set to 512,000 bytes."""
        assert MAX_FILE_SIZE == 512_000
