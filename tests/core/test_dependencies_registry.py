"""Tests for the dependency-source interface: the registry, and the two built-in sources."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from elspais.graph.dependencies import (
    NoSettings,
    Observation,
    ObservesFrame,
    SourceFailed,
    SourceRequest,
    SourceUnavailable,
    get_source,
    observes_required,
    source_names,
)
from elspais.graph.dependencies.command import CommandSettings


def _request(root: Path, units: tuple[str, ...], settings=None) -> SourceRequest:
    return SourceRequest(
        repo_root=root,
        cwd=root,
        target_name="unit",
        units=units,
        inputs=frozenset(units),
        observed=frozenset(units),
        settings=settings if settings is not None else NoSettings(),
    )


# Verifies: REQ-d00333-C
def test_every_registered_source_is_found_by_its_name():
    assert set(source_names()) >= {"declared", "command"}
    for name in source_names():
        assert get_source(name).name == name


# Verifies: REQ-d00333-C
def test_an_unknown_source_is_refused_naming_every_known_one():
    with pytest.raises(KeyError) as caught:
        get_source("imports:cobol")
    message = str(caught.value)
    assert "imports:cobol" in message
    for name in source_names():
        assert repr(name) in message


# Verifies: REQ-d00333-C
def test_importing_a_source_module_loads_no_library_beyond_the_core_dependencies():
    script = textwrap.dedent(
        """
        import json, sys
        before = set(sys.modules)
        from elspais.graph.dependencies import get_source, source_names
        for name in source_names():
            get_source(name)
        new = {m.split(".")[0] for m in set(sys.modules) - before}
        stdlib = set(sys.stdlib_module_names)
        print(json.dumps(sorted(m for m in new if m not in stdlib and not m.startswith("_"))))
        """
    )
    done = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    loaded = set(json.loads(done.stdout))
    # The core dependencies and what they load; an optional extra is none of them.
    core = {
        "elspais",
        "tomlkit",
        "pydantic",
        "pydantic_core",
        "typing_extensions",
        "annotated_types",
        "typing_inspection",
        "tyro",
        "lark",
    }
    assert loaded <= core


class _NeedsALibrary:
    """A source whose library is not installed: its evidence() fails to import it."""

    name = "declared"
    settings_model = NoSettings
    extra = "dart"

    def default_observes(self, frame):
        return frame.test

    def evidence(self, request):
        raise ImportError("No module named 'analyzer'", name="analyzer")


# Verifies: REQ-d00333-C
def test_a_source_missing_its_library_executes_every_test_naming_the_extra_it_declares(
    tmp_path, monkeypatch
):
    from elspais.config import validate_config
    from elspais.utilities.retention import plan_run

    root = tmp_path
    (root / "tests").mkdir()
    (root / "tests" / "test_a.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    config = validate_config(
        {
            "version": 5,
            "project": {"name": "p", "namespace": "REQ"},
            "scanning": {
                "test": {
                    "enabled": True,
                    "directories": ["tests"],
                    "file_patterns": ["test_*.py"],
                    "targets": [
                        {
                            "name": "unit",
                            "reporter": "junit",
                            "results": "junit.xml",
                            "command": "pytest {selection}",
                            "units": {"dependencies": {"source": "declared"}},
                        }
                    ],
                }
            },
        }
    )
    monkeypatch.setattr("elspais.utilities.retention.get_source", lambda name: _NeedsALibrary())

    plan = plan_run(root, config, config.scanning.test.targets[0], stale_only=True, full=False)

    assert plan.whole
    assert plan.evidence is None
    assert "needs analyzer" in plan.whole_reason
    assert "elspais[dart]" in plan.whole_reason


# Verifies: REQ-d00333-C
def test_a_source_needing_no_extra_that_fails_to_import_is_a_failed_source(tmp_path):
    from elspais.graph.dependencies import gather_evidence

    source = _NeedsALibrary()
    source.extra = None
    with pytest.raises(SourceFailed) as caught:
        gather_evidence(source, _request(tmp_path, ("tests/a_test.py",)))
    assert not isinstance(caught.value, SourceUnavailable)
    assert "could not import analyzer" in caught.value.reason


# Verifies: REQ-d00333-C
def test_the_declared_source_reaches_each_test_file_alone(tmp_path):
    source = get_source("declared")
    evidence = source.evidence(_request(tmp_path, ("tests/a_test.py", "tests/b_test.py")))
    assert evidence.files == {
        "tests/a_test.py": frozenset({"tests/a_test.py"}),
        "tests/b_test.py": frozenset({"tests/b_test.py"}),
    }


# Verifies: REQ-d00333-C
def test_the_declared_source_observes_the_test_selection_and_the_command_source_none():
    test = Observation(directories=("tests",), file_patterns=("test_*.py",))
    frame = ObservesFrame(cwd="", inputs=Observation(), test=test)
    assert get_source("declared").default_observes(frame) == test
    assert get_source("command").default_observes(frame) is None
    assert observes_required(get_source("command"))
    assert not observes_required(get_source("declared"))


def _script(tmp_path: Path, body: str) -> str:
    path = tmp_path / "deps.py"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return f"{sys.executable} {path}"


# Verifies: REQ-d00333-C
def test_the_command_source_reads_the_files_each_unit_reaches(tmp_path):
    command = _script(
        tmp_path,
        f"""
        import json, sys
        units = [line for line in sys.stdin.read().splitlines() if line]
        out = [{{"unit": u, "files": [u, "src/lib.py", "{tmp_path}/src/abs.py", "/usr/lib/x"]}}
               for u in units]
        print(json.dumps(out))
        """,
    )
    source = get_source("command")
    evidence = source.evidence(
        _request(tmp_path, ("tests/a_test.py",), CommandSettings(command=command))
    )
    assert evidence.files["tests/a_test.py"] == frozenset(
        {"tests/a_test.py", "src/lib.py", "src/abs.py", "/usr/lib/x"}
    )


# Verifies: REQ-d00333-C
def test_the_command_source_leaves_a_unit_its_output_omits_without_evidence(tmp_path):
    command = _script(tmp_path, 'print("[]")')
    evidence = get_source("command").evidence(
        _request(tmp_path, ("tests/a_test.py",), CommandSettings(command=command))
    )
    assert "tests/a_test.py" not in evidence.files


# Verifies: REQ-d00333-C
@pytest.mark.parametrize(
    ("body", "says"),
    [
        ("import sys; sys.exit(3)", "exited 3"),
        ('print("not json")', "not JSON"),
        ('print("{}")', "not an array"),
        ("print('[{\"unit\": 1}]')", "entry 0"),
    ],
)
def test_a_command_source_that_gives_no_usable_answer_fails_with_its_cause(tmp_path, body, says):
    command = _script(tmp_path, body)
    with pytest.raises(SourceFailed) as caught:
        get_source("command").evidence(
            _request(tmp_path, ("tests/a_test.py",), CommandSettings(command=command))
        )
    assert says in caught.value.reason


# Verifies: REQ-d00333-C
def test_the_command_source_places_a_path_given_through_a_symbolic_link(tmp_path):
    real = tmp_path / "real"
    (real / "src").mkdir(parents=True)
    (real / "src" / "lib.py").write_text("x = 1\n", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(real)
    command = _script(
        tmp_path,
        f"""
        import json, sys
        units = [line for line in sys.stdin.read().splitlines() if line]
        print(json.dumps([{{"unit": u, "files": ["{link}/src/lib.py"]}} for u in units]))
        """,
    )
    evidence = get_source("command").evidence(
        _request(real, ("tests/a_test.py",), CommandSettings(command=command))
    )
    assert evidence.files["tests/a_test.py"] == frozenset({"src/lib.py"})
