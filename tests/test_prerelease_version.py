"""Tests for the pre-release version of an automain commit (REQ-o00081).

The version is checked by what an installer and the package index make of it,
read through `packaging`, as well as by its spelling: an installer never
selects it for a requirement naming no pre-release, an exact pin reaches it,
it sorts above every release, and no version the index carries equals it.
"""

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from tools.prerelease_version import PrereleaseRefused, prerelease_version

REPO_ROOT = Path(__file__).parent.parent


def _final_releases(carried: list[str]) -> list[Version]:
    found = []
    for text in carried:
        try:
            version = Version(text)
        except InvalidVersion:
            continue
        if not (version.is_prerelease or version.is_devrelease or version.is_postrelease):
            found.append(version)
    return found


def _parsed(carried: list[str]) -> list[Version]:
    found = []
    for text in carried:
        try:
            found.append(Version(text))
        except InvalidVersion:
            continue
    return found


#: (declared, carried, count, expected)
_COMPUTED = [
    pytest.param("0.130.0", [], 5, "0.130.0.dev5", id="nothing-released"),
    pytest.param(
        "0.130.0", ["0.129.17", "0.129.16"], 12, "0.130.0.dev12", id="declared-above-releases"
    ),
    pytest.param(
        "0.129.17", ["0.129.17", "0.129.16"], 12, "0.129.18.dev12", id="declared-already-released"
    ),
    pytest.param(
        "0.129.10", ["0.130.7", "0.129.17"], 3, "0.130.8.dev3", id="declared-below-newest"
    ),
    pytest.param(
        "0.130.0",
        ["0.129.17", "0.130.0rc1", "0.130.0.dev4", "0.131.0.dev2"],
        9,
        "0.130.0.dev9",
        id="pre-releases-do-not-bump",
    ),
    pytest.param(
        "1.0.0",
        ["0.9", "nightly-build", "1.0.0-not+a version"],
        1,
        "1.0.0.dev1",
        id="legacy-ignored",
    ),
    pytest.param("1.2.3", ["1.2.3.4", "1.2.2"], 7, "1.2.3.5.dev7", id="four-part-release"),
    pytest.param(
        "0.130.0", ["0.129.17", "0.130.0.dev4"], 5, "0.130.0.dev5", id="other-number-same-base"
    ),
    pytest.param(
        "0.130.7",
        ["0.130.7.dev811", "0.130.7"],
        812,
        "0.130.8.dev812",
        id="other-number-earlier-base",
    ),
]


class TestComputedVersion:
    # Verifies: REQ-o00081-B+C
    @pytest.mark.parametrize("declared,carried,count,expected", _COMPUTED)
    def test_REQ_o00081_B_version_is_the_developmental_release(
        self, declared, carried, count, expected
    ):
        assert prerelease_version(declared, carried, count) == expected

    # Verifies: REQ-o00081-B
    @pytest.mark.parametrize("declared,carried,count,expected", _COMPUTED)
    def test_REQ_o00081_B_no_installer_selects_it_unasked(self, declared, carried, count, expected):
        """Offered the index's releases beside it, a requirement naming no
        pre-release selects a release, never the pre-release; an exact pin
        selects the pre-release. `filter` is the PEP 440 selection: it admits
        a pre-release only where the specifier names one or nothing else
        satisfies it, and the package's index always carries a release."""
        result = prerelease_version(declared, carried, count)
        version = Version(result)
        assert version.is_prerelease
        assert version.dev == count
        releases = [str(v) for v in _final_releases(carried)] or ["0.1.0"]
        offered = [*releases, result]
        for unasked in ("", ">=0", f">={min(releases, key=Version)}"):
            selected = list(SpecifierSet(unasked).filter(offered))
            assert selected, unasked
            assert result not in selected, unasked
        assert list(SpecifierSet(f"=={result}").filter(offered)) == [result]

    # Verifies: REQ-o00081-C
    @pytest.mark.parametrize("declared,carried,count,expected", _COMPUTED)
    def test_REQ_o00081_C_version_differs_from_every_carried_one(
        self, declared, carried, count, expected
    ):
        """The version sorts above every release and equals no version the
        index carries, under PEP 440's own comparison."""
        version = Version(prerelease_version(declared, carried, count))
        assert all(version > release for release in _final_releases(carried))
        assert all(version != other for other in _parsed(carried))


