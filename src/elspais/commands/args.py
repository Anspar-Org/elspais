# Implements: REQ-p00001-A
"""
Tyro-compatible dataclass definitions for all CLI subcommands.

Each dataclass maps 1:1 to an argparse subparser from cli.py.
Nested subcommands (config, rules, mcp, link, install, uninstall)
use Annotated[Union[...], tyro.conf.subcommand(...)] patterns.

Phase 3 of CONFIG-SCHEMA: these dataclasses will replace argparse
in cli.py via tyro.cli(GlobalArgs).
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Annotated, Literal

import tyro


# ---------------------------------------------------------------------------
# Health command
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class ChecksArgs:
    """Verify requirements traceability and configuration."""

    spec_only: Annotated[bool, tyro.conf.arg(name="spec")] = False
    """Run spec file checks only."""

    code_only: Annotated[bool, tyro.conf.arg(name="code")] = False
    """Run code reference checks only."""

    tests_only: Annotated[bool, tyro.conf.arg(name="tests")] = False
    """Run test mapping checks only."""

    format: Literal["text", "markdown", "json", "junit", "sarif"] = "text"
    """Output format."""

    lenient: bool = False
    """Allow warnings without affecting exit code."""

    status: list[str] | None = None
    """Additional statuses to include in coverage (e.g. Draft Proposed)."""

    include_passing_details: bool = False
    """Show full details for passing checks."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


# ---------------------------------------------------------------------------
# Gap listing commands
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class GapsArgs:
    """List all traceability gaps."""

    format: Literal["text", "markdown", "json"] = "text"
    """Output format."""

    status: list[str] | None = None
    """Statuses to include (default: Active)."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


@dataclasses.dataclass
class UncoveredArgs:
    """List requirements without code coverage."""

    format: Literal["text", "markdown", "json"] = "text"
    """Output format."""

    status: list[str] | None = None
    """Statuses to include (default: Active)."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


@dataclasses.dataclass
class UntestedArgs:
    """List requirements without test coverage."""

    format: Literal["text", "markdown", "json"] = "text"
    """Output format."""

    status: list[str] | None = None
    """Statuses to include (default: Active)."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


@dataclasses.dataclass
class UnvalidatedArgs:
    """List requirements without UAT (journey) coverage."""

    format: Literal["text", "markdown", "json"] = "text"
    """Output format."""

    status: list[str] | None = None
    """Statuses to include (default: Active)."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


@dataclasses.dataclass
class FailingArgs:
    """List requirements with failing test or UAT results."""

    format: Literal["text", "markdown", "json"] = "text"
    """Output format."""

    status: list[str] | None = None
    """Statuses to include (default: Active)."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


@dataclasses.dataclass
class BrokenArgs:
    """List broken references (edges targeting non-existent nodes)."""

    format: Literal["text", "markdown", "json"] = "text"
    """Output format."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


@dataclasses.dataclass
class ErrorsArgs:
    """List spec format violations and requirements with no assertions."""

    format: Literal["text", "markdown", "json"] = "text"
    """Output format."""

    status: list[str] | None = None
    """Statuses to include (default: Active)."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


@dataclasses.dataclass
class UnlinkedArgs:
    """List test and code nodes not linked to any requirement."""

    format: Literal["text", "markdown", "json"] = "text"
    """Output format."""

    verbose: Annotated[bool, tyro.conf.arg(aliases=["-v"])] = False
    """Show individual node IDs instead of just file counts."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


# ---------------------------------------------------------------------------
# Doctor command
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class DoctorArgs:
    """Diagnose environment and installation health."""

    format: Literal["text", "json"] = "text"
    """Output format."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


# ---------------------------------------------------------------------------
# Trace command
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class TraceArgs:
    """Generate traceability matrix."""

    format: Literal["text", "markdown", "html", "json", "csv"] = "markdown"
    """Output format."""

    preset: Literal["minimal", "standard", "full"] | None = None
    """Column preset."""

    body: bool = False
    """Show requirement body text in detail rows."""

    show_assertions: Annotated[bool, tyro.conf.arg(name="assertions")] = False
    """Show individual assertions in detail rows."""

    show_tests: Annotated[bool, tyro.conf.arg(name="tests")] = False
    """Show test references in detail rows."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


