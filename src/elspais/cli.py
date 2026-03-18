# Implements: REQ-p00001-A
"""
elspais.cli - Command-line interface.

Main entry point for the elspais CLI tool.
Uses Tyro for declarative CLI generation from dataclass definitions.
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

from elspais import __version__
from elspais.commands import (
    analysis_cmd,
    associate_cmd,
    changed,
    config_cmd,
    doctor,
    edit,
    example_cmd,
    fix_cmd,
    health,
    init,
    install_cmd,
    link_suggest,
    pdf_cmd,
    rules_cmd,
    summary,
    trace,
    viewer,
)
from elspais.commands.args import (
    AnalysisArgs,
    AssociateArgs,
    ChangedArgs,
    ConfigAddArgs,
    ConfigArgs,
    ConfigGetArgs,
    ConfigPathArgs,
    ConfigRemoveArgs,
    ConfigSetArgs,
    ConfigShowArgs,
    ConfigUnsetArgs,
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
    LinkArgs,
    LinkSuggestArgs,
    McpArgs,
    McpInstallArgs,
    McpServeArgs,
    McpUninstallArgs,
    PdfArgs,
    RulesArgs,
    RulesListArgs,
    RulesShowArgs,
    SummaryArgs,
    TraceArgs,
    UninstallArgs,
    VersionArgs,
    ViewerArgs,
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments via Tyro and return an argparse.Namespace.

    This is the Tyro-based replacement for create_parser().parse_args().
    Used by tests and internal code that needs parsed args without running main().
    """
    import tyro

    global_args = tyro.cli(GlobalArgs, args=argv)
    return _to_namespace(global_args)


def _to_namespace(global_args: GlobalArgs) -> argparse.Namespace:
    """Convert Tyro GlobalArgs to argparse.Namespace for backward compat.

    Merges global fields and command-specific fields into a flat namespace
    so existing command run() functions work without signature changes.
    """
    ns = argparse.Namespace()

    # Copy global fields (except 'command')
    for field in dataclasses.fields(global_args):
        if field.name != "command":
            setattr(ns, field.name, getattr(global_args, field.name))

    cmd = global_args.command

    # Determine the command name and nested action for dispatch
    _CMD_MAP: dict[type, str] = {
        HealthArgs: "health",
        DoctorArgs: "doctor",
        TraceArgs: "trace",
        ViewerArgs: "viewer",
        GraphArgs: "graph",
        FixArgs: "fix",
        SummaryArgs: "summary",
        ChangedArgs: "changed",
        AnalysisArgs: "analysis",
        VersionArgs: "version",
        InitArgs: "init",
        ExampleArgs: "example",
        EditArgs: "edit",
        ConfigArgs: "config",
        RulesArgs: "rules",
        DocsArgs: "docs",
        AssociateArgs: "associate",
        PdfArgs: "pdf",
        InstallArgs: "install",
        UninstallArgs: "uninstall",
        McpArgs: "mcp",
        LinkArgs: "link",
    }
    ns.command = _CMD_MAP.get(type(cmd), "")

    # Copy command-specific fields
    if hasattr(cmd, "__dataclass_fields__"):
        for field in dataclasses.fields(cmd):
            if field.name == "action":
                continue
            setattr(ns, field.name, getattr(cmd, field.name))

    # Handle nested subcommands — map action to the appropriate dest attr
    if isinstance(cmd, ConfigArgs):
        _ACTION_MAP = {
            ConfigShowArgs: "show",
            ConfigGetArgs: "get",
            ConfigSetArgs: "set",
            ConfigUnsetArgs: "unset",
            ConfigAddArgs: "add",
            ConfigRemoveArgs: "remove",
            ConfigPathArgs: "path",
        }
        ns.config_action = _ACTION_MAP.get(type(cmd.action), None)
        if hasattr(cmd.action, "__dataclass_fields__"):
            for field in dataclasses.fields(cmd.action):
                setattr(ns, field.name, getattr(cmd.action, field.name))
    elif isinstance(cmd, RulesArgs):
        _RULES_MAP = {RulesListArgs: "list", RulesShowArgs: "show"}
        ns.rules_action = _RULES_MAP.get(type(cmd.action), None)
        if hasattr(cmd.action, "__dataclass_fields__"):
            for field in dataclasses.fields(cmd.action):
                setattr(ns, field.name, getattr(cmd.action, field.name))
    elif isinstance(cmd, McpArgs):
        _MCP_MAP = {
            McpServeArgs: "serve",
            McpInstallArgs: "install",
            McpUninstallArgs: "uninstall",
        }
        ns.mcp_action = _MCP_MAP.get(type(cmd.action), None)
        if hasattr(cmd.action, "__dataclass_fields__"):
            for field in dataclasses.fields(cmd.action):
                setattr(ns, field.name, getattr(cmd.action, field.name))
    elif isinstance(cmd, LinkArgs):
        ns.link_action = "suggest" if isinstance(cmd.action, LinkSuggestArgs) else None
        if hasattr(cmd.action, "__dataclass_fields__"):
            for field in dataclasses.fields(cmd.action):
                setattr(ns, field.name, getattr(cmd.action, field.name))
    elif isinstance(cmd, InstallArgs):
        ns.install_action = "local"
        if hasattr(cmd.action, "__dataclass_fields__"):
            for field in dataclasses.fields(cmd.action):
                setattr(ns, field.name, getattr(cmd.action, field.name))
    elif isinstance(cmd, UninstallArgs):
        ns.uninstall_action = "local"
        if hasattr(cmd.action, "__dataclass_fields__"):
            for field in dataclasses.fields(cmd.action):
                setattr(ns, field.name, getattr(cmd.action, field.name))

    return ns


