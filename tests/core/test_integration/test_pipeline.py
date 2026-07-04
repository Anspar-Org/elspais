"""Integration tests for full Deserializer → MDparser → Graph pipeline."""

import tempfile
from pathlib import Path

import pytest

from elspais.config import find_config_file, load_config
from elspais.graph import NodeKind
from elspais.graph.builder import GraphBuilder
from elspais.graph.deserializer import DomainFile
from elspais.graph.parsers.lark import FileDispatcher
from elspais.graph.render import render_node
from elspais.utilities.patterns import build_resolver


def _make_resolver(config):
    """Build IdResolver from loaded config."""
    return build_resolver(config)


class TestFullPipeline:
    """Tests for the complete parsing pipeline."""

    # Verifies: REQ-o00050-A
    def test_pipeline_parses_all_requirements(self, integration_spec_dir):
        """Verify all requirements are parsed from spec files."""
        # Load config
        config_path = find_config_file(integration_spec_dir)
        config = load_config(config_path)

        # Create pattern config
        resolver = _make_resolver(config)

        # Create parser registry
        dispatcher = FileDispatcher(resolver)

        # Create deserializer for spec directory
        spec_dir = integration_spec_dir / "spec"
        deserializer = DomainFile(spec_dir, patterns=["*.md"])

        # Build graph
        builder = GraphBuilder(repo_root=integration_spec_dir)
        for content in deserializer.dispatch(dispatcher.dispatch_spec):
            builder.add_parsed_content(content)

        graph = builder.build()

        # Verify all requirements were found
        assert graph.find_by_id("REQ-p00001") is not None
        assert graph.find_by_id("REQ-p00002") is not None
        assert graph.find_by_id("REQ-o00001") is not None
        assert graph.find_by_id("REQ-o00002") is not None
        assert graph.find_by_id("REQ-o00003") is not None
        assert graph.find_by_id("REQ-o00004") is not None

    # Verifies: REQ-o00050-D
    def test_pipeline_creates_assertions(self, integration_spec_dir):
        """Verify assertions are created as child nodes."""
        config_path = find_config_file(integration_spec_dir)
        config = load_config(config_path)
        resolver = _make_resolver(config)
        dispatcher = FileDispatcher(resolver)

        spec_dir = integration_spec_dir / "spec"
        deserializer = DomainFile(spec_dir, patterns=["*.md"])

        builder = GraphBuilder(repo_root=integration_spec_dir)
        for content in deserializer.dispatch(dispatcher.dispatch_spec):
            builder.add_parsed_content(content)

        graph = builder.build()

        # REQ-p00001 should have 3 assertions
        p00001 = graph.find_by_id("REQ-p00001")
        assertions = [c for c in p00001.iter_children() if c.kind == NodeKind.ASSERTION]
        assert len(assertions) == 3

        # Verify assertion IDs
        assertion_ids = {a.id for a in assertions}
        assert "REQ-p00001-A" in assertion_ids
        assert "REQ-p00001-B" in assertion_ids
        assert "REQ-p00001-C" in assertion_ids

    # Verifies: REQ-o00050-C
    def test_pipeline_links_implements(self, integration_spec_dir):
        """Verify implements relationships are properly linked."""
        config_path = find_config_file(integration_spec_dir)
        config = load_config(config_path)
        resolver = _make_resolver(config)
        dispatcher = FileDispatcher(resolver)

        spec_dir = integration_spec_dir / "spec"
        deserializer = DomainFile(spec_dir, patterns=["*.md"])

        builder = GraphBuilder(repo_root=integration_spec_dir)
        for content in deserializer.dispatch(dispatcher.dispatch_spec):
            builder.add_parsed_content(content)

        graph = builder.build()

        # REQ-o00001 implements REQ-p00001-A
        o00001 = graph.find_by_id("REQ-o00001")
        p00001 = graph.find_by_id("REQ-p00001")

        # OPS req should have parent requirement (not assertion node)
        # with assertion_targets indicating which assertions it implements
        assert o00001.has_parent(p00001)

        # Verify the edge has assertion_targets=['A']
        for edge in p00001.iter_outgoing_edges():
            if edge.target.id == "REQ-o00001":
                assert edge.assertion_targets == ["A"]
                break
        else:
            raise AssertionError("Expected edge from REQ-p00001 to REQ-o00001 not found")

    # Verifies: REQ-d00071-A
    def test_pipeline_identifies_roots(self, integration_spec_dir):
        """Verify root nodes are correctly identified."""
        config_path = find_config_file(integration_spec_dir)
        config = load_config(config_path)
        resolver = _make_resolver(config)
        dispatcher = FileDispatcher(resolver)

        spec_dir = integration_spec_dir / "spec"
        deserializer = DomainFile(spec_dir, patterns=["*.md"])

        builder = GraphBuilder(repo_root=integration_spec_dir)
        for content in deserializer.dispatch(dispatcher.dispatch_spec):
            builder.add_parsed_content(content)

        graph = builder.build()

        # Only PRD requirements should be roots (no parents)
        assert graph.has_root("REQ-p00001")
        assert graph.has_root("REQ-p00002")

        # OPS requirements have parents, so not roots
        assert not graph.has_root("REQ-o00001")
        assert not graph.has_root("REQ-o00002")
        assert not graph.has_root("REQ-o00004")

    # Verifies: REQ-o00050-A
    def test_pipeline_node_counts(self, integration_spec_dir):
        """Verify expected node counts by type."""
        config_path = find_config_file(integration_spec_dir)
        config = load_config(config_path)
        resolver = _make_resolver(config)
        dispatcher = FileDispatcher(resolver)

        spec_dir = integration_spec_dir / "spec"
        deserializer = DomainFile(spec_dir, patterns=["*.md"])

        builder = GraphBuilder(repo_root=integration_spec_dir)
        for content in deserializer.dispatch(dispatcher.dispatch_spec):
            builder.add_parsed_content(content)

        graph = builder.build()

        # Count by type
        requirements = list(graph.nodes_by_kind(NodeKind.REQUIREMENT))
        assertions = list(graph.nodes_by_kind(NodeKind.ASSERTION))

        # 2 PRD + 4 OPS = 6 requirements
        assert len(requirements) == 6

        # 3 assertions (REQ-p00001) + 2 assertions (REQ-p00002) = 5 assertions
        assert len(assertions) == 5


