# Verifies: REQ-p00006-A, REQ-p00006-B, REQ-p00006-C
"""Tests for the embedded data layer (Phase 1 of Unified Trace Viewer).

Validates that HTMLGenerator produces embedded JSON indexes matching
the API response shapes used by the Flask server.
"""

from __future__ import annotations

import html as _html
import json
import re
from pathlib import Path

import pytest

from elspais.config import get_config
from elspais.graph.factory import build_graph
from tests.embedded_page import (
    EMBEDDED_KEYS,
    embedded_block_text,
    embedded_data,
    embedded_gzip,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "hht-like"


@pytest.fixture
def graph():
    """Build a graph from the hht-like fixture."""
    config = get_config(start_path=FIXTURE_DIR, quiet=True)
    return build_graph(config=config, repo_root=FIXTURE_DIR)


@pytest.fixture
def generator(graph):
    """Create an HTMLGenerator with coverage annotations applied."""
    from elspais.html.generator import HTMLGenerator

    gen = HTMLGenerator(graph, base_path=str(FIXTURE_DIR))
    gen._annotate_git_state()
    return gen


class TestBuildNodeIndex:
    """Validates REQ-p00006-A: Node index matches /api/node/ response shape."""

    # Verifies: REQ-d00321-B
    def test_REQ_d00321_B_node_index_holds_the_nodes_the_page_opens(self, generator, graph):
        """The index holds an entry for every node the page can open, and no other.

        The page opens a node from a tree row, or from a parent, a requirement
        child or a link shown on an open card. A REMAINDER is never opened (its
        text is inside its owner's entry), and a FILE only where a card links to it.
        """
        from elspais.graph import NodeKind

        index = generator._build_node_index()
        assert len(index) > 0

        for row in generator._build_tree_data():
            assert row["id"] in index, f"tree row {row['id']} has no index entry"

        for entry_id, entry in index.items():
            targets = list(entry.get("parents") or ())
            targets += [c for c in entry.get("children") or () if c.get("kind") == "requirement"]
            targets += [
                link
                for link in entry.get("links") or ()
                if link.get("kind") != NodeKind.REMAINDER.value
            ]
            for target in targets:
                assert target["id"] in index, f"{entry_id} opens {target['id']}, not indexed"

        linked_files = {
            link["id"]
            for entry in index.values()
            for link in entry.get("links") or ()
            if link.get("kind") == NodeKind.FILE.value
        }
        for node in graph.all_nodes():
            if node.kind == NodeKind.REMAINDER:
                assert node.id not in index, f"REMAINDER {node.id} is indexed"
            elif node.kind == NodeKind.FILE:
                assert (node.id in index) == (node.id in linked_files), node.id
            else:
                assert node.id in index, f"Missing node {node.id} from index"

    # Verifies: REQ-p00006-A
    def test_REQ_p00006_A_node_index_matches_api_shape(self, generator, graph):
        """Each node entry should have the standard API envelope fields."""
        index = generator._build_node_index()
        for node_id, data in index.items():
            assert "id" in data, f"Node {node_id} missing 'id'"
            assert "kind" in data, f"Node {node_id} missing 'kind'"
            assert "title" in data, f"Node {node_id} missing 'title'"
            assert "source" in data, f"Node {node_id} missing 'source'"
            assert "children" in data, f"Node {node_id} missing 'children'"
            assert "parents" in data, f"Node {node_id} missing 'parents'"
            assert "properties" in data, f"Node {node_id} missing 'properties'"

    # Verifies: REQ-p00006-A
    def test_REQ_p00006_A_requirement_node_has_correct_properties(self, generator, graph):
        """Requirement nodes should have level, status, hash in properties."""
        from elspais.graph import NodeKind

        index = generator._build_node_index()
        for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
            data = index[node.id]
            assert data["kind"] == "requirement"
            props = data["properties"]
            assert "level" in props
            assert "status" in props
            assert "hash" in props


class TestBuildCoverageIndex:
    """Validates REQ-p00006-B: Coverage index matches API response shapes."""

    # Verifies: REQ-p00006-B
    def test_REQ_p00006_B_coverage_index_has_all_requirements(self, generator, graph):
        """Coverage index should have an entry for every requirement."""
        from elspais.graph import NodeKind

        index = generator._build_coverage_index()
        req_count = sum(1 for _ in graph.nodes_by_kind(NodeKind.REQUIREMENT))
        assert len(index) == req_count

    # Verifies: REQ-p00006-B
    def test_REQ_p00006_B_coverage_entry_has_test_and_code(self, generator):
        """Each coverage entry should have 'test' and 'code' sub-dicts."""
        index = generator._build_coverage_index()
        for req_id, entry in index.items():
            assert "test" in entry, f"Missing 'test' in coverage for {req_id}"
            assert "code" in entry, f"Missing 'code' in coverage for {req_id}"

    # Verifies: REQ-p00006-B
    def test_REQ_p00006_B_test_coverage_matches_api_shape(self, generator):
        """Test coverage data should have success, assertion_tests, total_pct fields."""
        index = generator._build_coverage_index()
        for _req_id, entry in index.items():
            test_data = entry["test"]
            assert "success" in test_data
            assert "assertion_tests" in test_data
            assert "total_pct" in test_data

    # Verifies: REQ-p00006-B
    def test_REQ_p00006_B_code_coverage_matches_api_shape(self, generator):
        """Code coverage data should have success, assertion_code, total_pct fields."""
        index = generator._build_coverage_index()
        for _req_id, entry in index.items():
            code_data = entry["code"]
            assert "success" in code_data
            assert "assertion_code" in code_data
            assert "total_pct" in code_data


class TestBuildStatusData:
    """Validates REQ-p00006-C: Status data matches /api/status response shape."""

    # Verifies: REQ-p00006-C
    def test_REQ_p00006_C_status_data_has_required_fields(self, generator):
        """Status data should have node_counts, root_count, total_nodes."""
        data = generator._build_status_data()
        assert "node_counts" in data
        assert "root_count" in data
        assert "total_nodes" in data
        assert "has_orphans" in data
        assert "has_unresolved_references" in data
        assert "has_malformed_references" in data

    # Verifies: REQ-p00006-C
    def test_REQ_p00006_C_status_node_counts_are_positive(self, generator):
        """Node counts should contain at least requirement entries."""
        data = generator._build_status_data()
        assert data["total_nodes"] > 0
        assert "requirement" in data["node_counts"]


class TestEmbeddedDataInHTML:
    """Validates REQ-p00006-A: the embedded content appears in generated HTML output."""

    # Verifies: REQ-p00006-A
    def test_REQ_p00006_A_html_carries_every_embedded_value(self, graph):
        """A page with embedded content carries one block holding the tree, the
        sources, the node index, the coverage index and the status."""
        from elspais.html.generator import HTMLGenerator

        gen = HTMLGenerator(graph, base_path=str(FIXTURE_DIR))
        html = gen.generate(embed_content=True)

        assert html.count('id="embedded-data"') == 1
        data = embedded_data(html)
        assert data["tree"] and data["sources"] and data["nodes"] and data["coverage"]
        assert data["status"]["total_nodes"] > 0

    # Verifies: REQ-p00006-A
    def test_REQ_p00006_A_html_without_embed_carries_empty_values(self, graph):
        """A page generated without embedded content carries the block holding nothing."""
        from elspais.html.generator import HTMLGenerator

        gen = HTMLGenerator(graph, base_path=str(FIXTURE_DIR))
        html = gen.generate(embed_content=False)

        assert embedded_data(html) == {
            "tree": [],
            "sources": {},
            "nodes": {},
            "coverage": {},
            "status": {},
        }


def _plain_lines(highlighted: list[str]) -> list[str]:
    """The text of highlighted lines: markup removed, character references resolved."""
    return [_html.unescape(re.sub(r"<[^>]*>", "", line)) for line in highlighted]


# Text that ends a script element early, or makes the browser look for the end
# of a comment before it will end one.
SCRIPT_CLOSER = "</script>"
COMMENT_OPENER = "<!-- a comment -->"
# A line of a source file that no node's own content carries.
SENTINEL = "UNCITED_SENTINEL_LINE"

_HOSTILE_SPEC = f"""# Product

## REQ-p00001: Alpha

**Level**: prd | **Status**: Active

Alpha body mentions {SCRIPT_CLOSER} and {COMMENT_OPENER} inline.

### Assertions

A. The tool SHALL alpha.

*End* *Alpha* | **Hash**: 00000000
"""

_HOSTILE_CODE = f'''"""Module."""

{SENTINEL} = "{SCRIPT_CLOSER}{COMMENT_OPENER}"


# Implements: REQ-p00001-A
def alpha():
    return 1
'''


@pytest.fixture
def hostile_repo(tmp_path: Path) -> Path:
    """A repository whose spec and code text hold a script closer and a comment opener."""
    (tmp_path / ".elspais.toml").write_text(
        'version = 5\n\n[project]\nname = "emb"\nnamespace = "REQ"\n', encoding="utf-8"
    )
    (tmp_path / "spec").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "spec" / "prd.md").write_text(_HOSTILE_SPEC, encoding="utf-8")
    (tmp_path / "src" / "app.py").write_text(_HOSTILE_CODE, encoding="utf-8")
    return tmp_path


