"""Which terms are read in a federation member's text.

A member's text is read against the terms that member defines and the terms
every member its associate declarations reach defines, and no others. A
consumer may use its library's vocabulary; a library cannot mean its
consumer's.
"""

from __future__ import annotations

from pathlib import Path

from tests.core.graph_test_helpers import unmarked_term_requirement

_TOML = """version = 5

[project]
name = "{name}"
namespace = "{namespace}"

[terms]
markup_styles = ["*", "**"]
"""


def _write_member(
    base: Path,
    name: str,
    namespace: str,
    *,
    assertion: str,
    defines: tuple[str, ...] = (),
    associates: dict[str, str] | None = None,
) -> Path:
    """Write one member: a requirement whose assertion is *assertion*, as written.

    *defines* names the terms the member's glossary defines, and *associates*
    maps each member it declares (by directory name) to that member's
    namespace.
    """
    root = base / name
    spec = root / "spec"
    spec.mkdir(parents=True)
    toml = _TOML.format(name=name, namespace=namespace)
    for assoc_name, assoc_namespace in (associates or {}).items():
        toml += (
            f"\n[associates.{assoc_name}]\n"
            f'path = "../{assoc_name}"\n'
            f'namespace = "{assoc_namespace}"\n'
        )
    (root / ".elspais.toml").write_text(toml, encoding="utf-8")
    if defines:
        glossary = "# Glossary\n\n" + "".join(
            f"{term}\n: A {term.lower()} as {name} means it.\n\n" for term in defines
        )
        (spec / "glossary.md").write_text(glossary, encoding="utf-8")
    (spec / "dev.md").write_text(
        "# Dev\n\n"
        + unmarked_term_requirement(f"{namespace}-d00001", "dev", f"{name} rule", assertion),
        encoding="utf-8",
    )
    return root


def _build(root: Path):
    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    return build_graph(config=get_config(None, root), repo_root=root)


def _consumer_and_library(tmp_path: Path) -> Path:
    """APP declares LIB. APP defines *Role*; LIB defines *Session*.

    Each assertion names both words unmarked, so each member's text uses its
    own term and the other member's.
    """
    _write_member(
        tmp_path,
        "lib",
        "LIB",
        assertion="The library SHALL open a session for the database role.",
        defines=("Session",),
    )
    return _write_member(
        tmp_path,
        "app",
        "APP",
        assertion="The app SHALL open a session for every role.",
        defines=("Role",),
        associates={"lib": "LIB"},
    )


def _references(graph, term: str) -> set[tuple[str, str]]:
    """The (namespace, node id) pairs the federation records for *term*."""
    return {(ref.namespace, ref.node_id) for ref in graph.terms.lookup(term).references}


def _term_rewrites(graph, req_id: str) -> list[tuple[str, str]]:
    """The term replacements the build recorded against *req_id*."""
    from elspais.graph import NodeKind

    node = next(n for n in graph.nodes_by_kind(NodeKind.REQUIREMENT) if n.id == req_id)
    return list(node.get_field("term_replacements") or [])


def _rewrite_reasons(graph, config) -> dict[str, str]:
    """``spec.needs_rewrite`` findings keyed by node id."""
    from elspais.commands.health import check_spec_needs_rewrite

    check = check_spec_needs_rewrite(graph, config)
    return {f.node_id: f.message for f in check.findings}


# Verifies: REQ-d00239-E
def test_REQ_d00239_E_library_text_does_not_read_its_consumers_term(tmp_path: Path):
    """LIB's "role" is its own plain word: no reference, no rewrite, no marking."""
    from elspais.config import get_config

    app = _consumer_and_library(tmp_path)
    graph = _build(app)

    assert {ns for ns, _ in _references(graph, "Role")} == {"APP"}

    reasons = _rewrite_reasons(graph, get_config(None, app))
    # LIB's own term is still unmarked there, so LIB is reported -- for
    # Session alone.
    assert "non_canonical_term" in reasons.get("LIB-d00001", "")
    assert [new for _old, new in _term_rewrites(graph, "LIB-d00001")] == ["*Session*"]


