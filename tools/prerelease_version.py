"""The pre-release version of an automain commit.

A pre-release is the PEP 440 developmental release ``X.Y.Z.devN``. ``X.Y.Z``
is the version the commit declares, or the patch after the newest release
where the declared version is not above it, so the pre-release sorts above
every release. ``N`` is the count of first-parent commits on automain at the
commit. An installer selects a developmental release only for a requirement
that names a pre-release, and a version the package index carries or carried
is never computed twice: such a version is refused, never renumbered.

Usage::

    python -m tools.prerelease_version --pyproject pyproject.toml \\
        --index pypi.json --count 1234 [--write]

``--index`` is the package index's JSON description of the project; the keys
of its ``releases`` table are every version the index lists.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections.abc import Iterable
from pathlib import Path

from packaging.version import InvalidVersion, Version


class PrereleaseRefused(ValueError):
    """No pre-release version can be published for these inputs."""


def _parsed(versions: Iterable[str]) -> list[Version]:
    out = []
    for text in versions:
        try:
            out.append(Version(text))
        except InvalidVersion:
            continue
    return out


def _is_final(version: Version) -> bool:
    return not (
        version.is_prerelease or version.is_postrelease or version.is_devrelease or version.local
    )


# Implements: REQ-o00081-B+C
def prerelease_version(declared: str, carried: Iterable[str], count: int) -> str:
    """Return the pre-release version for a commit declaring ``declared``.

    ``carried`` is every version the package index lists, yanked ones
    included. ``count`` is the commit's first-parent count on automain.
    """
    try:
        declared_version = Version(declared)
    except InvalidVersion as exc:
        raise PrereleaseRefused(
            f"the declared version {declared!r} is not a PEP 440 version"
        ) from exc
    if not _is_final(declared_version):
        raise PrereleaseRefused(
            f"the declared version {declared} is not a final release (X.Y.Z); "
            "a pre-release is computed from a final version"
        )
    if count < 1:
        raise PrereleaseRefused(f"the commit count {count} is not a positive number")

    carried_versions = _parsed(carried)
    releases = [v for v in carried_versions if _is_final(v)]
    newest = max(releases, default=None)
    if newest is None or declared_version > newest:
        base = declared_version.base_version
    else:
        parts = list(newest.release)
        parts[-1] += 1
        base = ".".join(str(p) for p in parts)

    result = f"{base}.dev{count}"
    # N names one automain commit whatever the base, so a carried pre-release
    # with this N is this commit's, published under an earlier base.
    same_commit = [str(v) for v in carried_versions if v.dev == count]
    if same_commit:
        raise PrereleaseRefused(
            f"the package index already carries or carried {same_commit[0]}, the "
            f"pre-release with number {count}; a number is never reused. Either this "
            "commit's pre-release is already published (a re-run publishes nothing), "
            "or automain's first-parent history was rewritten"
        )
    return result


_VERSION_LINE = re.compile(r'^(version\s*=\s*)"[^"]*"', re.MULTILINE)


def _write_version(pyproject: Path, version: str) -> None:
    """Rewrite the ``[project]`` version line and leave every other byte."""
    text = pyproject.read_bytes().decode("utf-8")
    start = re.search(r"^\[project\]\s*$", text, re.MULTILINE)
    if start is None:
        raise PrereleaseRefused(f"{pyproject} holds no [project] table")
    end = re.search(r"^\[", text[start.end() :], re.MULTILINE)
    stop = start.end() + end.start() if end else len(text)
    table = text[start.end() : stop]
    new_table, replaced = _VERSION_LINE.subn(lambda m: f'{m.group(1)}"{version}"', table, count=1)
    if replaced != 1:
        raise PrereleaseRefused(f"{pyproject} declares no version in its [project] table")
    pyproject.write_bytes((text[: start.end()] + new_table + text[stop:]).encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pyproject", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--write", action="store_true", help="write the version into --pyproject")
    args = parser.parse_args(argv)

    with open(args.pyproject, "rb") as f:
        declared = tomllib.load(f).get("project", {}).get("version", "")
    carried = json.loads(args.index.read_text(encoding="utf-8")).get("releases", {})
    try:
        version = prerelease_version(str(declared), carried.keys(), args.count)
        if args.write:
            _write_version(args.pyproject, version)
    except PrereleaseRefused as exc:
        print(f"Refusing to compute a pre-release version: {exc}", file=sys.stderr)
        return 1
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
