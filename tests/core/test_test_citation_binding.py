"""Tests for which test a citation in a test file binds to.

A citation binds to the test directly below it.  A citation also binds to a
group directly below it, if the group holds a test.  This rule applies on
every pre-scan route that attributes the tests of a file.  If no such test
or group is below a citation, then the citation binds to no test.  A citation
at the top of a file is not a default for the tests below it.  A runner
reports the tests in a group and never the group itself.  Consequently, a
citation on a group takes its verdict from the results of its tests.
"""

from __future__ import annotations

import pytest

from elspais.config.schema import ElspaisConfig
from elspais.graph import EdgeKind, NodeKind
from elspais.graph.annotators import CoverageCreditConfig, annotate_coverage
from elspais.graph.metrics import tested_and_passing
from elspais.graph.parsers.lark import FileDispatcher
from elspais.utilities.patterns import IdPatternConfig, IdResolver
from tests.core.graph_test_helpers import (
    MockSourceContext,
    build_graph,
    make_requirement,
    make_test_result,
)


@pytest.fixture(scope="module")
def resolver():
    config = {
        "project": {"namespace": "REQ"},
        "levels": {
            "prd": {"rank": 1, "letter": "p", "implements": ["prd"]},
            "ops": {"rank": 2, "letter": "o", "implements": ["ops", "prd"]},
            "dev": {"rank": 3, "letter": "d", "implements": ["dev", "ops", "prd"]},
        },
        "id-patterns": {
            "canonical": "{namespace}-{level.letter}{component}",
            "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
            "assertions": {"label_style": "uppercase", "max_count": 26},
        },
    }
    ElspaisConfig.model_validate(config)
    return IdResolver(IdPatternConfig.from_dict(config))


def _line_of(source: str, needle: str) -> int:
    return next(i for i, text in enumerate(source.split("\n"), 1) if needle in text)


def _test_refs(items):
    return [i for i in items if i.content_type == "test_ref"]


# ---------------------------------------------------------------------------
# A citation above the second of two tests binds to the second
# ---------------------------------------------------------------------------

# CITATION_FORMS holds each spelling of the same references. A list continued
# with its separator states what a single list states. A pair of keyword lines
# also states what a single list states. Consequently, each form must bind
# where the single list binds.
CITATION_FORMS = {
    "single": "{m} Verifies: REQ-p00001-A",
    "comma-list": "{m} Verifies: REQ-p00001-A, REQ-p00001-B",
    "continued-list": "{m} Verifies: REQ-p00001-A,\n{m}   REQ-p00001-B",
    "two-keyword-lines": "{m} Verifies: REQ-p00001-A\n{m} Verifies: REQ-p00001-B",
    "prose-then-citation": "{m} Checks the second flow end to end.\n{m} Verifies: REQ-p00001-A",
}

TS_TWO_TESTS = """\
import {{ test }} from '@playwright/test';

test('first', async () => {{
  await go();
}});
{citation}
test('second', async () => {{
  await go();
}});
"""

GO_TWO_TESTS = """\
package checkout

func TestFirst(t *testing.T) {{
\tgo_()
}}

{citation}
func TestSecond(t *testing.T) {{
\tgo_()
}}
"""

PY_TWO_TESTS = """\
import os


def test_first():
    assert os


{citation}
def test_second():
    assert os
"""

DART_TWO_TESTS = """\
import 'package:test/test.dart';

void main() {{
  test('first', () {{
    expect(1, 1);
  }});

{citation}
  test('second', () {{
    expect(2, 2);
  }});
}}
"""


def _external_entries(path, source, first, second, with_end):
    """Return the records a prescan command gives for *source*, with or without ends."""
    first_line, second_line = _line_of(source, first), _line_of(source, second)
    lines = source.rstrip("\n").split("\n")
    entries = [
        {"function": "first", "class": None, "line": first_line},
        {"function": "second", "class": None, "line": second_line},
    ]
    if with_end:
        # Each test ends at the first closing line after it starts.
        for entry in entries:
            entry["end_line"] = next(
                n
                for n in range(entry["line"], len(lines) + 1)
                if lines[n - 1].lstrip().startswith("}")
            )
    return {path: entries}


