"""Tests for test_code_linker module."""

from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import GraphNode, NodeKind, SourceLocation
from elspais.graph.relations import EdgeKind
from elspais.graph.test_code_linker import (
    _build_code_index,
    _camel_to_snake,
    _extract_candidate_functions,
    link_tests_to_code,
)


class TestCamelToSnake:
    def test_simple(self):
        assert _camel_to_snake("AnnotateCoverage") == "annotate_coverage"

    def test_single_word(self):
        assert _camel_to_snake("Graph") == "graph"

    def test_consecutive_uppercase(self):
        assert _camel_to_snake("HTMLParser") == "html_parser"

    def test_already_lowercase(self):
        assert _camel_to_snake("already") == "already"

    def test_numbers(self):
        assert _camel_to_snake("Test2Things") == "test2_things"

    def test_empty_string(self):
        assert _camel_to_snake("") == ""

    def test_single_char(self):
        assert _camel_to_snake("A") == "a"

    def test_all_uppercase(self):
        result = _camel_to_snake("ABC")
        assert result == "abc"


class TestExtractCandidateFunctions:
    def test_strips_test_prefix(self):
        node = GraphNode(id="test:path::test_annotate_coverage", kind=NodeKind.TEST)
        node.set_field("function_name", "test_annotate_coverage")
        candidates = _extract_candidate_functions(node)
        assert "annotate_coverage" in candidates
        assert "annotate" in candidates

    def test_class_name_conversion(self):
        node = GraphNode(
            id="test:path::TestAnnotateCoverage::test_basic",
            kind=NodeKind.TEST,
        )
        node.set_field("function_name", "test_basic")
        node.set_field("class_name", "TestAnnotateCoverage")
        candidates = _extract_candidate_functions(node)
        assert "annotate_coverage" in candidates
        assert "basic" in candidates

    def test_no_test_prefix(self):
        node = GraphNode(id="test:path::helper", kind=NodeKind.TEST)
        node.set_field("function_name", "helper")
        candidates = _extract_candidate_functions(node)
        # "helper" doesn't start with "test_", no class → empty
        assert candidates == []

    def test_from_test_id_parsing(self):
        """Fallback: parse function_name from test ID when not in content."""
        node = GraphNode(
            id="test:path::TestGraph::test_build_graph",
            kind=NodeKind.TEST,
        )
        # No function_name or class_name set in content
        candidates = _extract_candidate_functions(node)
        assert "build_graph" in candidates
        assert "build" in candidates
        assert "graph" in candidates  # from TestGraph class

    def test_generates_progressive_shorter_matches(self):
        node = GraphNode(id="test:path::test_a_b_c_d", kind=NodeKind.TEST)
        node.set_field("function_name", "test_a_b_c_d")
        candidates = _extract_candidate_functions(node)
        assert candidates[0] == "a_b_c_d"
        assert "a_b_c" in candidates
        assert "a_b" in candidates
        assert "a" in candidates

    def test_test_only_prefix(self):
        """test_ with nothing after is empty stripped, so no candidates."""
        node = GraphNode(id="test:path::test_", kind=NodeKind.TEST)
        node.set_field("function_name", "test_")
        candidates = _extract_candidate_functions(node)
        assert candidates == []

    def test_class_without_test_prefix_ignored(self):
        """Class not starting with 'Test' should not contribute candidates."""
        node = GraphNode(id="test:path::Helpers::test_foo", kind=NodeKind.TEST)
        node.set_field("function_name", "test_foo")
        node.set_field("class_name", "Helpers")
        candidates = _extract_candidate_functions(node)
        assert "foo" in candidates
        # "Helpers" should NOT produce "helpers" because it doesn't start with "Test"
        assert "helpers" not in candidates