class TestRefusal:
    # Verifies: REQ-o00081-C
    @pytest.mark.parametrize(
        "declared,carried,count",
        [
            pytest.param("0.130.0", ["0.129.17", "0.130.0.dev5"], 5, id="already-published"),
            pytest.param("0.130.0", ["0.129.17", "0.130.0.dev05"], 5, id="padded-spelling"),
            pytest.param(
                "0.129.17", ["0.129.17", "0.129.18.dev12"], 12, id="bumped-version-published"
            ),
            pytest.param("0.129.17", ["0.129.17", "0.129.18.DEV12"], 12, id="other-case"),
            pytest.param(
                "0.130.7", ["0.130.7", "0.130.7.dev812"], 812, id="same-number-earlier-base"
            ),
            pytest.param(
                "0.131.0", ["0.130.7", "0.129.3.dev812"], 812, id="same-number-other-base"
            ),
        ],
    )
    def test_REQ_o00081_C_a_carried_version_is_refused(self, declared, carried, count):
        """A version the index holds or held is never computed again, and
        neither is a second version for one commit: N names one automain
        commit, so a carried pre-release numbered N refuses whatever its base,
        as after a release moved the base under a re-run. The refusal names
        the carried version."""
        with pytest.raises(PrereleaseRefused) as refused:
            prerelease_version(declared, carried, count)
        assert isinstance(refused.value, ValueError)
        assert str(Version(carried[-1])) in str(refused.value)

    # Verifies: REQ-o00081-B
    @pytest.mark.parametrize(
        "declared",
        ["0.130.0rc1", "0.130.0.dev3", "0.130.0.post1", "0.130.0+local", "not-a-version", ""],
    )
    def test_REQ_o00081_B_declared_version_must_be_final(self, declared):
        with pytest.raises(PrereleaseRefused):
            prerelease_version(declared, ["0.129.17"], 4)

    # Verifies: REQ-o00081-B
    @pytest.mark.parametrize("count", [0, -1])
    def test_REQ_o00081_B_count_must_be_positive(self, count):
        with pytest.raises(PrereleaseRefused):
            prerelease_version("0.130.0", ["0.129.17"], count)


# --- The command the pre-release workflow runs ---

_PYPROJECT = """\
# The version this project declares; a note naming version = "9.9.9" is prose.
[tool.first]
version = "2.2.2"

[project]
name = "demo"
# rewritten for a pre-release
version = "0.130.0"
description = "A demo"

[tool.demo]
version = "1.1.1"
"""


def _index(path: Path, versions: list[str]) -> Path:
    path.write_text(
        json.dumps(
            {
                "info": {"name": "demo", "version": "0.129.17"},
                "releases": {v: [{"yanked": v.endswith("16")}] for v in versions},
            }
        )
    )
    return path


def _command(tmp_path: Path, versions: list[str], count: int, write: bool):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_bytes(_PYPROJECT.encode())
    index = _index(tmp_path / "pypi.json", versions)
    args = [
        sys.executable,
        "-m",
        "tools.prerelease_version",
        "--pyproject",
        str(pyproject),
        "--index",
        str(index),
        "--count",
        str(count),
        *(["--write"] if write else []),
    ]
    result = subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True, timeout=60)
    return result, pyproject


class TestCommand:
    # Verifies: REQ-o00081-B+C
    def test_REQ_o00081_B_prints_the_version_and_writes_nothing(self, tmp_path):
        result, pyproject = _command(tmp_path, ["0.129.17", "0.129.16"], 7, write=False)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "0.130.0.dev7"
        assert pyproject.read_bytes() == _PYPROJECT.encode()

    # Verifies: REQ-o00081-B+C
    def test_REQ_o00081_B_write_rewrites_only_the_project_version(self, tmp_path):
        """The build reads the pre-release version from [project]; every other
        byte, the other tables' version keys among them, stays as written."""
        result, pyproject = _command(tmp_path, ["0.130.0", "0.129.16"], 7, write=True)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "0.130.1.dev7"
        before = _PYPROJECT.encode().splitlines(keepends=True)
        after = pyproject.read_bytes().splitlines(keepends=True)
        assert len(after) == len(before)
        changed = [i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b]
        assert changed == [before.index(b'version = "0.130.0"\n')]
        with open(pyproject, "rb") as f:
            written = tomllib.load(f)
        assert written["project"]["version"] == "0.130.1.dev7"
        assert written["tool"]["first"]["version"] == "2.2.2"
        assert written["tool"]["demo"]["version"] == "1.1.1"

    # Verifies: REQ-o00081-C
    @pytest.mark.parametrize("write", [False, True])
    @pytest.mark.parametrize(
        "versions",
        [
            pytest.param(["0.129.17", "0.130.0.dev7"], id="same-version"),
            pytest.param(["0.130.0", "0.130.0.dev7"], id="released-since"),
        ],
    )
    def test_REQ_o00081_C_refusal_exits_1_and_leaves_the_file(self, tmp_path, versions, write):
        """A re-run for a commit whose pre-release is published -- before or
        after a release moved the base -- is refused, naming the version it
        already took, and nothing is written."""
        result, pyproject = _command(tmp_path, versions, 7, write=write)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "0.130.0.dev7" in result.stderr
        assert result.stdout.strip() == ""
        assert pyproject.read_bytes() == _PYPROJECT.encode()