# (path, template, comment marker, first declaration, second declaration)
LANGUAGES = {
    "ts": ("tests/e2e/checkout.spec.ts", TS_TWO_TESTS, "//", "test('first'", "test('second'"),
    "go": ("checkout/checkout_test.go", GO_TWO_TESTS, "//", "func TestFirst", "func TestSecond"),
    "python": ("tests/test_checkout.py", PY_TWO_TESTS, "#", "def test_first", "def test_second"),
    "dart": ("test/checkout_test.dart", DART_TWO_TESTS, "  //", "test('first'", "test('second'"),
}

# (language, whether an external prescan attributes the file, whether its
# records report each test's end line)
ROUTES = [
    pytest.param("ts", True, True, id="ts-external-with-end"),
    pytest.param("ts", True, False, id="ts-external-no-end"),
    pytest.param("go", True, True, id="go-external-with-end"),
    pytest.param("go", True, False, id="go-external-no-end"),
    pytest.param("python", False, False, id="python-builtin"),
    pytest.param("dart", False, False, id="dart-builtin"),
]


# Verifies: REQ-d00254-S, REQ-d00254-V, REQ-d00269-M
@pytest.mark.parametrize("form", sorted(CITATION_FORMS))
@pytest.mark.parametrize(("language", "external", "with_end"), ROUTES)
def test_a_citation_above_the_second_test_binds_to_the_second(
    resolver, language, external, with_end, form
):
    path, template, marker, first, second = LANGUAGES[language]
    source = template.format(citation=CITATION_FORMS[form].format(m=marker))
    prescan_data = _external_entries(path, source, first, second, with_end) if external else None
    second_line = _line_of(source, second)

    items = FileDispatcher(resolver).dispatch_test(
        source, file_path=path, prescan_data=prescan_data
    )

    citing = [r for r in _test_refs(items) if r.parsed_data.get("verifies")]
    assert citing, f"the citation must be read; got {items}"
    for entry in citing:
        assert entry.parsed_data["binds_to_test"] is True
        assert entry.parsed_data["function_line"] == second_line, (
            f"{form} above the second test must bind to it, not to the test before it; "
            f"got {entry.parsed_data}"
        )


# ---------------------------------------------------------------------------
# A citation at the top of a file binds to no test
# ---------------------------------------------------------------------------

HEADERS = [
    pytest.param(
        "tests/test_header.py",
        "# Verifies: REQ-p00001-A\nimport os\n\n\ndef test_one():\n    assert os\n",
        None,
        id="python-builtin",
    ),
    pytest.param(
        "test/header_test.dart",
        "// Verifies: REQ-p00001-A\nimport 'package:test/test.dart';\n\n"
        "void main() {\n  test('one', () {\n    expect(1, 1);\n  });\n}\n",
        None,
        id="dart-builtin",
    ),
    pytest.param(
        "tests/e2e/header.spec.ts",
        "// Verifies: REQ-p00001-A\nimport { test } from '@playwright/test';\n\n"
        "test('one', async () => {\n  await go();\n});\n",
        {"tests/e2e/header.spec.ts": [{"function": "one", "class": None, "line": 4}]},
        id="ts-external",
    ),
]


# Verifies: REQ-d00254-T, REQ-d00274-G
@pytest.mark.parametrize(("path", "source", "prescan_data"), HEADERS)
def test_a_citation_above_the_first_test_binds_to_no_test(resolver, path, source, prescan_data):
    items = FileDispatcher(resolver).dispatch_test(
        source, file_path=path, prescan_data=prescan_data
    )
    refs = _test_refs(items)
    citation = [r for r in refs if r.start_line == 1]
    assert len(citation) == 1, f"the header citation must be read; got {items}"
    assert citation[0].parsed_data["binds_to_test"] is False
    tests = [r for r in refs if r.start_line != 1]
    assert tests, "the test below must still be found"
    assert all(r.parsed_data["verifies"] == [] for r in tests), (
        f"no test may inherit the header citation; got {[r.parsed_data for r in tests]}"
    )


# ---------------------------------------------------------------------------
# A citation on a group of tests
# ---------------------------------------------------------------------------

GROUP_PATH = "test/area_test.dart"

GROUP_DART = """\
void main() {
  // Verifies: REQ-p00001-A
  group('area', () {
    test('a', () {
      expect(1, 1);
    });
    test('b', () {
      expect(2, 2);
    });
  });
}
"""

EMPTY_GROUP_DART = """\
void main() {
  // Verifies: REQ-p00001-A
  group('area', () {
    setUp(() {});
  });
}
"""


