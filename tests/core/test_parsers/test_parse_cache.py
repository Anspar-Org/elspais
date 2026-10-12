"""The parse cache answers a reading asked for again without changing it.

Each test installs a private ``ParseCache`` so what the process's own cache
holds -- filled by every other test that built a graph -- decides nothing
here.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from elspais.config import config_defaults
from elspais.graph.parsers import parse_cache
from elspais.graph.parsers.lark import FileDispatcher
from elspais.utilities.patterns import build_resolver

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"

SPEC = """\
# Spec

## REQ-p00001: Widget

**Level**: prd | **Status**: Active | **Implements**: -

### Assertions

A. The system SHALL render a widget.

*End* *Widget* | **Hash**: 00000000
"""

CODE = """\
# Implements: REQ-p00001-A
def render():
    return 1
"""

TEST = """\
# Verifies: REQ-p00001-A
def test_render():
    assert True
"""


@pytest.fixture
def private_cache(monkeypatch: pytest.MonkeyPatch) -> parse_cache.ParseCache:
    """A fresh, empty cache in the on mode, replacing the process's one."""
    cache = parse_cache.ParseCache()
    monkeypatch.setattr(parse_cache, "_CACHE", cache)
    monkeypatch.setenv(parse_cache.ENV_VAR, "1")
    return cache


def _config(**overrides: dict) -> dict:
    config = config_defaults()
    config["project"] = {**config.get("project", {}), "namespace": "REQ"}
    for section, values in overrides.items():
        key = "id-patterns" if section == "id_patterns" else section
        merged = dict(config.get(key, {}))
        for name, value in values.items():
            if isinstance(value, dict) and isinstance(merged.get(name), dict):
                merged[name] = {**merged[name], **value}
            else:
                merged[name] = value
        config[key] = merged
    return config


def _dispatcher(config: dict | None = None, members: tuple = ()) -> FileDispatcher:
    return FileDispatcher(build_resolver(config or _config()), [build_resolver(m) for m in members])


def _read(dispatcher: FileDispatcher, reading: str, content: str, path: str) -> list:
    return getattr(dispatcher, f"dispatch_{reading}")(content, path)


READINGS = [
    ("spec", SPEC, "spec/prd.md"),
    ("code", CODE, "src/widget.py"),
    ("test", TEST, "tests/test_widget.py"),
]


class TestHitAndMiss:
    # Verifies: REQ-d00331-A
    @pytest.mark.parametrize("reading,content,path", READINGS)
    def test_a_repeated_reading_is_answered_from_the_cache(
        self, private_cache, reading, content, path
    ) -> None:
        dispatcher = _dispatcher()
        first = _read(dispatcher, reading, content, path)
        assert (private_cache.hits, private_cache.misses) == (0, 1)

        again = _read(_dispatcher(), reading, content, path)

        assert (private_cache.hits, private_cache.misses) == (1, 1)
        assert again == first
        assert again is not first

    # Verifies: REQ-d00331-F
    @pytest.mark.parametrize("reading,content,path", READINGS)
    def test_off_reads_nothing_from_the_cache_and_holds_nothing(
        self, private_cache, monkeypatch, reading, content, path
    ) -> None:
        monkeypatch.setenv(parse_cache.ENV_VAR, "0")
        dispatcher = _dispatcher()
        _read(dispatcher, reading, content, path)
        _read(dispatcher, reading, content, path)

        assert len(private_cache) == 0
        assert (private_cache.hits, private_cache.misses) == (0, 0)

    # Verifies: REQ-d00331-F
    def test_an_unknown_mode_is_refused_naming_the_variable(self, monkeypatch) -> None:
        monkeypatch.setenv(parse_cache.ENV_VAR, "verfy")
        with pytest.raises(ValueError, match=parse_cache.ENV_VAR):
            _read(_dispatcher(), "spec", SPEC, "spec/prd.md")

    # Verifies: REQ-d00331-B
    def test_a_spec_reading_read_at_another_path_is_the_same_reading(self, private_cache) -> None:
        """A spec reading consults no path, so a copy of the file shares it."""
        first = _read(_dispatcher(), "spec", SPEC, "/one/spec/prd.md")
        again = _read(_dispatcher(), "spec", SPEC, "/two/spec/prd.md")

        assert private_cache.hits == 1
        private_cache.clear()
        uncached = _read(_dispatcher(), "spec", SPEC, "/two/spec/prd.md")
        assert again == first == uncached


# A Dart test() body the prescan cannot balance: it warns as it reads.
UNBALANCED_DART = """\
void main() {
  // Verifies: REQ-p00001-A
  test('renders', () {
    expect(render(), isNotNull);
"""

