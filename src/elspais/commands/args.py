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

from elspais.utilities.docs_loader import DOCS_TOPICS


# Implements: REQ-d00278-A+B+C, REQ-p00084-A
@dataclasses.dataclass
class ScopeOptions:
    """Selection shared by every surface that reports over a set of requirements.

    One definition rather than a copy per command: REQ-d00279-C obliges every
    path producing a report to yield the same scoped set, and flags duplicated
    per command are how two paths start disagreeing.
    """

    level: list[str] | None = None
    """Report only requirements at these levels (space-separated)."""

    not_level: list[str] | None = None
    """Report no requirement at these levels."""

    status: list[str] | None = None
    """Report only requirements carrying these statuses (space-separated)."""

    not_status: list[str] | None = None
    """Report no requirement carrying these statuses."""

    match_status_roles: bool = False
    """Read each named status as every status sharing its role."""

    scope: str | None = None
    """Report under a scope the project declares by this name."""


# ---------------------------------------------------------------------------
# Health command
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class ChecksArgs:
    """Verify requirements traceability and configuration.

    With --run-tests, executes each configured [[scanning.test.targets]]
    entry (that has a command) before evaluating checks so coverage runs
    against fresh result files. Without the flag, checks still warns when
    result files are missing or older than any scanned spec/code/test source.
    """

    spec_only: Annotated[bool, tyro.conf.arg(name="spec")] = False
    """Run spec file checks only."""

    code_only: Annotated[bool, tyro.conf.arg(name="code-checks")] = False
    """Run code reference checks only. Named `--code-checks` rather than
    `--code` because `--code` selects findings by diagnostic code."""

    tests_only: Annotated[bool, tyro.conf.arg(name="tests")] = False
    """Run test mapping checks only."""

    terms_only: Annotated[bool, tyro.conf.arg(name="terms")] = False
    """Run defined-term checks only."""

    severity: list[str] | None = None
    """Report only findings whose check carries these severities
    (error, warning, info; space-separated)."""

    category: list[str] | None = None
    """Report only findings in these categories (config, spec, references,
    code, tests, uat, terms; space-separated)."""

    check: list[str] | None = None
    """Report only these checks by name, e.g. references.malformed
    (space-separated). This is what the `unresolved`, `errors` and `uncited`
    listings are: this report narrowed to one set of checks."""

    code: list[str] | None = None
    """Report only findings carrying these diagnostic codes, e.g.
    E_IDENTIFIER_WITH_TRAILING_TEXT (space-separated). Selects findings, not
    checks: use --code-checks to run the code checks alone."""

    file: list[str] | None = None
    """Report only findings located in files matching these glob patterns
    (space-separated), e.g. 'spec/*.md'. Named `--file` rather than `--path`
    because `--path` already names the repository root to work from."""

    format: Literal["text", "markdown", "json", "junit", "sarif"] = "text"
    """Output format."""

    lenient: bool = False
    """Allow warnings without affecting exit code."""

    treat_active: list[str] | None = None
    """Treat these statuses as committed, counting them alongside Active."""

    include_passing_details: bool = False
    """Show full details for passing checks."""

    run_tests: bool = False
    """Execute each [[scanning.test.targets]] command before checks; exits 2 if none have a command.
    """

    fail_fast: bool = False
    """Stop at the first target failure and skip the checks pass. Requires --run-tests."""

    targets: list[str] | None = None
    """Run/mark only these [[scanning.test.targets]] by name (space-separated).
    Default: the targets of the `default` group. With --run-tests, executes only
    this subset; on summary/trace, marks the rest as carried baselines."""

    groups: list[str] | None = None
    """Run/mark only the [[scanning.test.targets]] in these groups (space-separated).
    `all` names every target, `default` the ones a run with no selection executes,
    and a project declares the rest in [scanning.test.groups]. Narrows alongside
    --targets rather than adding to it."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


# ---------------------------------------------------------------------------
# Gap listing commands
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class GapsArgs(ScopeOptions):
    """List all traceability gaps."""

    format: Literal["text", "markdown", "json"] = "text"
    """Output format."""

    treat_active: list[str] | None = None
    """Treat these statuses as committed, counting them alongside Active."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