def main(argv: list[str] | None = None) -> int:
    """
    Main entry point for the CLI.

    Args:
        argv: Command line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    if argv is None:
        argv = sys.argv[1:]

    import os

    # Check ELSPAIS_VERSION env var for minimum version requirement
    from elspais.utilities.version_check import check_env_version_requirement

    version_check_result = check_env_version_requirement()
    if version_check_result is not None:
        return version_check_result

    # Handle --version before Tyro parsing
    if "--version" in argv:
        print(f"elspais {__version__}")
        return 0

    # Handle no args or "help" — show help text
    if not argv or argv == ["help"]:
        _print_help()
        return 0

    # Implements: REQ-d00085-A+D
    # Detect multi-section composition before Tyro parsing
    from elspais.commands.report import COMPOSABLE_SECTIONS

    # Extract -C/--directory before multi-section detection since global
    # args precede subcommands in argv
    start_dir = Path.cwd()
    filtered_argv: list[str] = []
    skip_next = False
    for j, arg in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if arg in ("-C", "--directory") and j + 1 < len(argv):
            start_dir = Path(argv[j + 1]).resolve()
            os.chdir(start_dir)
            skip_next = True
            continue
        if arg.startswith("-C") and len(arg) > 2:
            start_dir = Path(arg[2:]).resolve()
            os.chdir(start_dir)
            continue
        filtered_argv.append(arg)
    argv = filtered_argv

    sections: list[str] = []
    i = 0
    while i < len(argv) and argv[i] in COMPOSABLE_SECTIONS:
        sections.append(argv[i])
        i += 1

    if len(sections) > 1:
        from elspais.config import find_canonical_root, find_git_root

        git_root = find_git_root(start_dir)
        canonical_root = find_canonical_root(start_dir)
        if git_root and git_root != Path.cwd():
            os.chdir(git_root)

        from elspais.commands import report

        return report.run(sections, argv[i:], canonical_root=canonical_root)

    # Single command — Tyro parsing
    import tyro

    try:
        global_args = tyro.cli(GlobalArgs, args=argv)
    except SystemExit as e:
        # Tyro calls sys.exit on parse errors and --help
        return e.code if isinstance(e.code, int) else 2

    args = _to_namespace(global_args)

    # Auto-detect git repository root and change to it
    # This ensures elspais works the same from any subdirectory
    from elspais.config import find_canonical_root, find_git_root

    original_cwd = Path.cwd()  # Already changed by -C if provided

    # If --path is set on a command that supports it, use that as the root
    explicit_path = getattr(args, "path", None)
    if explicit_path:
        explicit_path = Path(explicit_path).resolve()
        git_root = explicit_path
        canonical_root = find_canonical_root(explicit_path)
    else:
        git_root = find_git_root(original_cwd)
        canonical_root = find_canonical_root(original_cwd)

    if git_root and git_root != original_cwd:
        os.chdir(git_root)
        if args.verbose:
            print(f"Working from repository root: {git_root}", file=sys.stderr)
            if canonical_root and canonical_root != git_root:
                print(f"Canonical root (main repo): {canonical_root}", file=sys.stderr)
    elif not git_root and args.verbose:
        print("Warning: Not in a git repository", file=sys.stderr)

    # Warn if --config points to a different directory than the working dir
    config_path = getattr(args, "config", None)
    if config_path and git_root:
        config_dir = Path(config_path).resolve().parent
        working_dir = git_root.resolve()
        if config_dir != working_dir:
            print(
                f"INFO: Config file is from {config_dir} but working directory is {working_dir}. "
                f"Use -C to change the working directory.",
                file=sys.stderr,
            )

    # Store roots on args for commands to use
    args.git_root = git_root
    args.canonical_root = canonical_root

    # Global --output: redirect stdout to file
    output_file = None
    output_path = getattr(args, "output", None)
    if output_path and args.command not in {"pdf"}:
        output_file = open(output_path, "w")  # noqa: SIM115
        sys.stdout = output_file

    try:
        # Dispatch to command handlers
        if args.command == "health":
            return health.run(args)
        elif args.command == "doctor":
            return doctor.run(args)
        elif args.command == "trace":
            return trace.run(args)
        elif args.command == "viewer":
            return viewer.run(args)
        elif args.command == "graph":
            return trace.run_graph(args)
        elif args.command == "fix":
            return fix_cmd.run(args)

        elif args.command == "summary":
            return summary.run(args)
        elif args.command == "changed":
            return changed.run(args)
        elif args.command == "analysis":
            return analysis_cmd.run(args)
        elif args.command == "version":
            return version_command(args)
        elif args.command == "init":
            return init.run(args)
        elif args.command == "example":
            return example_cmd.run(args)
        elif args.command == "edit":
            return edit.run(args)
        elif args.command == "config":
            return config_cmd.run(args)
        elif args.command == "rules":
            return rules_cmd.run(args)
        elif args.command == "docs":
            return docs_command(args)
        elif args.command == "mcp":
            return mcp_command(args)
        elif args.command == "associate":
            return associate_cmd.run(args)
        elif args.command == "link":
            if getattr(args, "link_action", None) == "suggest":
                return link_suggest.run(args)
            else:
                print("Usage: elspais link suggest [options]")
                return 1
        elif args.command == "pdf":
            return pdf_cmd.run(args)
        elif args.command == "install":
            return install_cmd.run(args)
        elif args.command == "uninstall":
            return install_cmd.run_uninstall(args)
        else:
            _print_help()
            return 1

    except KeyboardInterrupt:
        print("\nOperation cancelled.", file=sys.stderr)
        return 130
    except Exception as e:
        if args.verbose:
            raise
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        if output_file:
            sys.stdout = sys.__stdout__
            output_file.close()
            if not getattr(args, "quiet", False):
                print(f"Generated: {output_path}", file=sys.stderr)


def _print_help() -> None:
    """Print help text matching the original argparse output."""
    print(
        f"""elspais {__version__} — Requirements validation and traceability tools (L-Space)

