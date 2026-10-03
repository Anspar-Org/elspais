"""The named-file-pattern check reads each skip pattern against a root path.

A ``file_patterns`` entry with no wildcard names one file, which sits under a
scanned directory. A skip pattern is read against the path from the
repository root, so the check joins the entry under each directory before it
asks whether a skip pattern excludes it.
"""

from __future__ import annotations

import pytest

from elspais.commands.health import check_unmatched_file_pattern
from elspais.config import config_defaults

CHECK = "config.unmatched_file_pattern"


def _config(
    *,
    file_patterns: list[str],
    global_skip: list[str] | None = None,
    code_skip_files: list[str] | None = None,
) -> dict:
    cfg = config_defaults()
    scanning = cfg["scanning"]
    scanning["skip"] = list(global_skip or [])
    scanning["code"]["directories"] = ["src"]
    scanning["code"]["file_patterns"] = list(file_patterns)
    scanning["code"]["skip_files"] = list(code_skip_files or [])
    return cfg


def _skip_kwargs(where: str, skip: str) -> dict:
    if where == "global":
        return {"global_skip": [skip]}
    return {"code_skip_files": [skip]}


# Verifies: REQ-d00326-A
@pytest.mark.parametrize("where", ["global", "skip_files"])
def test_root_anchored_skip_naming_the_file_is_reported(where: str) -> None:
    """A skip pattern holding ``/`` names the file by its path from the root.

    The file pattern ``gen/out.py`` under directory ``src`` is the file
    ``src/gen/out.py``. Asking with the bare entry ``gen/out.py`` would not
    match the root-anchored skip ``src/gen/out.py``, so this exclusion was
    not found before the check joined the entry under its directory.
    """
    cfg = _config(file_patterns=["gen/out.py"], **_skip_kwargs(where, "src/gen/out.py"))

    result = check_unmatched_file_pattern(None, cfg)

    assert result.passed is False
    assert len(result.findings) == 1
    message = result.findings[0].message
    assert "'gen/out.py'" in message
    assert "'src/gen/out.py'" in message


# Verifies: REQ-d00326-A
@pytest.mark.parametrize("where", ["global", "skip_files"])
@pytest.mark.parametrize(
    ("file_pattern", "skip", "reported"),
    [
        # Root-anchored at gen/, which is not where the file sits (src/gen/).
        ("gen/out.py", "gen/out.py", False),
        # A pattern with no "/" is a name glob at any depth.
        ("gen/out.py", "out.py", True),
        # A wildcard entry describes a class of files; skipping some is normal.
        ("gen/*.py", "src/gen/out.py", False),
        ("gen/*.py", "out.py", False),
    ],
)
def test_skip_pattern_read_as_path_from_root(
    where: str, file_pattern: str, skip: str, reported: bool
) -> None:
    cfg = _config(file_patterns=[file_pattern], **_skip_kwargs(where, skip))

    result = check_unmatched_file_pattern(None, cfg)

    assert result.passed is (not reported)
    assert len(result.findings) == (1 if reported else 0)
    if reported:
        message = result.findings[0].message
        assert f"'{file_pattern}'" in message
        assert f"'{skip}'" in message


# Verifies: REQ-d00285-G
def test_check_turned_off_reports_nothing() -> None:
    cfg = _config(file_patterns=["gen/out.py"], global_skip=["src/gen/out.py"])
    cfg.setdefault("rules", {}).setdefault("severity", {})[CHECK] = "off"

    result = check_unmatched_file_pattern(None, cfg)

    assert result.passed is True
    assert result.findings == []
    assert result.details.get("skipped") is True