# ---------------------------------------------------------------------------
# Viewer command
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class ViewerArgs:
    """Interactive traceability viewer (live server or static HTML)."""

    server: bool = False
    """Start server without opening browser."""

    static: bool = False
    """Generate interactive HTML file instead of starting server."""

    embed_content: bool = False
    """Embed full requirement content in HTML for offline viewing."""

    port: int | None = None
    """Port number for the server (default: 5001)."""

    path: Path | None = None
    """Path to repository root (default: auto-detect from cwd)."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


# ---------------------------------------------------------------------------
# Graph command
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class GraphArgs:
    """Export the traceability graph structure as JSON."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


# ---------------------------------------------------------------------------
# Fix command
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class FixArgs:
    """Auto-fix spec file issues (hashes, formatting)."""

    req_id: tyro.conf.Positional[str | None] = None
    """Specific requirement ID to fix (hash only)."""

    dry_run: bool = False
    """Show what would be fixed without making changes."""

    message: Annotated[str | None, tyro.conf.arg(aliases=["-m"])] = None
    """Changelog reason for Active requirement hash updates."""

    mode: Literal["core", "combined", "associate"] = "combined"
    """Which repos to include in fix operation."""


# ---------------------------------------------------------------------------
# Glossary and Term Index commands
# Implements: REQ-d00225-A
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class GlossaryArgs:
    """Generate glossary from defined terms."""

    format: Literal["markdown", "json"] = "markdown"
    """Output format."""

    output_dir: str | None = None
    """Output directory (overrides [terms] output_dir config)."""


@dataclasses.dataclass
class CommentsCompactArgs:
    """Compact comment JSONL files (strip resolved, collapse promotes)."""


@dataclasses.dataclass
class CommentsArgs:
    """Comment management commands."""

    action: Annotated[CommentsCompactArgs, tyro.conf.subcommand("compact")]
    """Comment subcommand to execute."""


@dataclasses.dataclass
class TermIndexArgs:
    """Generate term index and collection manifests from defined terms."""

    format: Literal["markdown", "json"] = "markdown"
    """Output format."""

    output_dir: str | None = None
    """Output directory (overrides [terms] output_dir config)."""


# ---------------------------------------------------------------------------
# Summary command
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class SummaryArgs:
    """Coverage summary by level (implemented, validated, passing)."""

    format: Literal["text", "markdown", "json", "csv"] = "text"
    """Output format."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


# ---------------------------------------------------------------------------
# Changed command
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class ChangedArgs:
    """Detect git changes to spec files."""

    base_branch: str = "main"
    """Base branch for comparison."""

    format: Literal["text", "json"] = "text"
    """Output format."""

    all: Annotated[bool, tyro.conf.arg(aliases=["-a"])] = False
    """Include all changed files (not just spec)."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


# ---------------------------------------------------------------------------
# Analysis command
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class AnalysisArgs:
    """Analyze foundational requirement importance."""

    top: Annotated[int, tyro.conf.arg(aliases=["-n"])] = 10
    """Number of top results to show."""

    weights: str | None = None
    """Centrality,fan-in,neighborhood,uncovered weights (default: 0.3,0.2,0.2,0.3)."""

    format: Literal["table", "json"] = "table"
    """Output format."""

    show: Literal["foundations", "leaves", "all"] = "all"
    """Which sections to show."""

    level: Literal["prd", "ops", "dev"] | None = None
    """Filter results by requirement level."""

    include_code: bool = False
    """Include CODE nodes in the analysis."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


# ---------------------------------------------------------------------------
# Search command
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class SearchArgs:
    """Search requirements by keyword."""

    query: tyro.conf.Positional[str] = ""
    """Search terms (supports AND, OR, "phrases", -exclude, =exact)."""

    field: Literal["all", "id", "title", "body", "keywords"] = "all"
    """Which fields to search."""

    regex: bool = False
    """Treat query as a regular expression."""

    limit: Annotated[int, tyro.conf.arg(aliases=["-n"])] = 50
    """Maximum number of results."""

    format: Literal["text", "json"] = "text"
    """Output format."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""

    no_daemon: bool = False
    """Skip daemon, rebuild graph locally."""