Usage: elspais [options] <command> [command-options]

Commands:
  health      Check repository and configuration health
  doctor      Diagnose environment and installation health
  trace       Generate traceability matrix
  viewer      Interactive traceability viewer (live server or static HTML)
  graph       Export the traceability graph structure as JSON
  fix         Auto-fix spec file issues (hashes, formatting)
  summary     Coverage summary by level
  changed     Detect git changes to spec files
  analysis    Analyze foundational requirement importance
  version     Show version and check for updates
  init        Create .elspais.toml configuration
  example     Display requirement format examples and templates
  edit        Edit requirements in-place
  config      View and modify configuration (show, get, set, ...)
  rules       View and manage content rules (list, show)
  docs        Read the user guide
  associate   Manage associate repository links
  pdf         Compile spec files into a PDF document
  install     Install elspais variants
  uninstall   Revert elspais installation
  mcp         MCP server commands
  link        Link suggestion tools

Global options:
  --verbose, -v       Verbose output
  --quiet, -q         Suppress non-error output
  --directory, -C DIR Run as if started in this directory
  --config PATH       Path to configuration file
  --spec-dir PATH     Override spec directory
  --version           Show version and exit

Examples:
  elspais health                # Check project health
  elspais summary               # Show coverage summary
  elspais trace --format html   # Generate HTML traceability matrix
  elspais viewer                # Start interactive viewer
  elspais health summary trace  # Compose multiple report sections
  elspais config show           # View all settings