def _embedded_page(repo: Path) -> str:
    from elspais.html.generator import HTMLGenerator

    graph = build_graph(repo_root=repo)
    return HTMLGenerator(graph, base_path=str(repo)).generate(embed_content=True)


def _compact_json(value) -> bytes:
    """A value as the page's JSON spells it, before compression."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class TestEmbeddedSourceIsCarriedOnce:
    """Validates REQ-d00321-A: each embedded source file's text is carried once."""

    # Verifies: REQ-d00321-A
    def test_REQ_d00321_A_each_file_is_carried_once_as_highlighted_lines(self, hostile_repo):
        data = embedded_data(_embedded_page(hostile_repo))
        sources = data["sources"]

        assert set(sources) == {"spec/prd.md", "src/app.py"}
        for path, entry in sources.items():
            assert set(entry) == {"lines", "language"}, f"{path} carries {sorted(entry)}"
            expected = (hostile_repo / path).read_text(encoding="utf-8").split("\n")
            if expected[-1] == "":
                expected.pop()
            assert _plain_lines(entry["lines"]) == expected, path

        for key in EMBEDDED_KEYS:
            if key == "sources":
                continue
            assert SENTINEL not in json.dumps(data[key], ensure_ascii=False), (
                f"{key} carries source text a node's own content does not hold"
            )

    # Verifies: REQ-d00321-A
    def test_REQ_d00321_A_sources_are_proportionate_to_the_files(self, graph):
        """The embedded sources, before compression, stay within a small multiple
        of the files they embed.

        Highlighting markup costs a few times the text. Carrying the text a
        second time beside it, or once per containing node, exceeds the bound.
        """
        from elspais.html.generator import HTMLGenerator

        page = HTMLGenerator(graph, base_path=str(FIXTURE_DIR)).generate(embed_content=True)
        sources = embedded_data(page)["sources"]
        assert sources, "the fixture embeds no source files, so this measures nothing"

        embedded_bytes = sum(len((FIXTURE_DIR / path).read_bytes()) for path in sources)
        ratio = len(_compact_json(sources)) / embedded_bytes
        assert ratio <= 5, f"the embedded sources are {ratio:.1f}x the embedded files"