DART_WARNING = "dart_prescan could not balance a test() body"


class TestReadingWarnings:
    # Verifies: REQ-d00331-A
    @pytest.mark.parametrize("cache_mode", ["1", "verify", "0"])
    def test_a_reused_reading_repeats_the_warning_its_parse_reported(
        self, private_cache, monkeypatch, capsys, cache_mode
    ) -> None:
        monkeypatch.setenv(parse_cache.ENV_VAR, cache_mode)
        dispatcher = _dispatcher()
        first = dispatcher.dispatch_test(UNBALANCED_DART, "/x/widget_test.dart")
        first_err = capsys.readouterr().err
        second = dispatcher.dispatch_test(UNBALANCED_DART, "/x/widget_test.dart")
        second_err = capsys.readouterr().err

        assert first_err.count(DART_WARNING) == 1
        assert second_err == first_err
        assert second == first
        if cache_mode == "1":
            assert private_cache.hits == 1

    # Verifies: REQ-d00331-A
    def test_a_reading_that_warns_nothing_repeats_nothing(self, private_cache, capsys) -> None:
        _read(_dispatcher(), "test", TEST, "tests/test_widget.py")
        capsys.readouterr()
        _read(_dispatcher(), "test", TEST, "tests/test_widget.py")

        assert private_cache.hits == 1
        assert capsys.readouterr().err == ""


class TestIsolation:
    # Verifies: REQ-d00331-C
    @pytest.mark.parametrize("reading,content,path", READINGS)
    def test_mutating_a_returned_reading_does_not_reach_the_next(
        self, private_cache, reading, content, path
    ) -> None:
        dispatcher = _dispatcher()
        first = _read(dispatcher, reading, content, path)
        pristine = json.dumps([c.parsed_data for c in first], default=repr, sort_keys=True)

        for parsed in first:
            parsed.parsed_data["intruder"] = True
            parsed.parsed_data.clear()
            parsed.raw_text = "changed"
        first.clear()

        again = _read(dispatcher, reading, content, path)
        assert private_cache.hits == 1
        assert json.dumps([c.parsed_data for c in again], default=repr, sort_keys=True) == (
            pristine
        )
        assert all(c.raw_text != "changed" for c in again)


# Every setting the identifier grammar is derived from, each changed alone.
SETTING_CHANGES = {
    "namespace": {"project": {"namespace": "ABC"}},
    "canonical": {"id_patterns": {"canonical": "{namespace}-{level.letter}-{component}"}},
    "aliases": {"id_patterns": {"aliases": {"long": "{namespace}{level.letter}{component}"}}},
    "component_digits": {"id_patterns": {"component": {"digits": 4}}},
    "component_leading_zeros": {"id_patterns": {"component": {"leading_zeros": False}}},
    "component_style": {"id_patterns": {"component": {"style": "PascalCase"}}},
    "label_style": {"id_patterns": {"assertions": {"label_style": "numeric"}}},
    "assertion_separator": {"id_patterns": {"assertions": {"separator": "."}}},
    "multi_separator": {"id_patterns": {"assertions": {"multi_separator": "&"}}},
    "zero_pad": {"id_patterns": {"assertions": {"zero_pad": True}}},
    "max_count": {"id_patterns": {"assertions": {"max_count": 10}}},
    "level_letter": {"levels": {"prd": {"letter": "q"}}},
    "level_rank": {"levels": {"prd": {"rank": 4}}},
    "output_forms": {"output": {"id-patterns": {"trace": "short"}}},
}