UNBALANCED_GROUP_DART = """\
void main() {
  // Verifies: REQ-p00001-A
  group('area', () {
    test('a', () {
      expect(1, 1);
    });
"""


# Verifies: REQ-d00254-T
@pytest.mark.parametrize(
    "source",
    [
        pytest.param(EMPTY_GROUP_DART, id="group-holding-no-test"),
        pytest.param(UNBALANCED_GROUP_DART, id="group-with-no-known-end"),
    ],
)
def test_a_citation_above_a_group_holding_no_test_binds_to_no_test(resolver, source):
    items = FileDispatcher(resolver).dispatch_test(source, file_path=GROUP_PATH)
    citation = [r for r in _test_refs(items) if r.parsed_data.get("verifies")]
    assert len(citation) == 1
    assert citation[0].parsed_data["binds_to_test"] is False


def _group_graph(resolver, statuses):
    items = FileDispatcher(resolver).dispatch_test(GROUP_DART, file_path=GROUP_PATH)
    for item in items:
        item.source_context = MockSourceContext(GROUP_PATH)
    results = [
        make_test_result(
            f"r_{name}",
            status=status,
            source_file=GROUP_PATH,
            match="source",
            line=_line_of(GROUP_DART, f"test('{name}'"),
        )
        for name, status in statuses.items()
    ]
    req = make_requirement(
        "REQ-p00001",
        assertions=[{"label": "A", "text": "SHALL a"}, {"label": "B", "text": "SHALL b"}],
    )
    graph = build_graph(req, *items, *results)
    annotate_coverage(graph, CoverageCreditConfig())
    return graph


# Verifies: REQ-d00254-S, REQ-d00254-U
@pytest.mark.parametrize(
    ("statuses", "passing", "failing"),
    [
        pytest.param({"a": "passed", "b": "passed"}, 1.0, False, id="all-pass"),
        pytest.param({"a": "passed", "b": "failed"}, 0.0, True, id="one-fails"),
        pytest.param({"a": "passed"}, 1.0, False, id="one-reported"),
    ],
)
def test_a_citation_on_a_group_takes_the_verdicts_of_its_tests(
    resolver, statuses, passing, failing
):
    graph = _group_graph(resolver, statuses)
    group_line = _line_of(GROUP_DART, "group(")
    group = next(
        n for n in graph.iter_by_kind(NodeKind.TEST) if n.get_field("parse_line") == group_line
    )
    yielded = {r.id for r in group.iter_children(edge_kinds={EdgeKind.YIELDS})}
    assert yielded == {f"r_{name}" for name in statuses}, (
        "every result of a test the group holds must reach the group's citation"
    )
    metrics = graph.find_by_id("REQ-p00001").get_metric("rollup_metrics")
    passing_dim = tested_and_passing(metrics)
    assert passing_dim.total_by_label.get("A", 0.0) == passing
    assert ("A" in passing_dim.failing_labels) is failing
    # The tests themselves cite nothing. Consequently, nothing reaches B.
    assert metrics.tested.total_by_label.get("B", 0.0) == 0.0


# ---------------------------------------------------------------------------
# The build still judges the references of a citation that binds to no test
# ---------------------------------------------------------------------------

UNBOUND_BAD_REF = """\
# Verifies: REQ-p00001-A, REQ-p00001-Z, REQ-p09999-A
import os


def test_one():
    assert os
"""


# Verifies: REQ-d00269-D, REQ-d00254-T
def test_an_unbound_citation_still_reports_the_references_that_resolve_to_nothing(resolver):
    path = "tests/test_unbound_refs.py"
    items = FileDispatcher(resolver).dispatch_test(UNBOUND_BAD_REF, file_path=path)
    for item in items:
        item.source_context = MockSourceContext(path)
    req = make_requirement("REQ-p00001", assertions=[{"label": "A", "text": "SHALL a"}])
    graph = build_graph(req, *items)

    faulted = {f.target_id for f in graph.unresolved_references()}
    assert faulted == {"REQ-p00001-Z", "REQ-p09999-A"}, (
        f"each reference naming nothing must be reported, bound or not; got {faulted}"
    )
    assert [c.targets for c in graph.unbound_citations()] == [
        ("REQ-p00001-A", "REQ-p00001-Z", "REQ-p09999-A")
    ]
    assert not any(
        True for _ in graph.find_by_id("REQ-p00001").iter_edges_by_kind(EdgeKind.VERIFIES)
    ), "an unbound citation credits nothing, even through a reference that resolves"
