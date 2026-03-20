# Validates REQ-p00001-A: CLI entry point arg dataclasses
"""Tests for Tyro CLI arg dataclasses in commands/args.py.

Validates REQ-p00001-A: CLI entry point argument parsing and subcommand routing.
"""
from __future__ import annotations

import dataclasses
import typing

import tyro

from elspais.commands.args import (
    AnalysisArgs,
    AssociateArgs,
    ChangedArgs,
    ChecksArgs,
    Command,
    CompletionArgs,
    ConfigArgs,
    ConfigGetArgs,
    ConfigShowArgs,
    DocsArgs,
    DoctorArgs,
    EditArgs,
    ExampleArgs,
    FixArgs,
    GlobalArgs,
    GraphArgs,
    InitArgs,
    InstallArgs,
    InstallLocalArgs,
    LinkArgs,
    LinkSuggestArgs,
    McpArgs,
    McpInstallArgs,
    McpServeArgs,
    PdfArgs,
    RulesArgs,
    RulesShowArgs,
    SummaryArgs,
    TraceArgs,
    UninstallArgs,
    UninstallLocalArgs,
    VersionArgs,
    ViewerArgs,
)


class TestCliArgsDataclasses:
    """Validates REQ-p00001-A: CLI arg dataclass definitions and Tyro parsing."""

    def test_REQ_p00001_A_global_args_has_all_subcommands(self) -> None:
        """All 22 top-level subcommand types are present in the Command Union."""
        # Extract the types from the Union
        args = typing.get_args(Command)
        # Each arg is Annotated[SomeArgs, subcommand(...)], extract the base type
        base_types = set()
        for arg in args:
            origin = typing.get_origin(arg)
            if origin is typing.Annotated:
                base_types.add(typing.get_args(arg)[0])
            else:
                base_types.add(arg)

        expected = {
            ChecksArgs,
            DoctorArgs,
            TraceArgs,
            ViewerArgs,
            GraphArgs,
            FixArgs,
            SummaryArgs,
            ChangedArgs,
            AnalysisArgs,
            VersionArgs,
            InitArgs,
            ExampleArgs,
            EditArgs,
            ConfigArgs,
            RulesArgs,
            DocsArgs,
            AssociateArgs,
            PdfArgs,
            InstallArgs,
            UninstallArgs,
            McpArgs,
            LinkArgs,
            CompletionArgs,
        }
        assert base_types == expected
        assert len(args) == 23

    def test_REQ_p00001_A_health_args_defaults(self) -> None:
        """ChecksArgs defaults are correct."""
        h = ChecksArgs()
        assert h.spec_only is False
        assert h.code_only is False
        assert h.tests_only is False
        assert h.format == "text"
        assert h.lenient is False
        assert h.status is None
        assert h.include_passing_details is False
        assert h.output is None

    def test_REQ_p00001_A_tyro_parses_health(self) -> None:
        """Tyro parses 'health --format json' into ChecksArgs."""
        result = tyro.cli(
            GlobalArgs,
            args=["checks", "--format", "json"],
        )
        assert isinstance(result.command, ChecksArgs)
        assert result.command.format == "json"

    def test_REQ_p00001_A_tyro_parses_config_show(self) -> None:
        """Tyro parses nested 'config show --format json'."""
        result = tyro.cli(
            GlobalArgs,
            args=["config", "show", "--format", "json"],
        )
        assert isinstance(result.command, ConfigArgs)
        assert isinstance(result.command.action, ConfigShowArgs)
        assert result.command.action.format == "json"

    def test_REQ_p00001_A_tyro_parses_config_get(self) -> None:
        """Tyro parses nested 'config get patterns.prefix' (positional key)."""
        result = tyro.cli(
            GlobalArgs,
            args=["config", "get", "patterns.prefix"],
        )
        assert isinstance(result.command, ConfigArgs)
        assert isinstance(result.command.action, ConfigGetArgs)
        assert result.command.action.key == "patterns.prefix"

    def test_REQ_p00001_A_tyro_parses_mcp_serve(self) -> None:
        """Tyro parses nested 'mcp serve'."""
        result = tyro.cli(
            GlobalArgs,
            args=["mcp", "serve"],
        )
        assert isinstance(result.command, McpArgs)
        assert isinstance(result.command.action, McpServeArgs)
        assert result.command.action.transport == "stdio"

    def test_REQ_p00001_A_tyro_parses_mcp_install(self) -> None:
        """Tyro parses 'mcp install --global-scope'."""
        result = tyro.cli(
            GlobalArgs,
            args=["mcp", "install", "--global-scope"],
        )
        assert isinstance(result.command, McpArgs)
        assert isinstance(result.command.action, McpInstallArgs)
        assert result.command.action.global_scope is True

    def test_REQ_p00001_A_tyro_parses_link_suggest(self) -> None:
        """Tyro parses 'link --format json' (single subcommand union)."""
        result = tyro.cli(
            GlobalArgs,
            args=["link", "--format", "json"],
        )
        assert isinstance(result.command, LinkArgs)
        assert isinstance(result.command.action, LinkSuggestArgs)
        assert result.command.action.format == "json"

    def test_REQ_p00001_A_tyro_parses_rules_show(self) -> None:
        """Tyro parses nested 'rules show AI-AGENT.md' (positional file)."""
        result = tyro.cli(
            GlobalArgs,
            args=["rules", "show", "AI-AGENT.md"],
        )
        assert isinstance(result.command, RulesArgs)
        assert isinstance(result.command.action, RulesShowArgs)
        assert result.command.action.file == "AI-AGENT.md"

    def test_REQ_p00001_A_global_args_verbose(self) -> None:
        """Verbose flag passes through on GlobalArgs."""
        result = tyro.cli(
            GlobalArgs,
            args=["--verbose", "checks"],
        )
        assert result.verbose is True
        assert isinstance(result.command, ChecksArgs)

    def test_REQ_p00001_A_tyro_parses_install_local(self) -> None:
        """Tyro parses 'install' subcommand."""
        result = tyro.cli(
            GlobalArgs,
            args=["install"],
        )
        assert isinstance(result.command, InstallArgs)
        assert isinstance(result.command.action, InstallLocalArgs)

    def test_REQ_p00001_A_tyro_parses_uninstall_local(self) -> None:
        """Tyro parses 'uninstall' subcommand."""
        result = tyro.cli(
            GlobalArgs,
            args=["uninstall"],
        )
        assert isinstance(result.command, UninstallArgs)
        assert isinstance(result.command.action, UninstallLocalArgs)

    def test_REQ_p00001_A_all_args_classes_are_dataclasses(self) -> None:
        """Every *Args class exported from args.py is a proper dataclass."""
        args_classes = [
            ChecksArgs,
            DoctorArgs,
            TraceArgs,
            ViewerArgs,
            GraphArgs,
            FixArgs,
            SummaryArgs,
            ChangedArgs,
            AnalysisArgs,
            VersionArgs,
            InitArgs,
            ExampleArgs,
            EditArgs,
            ConfigArgs,
            ConfigShowArgs,
            ConfigGetArgs,
            RulesArgs,
            RulesShowArgs,
            DocsArgs,
            AssociateArgs,
            PdfArgs,
            InstallArgs,
            InstallLocalArgs,
            UninstallArgs,
            UninstallLocalArgs,
            McpArgs,
            McpServeArgs,
            McpInstallArgs,
            LinkArgs,
            LinkSuggestArgs,
            CompletionArgs,
            GlobalArgs,
        ]
        for cls in args_classes:
            assert dataclasses.is_dataclass(cls), f"{cls.__name__} is not a dataclass"