# ---------------------------------------------------------------------------
# Version command
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class VersionArgs:
    """Show version and check for updates."""

    check: tyro.conf.Positional[str | None] = None
    """Check for updates from PyPI."""


# ---------------------------------------------------------------------------
# Init command
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class InitArgs:
    """Create .elspais.toml configuration."""

    type: Literal["core", "associated"] | None = None
    """Repository type."""

    associated_prefix: str | None = None
    """Associated repo prefix (e.g., CAL)."""

    force: bool = False
    """Overwrite existing configuration."""

    template: bool = False
    """Create an example requirement file in spec/."""


# ---------------------------------------------------------------------------
# Example command
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class ExampleArgs:
    """Display requirement format examples and templates."""

    example_type: tyro.conf.Positional[
        Literal["requirement", "journey", "assertion", "ids"] | None
    ] = None
    """Example type to display."""

    full: bool = False
    """Display the full requirements specification file."""


# ---------------------------------------------------------------------------
# Edit command
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class EditArgs:
    """Edit requirements in-place (implements, status, move)."""

    req_id: tyro.conf.Positional[str | None] = None
    """Requirement ID to edit."""

    implements: str | None = None
    """New Implements value (comma-separated, empty string to clear)."""

    status: str | None = None
    """New Status value."""

    move_to: str | None = None
    """Move requirement to file (relative to spec dir)."""

    from_json: str | None = None
    """Batch edit from JSON file (- for stdin)."""

    dry_run: bool = False
    """Show changes without applying."""

    validate_refs: bool = False
    """Validate that implements references exist."""


# ---------------------------------------------------------------------------
# Config subcommands
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class ConfigShowArgs:
    """Show current configuration."""

    section: str | None = None
    """Show only a specific section (e.g., 'patterns', 'rules.format')."""

    format: Literal["text", "json"] = "text"
    """Output format."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


@dataclasses.dataclass
class ConfigGetArgs:
    """Get a configuration value."""

    key: tyro.conf.Positional[str] = ""
    """Configuration key (dot-notation, e.g., 'patterns.prefix')."""

    format: Literal["text", "json"] = "text"
    """Output format."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


@dataclasses.dataclass
class ConfigSetArgs:
    """Set a configuration value."""

    key: tyro.conf.Positional[str] = ""
    """Configuration key (dot-notation)."""

    value: tyro.conf.Positional[str] = ""
    """Value to set (auto-detected: bool, number, JSON array/object, string)."""


@dataclasses.dataclass
class ConfigUnsetArgs:
    """Remove a configuration key."""

    key: tyro.conf.Positional[str] = ""
    """Configuration key to remove."""


@dataclasses.dataclass
class ConfigAddArgs:
    """Add a value to an array configuration."""

    key: tyro.conf.Positional[str] = ""
    """Configuration key for array (e.g., 'directories.code')."""

    value: tyro.conf.Positional[str] = ""
    """Value to add to the array."""


@dataclasses.dataclass
class ConfigRemoveArgs:
    """Remove a value from an array configuration."""

    key: tyro.conf.Positional[str] = ""
    """Configuration key for array."""

    value: tyro.conf.Positional[str] = ""
    """Value to remove from the array."""


@dataclasses.dataclass
class ConfigPathArgs:
    """Show path to configuration file."""