# Verifies: REQ-d00081-D+E+G
class TestMultiAssertionPipelineExpansion:
    """Integration tests for multi-assertion expansion in the full pipeline.

    Validates REQ-d00081-D: Spec files using multi-assertion syntax expand into
    individual edges.
    Validates REQ-d00081-E: Code comments using multi-assertion syntax also expand
    (proving centralization).
    Validates REQ-d00081-G: When separator is empty/disabled, no expansion occurs.
    """

    def _build_graph(self, root_dir, multi_assertion_separator="+", include_code=False):
        """Helper to build a graph from the fixture directory.

        Args:
            root_dir: Root directory containing spec/ and optionally src/.
            multi_assertion_separator: Separator for multi-assertion expansion.
            include_code: Whether to also parse code files from src/.

        Returns:
            Built TraceGraph.
        """
        config_path = find_config_file(root_dir)
        config = load_config(config_path)
        resolver = _make_resolver(config)

        # Lark dispatcher for spec files
        dispatcher = FileDispatcher(resolver)

        # Parse spec files
        spec_dir = root_dir / "spec"
        spec_deserializer = DomainFile(spec_dir, patterns=["*.md"])

        builder = GraphBuilder(
            repo_root=root_dir,
            multi_assertion_separator=multi_assertion_separator,
        )
        for content in spec_deserializer.dispatch(dispatcher.dispatch_spec):
            builder.add_parsed_content(content)

        # Optionally parse code files via Lark FileDispatcher
        if include_code:
            code_dispatcher = FileDispatcher(resolver)
            code_dir = root_dir / "src"
            for py_file in sorted(code_dir.rglob("*.py")):
                text = py_file.read_text(encoding="utf-8")
                for parsed in code_dispatcher.dispatch_code(text, str(py_file)):
                    builder.add_parsed_content(parsed)

        return builder.build()

    def test_REQ_d00081_D_spec_multi_assertion_expands_to_individual_edges(
        self, multi_assertion_spec_dir
    ):
        """Multi-assertion syntax in spec Implements expands to individual edges.

        REQ-o00001 uses 'Implements: REQ-p00001-A+B+C' which should create
        three separate edges targeting assertions A, B, and C.
        """
        graph = self._build_graph(multi_assertion_spec_dir)

        # The OPS requirement should exist
        o00001 = graph.find_by_id("REQ-o00001")
        assert o00001 is not None, "REQ-o00001 should be in the graph"

        # The PRD requirement and its assertions should exist
        p00001 = graph.find_by_id("REQ-p00001")
        assert p00001 is not None

        for label in ("A", "B", "C"):
            assertion = graph.find_by_id(f"REQ-p00001-{label}")
            assert assertion is not None, f"Assertion REQ-p00001-{label} should exist"

        # REQ-o00001 should be linked under REQ-p00001 (parent)
        assert o00001.has_parent(p00001), "REQ-o00001 should have REQ-p00001 as parent"

        # Collect all assertion targets across edges from p00001 to o00001.
        # Each expanded assertion creates a separate edge with one target.
        all_targets = []
        for edge in p00001.iter_outgoing_edges():
            if edge.target.id == "REQ-o00001":
                all_targets.extend(edge.assertion_targets)
        assert len(all_targets) > 0, "Expected edges from REQ-p00001 to REQ-o00001"
        assert sorted(all_targets) == [
            "A",
            "B",
            "C",
        ], f"Expected assertion_targets ['A', 'B', 'C'], got {sorted(all_targets)}"

    def test_REQ_d00081_E_code_refs_resolve_through_same_builder(self, multi_assertion_spec_dir):
        """Code references resolve through the same builder as spec references.

        Both spec multi-assertion expansion (REQ-p00001-A+B+C in OPS) and
        code assertion references (# Implements: REQ-p00001-A, REQ-p00001-B)
        are processed by the same GraphBuilder.build(), proving centralization.
        The code file uses comma-separated assertion refs which the code parser
        captures individually; the builder resolves them to assertion nodes.
        """
        graph = self._build_graph(multi_assertion_spec_dir, include_code=True)

        # Find CODE nodes
        code_nodes = list(graph.nodes_by_kind(NodeKind.CODE))
        assert len(code_nodes) >= 1, "Should have at least one CODE node"

        # The code node should be linked to the parent requirement
        code_node = code_nodes[0]
        p00001 = graph.find_by_id("REQ-p00001")
        assert p00001 is not None

        # Code node should be a child of p00001 (via assertion target resolution)
        assert code_node.has_parent(
            p00001
        ), "CODE node should have REQ-p00001 as parent via assertion resolution"

        # Collect assertion targets across all edges from p00001 to the code node.
        # Both assertions A and B should be resolved from the code references.
        all_targets = []
        for edge in p00001.iter_outgoing_edges():
            if edge.target.id == code_node.id:
                all_targets.extend(edge.assertion_targets)
        assert len(all_targets) > 0, f"Expected edges from REQ-p00001 to CODE node {code_node.id}"
        assert sorted(all_targets) == [
            "A",
            "B",
        ], f"Expected assertion_targets ['A', 'B'], got {sorted(all_targets)}"

        # Verify spec multi-assertion expansion also worked in the same graph.
        # This proves both parser types share the same builder pipeline.
        o00001 = graph.find_by_id("REQ-o00001")
        assert o00001 is not None
        assert o00001.has_parent(p00001)
        spec_targets = []
        for edge in p00001.iter_outgoing_edges():
            if edge.target.id == "REQ-o00001":
                spec_targets.extend(edge.assertion_targets)
        assert sorted(spec_targets) == [
            "A",
            "B",
            "C",
        ], f"Spec multi-assertion should also expand, got {sorted(spec_targets)}"

    def test_REQ_d00081_G_empty_separator_disables_expansion(self, multi_assertion_spec_dir):
        """When multi_assertion_separator is empty, no expansion occurs.

        With separator disabled, 'REQ-p00001-A+B+C' is treated as a single
        literal reference ID which will not resolve to any known node,
        resulting in a broken reference.
        """
        graph = self._build_graph(multi_assertion_spec_dir, multi_assertion_separator="")

        # REQ-o00001 should exist but NOT be linked to REQ-p00001
        # because the literal ID "REQ-p00001-A+B+C" doesn't match any node
        o00001 = graph.find_by_id("REQ-o00001")
        assert o00001 is not None

        p00001 = graph.find_by_id("REQ-p00001")
        assert p00001 is not None

        # With no expansion, the literal "REQ-p00001-A+B+C" won't match
        # any node, so o00001 should NOT be a child of p00001
        assert not o00001.has_parent(
            p00001
        ), "With empty separator, multi-assertion should NOT expand"

        # The broken reference should be recorded
        broken = graph.broken_references()
        literal_targets = [br.target_id for br in broken]
        assert "REQ-p00001-A+B+C" in literal_targets, (
            f"Expected broken reference for literal 'REQ-p00001-A+B+C', " f"got {literal_targets}"
        )