class TestBuildCodeIndex:
    def test_indexes_by_path_and_function(self):
        graph = TraceGraph()
        node = GraphNode(
            id="code:src/auth.py:10",
            kind=NodeKind.CODE,
            source=SourceLocation(path="src/auth.py", line=10),
        )
        node.set_field("function_name", "authenticate")
        graph._index["code:src/auth.py:10"] = node

        index = _build_code_index(graph)
        assert ("src/auth.py", "authenticate") in index
        assert node in index[("src/auth.py", "authenticate")]

    def test_skips_nodes_without_function_name(self):
        graph = TraceGraph()
        node = GraphNode(
            id="code:src/auth.py:10",
            kind=NodeKind.CODE,
            source=SourceLocation(path="src/auth.py", line=10),
        )
        # No function_name set
        graph._index["code:src/auth.py:10"] = node

        index = _build_code_index(graph)
        assert len(index) == 0

    def test_skips_nodes_without_source(self):
        graph = TraceGraph()
        node = GraphNode(
            id="code:src/auth.py:10",
            kind=NodeKind.CODE,
        )
        node.set_field("function_name", "authenticate")
        graph._index["code:src/auth.py:10"] = node

        index = _build_code_index(graph)
        assert len(index) == 0

    def test_multiple_code_nodes_same_function(self):
        """Two CODE nodes for same file+function are both indexed."""
        graph = TraceGraph()
        node1 = GraphNode(
            id="code:src/auth.py:10",
            kind=NodeKind.CODE,
            source=SourceLocation(path="src/auth.py", line=10),
        )
        node1.set_field("function_name", "authenticate")
        graph._index[node1.id] = node1

        node2 = GraphNode(
            id="code:src/auth.py:20",
            kind=NodeKind.CODE,
            source=SourceLocation(path="src/auth.py", line=20),
        )
        node2.set_field("function_name", "authenticate")
        graph._index[node2.id] = node2

        index = _build_code_index(graph)
        assert len(index[("src/auth.py", "authenticate")]) == 2

    def test_ignores_non_code_nodes(self):
        graph = TraceGraph()
        test_node = GraphNode(
            id="test:tests/test_auth.py::test_foo",
            kind=NodeKind.TEST,
            source=SourceLocation(path="tests/test_auth.py", line=1),
        )
        test_node.set_field("function_name", "test_foo")
        graph._index[test_node.id] = test_node

        index = _build_code_index(graph)
        assert len(index) == 0

    def test_normalizes_path(self):
        """Paths with ./ prefix and backslashes are normalized."""
        graph = TraceGraph()
        node = GraphNode(
            id="code:./src\\auth.py:10",
            kind=NodeKind.CODE,
            source=SourceLocation(path="./src\\auth.py", line=10),
        )
        node.set_field("function_name", "authenticate")
        graph._index[node.id] = node

        index = _build_code_index(graph)
        assert ("src/auth.py", "authenticate") in index


