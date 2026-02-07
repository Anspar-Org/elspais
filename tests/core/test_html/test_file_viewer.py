# Validates: REQ-p00006-C
"""Tests for HTML Generator file viewer: _collect_source_files and _get_pygments_css.

Validates REQ-p00006-C: Embedded source file viewing with syntax highlighting.
"""

import tempfile
from pathlib import Path

import pytest

from elspais.graph.builder import TraceGraph
from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import GraphNode, NodeKind, SourceLocation
from elspais.html.generator import HTMLGenerator

# Fixture root for hht-like tests
_FIXTURE_ROOT = Path(__file__).parent.parent.parent / "fixtures" / "hht-like"


@pytest.fixture
def hht_graph():
    """Build a real graph from the hht-like fixture."""
    config_path = _FIXTURE_ROOT / ".elspais.toml"
    return build_graph(
        config_path=config_path,
        repo_root=_FIXTURE_ROOT,
        scan_code=False,
        scan_tests=False,
        scan_sponsors=False,
    )


@pytest.fixture
def empty_graph():
    """Create a graph with a node whose source file does not exist."""
    node = GraphNode(
        id="REQ-x00001",
        kind=NodeKind.REQUIREMENT,
        label="Ghost Requirement",
        source=SourceLocation(path="/nonexistent/path/ghost.md", line=1),
    )
    node._content = {"level": "PRD", "status": "Active", "hash": "00000000"}

    graph = TraceGraph(repo_root=Path("/nonexistent"))
    graph._roots = [node]
    graph._index = {"REQ-x00001": node}
    return graph


@pytest.fixture
def no_source_graph():
    """Create a graph with a node that has no source location."""
    node = GraphNode(
        id="REQ-x00002",
        kind=NodeKind.REQUIREMENT,
        label="Sourceless Requirement",
    )
    node._content = {"level": "PRD", "status": "Active", "hash": "00000000"}

    graph = TraceGraph(repo_root=Path("/tmp"))
    graph._roots = [node]
    graph._index = {"REQ-x00002": node}
    return graph


class TestCollectSourceFilesStructure:
    """Validates REQ-p00006-C: _collect_source_files returns correct data structure."""

    def test_REQ_p00006_C_collect_source_files_returns_dict(self, hht_graph):
        """_collect_source_files returns a dict."""
        generator = HTMLGenerator(hht_graph)
        result = generator._collect_source_files()
        assert isinstance(result, dict)

    def test_REQ_p00006_C_collect_source_files_returns_correct_keys(self, hht_graph):
        """Each entry in source_files has lines, language, and raw keys."""
        generator = HTMLGenerator(hht_graph)
        result = generator._collect_source_files()

        assert len(result) > 0, "Expected at least one source file from hht-like fixture"
        for path, data in result.items():
            assert "lines" in data, f"Missing 'lines' key for {path}"
            assert "language" in data, f"Missing 'language' key for {path}"
            assert "raw" in data, f"Missing 'raw' key for {path}"

    def test_REQ_p00006_C_collect_source_files_lines_is_list(self, hht_graph):
        """The lines value is a list of strings."""
        generator = HTMLGenerator(hht_graph)
        result = generator._collect_source_files()

        for path, data in result.items():
            assert isinstance(data["lines"], list), f"lines should be list for {path}"
            for line in data["lines"]:
                assert isinstance(line, str), f"Each line should be str for {path}"

    def test_REQ_p00006_C_collect_source_files_raw_is_string(self, hht_graph):
        """The raw value is a string containing the file contents."""
        generator = HTMLGenerator(hht_graph)
        result = generator._collect_source_files()

        for path, data in result.items():
            assert isinstance(data["raw"], str), f"raw should be str for {path}"
            assert len(data["raw"]) > 0, f"raw should not be empty for {path}"


class TestCollectSourceFilesHighlighting:
    """Validates REQ-p00006-C: _collect_source_files applies Pygments highlighting."""

    def test_REQ_p00006_C_collect_source_files_returns_highlighted_lines(self, hht_graph):
        """Lines contain Pygments HTML span tokens for syntax highlighting."""
        generator = HTMLGenerator(hht_graph)
        result = generator._collect_source_files()

        assert len(result) > 0
        # At least some lines in at least one file should have highlighting spans
        has_highlighted = False
        for _path, data in result.items():
            for line in data["lines"]:
                if '<span class="' in line:
                    has_highlighted = True
                    break
            if has_highlighted:
                break

        assert has_highlighted, "Expected at least some highlighted lines with <span class= tokens"


class TestCollectSourceFilesLanguageDetection:
    """Validates REQ-p00006-C: _collect_source_files detects correct language."""

    def test_REQ_p00006_C_collect_source_files_detects_markdown(self, hht_graph):
        """Markdown files are detected as markdown language."""
        generator = HTMLGenerator(hht_graph)
        result = generator._collect_source_files()

        # hht-like fixture has .md spec files
        md_files = {p: d for p, d in result.items() if p.endswith(".md")}
        assert len(md_files) > 0, "Expected at least one .md file"

        for path, data in md_files.items():
            # Pygments uses "markdown" for .md files
            assert (
                data["language"] == "markdown"
            ), f"Expected 'markdown' language for {path}, got '{data['language']}'"

    def test_REQ_p00006_C_collect_source_files_detects_python(self):
        """Python files are detected as python language."""
        # Create a graph with a real Python file as source
        py_file = Path(__file__)  # This test file itself is Python

        node = GraphNode(
            id="REQ-t00001",
            kind=NodeKind.REQUIREMENT,
            label="Python Source Test",
            source=SourceLocation(path=str(py_file), line=1),
        )
        node._content = {"level": "DEV", "status": "Active", "hash": "00000000"}

        graph = TraceGraph(repo_root=py_file.parent)
        graph._roots = [node]
        graph._index = {"REQ-t00001": node}

        generator = HTMLGenerator(graph)
        result = generator._collect_source_files()

        assert str(py_file) in result
        assert result[str(py_file)]["language"] == "python"