@dataclasses.dataclass
class UncoveredArgs(ScopeOptions):
    """List requirements without code coverage."""

    format: Literal["text", "markdown", "json"] = "text"
    """Output format."""

    treat_active: list[str] | None = None
    """Treat these statuses as committed, counting them alongside Active."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


@dataclasses.dataclass
class UntestedArgs(ScopeOptions):
    """List requirements without test coverage."""

    format: Literal["text", "markdown", "json"] = "text"
    """Output format."""

    treat_active: list[str] | None = None
    """Treat these statuses as committed, counting them alongside Active."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


@dataclasses.dataclass
class UnvalidatedArgs(ScopeOptions):
    """List requirements without UAT (journey) coverage."""

    format: Literal["text", "markdown", "json"] = "text"
    """Output format."""

    treat_active: list[str] | None = None
    """Treat these statuses as committed, counting them alongside Active."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


@dataclasses.dataclass
class FailingArgs(ScopeOptions):
    """List requirements with failing test or UAT results."""

    format: Literal["text", "markdown", "json"] = "text"
    """Output format."""

    treat_active: list[str] | None = None
    """Treat these statuses as committed, counting them alongside Active."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


@dataclasses.dataclass
class UnresolvedArgs:
    """List references that name nothing the federation holds.

    A shortcut for `checks` narrowed to the five reference checks: every
    reference that did not read as an identifier, or read as one and resolved
    to nothing.
    """

    format: Literal["text", "markdown", "json", "junit", "sarif"] = "text"
    """Output format."""

    verbose: Annotated[bool, tyro.conf.arg(aliases=["-v"])] = False
    """Show the full detail of every check, including the ones that passed."""

    lenient: bool = False
    """Allow warnings without affecting exit code."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


@dataclasses.dataclass
class ErrorsArgs:
    """List what is wrong with the spec files themselves.

    A shortcut for `checks` narrowed to the spec-file checks: files that do
    not parse, format-rule violations, requirements with no assertions, and
    issues `elspais fix` cannot repair.
    """

    format: Literal["text", "markdown", "json", "junit", "sarif"] = "text"
    """Output format."""

    verbose: Annotated[bool, tyro.conf.arg(aliases=["-v"])] = False
    """Show the full detail of every check, including the ones that passed."""

    lenient: bool = False
    """Allow warnings without affecting exit code."""

    output: Annotated[Path | None, tyro.conf.arg(aliases=["-o"])] = None
    """Write output to file instead of stdout."""


@dataclasses.dataclass
class UncitedArgs:
    """List scanned code and test files that cite no requirement.

    A shortcut for `checks` narrowed to the two uncited-file checks.
    """

    format: Literal["text", "markdown", "json", "junit", "sarif"] = "text"
    """Output format."""

    verbose: Annotated[bool, tyro.conf.arg(aliases=["-v"])] = False
    """Show the full detail of every check, including the ones that passed."""

    lenient: bool = False
    """Allow warnings without affecting exit code."""

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
class TraceArgs(ScopeOptions):
    """Generate traceability matrix."""

    format: Literal["text", "markdown", "html", "json", "csv"] = "markdown"
    """Output format."""

    # Implements: REQ-d00282-A
    # Stated on the commands that report facts about each row and nowhere else:
    # a flag a command accepts and cannot honour is worse than one it does not
    # offer, which is the defect value selection exists to remove.
    values: str | None = None
    """State these values, in this order (comma-separated value keys).
    Keys are stable names, never the words a project displays them under:
    id, title, level, status, implements, hash, file, journeys; the coverage
    dimensions implemented, tested, verified, uat_coverage, uat_verified, each
    also selectable per measure (e.g. tested.immediate_direct); and the
    lcov_tested dimension. Every coverage figure also offers the scalars
    behind it -- .count, .total and .ratio, as numbers (e.g.
    implemented.ratio, tested.immediate_direct.count) -- plus the counts-only
    tested.passed, tested.failed and tested.awaiting, and the provenance bit
    verified.carried. code_tested is measured in LINES: code_tested.count is
    the lines covered, .total the lines measured, .ratio their proportion,
    and .attributed the lines a verifying test can be named for (absent where
    the coverage data carries no per-test contexts)."""

    preset: Literal["minimal", "standard", "full"] | None = None
    """Named default value set."""

    body: bool = False
    """Show requirement body text in detail rows."""

    show_assertions: Annotated[bool, tyro.conf.arg(name="assertions")] = False
    """Show individual assertions in detail rows."""

    show_tests: Annotated[bool, tyro.conf.arg(name="tests")] = False
    """Show test references in detail rows."""

    dimension: str = ""
    """Report a named default value set.  Use 'uat' for user-acceptance
    evidence: the journeys validating each requirement with their verdicts, and
    the UAT coverage figures.  It states no implementation, test-verification or
    line-coverage figure, and selects no requirements -- every requirement is
    reported, including those no journey validates."""

    targets: list[str] | None = None
    """Mark only these [[scanning.test.targets]] as freshly-run; render the rest
    as carried baselines."""

    groups: list[str] | None = None
    """Mark only the [[scanning.test.targets]] in these groups as freshly-run;
    render the rest as carried baselines. `all` names every target, `default` the
    ones a run with no selection executes."""

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
class SummaryArgs(ScopeOptions):
    """Coverage summary by level (Implemented, Tested, Passing, UAT Covered, UAT Passed)."""

    format: Literal["text", "markdown", "json", "csv"] = "text"
    """Output format."""

    # Implements: REQ-d00282-A
    # The values this report offers are the ones a GROUP of requirements has:
    # level, the two counts describing the group, each coverage dimension with
    # the four measures behind it, and the line figure summed over the group.
    # Per-requirement values are not among them.
    values: str | None = None
    """State these values, in this order (comma-separated value keys).
    Keys are stable names, never the words a project displays them under:
    level, requirements, assertions, and the coverage dimensions implemented,
    tested, verified, uat_coverage, uat_verified -- each also selectable per
    measure (e.g. tested.immediate_direct), and every figure also by the
    scalars behind it: .count, .total and .ratio, as numbers. The three counts
    of the Tested breakdown are tested.passed, tested.failed and
    tested.awaiting. code_tested is the group's line coverage, measured in
    LINES: .count the lines covered, .total the lines measured, .ratio their
    proportion, and .attributed the lines a verifying test can be named for
    (absent where the coverage data carries no per-test contexts)."""

    targets: list[str] | None = None
    """Mark only these [[scanning.test.targets]] as freshly-run; render the rest
    as carried baselines."""

    groups: list[str] | None = None
    """Mark only the [[scanning.test.targets]] in these groups as freshly-run;
    render the rest as carried baselines. `all` names every target, `default` the
    ones a run with no selection executes."""

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
class AnalysisArgs(ScopeOptions):
    """Analyze foundational requirement importance."""

    top: Annotated[int, tyro.conf.arg(aliases=["-n"])] = 10
    """Number of top results to show."""

    weights: str | None = None
    """Centrality,fan-in,neighborhood,uncovered weights (default: 0.3,0.2,0.2,0.3)."""

    format: Literal["table", "json"] = "table"
    """Output format."""

    show: Literal["foundations", "leaves", "all"] = "all"
    """Which sections to show."""

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
# The topic set is declared once, in the loader that serves it, so the CLI
# cannot admit a topic the docs do not carry or refuse one they do.
# Implements: REQ-d00286-A


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

    global_scope: Annotated[bool, tyro.conf.arg(name="global")] = False
    """Install for all projects (user scope)."""

    desktop: bool = False
    """Also install into Claude Desktop."""

    transport: Literal["http", "stdio"] = "http"
    """How the client reaches elspais. http shares one graph with the CLI and the
    viewer and survives the daemon restarting; stdio holds a private graph and is
    for clients that cannot speak http."""


@dataclasses.dataclass
class McpUninstallArgs:
    """Remove elspais MCP server from Claude Code."""

    global_scope: Annotated[bool, tyro.conf.arg(name="global")] = False
    """Remove from user scope."""

    desktop: bool = False
    """Also remove from Claude Desktop."""


@dataclasses.dataclass
class McpEnvArgs:
    """Print shell assignments naming where this working tree is served.

    Meant to be evaluated by the shell that will launch the client:
    ``eval "$(elspais mcp env)"``. A process cannot set a variable in the
    shell that started it, so the assignments are printed for the shell
    to apply -- the same arrangement ssh-agent and direnv use.
    """

    no_start: bool = False
    """Report only an already-running daemon rather than starting one."""


McpAction = (
    Annotated[McpServeArgs, tyro.conf.subcommand("serve")]
    | Annotated[McpInstallArgs, tyro.conf.subcommand("install")]
    | Annotated[McpUninstallArgs, tyro.conf.subcommand("uninstall")]
    | Annotated[McpEnvArgs, tyro.conf.subcommand("env")]
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

    discard_changes: bool = False
    """Throw away the daemon's unsaved in-memory mutations instead of saving them."""

    persist: bool = False
    """Persist any unsaved in-memory mutations to disk before restarting."""

    message: str | None = None
    """Changelog reason recorded with --persist when Active requirements changed."""