class TestLinkTestsToCode:
    def test_creates_validates_edge(self, tmp_path):
        """Integration test: TEST node linked to CODE node via imports."""
        # Create source file with a function
        src_dir = tmp_path / "src" / "elspais"
        src_dir.mkdir(parents=True)
        (src_dir / "__init__.py").write_text("")
        (src_dir / "auth.py").write_text("def authenticate():\n    pass\n")

        # Create test file that imports the source module
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_auth.py").write_text(
            "from elspais.auth import authenticate\n\n" "def test_authenticate():\n    pass\n"
        )

        # Build graph with CODE and TEST nodes
        graph = TraceGraph(repo_root=tmp_path)
        code_node = GraphNode(
            id="code:src/elspais/auth.py:1",
            kind=NodeKind.CODE,
            source=SourceLocation(path="src/elspais/auth.py", line=1),
        )
        code_node.set_field("function_name", "authenticate")
        graph._index[code_node.id] = code_node

        test_node = GraphNode(
            id="test:tests/test_auth.py::test_authenticate",
            kind=NodeKind.TEST,
            source=SourceLocation(path="tests/test_auth.py", line=3),
        )
        test_node.set_field("function_name", "test_authenticate")
        graph._index[test_node.id] = test_node

        result = link_tests_to_code(graph, tmp_path)

        assert result == 1
        # Check edge was created
        found_edge = False
        for edge in code_node.iter_outgoing_edges():
            if edge.target is test_node and edge.kind == EdgeKind.VALIDATES:
                found_edge = True
        assert found_edge

    def test_skips_test_with_existing_code_parent(self, tmp_path):
        """TEST nodes already linked to CODE should not get duplicate edges."""
        src_dir = tmp_path / "src" / "elspais"
        src_dir.mkdir(parents=True)
        (src_dir / "__init__.py").write_text("")
        (src_dir / "auth.py").write_text("def authenticate():\n    pass\n")

        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_auth.py").write_text(
            "from elspais.auth import authenticate\n\n" "def test_authenticate():\n    pass\n"
        )

        graph = TraceGraph(repo_root=tmp_path)
        code_node = GraphNode(
            id="code:src/elspais/auth.py:1",
            kind=NodeKind.CODE,
            source=SourceLocation(path="src/elspais/auth.py", line=1),
        )
        code_node.set_field("function_name", "authenticate")
        graph._index[code_node.id] = code_node

        test_node = GraphNode(
            id="test:tests/test_auth.py::test_authenticate",
            kind=NodeKind.TEST,
            source=SourceLocation(path="tests/test_auth.py", line=3),
        )
        test_node.set_field("function_name", "test_authenticate")
        graph._index[test_node.id] = test_node

        # Pre-link: CODE already has TEST as child
        code_node.link(test_node, EdgeKind.VALIDATES)

        result = link_tests_to_code(graph, tmp_path)
        assert result == 0  # No new edges

    def test_returns_zero_when_no_code_nodes(self, tmp_path):
        graph = TraceGraph(repo_root=tmp_path)
        test_node = GraphNode(
            id="test:tests/test_something.py::test_func",
            kind=NodeKind.TEST,
            source=SourceLocation(path="tests/test_something.py", line=1),
        )
        test_node.set_field("function_name", "test_func")
        graph._index[test_node.id] = test_node

        result = link_tests_to_code(graph, tmp_path)
        assert result == 0

    def test_class_name_matching(self, tmp_path):
        """TestAnnotateCoverage should match annotate_coverage function."""
        src_dir = tmp_path / "src" / "elspais"
        src_dir.mkdir(parents=True)
        (src_dir / "__init__.py").write_text("")
        (src_dir / "annotators.py").write_text("def annotate_coverage():\n    pass\n")

        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_annotators.py").write_text(
            "from elspais.annotators import annotate_coverage\n\n"
            "class TestAnnotateCoverage:\n"
            "    def test_basic(self):\n        pass\n"
        )

        graph = TraceGraph(repo_root=tmp_path)
        code_node = GraphNode(
            id="code:src/elspais/annotators.py:1",
            kind=NodeKind.CODE,
            source=SourceLocation(path="src/elspais/annotators.py", line=1),
        )
        code_node.set_field("function_name", "annotate_coverage")
        graph._index[code_node.id] = code_node

        test_node = GraphNode(
            id="test:tests/test_annotators.py::TestAnnotateCoverage::test_basic",
            kind=NodeKind.TEST,
            source=SourceLocation(path="tests/test_annotators.py", line=4),
        )
        test_node.set_field("function_name", "test_basic")
        test_node.set_field("class_name", "TestAnnotateCoverage")
        graph._index[test_node.id] = test_node

        result = link_tests_to_code(graph, tmp_path)
        assert result == 1

    def test_no_match_when_import_not_resolved(self, tmp_path):
        """If test imports a module we can't resolve, no edges created."""
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_missing.py").write_text(
            "from nonexistent_pkg.auth import authenticate\n\n"
            "def test_authenticate():\n    pass\n"
        )

        graph = TraceGraph(repo_root=tmp_path)
        # CODE node exists but its module path won't match unresolvable import
        code_node = GraphNode(
            id="code:src/auth.py:1",
            kind=NodeKind.CODE,
            source=SourceLocation(path="src/auth.py", line=1),
        )
        code_node.set_field("function_name", "authenticate")
        graph._index[code_node.id] = code_node

        test_node = GraphNode(
            id="test:tests/test_missing.py::test_authenticate",
            kind=NodeKind.TEST,
            source=SourceLocation(path="tests/test_missing.py", line=3),
        )
        test_node.set_field("function_name", "test_authenticate")
        graph._index[test_node.id] = test_node

        result = link_tests_to_code(graph, tmp_path)
        assert result == 0

    def test_skips_test_without_source(self, tmp_path):
        """TEST nodes without source location are skipped."""
        graph = TraceGraph(repo_root=tmp_path)
        code_node = GraphNode(
            id="code:src/auth.py:1",
            kind=NodeKind.CODE,
            source=SourceLocation(path="src/auth.py", line=1),
        )
        code_node.set_field("function_name", "authenticate")
        graph._index[code_node.id] = code_node

        test_node = GraphNode(
            id="test:unknown::test_authenticate",
            kind=NodeKind.TEST,
            # No source location
        )
        test_node.set_field("function_name", "test_authenticate")
        graph._index[test_node.id] = test_node

        result = link_tests_to_code(graph, tmp_path)
        assert result == 0

    def test_caches_imports_across_test_nodes(self, tmp_path):
        """Multiple test nodes from same file should reuse import cache."""
        src_dir = tmp_path / "src" / "elspais"
        src_dir.mkdir(parents=True)
        (src_dir / "__init__.py").write_text("")
        (src_dir / "auth.py").write_text("def login():\n    pass\n\n" "def logout():\n    pass\n")

        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_auth.py").write_text(
            "from elspais.auth import login, logout\n\n"
            "def test_login():\n    pass\n\n"
            "def test_logout():\n    pass\n"
        )

        graph = TraceGraph(repo_root=tmp_path)

        code_login = GraphNode(
            id="code:src/elspais/auth.py:1",
            kind=NodeKind.CODE,
            source=SourceLocation(path="src/elspais/auth.py", line=1),
        )
        code_login.set_field("function_name", "login")
        graph._index[code_login.id] = code_login

        code_logout = GraphNode(
            id="code:src/elspais/auth.py:4",
            kind=NodeKind.CODE,
            source=SourceLocation(path="src/elspais/auth.py", line=4),
        )
        code_logout.set_field("function_name", "logout")
        graph._index[code_logout.id] = code_logout

        test_login = GraphNode(
            id="test:tests/test_auth.py::test_login",
            kind=NodeKind.TEST,
            source=SourceLocation(path="tests/test_auth.py", line=3),
        )
        test_login.set_field("function_name", "test_login")
        graph._index[test_login.id] = test_login

        test_logout = GraphNode(
            id="test:tests/test_auth.py::test_logout",
            kind=NodeKind.TEST,
            source=SourceLocation(path="tests/test_auth.py", line=5),
        )
        test_logout.set_field("function_name", "test_logout")
        graph._index[test_logout.id] = test_logout

        result = link_tests_to_code(graph, tmp_path)
        assert result == 2
