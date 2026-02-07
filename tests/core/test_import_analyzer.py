"""Tests for import_analyzer module."""

from pathlib import Path

from elspais.utilities.import_analyzer import extract_python_imports, module_to_source_path


class TestExtractPythonImports:
    def test_from_import(self):
        content = "from os.path import join\n"
        assert extract_python_imports(content) == ["os.path"]

    def test_plain_import(self):
        content = "import os\n"
        assert extract_python_imports(content) == ["os"]

    def test_multiple_plain_imports(self):
        content = "import os, sys\n"
        result = extract_python_imports(content)
        assert "os" in result
        assert "sys" in result

    def test_from_import_dotted(self):
        content = "from elspais.graph.annotators import annotate_coverage\n"
        assert extract_python_imports(content) == ["elspais.graph.annotators"]

    def test_skips_relative_imports(self):
        content = "from .utils import helper\nfrom ..base import Base\n"
        assert extract_python_imports(content) == []

    def test_skips_comments(self):
        content = "# import os\nfrom pathlib import Path\n"
        assert extract_python_imports(content) == ["pathlib"]

    def test_mixed_imports(self):
        content = (
            "from __future__ import annotations\n"
            "import re\n"
            "from pathlib import Path\n"
            "from elspais.graph.builder import GraphBuilder\n"
        )
        result = extract_python_imports(content)
        assert "__future__" in result
        assert "re" in result
        assert "pathlib" in result
        assert "elspais.graph.builder" in result

    def test_stops_at_code(self):
        content = "from os import path\n" "\n" "def main():\n" "    import inside_func\n"
        result = extract_python_imports(content)
        assert result == ["os"]

    def test_empty_content(self):
        assert extract_python_imports("") == []

    def test_type_checking_imports(self):
        content = (
            "from __future__ import annotations\n"
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from elspais.graph.builder import TraceGraph\n"
        )
        result = extract_python_imports(content)
        assert "elspais.graph.builder" in result

    def test_only_comments_and_blanks(self):
        content = "# just a comment\n\n# another\n"
        assert extract_python_imports(content) == []

    def test_from_import_with_parens(self):
        """Multi-line from import using parentheses."""
        content = (
            "from elspais.graph.builder import (\n" "    TraceGraph,\n" "    GraphBuilder,\n" ")\n"
        )
        result = extract_python_imports(content)
        assert "elspais.graph.builder" in result


class TestModuleToSourcePath:
    def test_resolves_module_in_src(self, tmp_path):
        # Create src/elspais/graph/annotators.py
        mod_path = tmp_path / "src" / "elspais" / "graph"
        mod_path.mkdir(parents=True)
        (mod_path / "annotators.py").write_text("# module")

        result = module_to_source_path("elspais.graph.annotators", tmp_path)
        assert result == Path("src/elspais/graph/annotators.py")

    def test_resolves_module_at_root(self, tmp_path):
        # Create utils.py at repo root
        (tmp_path / "utils.py").write_text("# module")

        result = module_to_source_path("utils", tmp_path, source_roots=["", "src"])
        assert result == Path("utils.py")

    def test_resolves_package_init(self, tmp_path):
        # Create src/elspais/__init__.py (package)
        pkg_path = tmp_path / "src" / "elspais"
        pkg_path.mkdir(parents=True)
        (pkg_path / "__init__.py").write_text("# package")

        result = module_to_source_path("elspais", tmp_path)
        assert result == Path("src/elspais/__init__.py")

    def test_returns_none_for_missing(self, tmp_path):
        result = module_to_source_path("nonexistent.module", tmp_path)
        assert result is None

    def test_custom_source_roots(self, tmp_path):
        # Create lib/mymod.py
        (tmp_path / "lib").mkdir()
        (tmp_path / "lib" / "mymod.py").write_text("# module")

        result = module_to_source_path("mymod", tmp_path, source_roots=["lib"])
        assert result == Path("lib/mymod.py")

    def test_prefers_first_source_root(self, tmp_path):
        # Create both src/mod.py and mod.py
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "mod.py").write_text("# in src")
        (tmp_path / "mod.py").write_text("# at root")

        result = module_to_source_path("mod", tmp_path, source_roots=["src", ""])
        assert result == Path("src/mod.py")

    def test_default_source_roots_src_first(self, tmp_path):
        """Default source_roots=["src", ""] tries src/ before root."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "mymod.py").write_text("# in src")

        result = module_to_source_path("mymod", tmp_path)
        assert result == Path("src/mymod.py")

    def test_nested_package_init(self, tmp_path):
        """Deep nested package resolves via __init__.py."""
        pkg = tmp_path / "src" / "a" / "b" / "c"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("# deep package")

        result = module_to_source_path("a.b.c", tmp_path)
        assert result == Path("src/a/b/c/__init__.py")
