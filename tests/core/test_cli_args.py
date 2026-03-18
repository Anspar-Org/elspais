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
    HealthArgs,
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
        """All 23 top-level subcommand types are present in the Command Union."""
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
            HealthArgs,
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
            CompletionArgs,
            AssociateArgs,
            PdfArgs,
            InstallArgs,
            UninstallArgs,
            McpArgs,
            LinkArgs,
        }
        assert base_types == expected
        assert len(args) == 23

    def test_REQ_p00001_A_health_args_defaults(self) -> None:
        """HealthArgs defaults are correct."""
        h = HealthArgs()
        assert h.spec_only is False
        assert h.code_only is False
        assert h.tests_only is False
        assert h.format == "text"
        assert h.lenient is False
        assert h.status is None
        assert h.include_passing_details is False
        assert h.output is None

    def test_REQ_p00001_A_tyro_parses_health(self) -> None:
        """Tyro parses 'command:health --command.format json' into HealthArgs."""
        result = tyro.cli(
            GlobalArgs,
            args=["command:health", "--command.format", "json"],
        )
        assert isinstance(result.command, HealthArgs)
        assert result.command.format == "json"

    def test_REQ_p00001_A_tyro_parses_config_show(self) -> None:
        """Tyro parses nested config show subcommand."""
        result = tyro.cli(
            GlobalArgs,
            args=[
                "command:config",
                "command.action:show",
                "--command.action.format",
                "json",
            ],
        )
        assert isinstance(result.command, ConfigArgs)
        assert isinstance(result.command.action, ConfigShowArgs)
        assert result.command.action.format == "json"

    def test_REQ_p00001_A_tyro_parses_config_get(self) -> None:
        """Tyro parses nested config get with key."""
        result = tyro.cli(
            GlobalArgs,
            args=[
                "command:config",
                "command.action:get",
                "--command.action.key",
                "patterns.prefix",
            ],
        )
        assert isinstance(result.command, ConfigArgs)
        assert isinstance(result.command.action, ConfigGetArgs)
        assert result.command.action.key == "patterns.prefix"

    def test_REQ_p00001_A_tyro_parses_mcp_serve(self) -> None:
        """Tyro parses nested mcp serve subcommand."""
        result = tyro.cli(
            GlobalArgs,
            args=["command:mcp", "command.action:serve"],
        )
        assert isinstance(result.command, McpArgs)
        assert isinstance(result.command.action, McpServeArgs)
        assert result.command.action.transport == "stdio"

    def test_REQ_p00001_A_tyro_parses_mcp_install(self) -> None:
        """Tyro parses mcp install with --global_scope."""
        result = tyro.cli(
            GlobalArgs,
            args=[
                "command:mcp",
                "command.action:install",
                "--command.action.global-scope",
            ],
        )
        assert isinstance(result.command, McpArgs)
        assert isinstance(result.command.action, McpInstallArgs)
        assert result.command.action.global_scope is True

    def test_REQ_p00001_A_tyro_parses_link_suggest(self) -> None:
        """Tyro parses link suggest (single subcommand union)."""
        result = tyro.cli(
            GlobalArgs,
            args=[
                "command:link",
                "--command.action.format",
                "json",
            ],
        )
        assert isinstance(result.command, LinkArgs)
        assert isinstance(result.command.action, LinkSuggestArgs)
        assert result.command.action.format == "json"

    def test_REQ_p00001_A_tyro_parses_rules_show(self) -> None:
        """Tyro parses nested rules show with file."""
        result = tyro.cli(
            GlobalArgs,
            args=[
                "command:rules",
                "command.action:show",
                "--command.action.file",
                "AI-AGENT.md",
            ],
        )
        assert isinstance(result.command, RulesArgs)
        assert isinstance(result.command.action, RulesShowArgs)
        assert result.command.action.file == "AI-AGENT.md"

    def test_REQ_p00001_A_global_args_verbose(self) -> None:
        """Verbose flag passes through on GlobalArgs."""
        result = tyro.cli(
            GlobalArgs,
            args=["--verbose", "command:health"],
        )
        assert result.verbose is True
        assert isinstance(result.command, HealthArgs)

    def test_REQ_p00001_A_tyro_parses_install_local(self) -> None:
        """Tyro parses install local subcommand."""
        result = tyro.cli(
            GlobalArgs,
            args=["command:install"],
        )
        assert isinstance(result.command, InstallArgs)
        assert isinstance(result.command.action, InstallLocalArgs)

    def test_REQ_p00001_A_tyro_parses_uninstall_local(self) -> None:
        """Tyro parses uninstall local subcommand."""
        result = tyro.cli(
            GlobalArgs,
            args=["command:uninstall"],
        )
        assert isinstance(result.command, UninstallArgs)
        assert isinstance(result.command.action, UninstallLocalArgs)

    def test_REQ_p00001_A_all_args_classes_are_dataclasses(self) -> None:
        """Every *Args class exported from args.py is a proper dataclass."""
        args_classes = [
            HealthArgs,
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
            CompletionArgs,
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
            GlobalArgs,
        ]
        for cls in args_classes:
            assert dataclasses.is_dataclass(cls), f"{cls.__name__} is not a dataclass"