class TestKeySensitivity:
    # Verifies: REQ-d00331-B
    @pytest.mark.parametrize("reading,content,path", READINGS)
    def test_changed_content_is_a_miss(self, private_cache, reading, content, path) -> None:
        dispatcher = _dispatcher()
        _read(dispatcher, reading, content, path)
        _read(dispatcher, reading, content + "\n", path)

        assert (private_cache.hits, private_cache.misses) == (0, 2)

    # Verifies: REQ-d00331-B
    @pytest.mark.parametrize(
        "reading,content,path,other",
        [
            ("code", CODE, "src/widget.py", "src/widget.sql"),
            ("code", CODE, "src/widget.py", "lib/widget.py"),
            ("test", TEST, "tests/test_widget.py", "tests/test_widget.dart"),
            ("test", TEST, "tests/test_widget.py", "other/test_widget.py"),
        ],
    )
    def test_a_changed_path_or_extension_is_a_miss(
        self, private_cache, reading, content, path, other
    ) -> None:
        dispatcher = _dispatcher()
        _read(dispatcher, reading, content, path)
        _read(dispatcher, reading, content, other)

        assert (private_cache.hits, private_cache.misses) == (0, 2)

    # Verifies: REQ-d00331-B
    @pytest.mark.parametrize("setting", sorted(SETTING_CHANGES))
    @pytest.mark.parametrize("reading,content,path", READINGS)
    def test_each_grammar_setting_is_in_the_key(
        self, private_cache, setting, reading, content, path
    ) -> None:
        _read(_dispatcher(), reading, content, path)
        changed = _dispatcher(_config(**SETTING_CHANGES[setting]))
        _read(changed, reading, content, path)

        assert private_cache.hits == 0, f"{setting} was not in the key"
        assert private_cache.misses == 2

    # Verifies: REQ-d00331-B
    @pytest.mark.parametrize("reading,content,path", READINGS)
    def test_a_member_resolver_is_in_the_key(self, private_cache, reading, content, path) -> None:
        member = _config(project={"namespace": "LIB"})
        _read(_dispatcher(), reading, content, path)
        _read(_dispatcher(members=(member,)), reading, content, path)
        changed_member = _config(
            project={"namespace": "LIB"}, id_patterns={"assertions": {"separator": "."}}
        )
        _read(_dispatcher(members=(changed_member,)), reading, content, path)

        assert (private_cache.hits, private_cache.misses) == (0, 3)

    # Verifies: REQ-d00331-B
    def test_the_test_reading_keys_this_files_prescan_entry(self, private_cache) -> None:
        dispatcher = _dispatcher()
        path = "tests/widget_test.go"
        entry = [{"file": path, "function": "TestRender", "class": None, "line": 2}]
        other = [{"file": path, "function": "TestOther", "class": None, "line": 2}]

        dispatcher.dispatch_test(TEST, path, prescan_data={path: entry})
        dispatcher.dispatch_test(TEST, path, prescan_data={path: entry, "x.go": other})
        dispatcher.dispatch_test(TEST, path, prescan_data={path: other})
        dispatcher.dispatch_test(TEST, path, prescan_data=None)

        # Another file's entry is not read, so it does not split the key.
        assert (private_cache.hits, private_cache.misses) == (1, 3)

    # Verifies: REQ-d00331-B
    def test_the_code_reading_keys_its_line_context(self, private_cache) -> None:
        dispatcher = _dispatcher()
        path = "src/widget.py"
        dispatcher.dispatch_code(CODE, path)
        dispatcher.dispatch_code(CODE, path, line_context={2: ("render", None, 2, 3)})
        dispatcher.dispatch_code(CODE, path, line_context={2: ("other", None, 2, 3)})

        assert (private_cache.hits, private_cache.misses) == (0, 3)

    # Verifies: REQ-d00331-B
    def test_a_dispatcher_subclass_is_not_cached(self, private_cache) -> None:
        class Reader(FileDispatcher):
            pass

        dispatcher = Reader(build_resolver(_config()))
        dispatcher.dispatch_spec(SPEC, "spec/prd.md")
        dispatcher.dispatch_spec(SPEC, "spec/prd.md")

        assert len(private_cache) == 0


class TestVerify:
    # Verifies: REQ-d00331-E
    def test_verify_parses_and_passes_when_the_held_reading_matches(
        self, private_cache, monkeypatch
    ) -> None:
        _read(_dispatcher(), "code", CODE, "src/widget.py")
        monkeypatch.setenv(parse_cache.ENV_VAR, "verify")
        again = _read(_dispatcher(), "code", CODE, "src/widget.py")

        assert private_cache.verified == 1
        assert again

    # Verifies: REQ-d00331-E
    def test_verify_raises_naming_the_file_and_reading_on_a_mismatch(
        self, private_cache, monkeypatch
    ) -> None:
        dispatcher = _dispatcher()
        _read(dispatcher, "test", TEST, "tests/test_widget.py")
        # Corrupt what is held: the next fresh reading cannot match it.
        ((key, blob),) = private_cache._entries.items()
        import pickle

        held = pickle.loads(blob)
        held[0][0].raw_text = "not what the file says"
        private_cache.put(key, pickle.dumps(held))

        monkeypatch.setenv(parse_cache.ENV_VAR, "verify")
        with pytest.raises(AssertionError, match=r"dispatch_test of tests/test_widget\.py"):
            _read(dispatcher, "test", TEST, "tests/test_widget.py")
        assert private_cache.mismatches == [("test", "tests/test_widget.py")]


