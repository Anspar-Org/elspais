# Verifies: REQ-d00252
"""Validates REQ-d00252-B: Integrates: in non-spec files creates no edge."""
import subprocess
import textwrap
from pathlib import Path

from lark import Tree
from lark.lexer import Token

from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import NodeKind
from elspais.graph.parsers.lark.transformers.reference import ReferenceTransformer
from elspais.graph.relations import EdgeKind
from elspais.utilities.patterns import IdPatternConfig, IdResolver


def _resolver() -> IdResolver:
    config = IdPatternConfig.from_dict(
        {
            "project": {"namespace": "REQ"},
            "id-patterns": {
                "canonical": "{namespace}-{type.letter}{component}",
                "aliases": {"short": "{type.letter}{component}"},
                "types": {
                    "prd": {"level": 1, "aliases": {"letter": "p"}},
                    "dev": {"level": 3, "aliases": {"letter": "d"}},
                },
                "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
                "assertions": {"label_style": "uppercase", "max_count": 26},
            },
        }
    )
    return IdResolver(config)


def _single_ref(text: str) -> Tree:
    tok = Token("SINGLE_REF_LINE", text)
    tok.line = 1
    return Tree("single_ref", [tok])


def _write(repo: Path, rel: str, body: str) -> None:
    full = repo / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(textwrap.dedent(body).strip() + "\n")


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"],
        cwd=repo,
        check=True,
    )


def _build_code(tmp_path: Path):
    _write(
        tmp_path,
        ".elspais.toml",
        """
        version = 3
        [project]
        name = "demo"
        namespace = "REQ"
        [levels.dev]
        rank = 1
        letter = "d"
        implements = ["dev"]
        [scanning.spec]
        directories = ["spec"]
        [scanning.code]
        directories = ["src"]
        [scanning.test]
        enabled = false
        directories = []
        """,
    )
    _write(
        tmp_path,
        "spec/dev.md",
        """
        # REQ-d00001: Consumer requirement

        **Level**: dev | **Status**: Active

        ### Assertions

        A. The consumer SHALL integrate the upstream service.

        *End* *Consumer requirement*
        """,
    )
    _write(
        tmp_path,
        "src/lib.py",
        """
        # Integrates: REQ-d00001
        def thing():
            return 1
        """,
    )
    _git_init(tmp_path)
    return build_graph(repo_root=tmp_path, scan_code=True, scan_tests=False)


def _build_test(tmp_path: Path):
    _write(
        tmp_path,
        ".elspais.toml",
        """
        version = 3
        [project]
        name = "demo"
        namespace = "REQ"
        [levels.dev]
        rank = 1
        letter = "d"
        implements = ["dev"]
        [scanning.spec]
        directories = ["spec"]
        [scanning.code]
        directories = []
        [scanning.test]
        enabled = true
        directories = ["tests"]
        """,
    )
    _write(
        tmp_path,
        "spec/dev.md",
        """
        # REQ-d00001: Consumer requirement

        **Level**: dev | **Status**: Active

        ### Assertions

        A. The consumer SHALL integrate the upstream service.

        *End* *Consumer requirement*
        """,
    )
    _write(
        tmp_path,
        "tests/test_lib.py",
        """
        # Integrates: REQ-d00001
        def test_thing():
            assert True
        """,
    )
    _git_init(tmp_path)
    return build_graph(repo_root=tmp_path, scan_code=False, scan_tests=True)


def _req(graph):
    return next(n for n in graph.iter_by_kind(NodeKind.REQUIREMENT) if n.id == "REQ-d00001")


def test_REQ_d00252_B_integrates_in_code_file_creates_no_edge(tmp_path):
    graph = _build_code(tmp_path)
    req = _req(graph)
    assert all(
        e.kind not in (EdgeKind.IMPLEMENTS, EdgeKind.INTEGRATES) for e in req.iter_outgoing_edges()
    ), "Integrates: in a code file must not create a traceability edge"
    assert all(
        e.kind not in (EdgeKind.IMPLEMENTS, EdgeKind.INTEGRATES) for e in req.iter_incoming_edges()
    ), "Integrates: in a code file must not create an inbound traceability edge"


def test_REQ_d00252_B_integrates_in_test_file_creates_no_edge(tmp_path):
    graph = _build_test(tmp_path)
    req = _req(graph)
    assert all(
        e.kind not in (EdgeKind.IMPLEMENTS, EdgeKind.INTEGRATES, EdgeKind.VERIFIES)
        for e in req.iter_outgoing_edges()
    ), "Integrates: in a test file must not create a traceability edge"
    assert all(
        e.kind not in (EdgeKind.IMPLEMENTS, EdgeKind.INTEGRATES, EdgeKind.VERIFIES)
        for e in req.iter_incoming_edges()
    ), "Integrates: in a test file must not create an inbound traceability edge"


def test_REQ_d00252_B_integrates_ref_skipped_in_code_transformer():
    """An Integrates: comment must not be reclassified as an IMPLEMENTS ref.

    Drives the transformer directly because the reference grammar does not
    list ``Integrates`` as a keyword today; this guard ensures that if such
    a ref ever reaches the transformer it is dropped rather than falling
    back to ``implements``.
    """
    tx = ReferenceTransformer(_resolver(), "code_ref")
    assert tx._handle_single_ref(_single_ref("# Integrates: REQ-d00001")) is None
    # A genuine Implements ref must still be honored (no over-skipping).
    pc = tx._handle_single_ref(_single_ref("# Implements: REQ-d00001"))
    assert pc is not None
    assert pc.parsed_data["implements"] == ["REQ-d00001"]


def test_REQ_d00252_B_integrates_ref_skipped_in_test_transformer():
    """An Integrates: comment in a test file yields no parsed ref."""
    tx = ReferenceTransformer(_resolver(), "test_ref")
    assert tx._handle_single_ref(_single_ref("# Integrates: REQ-d00001")) is None
