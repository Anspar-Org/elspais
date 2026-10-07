"""A remedy names the write scope where the change it asks for cannot reach.

With federation.write_associates false, a fix run from the primary repository
writes nothing in an associate. A finding in the associate whose remedy is that
fix says the write scope does not reach the associate, rather than naming a
command that would leave the finding in place.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

_PRIMARY_CONFIG = """\
version = 5

[project]
name = "primary"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = false

[associates.callisto]
path = "../callisto"
namespace = "CAL"
"""

_ASSOCIATE_CONFIG = """\
version = 5

[project]
name = "callisto"
namespace = "CAL"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = false
"""

_PRIMARY_SPEC = """\
# Primary Requirements

## REQ-p00001: Primary Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

Primary intro text.

### Assertions

A. The system SHALL validate input.

*End* *Primary Requirement* | **Hash**: deadbeef
"""

_ASSOCIATE_SPEC = """\
# Callisto Requirements

## CAL-p00001: Library Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

Library intro text.

### Assertions

A. The system SHALL process data.

*End* *Library Requirement* | **Hash**: 00000000
"""


@pytest.fixture()
def workspace(tmp_path: Path) -> dict[str, Path]:
    """A primary repository and an associate, each with one stale hash."""
    primary = tmp_path / "primary"
    associate = tmp_path / "callisto"
    (primary / "spec").mkdir(parents=True)
    (associate / "spec").mkdir(parents=True)
    (primary / ".elspais.toml").write_text(_PRIMARY_CONFIG)
    (primary / "spec" / "core.md").write_text(_PRIMARY_SPEC)
    (associate / ".elspais.toml").write_text(_ASSOCIATE_CONFIG)
    (associate / "spec" / "lib.md").write_text(_ASSOCIATE_SPEC)
    return {"primary": primary, "associate": associate}


def _spec_checks(primary: Path):
    from elspais.commands.health import run_spec_checks
    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    config = get_config(primary / ".elspais.toml", primary)
    graph = build_graph(config_path=primary / ".elspais.toml", repo_root=primary)
    return run_spec_checks(graph, config)


def _failing(checks, name: str) -> dict[str, str]:
    """Each failing check of *name*, keyed by the repository its findings name."""
    found: dict[str, str] = {}
    for check in checks:
        if check.name == name and not check.passed:
            repos = {f.repo for f in check.findings} or {None}
            for repo in repos:
                found[repo] = check.remedy
    return found


def _fix(primary: Path, monkeypatch) -> int:
    from elspais.commands.fix_cmd import run

    monkeypatch.chdir(primary)
    args = argparse.Namespace(
        req_id=None,
        dry_run=False,
        spec_dir=None,
        config=primary / ".elspais.toml",
        quiet=False,
        verbose=False,
        message=None,
        git_root=primary,
    )
    return run(args)


class TestRemedyNamesTheWriteScope:
    # Verifies: REQ-d00204-L
    def test_associate_rewrite_remedy_names_the_write_scope(self, workspace):
        remedies = _failing(_spec_checks(workspace["primary"]), "spec.needs_rewrite")

        assert remedies["primary"] == "elspais fix"
        associate = remedies["callisto"]
        assert "does not reach callisto" in associate
        assert "federation.write_associates" in associate
        assert not associate.startswith("elspais fix")

    # Verifies: REQ-d00204-L
    def test_stale_hash_remedy_names_each_unreached_member(self, workspace, monkeypatch):
        from elspais.utilities.findings import OUTSIDE_WRITE_SCOPE

        checks = _spec_checks(workspace["primary"])
        (mixed,) = [c for c in checks if c.name == "spec.hash_integrity"]
        assert not mixed.passed
        # Both members hold a stale hash: the fix resolves one of them here.
        assert mixed.remedy.startswith("elspais fix; ")
        assert f"{OUTSIDE_WRITE_SCOPE} callisto" in mixed.remedy

        assert _fix(workspace["primary"], monkeypatch) == 0
        checks = _spec_checks(workspace["primary"])
        (left,) = [c for c in checks if c.name == "spec.hash_integrity"]
        assert not left.passed
        # Only the associate's stale hash is left, which the fix cannot write.
        assert left.remedy.startswith(f"{OUTSIDE_WRITE_SCOPE} callisto")

    # Verifies: REQ-d00204-L
    def test_widened_write_scope_keeps_the_plain_remedy(self, workspace):
        config = workspace["primary"] / ".elspais.toml"
        config.write_text(_PRIMARY_CONFIG + "\n[federation]\nwrite_associates = true\n")

        checks = _spec_checks(workspace["primary"])

        assert set(_failing(checks, "spec.needs_rewrite").values()) == {"elspais fix"}
        (stale,) = [c for c in checks if c.name == "spec.hash_integrity"]
        assert stale.remedy == "elspais fix"

    # Verifies: REQ-d00204-L
    def test_markdown_renders_the_scoped_remedy_as_prose(self):
        from elspais.utilities.findings import (
            NO_KNOWN_REMEDY,
            remedy_is_command,
            remedy_outside_write_scope,
        )

        scoped = remedy_outside_write_scope("spec.needs_rewrite", ["callisto"], in_scope=False)
        assert not remedy_is_command(scoped)
        assert not remedy_is_command(NO_KNOWN_REMEDY)
        assert remedy_is_command("elspais fix")
        # A remedy that writes no file is the same wherever the finding lies.
        listing = remedy_outside_write_scope("spec.format_rules", ["callisto"], in_scope=False)
        assert listing == "elspais errors"
