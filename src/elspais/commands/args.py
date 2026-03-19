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
class HealthArgs:
    """Check repository and configuration health."""

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
    """Statuses to include in coverage (default: Active)."""

    include_passing_details: bool = False
    """Show full details for passing checks."""

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
    "health",
    "mcp",
    "all",
]


@dataclasses.dataclass
class DocsArgs:
    """Read the user guide."""

    topic: tyro.conf.Positional[DOCS_TOPICS] = "quickstart"
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
# Top-level command union — each entry becomes a subcommand
# ---------------------------------------------------------------------------
Command = (
    Annotated[HealthArgs, tyro.conf.subcommand("health")]
    | Annotated[DoctorArgs, tyro.conf.subcommand("doctor")]
    | Annotated[TraceArgs, tyro.conf.subcommand("trace")]
    | Annotated[ViewerArgs, tyro.conf.subcommand("viewer")]
    | Annotated[GraphArgs, tyro.conf.subcommand("graph")]
    | Annotated[FixArgs, tyro.conf.subcommand("fix")]
    | Annotated[SummaryArgs, tyro.conf.subcommand("summary")]
    | Annotated[ChangedArgs, tyro.conf.subcommand("changed")]
    | Annotated[AnalysisArgs, tyro.conf.subcommand("analysis")]
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
    | Annotated[LinkArgs, tyro.conf.subcommand("link")]
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
