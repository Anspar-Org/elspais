"""The requirements each named file defines, implements, verifies or validates.

``compute_files`` answers from the file side: for every path a caller names it
says whether a file exists there, whether the scan reads it, which role the
scan gave it, and the links the federated graph holds for it.

Most cases read the canonical hht-like fixture, which holds:

- ``spec/dev-impl.md`` -- REQ-d00001..REQ-d00003, four assertions each, and
  requirement-level references to other requirements in its metadata lines;
- ``spec/journeys.md`` -- one journey validating REQ-p00001-A and -B; the scan
  reads this file as a spec file;
- ``spec/glossary.md`` -- a scanned spec file holding no requirement;
- ``database/schema.sql`` -- code citing REQ-p00001, REQ-d00001, REQ-p00003 and
  REQ-d00003 as whole requirements, some of them on more than one line;
- ``tests/test_auth.py`` -- three tests each citing REQ-d00001-A+B;
- ``spec/INDEX.md`` -- a skipped spec file; ``traceability.md`` lies outside
  every scanned directory.

The cases the fixture lacks are built in a small federation under a temporary
directory (see ``_build_federation``).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from elspais.commands._requests import FilesRequest, files_request_from_params
from elspais.commands.files_cmd import compute_files
from elspais.graph.factory import build_graph
from elspais.graph.reference_faults import FaultClass
from tests.e2e.helpers import (
    Requirement,
    base_config,
    build_associate,
    build_project,
    write_python_code,
    write_python_test,
)

FIXTURE_ROOT = (Path(__file__).parent.parent / "fixtures" / "hht-like").resolve()


def _answer(graph, config, *paths: str, built_at: float | None = None) -> dict:
    """The answer for ``paths``, from a graph built before now."""
    when = time.time() if built_at is None else built_at
    return compute_files(graph, config, FilesRequest(paths=tuple(paths)), built_at=when)


def _entry(graph, config, path: str, built_at: float | None = None) -> dict:
    """The single entry the answer gives for one path."""
    (entry,) = _answer(graph, config, path, built_at=built_at)["files"]
    return entry


def _links(entry: dict) -> list[tuple[str, str, str]]:
    return [(link["kind"], link["id"], link["requirement"]) for link in entry["links"]]


# ---------------------------------------------------------------------------
# The canonical fixture
# ---------------------------------------------------------------------------


# Verifies: REQ-d00335-A
def test_one_answer_per_path_in_the_order_named(canonical_federated_graph, canonical_config):
    """A repeated path is answered twice; paths with no link still get one."""
    named = [
        "tests/test_auth.py",
        "spec/glossary.md",
        "no/such/file.py",
        "traceability.md",
        "tests/test_auth.py",
    ]
    answer = _answer(canonical_federated_graph, canonical_config, *named)
    assert [entry["path"] for entry in answer["files"]] == named
    assert [entry["status"] for entry in answer["files"]] == [
        "scanned",
        "scanned",
        "no_file",
        "not_scanned",
        "scanned",
    ]


# Verifies: REQ-d00335-B
def test_a_relative_path_is_read_against_the_repository_root(
    canonical_federated_graph, canonical_config, tmp_path, monkeypatch
):
    """The process's working directory plays no part: from an unrelated
    directory the relative path still names the fixture's file, and it is
    answered as its absolute spelling is."""
    monkeypatch.chdir(tmp_path)
    relative = "database/schema.sql"
    absolute = str(FIXTURE_ROOT / relative)
    by_relative, by_absolute = _answer(
        canonical_federated_graph, canonical_config, relative, absolute
    )["files"]

    assert by_relative["path"] == relative
    assert by_absolute["path"] == absolute
    for entry in (by_relative, by_absolute):
        assert entry["status"] == "scanned"
        assert entry["relative_path"] == relative
        assert entry["namespace"] == "REQ"
    assert by_relative["links"] == by_absolute["links"]
    assert ("implements", "REQ-d00001", "REQ-d00001") in _links(by_relative)


# Verifies: REQ-d00335-C
@pytest.mark.parametrize(
    ("path", "ids"),
    [
        pytest.param(
            "database/schema.sql",
            ["REQ-d00001", "REQ-d00003", "REQ-p00001", "REQ-p00003"],
            id="code-whole-requirements",
        ),
        pytest.param(
            "tests/test_auth.py",
            ["REQ-d00001-A", "REQ-d00001-B"],
            id="test-assertions",
        ),
        pytest.param(
            "spec/journeys.md",
            ["REQ-p00001-A", "REQ-p00001-B"],
            id="journey-validates",
        ),
        pytest.param(
            "spec/dev-impl.md",
            [
                rid
                for req in ("REQ-d00001", "REQ-d00002", "REQ-d00003")
                for rid in (req, f"{req}-A", f"{req}-B", f"{req}-C", f"{req}-D")
            ],
            id="spec-requirements-and-assertions",
        ),
    ],
)
def test_every_identifier_the_file_bears_on_is_named(
    canonical_federated_graph, canonical_config, path, ids
):
    """Exactly the identifiers the graph links the file to, each once.

    schema.sql cites REQ-p00001 and REQ-d00001 on two lines each and is named
    for them once; test_auth.py carries a third assertion only inside a
    docstring, which the scan does not read as a citation.
    """
    entry = _entry(canonical_federated_graph, canonical_config, path)
    assert entry["status"] == "scanned"
    assert sorted(link["id"] for link in entry["links"]) == sorted(ids)


# Verifies: REQ-d00335-D
@pytest.mark.parametrize(
    ("path", "expected"),
    [
        pytest.param(
            "database/schema.sql",
            [
                ("implements", "REQ-d00001", "REQ-d00001"),
                ("implements", "REQ-d00003", "REQ-d00003"),
                ("implements", "REQ-p00001", "REQ-p00001"),
                ("implements", "REQ-p00003", "REQ-p00003"),
            ],
            id="code",
        ),
        pytest.param(
            "tests/test_auth.py",
            [
                ("verifies", "REQ-d00001-A", "REQ-d00001"),
                ("verifies", "REQ-d00001-B", "REQ-d00001"),
            ],
            id="test",
        ),
        pytest.param(
            "spec/journeys.md",
            [
                ("validates", "REQ-p00001-A", "REQ-p00001"),
                ("validates", "REQ-p00001-B", "REQ-p00001"),
            ],
            id="journey",
        ),
    ],
)
def test_each_link_states_how_the_file_bears_on_it(
    canonical_federated_graph, canonical_config, path, expected
):
    """The relationship and the requirement an assertion belongs to, in
    (kind, id) order."""
    entry = _entry(canonical_federated_graph, canonical_config, path)
    assert _links(entry) == expected


# Verifies: REQ-d00335-D
def test_a_spec_file_defines_its_requirements_and_reports_no_metadata_reference(
    canonical_federated_graph, canonical_config
):
    """dev-impl.md's metadata lines reference REQ-p00001-A+B+C, REQ-o00001 and
    others; those are relationships of the requirements, not links of the
    file, so every link it has is a definition."""
    entry = _entry(canonical_federated_graph, canonical_config, "spec/dev-impl.md")
    links = _links(entry)
    assert {kind for kind, _id, _req in links} == {"defines"}
    assert ("defines", "REQ-d00002", "REQ-d00002") in links
    assert ("defines", "REQ-d00002-C", "REQ-d00002") in links
    assert not any(rid.startswith(("REQ-p", "REQ-o")) for _kind, rid, _req in links)
    assert links == sorted(set(links))


# Verifies: REQ-d00335-D
@pytest.mark.parametrize(
    ("path", "role"),
    [
        ("spec/dev-impl.md", "spec"),
        ("spec/journeys.md", "spec"),
        ("database/schema.sql", "code"),
        ("tests/test_auth.py", "test"),
        (".elspais.toml", "config"),
        ("spec/INDEX.md", None),
        ("no/such/file.py", None),
    ],
)
def test_the_answer_names_the_role_the_scan_gave_the_file(
    canonical_federated_graph, canonical_config, path, role
):
    entry = _entry(canonical_federated_graph, canonical_config, path)
    assert entry["role"] == role


# Verifies: REQ-d00335-E
@pytest.mark.parametrize(
    "path",
    [
        pytest.param("no/such/file.py", id="missing-file"),
        pytest.param("spec", id="directory"),
        pytest.param("spec/no-such-spec.md", id="missing-in-scanned-directory"),
    ],
)
def test_a_path_with_no_file_is_answered_as_no_file(
    canonical_federated_graph, canonical_config, path
):
    entry = _entry(canonical_federated_graph, canonical_config, path)
    assert entry["status"] == "no_file"
    assert entry["role"] is None
    assert entry["links"] == []


# Verifies: REQ-d00335-F
@pytest.mark.parametrize(
    "path",
    [
        pytest.param("spec/INDEX.md", id="skipped-file-in-scanned-directory"),
        pytest.param("traceability.md", id="outside-every-scanned-directory"),
    ],
)
def test_an_existing_file_the_scan_does_not_read_is_answered_as_not_scanned(
    canonical_federated_graph, canonical_config, path
):
    assert (FIXTURE_ROOT / path).is_file()
    entry = _entry(canonical_federated_graph, canonical_config, path)
    assert entry["status"] == "not_scanned"
    assert entry["role"] is None
    assert entry["links"] == []
    assert entry["relative_path"] == path
    assert entry["namespace"] == "REQ"


# Verifies: REQ-d00335-G
@pytest.mark.parametrize("path", ["spec/glossary.md", ".elspais.toml"])
def test_a_scanned_file_naming_no_requirement_is_scanned_with_no_link(
    canonical_federated_graph, canonical_config, path
):
    entry = _entry(canonical_federated_graph, canonical_config, path)
    assert entry["status"] == "scanned"
    assert entry["links"] == []
    assert entry["unresolved"] == []
    assert entry["unbound"] == []
    assert entry["current"] is True


# Verifies: REQ-p00060-C
def test_asking_changes_no_graph_state(canonical_federated_graph, canonical_config):
    graph = canonical_federated_graph
    nodes_before = graph.node_count()
    log_before = len(graph.mutation_log)
    _answer(
        graph,
        canonical_config,
        "spec/dev-impl.md",
        "database/schema.sql",
        "tests/test_auth.py",
        "spec/journeys.md",
        "spec/INDEX.md",
        "no/such/file.py",
        str(FIXTURE_ROOT / "spec"),
    )
    assert graph.node_count() == nodes_before
    assert len(graph.mutation_log) == log_before


# ---------------------------------------------------------------------------
# The request and its wire form
# ---------------------------------------------------------------------------


# Verifies: REQ-d00335-A
@pytest.mark.parametrize(
    "paths",
    [
        pytest.param((), id="none"),
        pytest.param(("src/a.py",), id="one"),
        pytest.param(("src/a.py", "src/a.py", "spec/x, y.md", "dir with space/f.py"), id="awkward"),
        pytest.param(("/abs/path/f.py", "rel/f.py"), id="absolute-and-relative"),
    ],
)
def test_a_files_request_survives_its_wire_form(paths):
    """Every path, its order and its repetitions reach the serving process
    unchanged, however its characters would divide a list."""
    request = FilesRequest(paths=paths)
    params = request.to_params()
    assert json.loads(params["paths"]) == list(paths)
    assert files_request_from_params(params) == request


# ---------------------------------------------------------------------------
# A federation built for the cases the fixture lacks
# ---------------------------------------------------------------------------

UNKNOWN_ID = "REQ-d09999"
ASSOCIATE_REQ = "XX-p00099"


def _build_federation(base: Path) -> tuple[Path, Path]:
    """A core repository and one associate (namespace XX).

    core:
      spec/prd.md, spec/dev.md   REQ-p00001 (A, B); REQ-d00001 (A, B)
      src/linked.py              cites REQ-d00001-A+B and REQ-p00001
      src/empty.py               cites nothing
      src/unresolved.py          cites an identifier nothing holds
      src/assoc_cite.py          cites the associate's XX-p00099-A
      src/vendor/lib.py          cites REQ-d00001; its directory is skipped
      src/notes.txt              cites REQ-d00001; the code patterns exclude it
      tests/test_linked.py       a test verifying REQ-d00001-A
      tests/test_unbound.py      a citation of REQ-d00001-B followed by no test
      README.md                  cites REQ-d00001; outside every scan
    assoc:
      spec/prd-assoc.md          XX-p00099 (A)
    """
    core = base / "core"
    assoc = base / "assoc"
    cfg = base_config(name="files-core", testing_enabled=True)
    cfg["scanning"]["code"]["file_patterns"] = ["*.py"]
    cfg["scanning"]["code"]["skip_dirs"] = ["src/vendor"]
    cfg["associates"] = {"assoc": {"path": "../assoc", "namespace": "XX"}}
    build_project(
        core,
        cfg,
        spec_files={
            "spec/prd.md": [
                Requirement(
                    "REQ-p00001",
                    "Core",
                    "PRD",
                    assertions=[("A", "The system SHALL a."), ("B", "The system SHALL b.")],
                )
            ],
            "spec/dev.md": [
                Requirement(
                    "REQ-d00001",
                    "Dev",
                    "DEV",
                    implements="REQ-p00001",
                    assertions=[("A", "The module SHALL a."), ("B", "The module SHALL b.")],
                )
            ],
        },
        code_files={
            "src/linked.py": {"implements": ["REQ-d00001-A+B", "REQ-p00001"]},
            "src/empty.py": {},
            "src/unresolved.py": {"implements": [UNKNOWN_ID]},
            "src/assoc_cite.py": {"implements": [f"{ASSOCIATE_REQ}-A"]},
            "src/vendor/lib.py": {"implements": ["REQ-d00001"]},
        },
        test_files={"tests/test_linked.py": {"verifies": ["REQ-d00001-A"]}},
        init_git=False,
    )
    write_python_code(core / "src" / "notes.txt", implements=["REQ-d00001"])
    write_python_code(core / "README.md", implements=["REQ-d00001"])
    write_python_test(
        core / "tests" / "test_unbound.py", verifies=["REQ-d00001-B"], content="X = 1"
    )
    build_associate(
        assoc,
        "assoc",
        "XX",
        "../core",
        spec_files={
            "spec/prd-assoc.md": [
                Requirement(
                    ASSOCIATE_REQ,
                    "Associate",
                    "PRD",
                    assertions=[("A", "The system SHALL x.")],
                )
            ]
        },
    )
    return core, assoc


def _built(core: Path):
    graph = build_graph(repo_root=core)
    return graph, graph.root_config


@pytest.fixture(scope="module")
def federation(tmp_path_factory):
    """A read-only federation, shared by the tests that only ask."""
    core, assoc = _build_federation(tmp_path_factory.mktemp("files_federation"))
    graph, config = _built(core)
    return core, assoc, graph, config


@pytest.fixture
def private_federation(tmp_path):
    """A federation a test may change on disk after its graph is built."""
    core, assoc = _build_federation(tmp_path)
    graph, config = _built(core)
    return core, assoc, graph, config


# Verifies: REQ-d00335-D
def test_a_code_citation_of_assertions_links_each_assertion(federation):
    """Assertions cited together are one link each, bound to their
    requirement; a requirement cited whole is one link of its own id."""
    _core, _assoc, graph, config = federation
    entry = _entry(graph, config, "src/linked.py")
    assert _links(entry) == [
        ("implements", "REQ-d00001-A", "REQ-d00001"),
        ("implements", "REQ-d00001-B", "REQ-d00001"),
        ("implements", "REQ-p00001", "REQ-p00001"),
    ]


# Verifies: REQ-d00335-G
def test_a_scanned_code_file_citing_nothing_is_scanned_with_no_link(federation):
    _core, _assoc, graph, config = federation
    entry = _entry(graph, config, "src/empty.py")
    assert entry["status"] == "scanned"
    assert entry["role"] == "code"
    assert entry["links"] == []
    assert entry["unresolved"] == []
    assert entry["unbound"] == []


# Verifies: REQ-d00241-E
def test_a_citation_naming_nothing_held_is_reported_with_the_file(federation):
    """The file has no link, and the answer says why rather than reading as
    a file that cites nothing."""
    _core, _assoc, graph, config = federation
    entry = _entry(graph, config, "src/unresolved.py")
    assert entry["status"] == "scanned"
    assert entry["links"] == []
    assert entry["unresolved"] == [
        {
            "reference": UNKNOWN_ID,
            "kind": "implements",
            "fault": FaultClass.UNKNOWN_REQUIREMENT.label,
        }
    ]


# Verifies: REQ-d00241-E
def test_a_test_citation_binding_to_no_test_is_reported_with_the_file(federation):
    core, _assoc, graph, config = federation
    lines = (core / "tests" / "test_unbound.py").read_text().splitlines()
    (citation_line,) = [n for n, text in enumerate(lines, start=1) if "REQ-d00001-B" in text]
    entry = _entry(graph, config, "tests/test_unbound.py")
    assert entry["status"] == "scanned"
    assert entry["role"] == "test"
    assert entry["links"] == []
    assert entry["unbound"] == [{"reference": "REQ-d00001-B", "line": citation_line}]


# Verifies: REQ-d00335-F
@pytest.mark.parametrize(
    ("path", "declined"),
    [
        pytest.param("src/vendor/lib.py", None, id="skipped-directory"),
        pytest.param("src/notes.txt", True, id="pattern-excludes-a-citing-file"),
        pytest.param("README.md", False, id="outside-every-scanned-directory"),
    ],
)
def test_a_file_the_scan_does_not_read_is_not_scanned_whatever_it_cites(federation, path, declined):
    """Each of these files carries a citation, which the answer does not
    present as links; a citing file the scan declined inside a scanned
    directory is said to carry citations."""
    core, _assoc, graph, config = federation
    assert (core / path).is_file()
    entry = _entry(graph, config, path)
    assert entry["status"] == "not_scanned"
    assert entry["links"] == []
    if declined is not None:
        assert entry["declined_citations"] is declined


# Verifies: REQ-d00335-F
def test_a_file_outside_every_member_is_not_scanned_and_belongs_to_none(federation, tmp_path):
    _core, _assoc, graph, config = federation
    outside = tmp_path / "elsewhere.py"
    outside.write_text("X = 1\n")
    entry = _entry(graph, config, str(outside))
    assert entry["status"] == "not_scanned"
    assert entry["relative_path"] is None
    assert entry["namespace"] is None
    assert entry["links"] == []


# Verifies: REQ-d00335-C
def test_an_absolute_path_into_an_associate_names_what_it_defines(federation):
    _core, assoc, graph, config = federation
    entry = _entry(graph, config, str(assoc / "spec" / "prd-assoc.md"))
    assert entry["status"] == "scanned"
    assert entry["namespace"] == "XX"
    assert entry["relative_path"] == "spec/prd-assoc.md"
    assert _links(entry) == [
        ("defines", ASSOCIATE_REQ, ASSOCIATE_REQ),
        ("defines", f"{ASSOCIATE_REQ}-A", ASSOCIATE_REQ),
    ]


# Verifies: REQ-p00005-A
def test_a_core_file_citing_an_associate_identifier_links_the_associate_requirement(
    federation,
):
    _core, _assoc, graph, config = federation
    entry = _entry(graph, config, "src/assoc_cite.py")
    assert entry["namespace"] == "REQ"
    assert entry["unresolved"] == []
    assert _links(entry) == [("implements", f"{ASSOCIATE_REQ}-A", ASSOCIATE_REQ)]


# Verifies: REQ-p00015-E
@pytest.mark.parametrize(
    ("offset", "current"),
    [
        pytest.param(-1.0, False, id="written-after-the-build"),
        pytest.param(1.0, True, id="written-before-the-build"),
    ],
)
def test_a_file_written_after_the_graph_was_built_is_not_current(
    private_federation, offset, current
):
    core, _assoc, graph, config = private_federation
    path = core / "src" / "linked.py"
    built_at = path.stat().st_mtime + offset
    entry = _entry(graph, config, "src/linked.py", built_at=built_at)
    assert entry["status"] == "scanned"
    assert entry["current"] is current


# Verifies: REQ-p00015-E
def test_a_file_deleted_after_the_build_is_no_file_and_not_current(private_federation):
    """A file the graph still holds a node for but which is gone is stale;
    a path that never held a file is simply absent."""
    core, _assoc, graph, config = private_federation
    built_at = time.time()
    (core / "src" / "linked.py").unlink()
    deleted, never = _answer(graph, config, "src/linked.py", "src/never.py", built_at=built_at)[
        "files"
    ]
    assert deleted["status"] == "no_file"
    assert deleted["current"] is False
    assert never["status"] == "no_file"
    assert never["current"] is True


# Verifies: REQ-p00060-C
def test_asking_changes_no_file_and_no_graph_state(private_federation):
    core, assoc, graph, config = private_federation

    def snapshot() -> dict[str, tuple[int, bytes]]:
        return {
            str(p): (p.stat().st_mtime_ns, p.read_bytes())
            for top in (core, assoc)
            for p in sorted(top.rglob("*"))
            if p.is_file()
        }

    files_before = snapshot()
    nodes_before = graph.node_count()
    log_before = len(graph.mutation_log)
    _answer(
        graph,
        config,
        "src/linked.py",
        "src/unresolved.py",
        "tests/test_unbound.py",
        "src/notes.txt",
        "README.md",
        "src/never.py",
        str(assoc / "spec" / "prd-assoc.md"),
    )
    assert snapshot() == files_before
    assert graph.node_count() == nodes_before
    assert len(graph.mutation_log) == log_before
    assert os.path.exists(core / "src" / "linked.py")