class TestBounds:
    # Verifies: REQ-d00331-D
    def test_entries_beyond_the_bound_evict_the_least_recently_used(self, monkeypatch) -> None:
        cache = parse_cache.ParseCache(max_entries=2)
        monkeypatch.setattr(parse_cache, "_CACHE", cache)
        monkeypatch.setenv(parse_cache.ENV_VAR, "1")
        dispatcher = _dispatcher()

        dispatcher.dispatch_code(CODE, "a.py")
        dispatcher.dispatch_code(CODE, "b.py")
        dispatcher.dispatch_code(CODE, "a.py")  # a is now the most recent
        dispatcher.dispatch_code(CODE, "c.py")  # evicts b

        assert len(cache) == 2
        assert cache.evictions == 1
        dispatcher.dispatch_code(CODE, "a.py")
        assert cache.hits == 2
        dispatcher.dispatch_code(CODE, "b.py")
        assert cache.hits == 2

    # Verifies: REQ-d00331-D
    def test_bytes_are_bounded(self) -> None:
        cache = parse_cache.ParseCache(max_bytes=10)
        cache.put(("a",), b"12345")
        cache.put(("b",), b"12345")
        cache.put(("c",), b"12345")
        cache.put(("huge",), b"x" * 11)

        assert cache.size_bytes <= 10
        assert cache.get(("a",)) is None
        assert cache.get(("huge",)) is None
        assert cache.get(("c",)) == b"12345"


class TestThreads:
    # Verifies: REQ-d00331-A+C
    def test_concurrent_readings_agree_with_an_uncached_one(
        self, private_cache, monkeypatch
    ) -> None:
        paths = [f"src/m{i}.py" for i in range(8)]
        monkeypatch.setenv(parse_cache.ENV_VAR, "0")
        expected = {p: _dispatcher().dispatch_code(CODE, p) for p in paths}
        monkeypatch.setenv(parse_cache.ENV_VAR, "1")

        failures: list[str] = []
        barrier = threading.Barrier(8)

        def work(offset: int) -> None:
            dispatcher = _dispatcher()
            barrier.wait()
            for n in range(40):
                path = paths[(offset + n) % len(paths)]
                if dispatcher.dispatch_code(CODE, path) != expected[path]:
                    failures.append(path)

        threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not failures
        assert private_cache.hits + private_cache.misses == 8 * 40
        assert len(private_cache) == len(paths)


def _graph_text(root: Path) -> str:
    from elspais.graph.factory import build_graph
    from elspais.graph.serialize import serialize_graph

    data = serialize_graph(build_graph(repo_root=root))
    for node in data["nodes"].values():
        node.pop("uuid", None)
    return json.dumps(data, default=repr, sort_keys=True)


# Verifies: REQ-d00331-A
@pytest.mark.parametrize("fixture", ["hht-like", "e2e-standard"])
def test_a_build_is_the_same_graph_with_the_cache_on_or_off(
    private_cache, monkeypatch, fixture
) -> None:
    root = FIXTURES / fixture
    monkeypatch.setenv(parse_cache.ENV_VAR, "0")
    uncached = _graph_text(root)

    monkeypatch.setenv(parse_cache.ENV_VAR, "1")
    filling = _graph_text(root)
    misses = private_cache.misses
    answered = _graph_text(root)

    assert private_cache.misses == misses, "the second build parsed a file again"
    assert private_cache.hits > 0
    assert filling == uncached
    assert answered == uncached


# Verifies: REQ-d00331-G
@pytest.mark.parametrize("record,expected", [("1", "0"), ("", "<unset>")])
def test_a_tia_recording_run_turns_the_parse_cache_off(tmp_path, record, expected) -> None:
    """The unit tier's runner turns the cache off exactly when it records TIA.

    Stand-in ``pytest`` and ``python`` report the environment they were given
    and do nothing else, so no tier runs.
    """
    import os
    import subprocess

    runner = Path(__file__).resolve().parents[3] / ".githooks" / "run-unit-tier"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    seen = tmp_path / "seen"
    for name in ("pytest", "python"):
        stub = bin_dir / name
        stub.write_text(f'#!/bin/sh\necho "${{ELSPAIS_PARSE_CACHE-<unset>}}" >> "{seen}"\nexit 0\n')
        stub.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k != parse_cache.ENV_VAR}
    env.update(
        PATH=f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
        ELSPAIS_TEST_WORKERS="1",
        ELSPAIS_TIA_RECORD=record,
        ELSPAIS_TIA_BASELINE=str(tmp_path / "baseline"),
    )

    result = subprocess.run(
        ["bash", str(runner), str(tmp_path / "out")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    # The tier itself is the first process the runner starts.
    assert seen.read_text().splitlines()[0] == expected
