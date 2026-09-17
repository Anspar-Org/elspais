# Validates REQ-p00001-A: CLI entry point arg dataclasses
"""Tests for Tyro CLI arg dataclasses in commands/args.py.

Validates REQ-p00001-A: CLI entry point argument parsing and subcommand routing.
"""

from __future__ import annotations

import dataclasses
import typing

import tyro

from elspais.commands.args import (
    COMMAND_GROUPS,
    AnalysisArgs,
    AssociateArgs,
    ChangedArgs,
    ChecksArgs,
    Command,
    CommentsArgs,
    CompletionArgs,
    ConfigArgs,
    ConfigGetArgs,
    ConfigShowArgs,
    DaemonArgs,
    DocsArgs,
    DoctorArgs,
    EditArgs,
    ErrorsArgs,
    ExampleArgs,
    FailingArgs,
    FixArgs,
    GapsArgs,
    GlobalArgs,
    GlossaryArgs,
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
    SearchArgs,
    SummaryArgs,
    TermIndexArgs,
    TraceArgs,
    UncitedArgs,
    UncoveredArgs,
    UninstallArgs,
    UninstallLocalArgs,
    UnresolvedArgs,
    UntestedArgs,
    UnvalidatedArgs,
    VersionArgs,
    ViewerArgs,
    generate_help,
    iter_command_entries,
)