DaemonAction = Annotated[DaemonRestartArgs, tyro.conf.subcommand("restart")]


@dataclasses.dataclass
class DaemonArgs:
    """Manage the background daemon (MCP + CLI share one daemon per repo).

    A daemon restarted here is tied to no session and lives by cli_ttl
    alone; one a CLI command auto-started ends with that session.
    """

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
    | Annotated[UnresolvedArgs, tyro.conf.subcommand("unresolved")]
    | Annotated[UncitedArgs, tyro.conf.subcommand("uncited")]
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
    "unresolved": "Gaps & Issues",
    "uncited": "Gaps & Issues",
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


@dataclasses.dataclass(frozen=True)
class CommandEntry:
    """One command the CLI exposes, read from the definitions it dispatches on."""

    name: str
    group: str
    description: str
    #: Names of the command's own nested subcommands, where it has any.
    actions: tuple[str, ...] = ()

    @property
    def summary(self) -> str:
        """The description with the nested subcommand names appended."""
        if not self.actions:
            return self.description
        return f"{self.description} ({', '.join(self.actions)})"


def _action_names(base_type: type) -> tuple[str, ...]:
    """The nested subcommand names a command's `action` field offers."""
    import typing

    if not dataclasses.is_dataclass(base_type):
        return ()
    hints = typing.get_type_hints(base_type, include_extras=True)
    if "action" not in hints:
        return ()
    action_t = hints["action"]
    # Unwrap tyro wrapper types to reach the inner Union
    while (
        typing.get_origin(action_t) is not None and typing.get_origin(action_t) is not typing.Union
    ):
        inner = typing.get_args(action_t)
        if not inner:
            break
        action_t = inner[0]
    names: list[str] = []
    for aa in typing.get_args(action_t):
        if typing.get_origin(aa) is typing.Annotated:
            _, *ameta = typing.get_args(aa)
            for am in ameta:
                if hasattr(am, "name"):
                    names.append(am.name)
    return tuple(names)


