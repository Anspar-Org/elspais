# Verifies: REQ-d00251-L
"""Regression: a requirement header is recognised under the repository's own
identifier configuration, whatever spelling that configuration admits.

Root cause: the requirement transformer re-checked an already-tokenised
header against a hand-written identifier pattern that assumed an
all-uppercase namespace joined to an ``[A-Za-z0-9-]`` component. The Lark
terminal that produced the token was built from the repository's configured
grammar, so the two disagreed for any configuration outside that
assumption -- and the hand-written one won by *discarding*: the block
became a REMAINDER, the requirement left the graph, and nothing was
reported. A later ``elspais fix`` would then re-render the file from a
graph that no longer knew it held a requirement.

The triggers below are ordinary, legal configurations: a namespace
containing a digit, a ``snake_case`` component style, and a mixed-case
namespace. Every ``.elspais.toml`` in this repository happens to use an
all-uppercase namespace with a ``-`` boundary, which is why the estate's
own fixtures never caught it.

Reproduced through the production pipeline (``elspais.graph.factory
.build_graph``) against an on-disk project, in the style of
``test_assertion_separator_combinations.py``: the assertion is on the
built graph, never on the shape of any pattern.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.graph.GraphNode import NodeKind

_CONFIG_TEMPLATE = """\
version = 3

[project]
name = "grammartest"
namespace = "{namespace}"

[id-patterns]
canonical = "{{namespace}}-{{level.letter}}{{component}}"

[id-patterns.component]
style = "{style}"
{component_extra}
[id-patterns.assertions]
label_style = "uppercase"
separator = "{sep}"

[levels.prd]
rank = 1
letter = "p"
implements = []
"""

_SPEC_TEMPLATE = """\
# {req_id}: Widget

The system provides widgets.

## Assertions

A. The system SHALL frob.

B. The system SHALL twiddle.

*End* *{req_id}*
"""


def _make_project(
    tmp_path: Path,
    namespace: str,
    style: str,
    sep: str,
    req_id: str,
) -> Path:
    """Write a minimal on-disk project: one config, one spec file holding a
    single requirement authored under that config's identifier grammar."""
    project = tmp_path / "project"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "prd.md").write_text(_SPEC_TEMPLATE.format(req_id=req_id), encoding="utf-8")

    component_extra = "digits = 5\nleading_zeros = true\n" if style == "numeric" else ""
    (project / ".elspais.toml").write_text(
        _CONFIG_TEMPLATE.format(
            namespace=namespace,
            style=style,
            sep=sep,
            component_extra=component_extra,
        ),
        encoding="utf-8",
    )
    return project


# (namespace, component style, assertion separator, authored identifier)
#
# The separator is "/" for the snake_case row because a component under that
# style may legally contain the default "-"-adjacent punctuation the config
# layer guards (REQ-d00251-F): the boundary character must be one the
# component cannot contain, and configuring it properly is part of
# configuring that style at all.
_GRAMMARS = [
    pytest.param("EVS2", "numeric", "-", "EVS2-p00001", id="digit-bearing-namespace"),
    pytest.param("REQ", "snake_case", "/", "REQ-puser_auth", id="snake_case-component"),
    pytest.param("Evs", "numeric", "-", "Evs-p00001", id="mixed-case-namespace"),
]


class TestHeaderRecognisedUnderRepositoryGrammar:
    """Validates REQ-d00251-L: a repository's identifier grammar is derived
    from that repository's own identifier configuration."""

    # Verifies: REQ-d00251-L
    @pytest.mark.parametrize("namespace,style,sep,req_id", _GRAMMARS)
    def test_req_d00251_l_header_parses_as_requirement(
        self, namespace, style, sep, req_id, tmp_path
    ):
        """A requirement whose identifier its own configuration admits is in
        the graph as a REQUIREMENT, under the id it was authored with."""
        from elspais.graph.factory import build_graph

        project = _make_project(tmp_path, namespace, style, sep, req_id)
        graph = build_graph(
            config_path=project / ".elspais.toml",
            repo_root=project,
            scan_code=False,
            scan_tests=False,
        )

        node = graph.find_by_id(req_id)
        assert node is not None, (
            f"{req_id!r} is absent from the graph. Its header was authored "
            f"under this repository's own configuration (namespace="
            f"{namespace!r}, component style={style!r}), so the grammar that "
            f"reads it must be the one that configuration produces. Graph "
            f"holds: {sorted(n.id for n in graph.iter_by_kind(NodeKind.REQUIREMENT))}"
        )
        assert (
            node.kind == NodeKind.REQUIREMENT
        ), f"{req_id!r} is in the graph as {node.kind}, not a REQUIREMENT"

    # Verifies: REQ-d00251-L
    @pytest.mark.parametrize("namespace,style,sep,req_id", _GRAMMARS)
    def test_req_d00251_l_header_is_not_demoted_to_prose(
        self, namespace, style, sep, req_id, tmp_path
    ):
        """The requirement block is not silently swept into REMAINDER text.

        A header the reading grammar fails to recognise does not raise -- the
        block is claimed as prose instead, which is how the whole requirement
        left the graph without a diagnostic.
        """
        from elspais.graph.factory import build_graph

        project = _make_project(tmp_path, namespace, style, sep, req_id)
        graph = build_graph(
            config_path=project / ".elspais.toml",
            repo_root=project,
            scan_code=False,
            scan_tests=False,
        )

        swallowed = [
            (node, text)
            for node in graph.iter_by_kind(NodeKind.REMAINDER)
            for text in [node.get_field("text") or node.get_field("raw_text") or ""]
            if req_id in text
        ]
        assert not swallowed, (
            f"The header for {req_id!r} was demoted to prose: it appears in "
            f"{len(swallowed)} REMAINDER node(s) rather than being parsed as "
            f"a requirement. First offending remainder ({swallowed[0][0].id}):\n"
            f"{swallowed[0][1]!r}"
        )

    # Verifies: REQ-d00251-L
    @pytest.mark.parametrize("namespace,style,sep,req_id", _GRAMMARS)
    def test_req_d00251_l_assertions_reachable_under_grammar(
        self, namespace, style, sep, req_id, tmp_path
    ):
        """The recognised requirement carries its authored assertions, so a
        header read under the configured grammar yields a whole requirement
        rather than a truncated one."""
        from elspais.graph.factory import build_graph

        project = _make_project(tmp_path, namespace, style, sep, req_id)
        graph = build_graph(
            config_path=project / ".elspais.toml",
            repo_root=project,
            scan_code=False,
            scan_tests=False,
        )

        node = graph.find_by_id(req_id)
        assert node is not None, f"{req_id!r} is absent from the graph"

        labels = sorted(
            child.get_field("label")
            for child in node.iter_children()
            if child.kind == NodeKind.ASSERTION
        )
        assert labels == ["A", "B"], f"Expected assertions A and B under {req_id!r}, got {labels}"
