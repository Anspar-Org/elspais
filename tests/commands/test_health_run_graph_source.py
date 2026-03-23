# tests/commands/test_health_run_graph_source.py
# Implements: REQ-d00010

"""Tests that the checks run() function passes graph_source to output."""

import argparse
from unittest.mock import patch

from elspais.commands import _engine as _engine_mod
from elspais.commands.health import run


def test_run_passes_daemon_source_to_report(capsys):
    """run() should display daemon source when engine returns it."""
    fake_data = {
        "healthy": True,
        "summary": {"passed": 1, "failed": 0, "warnings": 0, "skipped": 0},
        "checks": [
            {
                "name": "spec.parseable",
                "passed": True,
                "message": "Parsed 10 requirements",
                "category": "spec",
                "severity": "error",
                "details": {},
                "findings": [],
            }
        ],
        "graph_source": {
            "type": "daemon",
            "port": 35121,
            "started_at": "2026-03-23T10:19:59",
        },
    }

    args = argparse.Namespace(
        format="text",
        lenient=False,
        quiet=False,
        verbose=False,
        include_passing_details=False,
        spec_only=False,
        code_only=False,
        tests_only=False,
        spec_dir=None,
        status=None,
        config=None,
        canonical_root=None,
        output=None,
    )

    with patch.object(_engine_mod, "call", return_value=fake_data):
        exit_code = run(args)

    captured = capsys.readouterr()
    assert "daemon" in captured.out
    assert "35121" in captured.out
    assert exit_code == 0