class TestEmbeddedValuesStayData:
    """Validates REQ-d00321-C: every embedded value survives as data."""

    # Verifies: REQ-d00321-C
    def test_REQ_d00321_C_every_value_decodes_whole(self, hostile_repo):
        """A value holding a script closer or a comment opener does not cut the block short."""
        data = embedded_data(_embedded_page(hostile_repo))

        app_lines = _plain_lines(data["sources"]["src/app.py"]["lines"])
        assert f'{SENTINEL} = "{SCRIPT_CLOSER}{COMMENT_OPENER}"' in app_lines
        spec_lines = _plain_lines(data["sources"]["spec/prd.md"]["lines"])
        assert any(SCRIPT_CLOSER in line and COMMENT_OPENER in line for line in spec_lines)
        body = json.dumps(data["nodes"]["REQ-p00001"], ensure_ascii=False)
        assert SCRIPT_CLOSER in body and COMMENT_OPENER in body

    # Verifies: REQ-d00321-C
    def test_REQ_d00321_C_the_block_holds_no_closer_or_comment_opener(self, hostile_repo):
        """Negative: the page text of the block is base64 alone, so it spells
        neither an end-tag opener nor a comment opener."""
        page = _embedded_page(hostile_repo)
        text = embedded_block_text(page)

        assert re.fullmatch(r"[A-Za-z0-9+/]*={0,2}", text), "the block holds more than base64"
        assert "</" not in text and "<!--" not in text
        assert page.count("<script") == page.count(SCRIPT_CLOSER), (
            "a script element ends where no script element was opened"
        )