class TestCliArgsDataclasses:
    """Validates REQ-p00001-A: CLI arg dataclass definitions and Tyro parsing."""

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_global_args_has_all_subcommands(self) -> None:
        """All top-level subcommand types are present in the Command Union."""
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
            DaemonArgs,
            LinkArgs,
            CompletionArgs,
            GapsArgs,
            UncoveredArgs,
            UntestedArgs,
            UnvalidatedArgs,
            FailingArgs,
            ErrorsArgs,
            UnresolvedArgs,
            UncitedArgs,
            SearchArgs,
            GlossaryArgs,
            TermIndexArgs,
            CommentsArgs,
        }
        assert base_types == expected
        assert len(args) == 36

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_health_args_defaults(self) -> None:
        """ChecksArgs defaults are correct."""
        h = ChecksArgs()
        assert h.spec_only is False
        assert h.code_only is False
        assert h.tests_only is False
        assert h.format == "text"
        assert h.lenient is False
        # A list flag that accumulates (REQ-p00084-H) defaults to no names
        # rather than to None; `_scope.flag_values` reads both as none named.
        assert h.treat_active == []
        assert h.include_passing_details is False
        assert h.output is None

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_tyro_parses_health(self) -> None:
        """Tyro parses 'health --format json' into ChecksArgs."""
        result = tyro.cli(
            GlobalArgs,
            args=["checks", "--format", "json"],
        )
        assert isinstance(result.command, ChecksArgs)
        assert result.command.format == "json"

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_tyro_parses_config_show(self) -> None:
        """Tyro parses nested 'config show --format json'."""
        result = tyro.cli(
            GlobalArgs,
            args=["config", "show", "--format", "json"],
        )
        assert isinstance(result.command, ConfigArgs)
        assert isinstance(result.command.action, ConfigShowArgs)
        assert result.command.action.format == "json"

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_tyro_parses_config_get(self) -> None:
        """Tyro parses nested 'config get patterns.prefix' (positional key)."""
        result = tyro.cli(
            GlobalArgs,
            args=["config", "get", "patterns.prefix"],
        )
        assert isinstance(result.command, ConfigArgs)
        assert isinstance(result.command.action, ConfigGetArgs)
        assert result.command.action.key == "patterns.prefix"

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_tyro_parses_mcp_serve(self) -> None:
        """Tyro parses nested 'mcp serve'."""
        result = tyro.cli(
            GlobalArgs,
            args=["mcp", "serve"],
        )
        assert isinstance(result.command, McpArgs)
        assert isinstance(result.command.action, McpServeArgs)
        assert result.command.action.transport == "stdio"

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_tyro_parses_mcp_install(self) -> None:
        """Tyro parses 'mcp install --global' (maps to global_scope field)."""
        result = tyro.cli(
            GlobalArgs,
            args=["mcp", "install", "--global"],
        )
        assert isinstance(result.command, McpArgs)
        assert isinstance(result.command.action, McpInstallArgs)
        assert result.command.action.global_scope is True

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_tyro_parses_link_suggest(self) -> None:
        """Tyro parses 'link --format json' (single subcommand union)."""
        result = tyro.cli(
            GlobalArgs,
            args=["link", "--format", "json"],
        )
        assert isinstance(result.command, LinkArgs)
        assert isinstance(result.command.action, LinkSuggestArgs)
        assert result.command.action.format == "json"

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_tyro_parses_rules_show(self) -> None:
        """Tyro parses nested 'rules show AI-AGENT.md' (positional file)."""
        result = tyro.cli(
            GlobalArgs,
            args=["rules", "show", "AI-AGENT.md"],
        )
        assert isinstance(result.command, RulesArgs)
        assert isinstance(result.command.action, RulesShowArgs)
        assert result.command.action.file == "AI-AGENT.md"

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_global_args_verbose(self) -> None:
        """Verbose flag passes through on GlobalArgs."""
        result = tyro.cli(
            GlobalArgs,
            args=["--verbose", "checks"],
        )
        assert result.verbose is True
        assert isinstance(result.command, ChecksArgs)

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_tyro_parses_install_local(self) -> None:
        """Tyro parses 'install' subcommand."""
        result = tyro.cli(
            GlobalArgs,
            args=["install"],
        )
        assert isinstance(result.command, InstallArgs)
        assert isinstance(result.command.action, InstallLocalArgs)

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_tyro_parses_uninstall_local(self) -> None:
        """Tyro parses 'uninstall' subcommand."""
        result = tyro.cli(
            GlobalArgs,
            args=["uninstall"],
        )
        assert isinstance(result.command, UninstallArgs)
        assert isinstance(result.command.action, UninstallLocalArgs)

    # Verifies: REQ-p00001-A
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
            GapsArgs,
            UncoveredArgs,
            UntestedArgs,
            UnvalidatedArgs,
            FailingArgs,
            ErrorsArgs,
            UnresolvedArgs,
            UncitedArgs,
            GlobalArgs,
        ]
        for cls in args_classes:
            assert dataclasses.is_dataclass(cls), f"{cls.__name__} is not a dataclass"

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_command_groups_covers_all_subcommands(self) -> None:
        """Every subcommand in the Command Union has a COMMAND_GROUPS entry."""
        args = typing.get_args(Command)
        subcommand_names = set()
        for arg in args:
            if typing.get_origin(arg) is typing.Annotated:
                _, *metadata = typing.get_args(arg)
                for m in metadata:
                    if hasattr(m, "name"):
                        subcommand_names.add(m.name)

        missing = subcommand_names - set(COMMAND_GROUPS)
        assert not missing, (
            f"Subcommands missing from COMMAND_GROUPS: {missing}. "
            f"Add them to elspais/commands/args.py"
        )
        # Also check no stale entries in COMMAND_GROUPS
        extra = set(COMMAND_GROUPS) - subcommand_names
        assert not extra, f"Stale entries in COMMAND_GROUPS (not in Command Union): {extra}"

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_command_entries_covers_the_command_union(self) -> None:
        """iter_command_entries() names every command the Command Union declares."""
        declared = set()
        for arg in typing.get_args(Command):
            if typing.get_origin(arg) is typing.Annotated:
                _, *metadata = typing.get_args(arg)
                for m in metadata:
                    if hasattr(m, "name"):
                        declared.add(m.name)

        entries = iter_command_entries()
        assert {e.name for e in entries} == declared
        # Every entry carries the group the CLI groups it under.
        assert all(e.group == COMMAND_GROUPS[e.name] for e in entries)
        # Entries arrive grouped: a group's commands are contiguous.
        seen_groups = [e.group for e in entries]
        assert len(set(seen_groups)) == len(
            [g for i, g in enumerate(seen_groups) if i == 0 or seen_groups[i - 1] != g]
        )

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_help_renders_the_shared_command_entries(self) -> None:
        """generate_help() presents exactly what iter_command_entries() returns.

        The help text and the documentation's command index read the same
        routine, so a command cannot appear in one and be missing from the
        other, and neither can describe a command differently.
        """
        help_text = generate_help("0.0.0")
        for entry in iter_command_entries():
            assert entry.summary in help_text, (
                f"{entry.name!r} is described as {entry.summary!r} by "
                f"iter_command_entries(), which the help text does not show"
            )
            assert entry.group in help_text

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_nested_subcommands_reach_the_summary(self) -> None:
        """A command with nested subcommands lists them in its summary, not its description."""
        entries = {e.name: e for e in iter_command_entries()}
        config = entries["config"]
        assert config.actions, "the `config` command declares nested subcommands"
        assert config.summary == f"{config.description} ({', '.join(config.actions)})"
        # A command without nested subcommands is summarised by its description alone.
        summary_only = entries["version"]
        assert summary_only.actions == ()
        assert summary_only.summary == summary_only.description

    # Verifies: REQ-p00001-A
    def test_REQ_p00001_A_generate_help_includes_all_commands(self) -> None:
        """generate_help() output contains every subcommand name."""
        help_text = generate_help("0.0.0")
        args = typing.get_args(Command)
        for arg in args:
            if typing.get_origin(arg) is typing.Annotated:
                _, *metadata = typing.get_args(arg)
                for m in metadata:
                    if hasattr(m, "name"):
                        assert m.name in help_text, (
                            f"Subcommand {m.name!r} not found in help output"
                        )
