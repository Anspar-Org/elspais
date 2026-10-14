"""Helpers for tests whose fixture areas hold a test tool's coverage file."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def finish_coverage_area(repo_root: Path, config: dict | Any, target_name: str) -> None:
    """Record a fixture area's coverage the way a finished run does.

    The build reads a target's line coverage from its coverage record alone,
    so a fixture that writes a tool's coverage file into an output area calls
    this to record it. The area's fingerprint names the run where one exists.
    """
    from elspais.config import validate_config
    from elspais.utilities.coverage import finish_coverage
    from elspais.utilities.fingerprint import read_fingerprint, target_folder

    typed = validate_config(config) if isinstance(config, dict) else config
    target = next(t for t in typed.scanning.test.targets if t.name == target_name)
    root = Path(repo_root).resolve()
    fingerprint = read_fingerprint(target_folder(root, typed, target_name)) or {
        "commit": "",
        "root": str(root),
        "started_at": "fixture",
    }
    finish_coverage(root, typed, target, fingerprint, None)
