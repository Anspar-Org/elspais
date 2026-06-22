"""Tests for JSON Schema export and `elspais config schema` command.

Validates REQ-d00208-A: cmd_schema outputs JSON Schema to stdout/file
Validates REQ-d00208-B: committed schema file matches model output
Validates REQ-d00208-C: generated schema includes $schema and title keys
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from elspais.config.schema import ElspaisConfig

# Path to the committed schema file (relative to repo root)
_REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILE = _REPO_ROOT / "src" / "elspais" / "config" / "elspais-schema.json"


class TestJsonSchemaExport:
    """Validates REQ-d00208-A: cmd_schema outputs JSON Schema to stdout."""

    def test_REQ_d00208_A_cmd_schema_outputs_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        """cmd_schema() must write valid JSON Schema to stdout."""
        # cmd_schema should exist and return 0
        import argparse

        from elspais.commands.config_cmd import cmd_schema

        args = argparse.Namespace(output=None)
        rc = cmd_schema(args)
        assert rc == 0

        captured = capsys.readouterr()
        schema = json.loads(captured.out)
        assert isinstance(schema, dict)
        assert "properties" in schema

    def test_REQ_d00208_A_cmd_schema_always_writes_to_stdout(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """cmd_schema always writes to stdout; --output redirection is the CLI's job.

        File writing is handled generically by cli.py (redirect stdout → file).
        cmd_schema must NOT independently write to args.output — that would
        collide with the CLI's generic redirect and corrupt the output file.
        """
        import argparse

        from elspais.commands.config_cmd import cmd_schema

        # Even with output set, cmd_schema only writes to stdout
        args = argparse.Namespace(output="/dev/null")  # must be ignored by cmd_schema
        rc = cmd_schema(args)
        assert rc == 0

        captured = capsys.readouterr()
        schema = json.loads(captured.out)
        assert isinstance(schema, dict)
        assert "properties" in schema

    def test_REQ_d00208_A_cli_output_flag_produces_valid_json(self, tmp_path: Path) -> None:
        """elspais config schema --output FILE via cli.main() must produce pure valid JSON.

        Regression for the double-write corruption bug: cli.py redirects stdout
        to the file AND cmd_schema independently wrote to the same file, resulting
        in a file beginning with "Schema written to ..." followed by truncated JSON.
        After the fix, only the generic CLI redirect writes; cmd_schema only writes
        to stdout.
        """
        # Verifies: REQ-d00208-A
        from elspais.cli import main

        outfile = tmp_path / "schema_via_cli.json"
        # Redirect stderr to suppress "Generated: ..." notice during test
        rc = main(["config", "schema", "--output", str(outfile)])
        assert rc == 0

        content = outfile.read_text(encoding="utf-8")

        # File must NOT contain any status/notice text from cmd_schema or cli.py
        assert "Schema written" not in content, (
            "File contains 'Schema written' — cmd_schema is independently writing to the file "
            "in addition to the generic stdout redirect in cli.py"
        )
        assert (
            "Generated:" not in content
        ), "File contains 'Generated:' — the CLI notice leaked into the output file"

        # File must be pure valid JSON equal to the model schema
        schema = json.loads(content)  # raises JSONDecodeError if corrupt
        assert (
            schema == ElspaisConfig.model_json_schema()
        ), "Schema written via --output does not match ElspaisConfig.model_json_schema()"


class TestCommittedSchemaFile:
    """Validates REQ-d00208-B: committed schema file matches model output."""

    def test_REQ_d00208_B_committed_schema_matches_model(self) -> None:
        """The committed elspais-schema.json must match ElspaisConfig.model_json_schema()."""
        assert SCHEMA_FILE.exists(), (
            f"Committed schema file not found at {SCHEMA_FILE}. "
            "Run `elspais config schema --output <path>` to generate it."
        )

        committed = json.loads(SCHEMA_FILE.read_text())
        generated = ElspaisConfig.model_json_schema()

        assert committed == generated, (
            "Committed schema is out of date. Regenerate with: "
            "elspais config schema --output src/elspais/config/elspais-schema.json"
        )


class TestSchemaContent:
    """Validates REQ-d00208-C: generated schema includes $schema and title keys."""

    def test_REQ_d00208_C_schema_has_required_keys(self) -> None:
        """model_json_schema() output must include $schema and title top-level keys."""
        schema = ElspaisConfig.model_json_schema()

        assert "title" in schema, "Generated JSON Schema must have a 'title' key"
        assert "$schema" in schema, (
            "Generated JSON Schema must have a '$schema' key. "
            "The implementation should inject this via schema_extra or post-processing."
        )

    def test_REQ_d00208_C_schema_title_is_elspais_config(self) -> None:
        """The schema title should be 'ElspaisConfig'."""
        schema = ElspaisConfig.model_json_schema()
        assert schema.get("title") == "ElspaisConfig"

    def test_REQ_d00208_C_schema_is_valid_json_schema(self) -> None:
        """The generated schema must be a valid JSON Schema document."""
        schema = ElspaisConfig.model_json_schema()

        # Basic structural checks for a JSON Schema document
        assert isinstance(schema, dict)
        assert "properties" in schema or "$defs" in schema
        assert schema.get("type") == "object"