class TestEmbeddedContentIsCompressed:
    """Validates REQ-d00321-D: the embedded content is carried compressed."""

    # Verifies: REQ-d00321-D
    def test_REQ_d00321_D_the_block_carries_a_gzip_stream(self, graph):
        from elspais.html.generator import HTMLGenerator

        page = HTMLGenerator(graph, base_path=str(FIXTURE_DIR)).generate(embed_content=True)

        assert embedded_gzip(page)[:2] == b"\x1f\x8b", "the block does not carry gzip"

    # Verifies: REQ-d00321-D
    def test_REQ_d00321_D_the_block_is_a_fraction_of_its_content(self, graph):
        """The block's page text is a small fraction of the JSON it restores to.

        Over the fixture the block is about a tenth of that JSON. Carrying the
        content uncompressed, even spelled in base64, exceeds the bound.
        """
        from elspais.html.generator import HTMLGenerator

        page = HTMLGenerator(graph, base_path=str(FIXTURE_DIR)).generate(embed_content=True)
        block = embedded_block_text(page).encode("ascii")
        content = _compact_json(embedded_data(page))

        ratio = len(block) / len(content)
        assert ratio <= 0.25, f"the block is {ratio:.2f}x the content it carries"


def _as_page_reads_it(value):
    """A value as JSON hands it back: tuples become lists, keys become strings."""
    return json.loads(json.dumps(value, ensure_ascii=False))


class TestEmbeddedContentIsRestored:
    """Validates REQ-d00321-E: the embedded content restores exactly."""

    # Verifies: REQ-d00321-E
    def test_REQ_d00321_E_compression_round_trips_any_text(self):
        """Decompressing restores a value holding non-ASCII text, a script
        closer and a comment opener exactly as it was."""
        import base64
        import gzip

        from elspais.html.generator import compress_embedded

        value = {
            "text": "na\u00efve caf\u00e9 \u2014 \u2713 \U0001f600",
            "markup": f"{SCRIPT_CLOSER} {COMMENT_OPENER}",
            "lines": ["", "  indented", "tab\there", 'back\\slash "quoted"'],
            "nested": {"n": 1, "f": 0.5, "t": True, "z": None, "empty": []},
        }

        restored = json.loads(gzip.decompress(base64.b64decode(compress_embedded(value))))

        assert restored == value

    # Verifies: REQ-d00321-E
    def test_REQ_d00321_E_the_page_restores_what_the_generator_built(self, graph):
        """The block's content restores to the values the generator built."""
        from elspais.html.generator import HTMLGenerator

        gen = HTMLGenerator(graph, base_path=str(FIXTURE_DIR))
        page = gen.generate(embed_content=True)
        data = embedded_data(page)

        assert data["tree"] == _as_page_reads_it(gen._build_tree_data())
        assert data["sources"] == _as_page_reads_it(gen._collect_source_files())
        assert data["nodes"] == _as_page_reads_it(gen._build_node_index())
        assert data["coverage"] == _as_page_reads_it(gen._build_coverage_index())
        assert data["status"] == _as_page_reads_it(gen._build_status_data())