@dataclasses.dataclass
class ConfigSchemaArgs:
    """Output JSON Schema for .elspais.toml configuration."""

    output: Annotated[str | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write schema to file instead of stdout."""


ConfigAction = (
    Annotated[ConfigShowArgs, tyro.conf.subcommand("show")]
    | Annotated[ConfigGetArgs, tyro.conf.subcommand("get")]
    | Annotated[ConfigSetArgs, tyro.conf.subcommand("set")]
    | Annotated[ConfigUnsetArgs, tyro.conf.subcommand("unset")]
    | Annotated[ConfigAddArgs, tyro.conf.subcommand("add")]
    | Annotated[ConfigRemoveArgs, tyro.conf.subcommand("remove")]
    | Annotated[ConfigPathArgs, tyro.conf.subcommand("path")]
    | Annotated[ConfigSchemaArgs, tyro.conf.subcommand("schema")]
)


@dataclasses.dataclass
class ConfigArgs:
    """View and modify configuration."""

    action: tyro.conf.OmitSubcommandPrefixes[tyro.conf.OmitArgPrefixes[ConfigAction]] = (
        dataclasses.field(default_factory=lambda: ConfigShowArgs())
    )
    """Config subcommand (show, get, set, unset, add, remove, path)."""


# ---------------------------------------------------------------------------
# Rules subcommands
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class RulesListArgs:
    """List configured content rules."""


@dataclasses.dataclass
class RulesShowArgs:
    """Show content of a content rule file."""

    file: tyro.conf.Positional[str] = ""
    """Content rule file name (e.g., 'AI-AGENT.md')."""


RulesAction = (
    Annotated[RulesListArgs, tyro.conf.subcommand("list")]
    | Annotated[RulesShowArgs, tyro.conf.subcommand("show")]
)


@dataclasses.dataclass
class RulesArgs:
    """View and manage content rules."""

    action: tyro.conf.OmitSubcommandPrefixes[tyro.conf.OmitArgPrefixes[RulesAction]] = (
        dataclasses.field(default_factory=lambda: RulesListArgs())
    )
    """Rules subcommand (list, show)."""


# ---------------------------------------------------------------------------
# Docs command
# ---------------------------------------------------------------------------
DOCS_TOPICS = Literal[
    "quickstart",
    "format",
    "hierarchy",
    "assertions",
    "traceability",
    "linking",
    "validation",
    "git",
    "config",
    "commands",
    "checks",
    "doctor",
    "analysis",
    "terms",
    "associate",
    "ignore",
    "graph-model",
    "mcp",
    "topics",
    "all",
]


@dataclasses.dataclass
class DocsArgs:
    """Read the user guide."""

    topic: tyro.conf.Positional[DOCS_TOPICS] = "topics"
    """Documentation topic."""

    plain: bool = False
    """Plain text output (no ANSI colors)."""

    no_pager: bool = False
    """Disable paging (print directly to stdout)."""


# ---------------------------------------------------------------------------
# Associate command
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class AssociateArgs:
    """Manage associate repository links (link, list, unlink)."""

    associate_path: tyro.conf.Positional[str | None] = None
    """Path to associate repo or name to search for."""

    all: bool = False
    """Auto-discover and link all associates in sibling directories."""

    list: bool = False
    """Show current associate links and status."""

    unlink: str | None = None
    """Remove a linked associate (matches name, path, or prefix code)."""


# ---------------------------------------------------------------------------
# PDF command
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class PdfArgs:
    """Compile spec files into a PDF document."""

    output: Path = Path("spec-output.pdf")
    """Output PDF file path."""

    engine: str = "xelatex"
    """PDF engine: xelatex (default), lualatex, pdflatex."""

    template: Path | None = None
    """Custom pandoc LaTeX template."""

    title: str | None = None
    """Document title (default: project name from config)."""

    cover: Path | None = None
    """Markdown file for custom cover page."""

    overview: bool = False
    """Generate stakeholder overview (PRD requirements only)."""

    max_depth: int | None = None
    """Max graph depth for core PRDs in overview mode."""


# ---------------------------------------------------------------------------
# Install subcommands
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class InstallLocalArgs:
    """Install local source as editable (replaces PyPI version)."""

    path: str | None = None
    """Path to elspais source directory (auto-detected if omitted)."""

    extras: str | None = None
    """Comma-separated extras to install (e.g., 'all', 'mcp,trace-view')."""

    tool: Literal["pipx", "uv"] | None = None
    """Package tool to use (auto-detected if omitted)."""


InstallAction = Annotated[InstallLocalArgs, tyro.conf.subcommand("local")]


@dataclasses.dataclass
class InstallArgs:
    """Install elspais variants."""

    action: tyro.conf.OmitSubcommandPrefixes[tyro.conf.OmitArgPrefixes[InstallAction]] = (
        dataclasses.field(default_factory=InstallLocalArgs)
    )
    """Install subcommand."""


# ---------------------------------------------------------------------------
# Uninstall subcommands
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class UninstallLocalArgs:
    """Revert to PyPI release version."""

    extras: str | None = None
    """Comma-separated extras to install."""

    version: str | None = None
    """Specific PyPI version to install (default: latest)."""

    tool: Literal["pipx", "uv"] | None = None
    """Package tool to use (auto-detected if omitted)."""


UninstallAction = Annotated[UninstallLocalArgs, tyro.conf.subcommand("local")]


@dataclasses.dataclass
class UninstallArgs:
    """Revert elspais installation."""

    action: tyro.conf.OmitSubcommandPrefixes[tyro.conf.OmitArgPrefixes[UninstallAction]] = (
        dataclasses.field(default_factory=UninstallLocalArgs)
    )
    """Uninstall subcommand."""


# ---------------------------------------------------------------------------
# MCP subcommands
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class McpServeArgs:
    """Start MCP server."""

    transport: Literal["stdio", "sse", "streamable-http"] = "stdio"
    """Transport type."""

    port: int = 8000
    """Port for HTTP transports (0 = auto-assign)."""

    ttl: int = 0
    """Auto-exit after N minutes of inactivity (0 = run forever)."""


@dataclasses.dataclass
class McpInstallArgs:
    """Register elspais MCP server with Claude Code."""

    global_scope: bool = False
    """Install for all projects (user scope)."""

    desktop: bool = False
    """Also install into Claude Desktop."""


@dataclasses.dataclass
class McpUninstallArgs:
    """Remove elspais MCP server from Claude Code."""

    global_scope: bool = False
    """Remove from user scope."""

    desktop: bool = False
    """Also remove from Claude Desktop."""


McpAction = (
    Annotated[McpServeArgs, tyro.conf.subcommand("serve")]
    | Annotated[McpInstallArgs, tyro.conf.subcommand("install")]
    | Annotated[McpUninstallArgs, tyro.conf.subcommand("uninstall")]
)


@dataclasses.dataclass
class McpArgs:
    """MCP server commands."""

    action: tyro.conf.OmitSubcommandPrefixes[tyro.conf.OmitArgPrefixes[McpAction]] = (
        dataclasses.field(default_factory=McpServeArgs)
    )
    """MCP subcommand (serve, install, uninstall)."""


# ---------------------------------------------------------------------------
# Daemon subcommands
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class DaemonRestartArgs:
    """Restart the background daemon to pick up config file changes."""

    force: bool = False
    """Restart even if the daemon has unsaved in-memory mutations (discards them)."""

    persist: bool = False
    """Persist any unsaved in-memory mutations to disk before restarting."""


DaemonAction = Annotated[DaemonRestartArgs, tyro.conf.subcommand("restart")]


@dataclasses.dataclass
class DaemonArgs:
    """Manage the background daemon (MCP + CLI share one daemon per repo)."""

    action: tyro.conf.OmitSubcommandPrefixes[tyro.conf.OmitArgPrefixes[DaemonAction]] = (
        dataclasses.field(default_factory=DaemonRestartArgs)
    )
    """Daemon subcommand (restart)."""


# ---------------------------------------------------------------------------
# Link subcommands
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class LinkSuggestArgs:
    """Suggest requirement links for unlinked tests."""

    file: Path | None = None
    """Restrict analysis to a single file."""

    format: Literal["text", "json"] = "text"
    """Output format."""

    min_confidence: Literal["high", "medium", "low"] | None = None
    """Minimum confidence band to show."""

    limit: int = 50
    """Maximum suggestions to return."""

    apply: bool = False
    """Apply suggestions by inserting # Implements: comments."""

    dry_run: bool = False
    """Preview changes without modifying files (use with --apply)."""


LinkAction = Annotated[LinkSuggestArgs, tyro.conf.subcommand("suggest")]


@dataclasses.dataclass
class LinkArgs:
    """Link suggestion tools."""

    action: tyro.conf.OmitSubcommandPrefixes[tyro.conf.OmitArgPrefixes[LinkAction]] = (
        dataclasses.field(default_factory=LinkSuggestArgs)
    )
    """Link subcommand."""


# ---------------------------------------------------------------------------
# Completion subcommands
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class CompletionInstallArgs:
    """Generate and install a tab-completion script for your shell."""

    shell: Literal["bash", "zsh", "tcsh"] | None = None
    """Target shell (auto-detected from $SHELL if omitted)."""


@dataclasses.dataclass
class CompletionUninstallArgs:
    """Remove a previously installed tab-completion script."""

    shell: Literal["bash", "zsh", "tcsh"] | None = None
    """Target shell (auto-detected from $SHELL if omitted)."""


CompletionAction = (
    Annotated[CompletionInstallArgs, tyro.conf.subcommand("install")]
    | Annotated[CompletionUninstallArgs, tyro.conf.subcommand("uninstall")]
)


@dataclasses.dataclass
class CompletionArgs:
    """Generate and install shell tab-completion scripts (bash, zsh, tcsh)."""

    action: tyro.conf.OmitSubcommandPrefixes[tyro.conf.OmitArgPrefixes[CompletionAction]] = (
        dataclasses.field(default_factory=CompletionInstallArgs)
    )
    """Completion subcommand (install, uninstall)."""


# ---------------------------------------------------------------------------
# Top-level command union — each entry becomes a subcommand
# ---------------------------------------------------------------------------
Command = (
    Annotated[ChecksArgs, tyro.conf.subcommand("checks")]
    | Annotated[GapsArgs, tyro.conf.subcommand("gaps")]
    | Annotated[UncoveredArgs, tyro.conf.subcommand("uncovered")]
    | Annotated[UntestedArgs, tyro.conf.subcommand("untested")]
    | Annotated[UnvalidatedArgs, tyro.conf.subcommand("unvalidated")]
    | Annotated[FailingArgs, tyro.conf.subcommand("failing")]
    | Annotated[ErrorsArgs, tyro.conf.subcommand("errors")]
    | Annotated[BrokenArgs, tyro.conf.subcommand("broken")]
    | Annotated[UnlinkedArgs, tyro.conf.subcommand("unlinked")]
    | Annotated[DoctorArgs, tyro.conf.subcommand("doctor")]
    | Annotated[TraceArgs, tyro.conf.subcommand("trace")]
    | Annotated[ViewerArgs, tyro.conf.subcommand("viewer")]
    | Annotated[GraphArgs, tyro.conf.subcommand("graph")]
    | Annotated[FixArgs, tyro.conf.subcommand("fix")]
    | Annotated[SummaryArgs, tyro.conf.subcommand("summary")]
    | Annotated[ChangedArgs, tyro.conf.subcommand("changed")]
    | Annotated[AnalysisArgs, tyro.conf.subcommand("analysis")]
    | Annotated[SearchArgs, tyro.conf.subcommand("search")]
    | Annotated[VersionArgs, tyro.conf.subcommand("version")]
    | Annotated[InitArgs, tyro.conf.subcommand("init")]
    | Annotated[ExampleArgs, tyro.conf.subcommand("example")]
    | Annotated[EditArgs, tyro.conf.subcommand("edit")]
    | Annotated[ConfigArgs, tyro.conf.subcommand("config")]
    | Annotated[RulesArgs, tyro.conf.subcommand("rules")]
    | Annotated[DocsArgs, tyro.conf.subcommand("docs")]
    | Annotated[AssociateArgs, tyro.conf.subcommand("associate")]
    | Annotated[PdfArgs, tyro.conf.subcommand("pdf")]
    | Annotated[InstallArgs, tyro.conf.subcommand("install")]
    | Annotated[UninstallArgs, tyro.conf.subcommand("uninstall")]
    | Annotated[McpArgs, tyro.conf.subcommand("mcp")]
    | Annotated[DaemonArgs, tyro.conf.subcommand("daemon")]
    | Annotated[LinkArgs, tyro.conf.subcommand("link")]
    | Annotated[CompletionArgs, tyro.conf.subcommand("completion")]
    | Annotated[GlossaryArgs, tyro.conf.subcommand("glossary")]
    | Annotated[TermIndexArgs, tyro.conf.subcommand("term-index")]
    | Annotated[CommentsArgs, tyro.conf.subcommand("comments")]
)


@dataclasses.dataclass
class GlobalArgs:
    """Requirements validation and traceability tools (L-Space)."""

    command: tyro.conf.OmitSubcommandPrefixes[tyro.conf.OmitArgPrefixes[Command]]
    """Subcommand to execute."""

    directory: Annotated[Path | None, tyro.conf.arg(aliases=["-C"])] = None
    """Run as if started in this directory (like git -C)."""

    config: Path | None = None
    """Path to configuration file."""

    spec_dir: Path | None = None
    """Override spec directory."""

    verbose: Annotated[bool, tyro.conf.arg(aliases=["-v"])] = False
    """Verbose output."""

    quiet: Annotated[bool, tyro.conf.arg(aliases=["-q"])] = False
    """Suppress non-error output."""


# ---------------------------------------------------------------------------
# Grouped help generation
# ---------------------------------------------------------------------------
# Maps each subcommand name to its display group.  Group display order is
# determined by first occurrence (Python 3.7+ insertion order).
COMMAND_GROUPS: dict[str, str] = {
    "checks": "Reports",
    "summary": "Reports",
    "trace": "Reports",
    "changed": "Reports",
    "pdf": "Reports",
    "gaps": "Gaps & Issues",
    "uncovered": "Gaps & Issues",
    "untested": "Gaps & Issues",
    "unvalidated": "Gaps & Issues",
    "failing": "Gaps & Issues",
    "errors": "Gaps & Issues",
    "broken": "Gaps & Issues",
    "unlinked": "Gaps & Issues",
    "search": "Reports",
    "analysis": "Authoring",
    "fix": "Authoring",
    "edit": "Authoring",
    "example": "Authoring",
    "link": "Authoring",
    "glossary": "Authoring",
    "term-index": "Authoring",
    "comments": "Authoring",
    "viewer": "Viewing",
    "graph": "Viewing",
    "init": "Configuration",
    "config": "Configuration",
    "rules": "Configuration",
    "associate": "Configuration",
    "doctor": "Install",
    "mcp": "Install",
    "daemon": "Install",
    "install": "Install",
    "uninstall": "Install",
    "completion": "Install",
    "docs": "Info",
    "version": "Info",
}

# Ordered list of groups for display (derived from COMMAND_GROUPS).
_GROUP_ORDER: list[str] = list(dict.fromkeys(COMMAND_GROUPS.values()))


def generate_help(version: str) -> str:
    """Generate grouped CLI help text from Command Union metadata.

    Reads subcommand names and descriptions directly from the dataclass
    definitions so the help output cannot drift from reality.
    """
    import typing

    # --- Extract subcommand info from the Command Union ---
    commands: list[tuple[str, str]] = []  # (name, description)
    for arg in typing.get_args(Command):
        if typing.get_origin(arg) is not typing.Annotated:
            continue
        base_type, *metadata = typing.get_args(arg)
        # Find the subcommand name from tyro metadata
        name = None
        for m in metadata:
            if hasattr(m, "name"):
                name = m.name
        if name is None:
            continue

        # Description from docstring (first line only)
        doc = (base_type.__doc__ or "").strip().split("\n")[0]
        # Strip trailing period for cleaner display
        if doc.endswith("."):
            doc = doc[:-1]

        # Auto-detect nested subcommand hints from 'action' field
        if dataclasses.is_dataclass(base_type):
            hints = typing.get_type_hints(base_type, include_extras=True)
            if "action" in hints:
                action_t = hints["action"]
                # Unwrap tyro wrapper types to reach the inner Union
                while (
                    typing.get_origin(action_t) is not None
                    and typing.get_origin(action_t) is not typing.Union
                ):
                    inner = typing.get_args(action_t)
                    if inner:
                        action_t = inner[0]
                    else:
                        break
                # Extract subcommand names from the Union
                sub_names = []
                for aa in typing.get_args(action_t):
                    if typing.get_origin(aa) is typing.Annotated:
                        _, *ameta = typing.get_args(aa)
                        for am in ameta:
                            if hasattr(am, "name"):
                                sub_names.append(am.name)
                if sub_names:
                    doc += f" ({', '.join(sub_names)})"

        assert name in COMMAND_GROUPS, (
            f"Subcommand {name!r} missing from COMMAND_GROUPS — "
            f"add it to elspais/commands/args.py"
        )
        commands.append((name, doc))

    # --- Build grouped output ---
    # Bucket commands by group, ordered by COMMAND_GROUPS dict order
    cmd_lookup: dict[str, str] = dict(commands)
    groups: dict[str, list[str]] = {g: [] for g in _GROUP_ORDER}
    for name in COMMAND_GROUPS:
        if name in cmd_lookup:
            groups[COMMAND_GROUPS[name]].append(name)

    # Compute column width for subcommands
    max_name = max((len(n) for n, _ in commands), default=0)
    cmd_col = max_name + 2

    # Fixed column width for global options (widest entry is --directory, -C DIR)
    opt_col = 21

    lines: list[str] = []
    lines.append(
        f"elspais {version} \u2014 Requirements validation and traceability tools (L-Space)"
    )
    lines.append("")
    lines.append("Usage: elspais [options] <command> [command-options]")

    for group_title in _GROUP_ORDER:
        entries = groups[group_title]
        if not entries:
            continue
        lines.append("")
        lines.append(f"{group_title}:")
        for name in entries:
            lines.append(f"  {name:<{cmd_col}}{cmd_lookup[name]}")

    lines.append("")
    lines.append("Global options:")
    lines.append(f"  {'--verbose, -v':<{opt_col}}Verbose output")
    lines.append(f"  {'--quiet, -q':<{opt_col}}Suppress non-error output")
    lines.append(f"  {'--directory, -C DIR':<{opt_col}}Run as if started in this directory")
    lines.append(f"  {'--config PATH':<{opt_col}}Path to configuration file")
    lines.append(f"  {'--spec-dir PATH':<{opt_col}}Override spec directory")
    lines.append(f"  {'--version':<{opt_col}}Show version and exit")

    lines.append("")
    lines.append("Compose multiple sections:")
    lines.append("  elspais checks summary trace  # Run checks, summary, and trace together")

    lines.append("")
    lines.append("For command help: elspais <command> --help")

    return "\n".join(lines)