def iter_command_entries() -> list[CommandEntry]:
    """Every command the CLI exposes, in group order.

    Read from the `Command` union and `COMMAND_GROUPS`, which are what the CLI
    itself dispatches on, so no presentation of the command set can name a
    command the tool does not have or miss one it does. This is the one place
    that reflection happens; the grouped `--help` text and the documentation's
    command index are both rendered from what it returns.
    """
    import typing

    described: dict[str, CommandEntry] = {}
    for arg in typing.get_args(Command):
        if typing.get_origin(arg) is not typing.Annotated:
            continue
        base_type, *metadata = typing.get_args(arg)
        name = None
        for m in metadata:
            if hasattr(m, "name"):
                name = m.name
        if name is None:
            continue
        # Description from the docstring's first line, without its full stop.
        doc = (base_type.__doc__ or "").strip().split("\n")[0].strip()
        if doc.endswith("."):
            doc = doc[:-1]
        group = COMMAND_GROUPS.get(name)
        if group is None:
            raise ValueError(
                f"Subcommand {name!r} missing from COMMAND_GROUPS — "
                f"add it to elspais/commands/args.py"
            )
        described[name] = CommandEntry(
            name=name, group=group, description=doc, actions=_action_names(base_type)
        )

    entries: list[CommandEntry] = []
    for group in _GROUP_ORDER:
        for name, command_group in COMMAND_GROUPS.items():
            if command_group == group and name in described:
                entries.append(described[name])
    return entries


def generate_help(version: str) -> str:
    """Generate grouped CLI help text from the CLI's own command definitions.

    Reads subcommand names and descriptions through `iter_command_entries()`,
    so the help output cannot drift from what the CLI dispatches on.
    """
    entries = iter_command_entries()

    # --- Build grouped output ---
    cmd_lookup: dict[str, str] = {e.name: e.summary for e in entries}
    groups: dict[str, list[str]] = {g: [] for g in _GROUP_ORDER}
    for entry in entries:
        groups[entry.group].append(entry.name)

    # Compute column width for subcommands
    max_name = max((len(e.name) for e in entries), default=0)
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
    lines.append("  elspais checks --run-tests    # Run configured test runners, then verify")

    lines.append("")
    lines.append("For command help: elspais <command> --help")

    return "\n".join(lines)