# Verifies: REQ-d00081-D+E
class TestMultiAssertionSeparatorRoundTrip:
    """Regression tests for the configured-separator multi-assertion bug.

    The user reported that with ``[id-patterns.assertions]`` configured as
    ``separator = "/"`` and ``multi_separator = "/"``, references of the
    form ``EVS-PRD-event-log/A/B`` silently fail to resolve: the builder
    creates assertion node IDs using a hardcoded ``-`` (e.g.
    ``EVS-PRD-event-log-A``) while the multi-assertion expansion path uses
    the resolver's ``render_canonical()`` which honors the configured
    separator (producing ``EVS-PRD-event-log/A``). The mismatch lands the
    refs in ``_broken_references`` and no REFINES edges get wired.

    A symmetric bug exists on the render side: the ``_derive_*_refs``
    helpers in ``graph/render.py`` hardcode ``-`` between requirement ID
    and assertion label, and emit one ref per ``assertion_targets`` entry
    with no multi-assertion aggregation.

    These tests assert the CORRECT post-fix behavior. They are expected to
    FAIL until both bugs are fixed.
    """

    # Minimal config common to both parametrizations.
    _CONFIG_TEMPLATE = """\
[project]
name = "test"
namespace = "EVS"

[id-patterns]
canonical = "{{namespace}}-{{level.letter}}-{{component}}"
aliases = {{ short = "{{level.letter}}-{{component}}" }}

[id-patterns.component]
style = "kebab-case"

[id-patterns.assertions]
label_style = "uppercase"
separator = "{assert_sep}"
multi_separator = "{multi_sep}"

[levels.prd]
rank = 1
letter = "PRD"
implements = ["prd"]

[levels.dev]
rank = 2
letter = "DEV"
implements = ["dev", "prd"]

[scanning.spec]
directories = ["spec"]
"""

    _PRD_TEMPLATE = """\
# Event Logging PRD

## EVS-PRD-event-log: Event Logging

**Level**: PRD | **Status**: Active

The system SHALL log events.

## Assertions

A. The system SHALL log login events.
B. The system SHALL log logout events.

*End* *EVS-PRD-event-log*
"""

    _DEV_TEMPLATE = """\
# Event Storage DEV

## EVS-DEV-event-store: Event Storage

**Level**: DEV | **Status**: Active

**Refines**: {refines_ref}

The system SHALL store event records.

*End* *EVS-DEV-event-store*
"""

    def _build_project(self, tmpdir, assert_sep, multi_sep, refines_ref):
        """Materialize a spec directory + config and build a graph from it.

        Returns:
            Tuple ``(graph, dev_node, prd_node)``.
        """
        root = Path(tmpdir)
        spec_dir = root / "spec"
        spec_dir.mkdir()

        (spec_dir / "prd-event.md").write_text(self._PRD_TEMPLATE)
        (spec_dir / "dev-event.md").write_text(self._DEV_TEMPLATE.format(refines_ref=refines_ref))
        (root / ".elspais.toml").write_text(
            self._CONFIG_TEMPLATE.format(assert_sep=assert_sep, multi_sep=multi_sep)
        )

        config_path = find_config_file(root)
        config = load_config(config_path)
        resolver = build_resolver(config)
        dispatcher = FileDispatcher(resolver)
        deserializer = DomainFile(spec_dir, patterns=["*.md"])

        builder = GraphBuilder(
            repo_root=root,
            multi_assertion_separator=multi_sep,
            resolver=resolver,
            namespace="EVS",
        )
        for content in deserializer.dispatch(dispatcher.dispatch_spec):
            builder.add_parsed_content(content)
        graph = builder.build()

        prd_node = graph.find_by_id("EVS-PRD-event-log")
        dev_node = graph.find_by_id("EVS-DEV-event-store")
        return graph, dev_node, prd_node

    @pytest.mark.parametrize(
        "assert_sep, multi_sep, refines_ref, expected_assertion_ids",
        [
            pytest.param(
                "/",
                "/",
                "EVS-PRD-event-log/A/B",
                ("EVS-PRD-event-log/A", "EVS-PRD-event-log/B"),
                id="slash-separator",
            ),
            pytest.param(
                "-",
                "+",
                "EVS-PRD-event-log-A+B",
                ("EVS-PRD-event-log-A", "EVS-PRD-event-log-B"),
                id="default-plus-separator",
            ),
        ],
    )
    def test_multi_assertion_wires_refines_edges(
        self, assert_sep, multi_sep, refines_ref, expected_assertion_ids
    ):
        """Multi-assertion refines refs resolve to edges with assertion_targets.

        After the fix, the configured assertion separator must be honored by
        BOTH assertion node creation and reference expansion, so the lookup
        finds the assertion's parent requirement and a REFINES edge gets
        wired with ``assertion_targets`` containing the labels.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            graph, dev_node, prd_node = self._build_project(
                tmpdir, assert_sep, multi_sep, refines_ref
            )

            assert prd_node is not None, "PRD requirement must exist"
            assert dev_node is not None, "DEV requirement must exist"

            # Assertion nodes must be queryable under the configured separator.
            for assertion_id in expected_assertion_ids:
                node = graph.find_by_id(assertion_id)
                assert node is not None, (
                    f"Assertion node {assertion_id!r} should exist " f"(separator={assert_sep!r})"
                )
                assert node.kind == NodeKind.ASSERTION

            # No broken references for the multi-assertion form. The bug
            # currently records both expanded refs as broken.
            broken = graph.broken_references()
            broken_targets = [br.target_id for br in broken]
            offending = [t for t in broken_targets if t.startswith("EVS-PRD-event-log")]
            assert not offending, (
                f"Multi-assertion refs should resolve cleanly, but got "
                f"broken references: {offending}"
            )

            # REFINES edge(s) must exist from PRD requirement to DEV
            # requirement carrying both labels in ``assertion_targets``.
            refines_targets: list[str] = []
            for edge in dev_node.iter_incoming_edges():
                if edge.source.id == prd_node.id and edge.kind.name == "REFINES":
                    refines_targets.extend(edge.assertion_targets)

            assert sorted(refines_targets) == ["A", "B"], (
                f"Expected REFINES edge(s) from {prd_node.id} to {dev_node.id} "
                f"with assertion_targets ['A', 'B'], got {sorted(refines_targets)}"
            )

    @pytest.mark.parametrize(
        "assert_sep, multi_sep, refines_ref",
        [
            pytest.param("/", "/", "EVS-PRD-event-log/A/B", id="slash-separator"),
            pytest.param("-", "+", "EVS-PRD-event-log-A+B", id="default-plus-separator"),
        ],
    )
    def test_multi_assertion_round_trips_through_render(self, assert_sep, multi_sep, refines_ref):
        """Rendering a requirement aggregates multi-assertion refines refs.

        Post-fix, the renderer must:
        1. Use the configured assertion separator between requirement ID
           and label (not hardcoded ``-``).
        2. Aggregate multiple labels for the same target requirement using
           the configured ``multi_separator`` (e.g.
           ``EVS-PRD-event-log-A+B``), not emit one ref per label
           comma-separated.

        Currently:
        - Slash config: render produces the correct aggregated string by
          accident, because edges fail to wire (bug #1) so render falls
          back to the raw stored ``refines_refs`` field.
        - Default config: edges ARE wired but render emits
          ``EVS-PRD-event-log-A, EVS-PRD-event-log-B`` (one per label,
          comma-separated, no aggregation).

        Once bug #1 is fixed for the slash case, edges will wire and this
        test will exercise the same broken aggregation path that the
        default config exercises today — so locking down aggregation
        protects against both regressions.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            graph, dev_node, _prd_node = self._build_project(
                tmpdir, assert_sep, multi_sep, refines_ref
            )
            assert dev_node is not None

            # Pass the graph's resolver so render uses configured separators.
            # In production this is wired automatically by render_save via the
            # owning TraceGraph; tests calling render_node directly must pass it.
            rendered = render_node(dev_node, resolver=graph._resolver)

            # The Refines line must appear in the rendered output.
            assert "**Refines**:" in rendered, (
                f"Rendered DEV requirement must contain a Refines line.\n"
                f"Rendered output:\n{rendered}"
            )

            aggregated = f"EVS-PRD-event-log{assert_sep}A{multi_sep}B"
            assert aggregated in rendered, (
                f"Rendered Refines line must aggregate multi-assertion "
                f"labels as {aggregated!r}.\n"
                f"Rendered output:\n{rendered}"
            )

            # And it must NOT use the wrong (hardcoded ``-``) separator when
            # the configured separator is different.
            if assert_sep != "-":
                wrong_a = "EVS-PRD-event-log-A"
                wrong_b = "EVS-PRD-event-log-B"
                assert wrong_a not in rendered, (
                    f"Rendered output uses hardcoded '-' separator "
                    f"({wrong_a!r}) instead of configured {assert_sep!r}.\n"
                    f"Rendered output:\n{rendered}"
                )
                assert wrong_b not in rendered, (
                    f"Rendered output uses hardcoded '-' separator "
                    f"({wrong_b!r}) instead of configured {assert_sep!r}.\n"
                    f"Rendered output:\n{rendered}"
                )
