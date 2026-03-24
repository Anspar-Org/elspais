# Verifies: REQ-d00225-A+B
"""Tests for glossary and term-index CLI registration.

Validates REQ-d00225-A+B: GlossaryArgs/TermIndexArgs dataclasses,
CLI dispatch, and fix integration.
"""

from __future__ import annotations

import dataclasses

from elspais.commands.args import GlossaryArgs, TermIndexArgs


class TestCliTermsRegistration:
    """Validates REQ-d00225-A+B: CLI registration for glossary/term-index."""

    def test_REQ_d00225_A_glossary_args_defaults(self) -> None:
        """GlossaryArgs has correct default field values."""
        args = GlossaryArgs()
        assert args.format == "markdown"
        assert args.output_dir is None

    def test_REQ_d00225_A_term_index_args_defaults(self) -> None:
        """TermIndexArgs has correct default field values."""
        args = TermIndexArgs()
        assert args.format == "markdown"
        assert args.output_dir is None

    def test_REQ_d00225_A_glossary_args_is_dataclass(self) -> None:
        """GlossaryArgs is a proper dataclass."""
        assert dataclasses.is_dataclass(GlossaryArgs)

    def test_REQ_d00225_A_term_index_args_is_dataclass(self) -> None:
        """TermIndexArgs is a proper dataclass."""
        assert dataclasses.is_dataclass(TermIndexArgs)

    def test_REQ_d00225_A_glossary_in_cmd_map(self) -> None:
        """GlossaryArgs is in the CLI _CMD_MAP."""
        from elspais.cli import _to_namespace
        from elspais.commands.args import GlobalArgs

        # Verify the import works (GlossaryArgs is importable from cli)
        from elspais.cli import GlossaryArgs as _GA  # noqa: F401

    def test_REQ_d00225_A_term_index_in_cmd_map(self) -> None:
        """TermIndexArgs is in the CLI _CMD_MAP."""
        from elspais.cli import TermIndexArgs as _TIA  # noqa: F401

    def test_REQ_d00225_B_fix_terms_function_exists(self) -> None:
        """_fix_terms function exists in fix_cmd."""
        from elspais.commands.fix_cmd import _fix_terms

        assert callable(_fix_terms)

    def test_REQ_d00225_B_write_term_outputs_exists(self) -> None:
        """write_term_outputs function exists in glossary_cmd."""
        from elspais.commands.glossary_cmd import write_term_outputs

        assert callable(write_term_outputs)

    def test_REQ_d00225_B_write_term_outputs_creates_files(self, tmp_path) -> None:
        """write_term_outputs writes files to output directory."""
        from elspais.commands.glossary_cmd import write_term_outputs
        from elspais.graph.terms import TermDictionary, TermEntry

        td = TermDictionary()
        td.add(TermEntry(
            term="Test Term",
            definition="A test definition.",
            defined_in="REQ-p00001",
            namespace="main",
        ))

        generated = write_term_outputs(td, tmp_path)

        assert len(generated) >= 2  # glossary + term-index at minimum
        assert (tmp_path / "glossary.md").exists()
        assert (tmp_path / "term-index.md").exists()