For command help: elspais <command> --help"""
    )


def docs_command(args: argparse.Namespace) -> int:
    """Handle docs command - display user documentation from markdown files."""
    import pydoc

    from elspais.utilities.docs_loader import load_all_topics, load_topic
    from elspais.utilities.md_renderer import render_markdown

    topic = args.topic
    use_pager = not args.no_pager and sys.stdout.isatty()
    use_color = not args.plain and sys.stdout.isatty()

    # Load content from markdown files
    if topic == "all":
        content = load_all_topics()
    else:
        content = load_topic(topic)

    if content is None:
        print(f"Error: Documentation not found for topic '{topic}'", file=sys.stderr)
        print("Documentation files may not be installed correctly.", file=sys.stderr)
        return 1

    # Render markdown to ANSI and display
    output = render_markdown(content, use_color=use_color)

    if use_pager:
        pydoc.pager(output)
    else:
        print(output)

    return 0


def version_command(args: argparse.Namespace) -> int:
    """Handle version command."""
    if args.check:
        from elspais.utilities.version_check import check_for_updates

        return check_for_updates(__version__)

    print(f"elspais {__version__}")
    return 0


def mcp_command(args: argparse.Namespace) -> int:
    """Handle MCP server commands."""
    if args.mcp_action == "install":
        desktop = getattr(args, "desktop", False)
        rc = _mcp_install(global_scope=args.global_scope)
        if desktop:
            rc_desktop = _mcp_install_desktop()
            if rc == 0:
                rc = rc_desktop
        return rc
    elif args.mcp_action == "uninstall":
        desktop = getattr(args, "desktop", False)
        rc = _mcp_uninstall(global_scope=args.global_scope)
        if desktop:
            rc_desktop = _mcp_uninstall_desktop()
            if rc == 0:
                rc = rc_desktop
        return rc

    try:
        from elspais.mcp.server import run_server
    except ImportError:
        print("Error: MCP dependencies not installed.", file=sys.stderr)
        print("Install with: pip install elspais[mcp]", file=sys.stderr)
        return 1

    if args.mcp_action == "serve":
        working_dir = Path.cwd()
        if hasattr(args, "spec_dir") and args.spec_dir:
            working_dir = args.spec_dir.parent

        print("Starting elspais MCP server...")
        print(f"Working directory: {working_dir}")
        print(f"Transport: {args.transport}")

        try:
            run_server(working_dir=working_dir, transport=args.transport)
        except KeyboardInterrupt:
            print("\nServer stopped.")
        return 0
    else:
        print("Usage: elspais mcp {serve|install|uninstall}")
        return 1


def _claude_env() -> dict[str, str]:
    """Return env dict with Claude nesting guards removed.

    ``claude mcp add`` refuses to run inside an active Claude Code session.
    Strip the sentinel variables so the subprocess succeeds even when
    ``elspais mcp install`` is invoked from a Claude Code terminal.
    """
    import os

    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    return env


def _mcp_install(global_scope: bool = False) -> int:
    """Register elspais MCP server with Claude Code."""
    import shutil
    import subprocess

    claude = shutil.which("claude")
    if not claude:
        print("Error: 'claude' not found on PATH.", file=sys.stderr)
        print(
            "Install Claude Code: https://docs.anthropic.com/claude-code",
            file=sys.stderr,
        )
        return 1

    elspais_bin = shutil.which("elspais")
    if not elspais_bin:
        print("Error: 'elspais' not found on PATH.", file=sys.stderr)
        return 1

    cmd = [claude, "mcp", "add", "elspais", "--transport", "stdio"]
    if global_scope:
        cmd.extend(["--scope", "user"])
    cmd.extend(["--", "elspais", "mcp", "serve"])

    result = subprocess.run(cmd, capture_output=True, text=True, env=_claude_env())
    if result.returncode != 0:
        print(f"Error: {result.stderr.strip()}", file=sys.stderr)
        return 1

    scope_label = "all projects (user scope)" if global_scope else "current project (local scope)"
    print(f"elspais MCP server registered for {scope_label}.")
    if not global_scope:
        print("Tip: Use --global to make elspais MCP available in all projects.")
    return 0


def _claude_desktop_config_path() -> Path | None:
    """Return the Claude Desktop config file path for the current platform.

    Returns:
        Path to claude_desktop_config.json, or None if platform unsupported.
    """
    import platform

    system = platform.system()
    home = Path.home()

    if system == "Darwin":
        return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif system == "Linux":
        return home / ".config" / "Claude" / "claude_desktop_config.json"
    elif system == "Windows":
        import os

        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return Path(appdata) / "Claude" / "claude_desktop_config.json"
    return None


def _mcp_install_desktop() -> int:
    """Register elspais MCP server in Claude Desktop config."""
    import json

    config_path = _claude_desktop_config_path()
    if config_path is None:
        print("Error: Unsupported platform for Claude Desktop.", file=sys.stderr)
        return 1

    entry = {
        "command": "elspais",
        "args": ["mcp", "serve"],
    }

    try:
        if config_path.exists():
            data = json.loads(config_path.read_text(encoding="utf-8"))
        else:
            data = {}

        servers = data.setdefault("mcpServers", {})
        servers["elspais"] = entry
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error writing Claude Desktop config: {e}", file=sys.stderr)
        return 1

    print(f"Claude Desktop: registered elspais in {config_path}")
    return 0


def _mcp_uninstall_desktop() -> int:
    """Remove elspais MCP server from Claude Desktop config."""
    import json

    config_path = _claude_desktop_config_path()
    if config_path is None:
        print("Error: Unsupported platform for Claude Desktop.", file=sys.stderr)
        return 1

    if not config_path.exists():
        print("Claude Desktop: config not found, nothing to remove.")
        return 0

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        servers = data.get("mcpServers", {})
        if "elspais" not in servers:
            print("Claude Desktop: elspais not registered, nothing to remove.")
            return 0

        del servers["elspais"]
        config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error updating Claude Desktop config: {e}", file=sys.stderr)
        return 1

    print("Claude Desktop: elspais removed.")
    return 0


def _mcp_uninstall(global_scope: bool = False) -> int:
    """Remove elspais MCP server from Claude Code."""
    import shutil
    import subprocess

    claude = shutil.which("claude")
    if not claude:
        print("Error: 'claude' not found on PATH.", file=sys.stderr)
        return 1

    cmd = [claude, "mcp", "remove", "elspais"]
    if global_scope:
        cmd.extend(["--scope", "user"])

    result = subprocess.run(cmd, capture_output=True, text=True, env=_claude_env())
    if result.returncode != 0:
        print(f"Error: {result.stderr.strip()}", file=sys.stderr)
        return 1

    print("elspais MCP server removed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