# Verifies: REQ-d00239-E
def test_REQ_d00239_E_library_whose_only_unmarked_word_is_a_consumer_term_is_not_reported(
    tmp_path: Path,
):
    """A library assertion naming only a consumer's term needs no rewrite."""
    from elspais.config import get_config

    _write_member(
        tmp_path,
        "lib",
        "LIB",
        assertion="The library SHALL grant the database role.",
        defines=("Session",),
    )
    app = _write_member(
        tmp_path,
        "app",
        "APP",
        assertion="The app SHALL check every role.",
        defines=("Role",),
        associates={"lib": "LIB"},
    )
    graph = _build(app)

    reasons = _rewrite_reasons(graph, get_config(None, app))
    assert "LIB-d00001" not in reasons, reasons
    assert _term_rewrites(graph, "LIB-d00001") == []
    assert {ns for ns, _ in _references(graph, "Role")} == {"APP"}


# Verifies: REQ-d00239-E
def test_REQ_d00239_E_consumer_text_reads_its_associates_term(tmp_path: Path):
    """APP's "session" references LIB's term and is reported for marking."""
    from elspais.config import get_config

    app = _consumer_and_library(tmp_path)
    graph = _build(app)

    assert "APP" in {ns for ns, _ in _references(graph, "Session")}
    rewrites = {new for _old, new in _term_rewrites(graph, "APP-d00001")}
    assert "*Session*" in rewrites
    assert "non_canonical_term" in _rewrite_reasons(graph, get_config(None, app)).get(
        "APP-d00001", ""
    )


# Verifies: REQ-d00239-E
def test_REQ_d00239_E_each_member_reads_its_own_terms(tmp_path: Path):
    """A member's own term is recorded and marked in its own text, as alone."""
    app = _consumer_and_library(tmp_path)
    graph = _build(app)

    assert "APP" in {ns for ns, _ in _references(graph, "Role")}
    assert "LIB" in {ns for ns, _ in _references(graph, "Session")}
    assert "*Role*" in {new for _old, new in _term_rewrites(graph, "APP-d00001")}
    assert "*Session*" in {new for _old, new in _term_rewrites(graph, "LIB-d00001")}


# Verifies: REQ-d00239-E
def test_REQ_d00239_E_transitive_associates_term_is_read_by_the_root(tmp_path: Path):
    """ROOT -> MID -> LEAF: ROOT reads LEAF's term; LEAF does not read ROOT's."""
    from elspais.config import get_config

    _write_member(
        tmp_path,
        "leaf",
        "LEAF",
        assertion="The leaf SHALL hold a gadget and a widget.",
        defines=("Gadget",),
    )
    _write_member(
        tmp_path,
        "mid",
        "MID",
        assertion="The middle SHALL pass a gadget on.",
        associates={"leaf": "LEAF"},
    )
    root = _write_member(
        tmp_path,
        "root",
        "ROOT",
        assertion="The root SHALL use a gadget in a widget.",
        defines=("Widget",),
        associates={"mid": "MID"},
    )
    graph = _build(root)

    assert {ns for ns, _ in _references(graph, "Gadget")} == {"LEAF", "MID", "ROOT"}
    assert {ns for ns, _ in _references(graph, "Widget")} == {"ROOT"}

    reasons = _rewrite_reasons(graph, get_config(None, root))
    assert "*Gadget*" in {new for _old, new in _term_rewrites(graph, "ROOT-d00001")}
    assert "non_canonical_term" in reasons.get("ROOT-d00001", "")
    assert [new for _old, new in _term_rewrites(graph, "LEAF-d00001")] == ["*Gadget*"]


# Verifies: REQ-d00239-E
def test_REQ_d00239_E_marking_hashed_text_uses_the_members_own_terms(tmp_path: Path):
    """Marking a library's assertion marks its term and leaves the consumer's alone."""
    from elspais.graph import NodeKind
    from elspais.graph.term_scanner import mark_terms_in_hashed_text

    app = _consumer_and_library(tmp_path)
    graph = _build(app)
    requirements = {n.id: n for n in graph.nodes_by_kind(NodeKind.REQUIREMENT)}

    mark_terms_in_hashed_text(graph, [requirements["LIB-d00001"], requirements["APP-d00001"]])

    lib_text = graph.find_by_id("LIB-d00001-A").get_label()
    app_text = graph.find_by_id("APP-d00001-A").get_label()
    assert lib_text == "The library SHALL open a *Session* for the database role."
    assert app_text == "The app SHALL open a *Session* for every *Role*."