class TestCollectSourceFilesBinarySkip:
    """Validates REQ-p00006-C: _collect_source_files skips binary files."""

    def test_REQ_p00006_C_collect_source_files_skips_binary_files(self):
        """Binary files (containing null bytes) are skipped."""
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(b"Hello\x00World\x00Binary")
            binary_path = f.name

        try:
            node = GraphNode(
                id="REQ-b00001",
                kind=NodeKind.REQUIREMENT,
                label="Binary Source",
                source=SourceLocation(path=binary_path, line=1),
            )
            node._content = {"level": "DEV", "status": "Active", "hash": "00000000"}

            graph = TraceGraph(repo_root=Path(binary_path).parent)
            graph._roots = [node]
            graph._index = {"REQ-b00001": node}

            generator = HTMLGenerator(graph)
            result = generator._collect_source_files()

            assert binary_path not in result, "Binary file should be skipped"
        finally:
            Path(binary_path).unlink(missing_ok=True)


class TestCollectSourceFilesSizeLimit:
    """Validates REQ-p00006-C: _collect_source_files skips files over 500KB."""

    def test_REQ_p00006_C_collect_source_files_skips_large_files(self):
        """Files exceeding the 500KB (512000 bytes) limit are skipped."""
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w") as f:
            # Write just over 512KB of text content
            f.write("x" * 520_000)
            large_path = f.name

        try:
            node = GraphNode(
                id="REQ-l00001",
                kind=NodeKind.REQUIREMENT,
                label="Large Source",
                source=SourceLocation(path=large_path, line=1),
            )
            node._content = {"level": "DEV", "status": "Active", "hash": "00000000"}

            graph = TraceGraph(repo_root=Path(large_path).parent)
            graph._roots = [node]
            graph._index = {"REQ-l00001": node}

            generator = HTMLGenerator(graph)
            result = generator._collect_source_files()

            assert large_path not in result, "File over 500KB should be skipped"
        finally:
            Path(large_path).unlink(missing_ok=True)


class TestCollectSourceFilesEmpty:
    """Validates REQ-p00006-C: _collect_source_files returns empty dict when no files."""

    def test_REQ_p00006_C_collect_source_files_empty_when_no_source_files(self, no_source_graph):
        """Returns empty dict when nodes have no source locations."""
        generator = HTMLGenerator(no_source_graph)
        result = generator._collect_source_files()

        assert result == {}

    def test_REQ_p00006_C_collect_source_files_empty_when_files_missing(self, empty_graph):
        """Returns empty dict when source files do not exist on disk."""
        generator = HTMLGenerator(empty_graph)
        result = generator._collect_source_files()

        assert result == {}


class TestGetPygmentsCss:
    """Validates REQ-p00006-C: _get_pygments_css returns CSS for syntax highlighting."""

    def test_REQ_p00006_C_get_pygments_css_returns_nonempty_string(self, hht_graph):
        """Returns a non-empty string."""
        generator = HTMLGenerator(hht_graph)
        css = generator._get_pygments_css()

        assert isinstance(css, str)
        assert len(css) > 0

    def test_REQ_p00006_C_get_pygments_css_contains_highlight_class(self, hht_graph):
        """Returned CSS contains .highlight selector."""
        generator = HTMLGenerator(hht_graph)
        css = generator._get_pygments_css()

        assert ".highlight" in css


class TestGenerateEmbedContentSourceFiles:
    """Validates REQ-p00006-C: generate() integrates source files and Pygments CSS."""

    def test_REQ_p00006_C_generate_embed_includes_source_files(self, hht_graph):
        """generate(embed_content=True) includes source_files data in HTML."""
        generator = HTMLGenerator(hht_graph)
        html = generator.generate(embed_content=True)

        # The template should render source file paths from the fixture
        # At minimum, one of the spec file paths should appear in the output
        spec_paths = [
            "spec/prd-core.md",
            "spec/ops-deploy.md",
            "spec/dev-impl.md",
        ]
        found_any = any(p in html for p in spec_paths)
        assert found_any, "Expected at least one spec file path in embedded content HTML"

    def test_REQ_p00006_C_generate_no_embed_has_empty_source_files(self, hht_graph):
        """generate(embed_content=False) does not include source file content."""
        generator = HTMLGenerator(hht_graph)
        html = generator.generate(embed_content=False)

        # With embed_content=False, _collect_source_files is not called,
        # so source_files={} and pygments_css="" are passed to template.
        # The HTML should NOT contain Pygments CSS class definitions.
        # We verify by checking that the specific Pygments token classes
        # (like .highlight .k, .highlight .s) are absent.
        assert ".highlight .k " not in html
        assert ".highlight .s " not in html

    def test_REQ_p00006_C_generate_embed_includes_pygments_css(self, hht_graph):
        """generate(embed_content=True) includes Pygments CSS in a style block."""
        generator = HTMLGenerator(hht_graph)
        html = generator.generate(embed_content=True)

        # Pygments CSS should be inside a <style> tag
        assert "<style>" in html
        # The Pygments CSS contains .highlight class rules
        assert ".highlight" in html
