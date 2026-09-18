# CLI COMMANDS REFERENCE

Complete reference for all elspais commands.

## Command Index

<!-- generated: command-index -->
<!-- Rendered from the program's own definitions; edits here are overwritten. Regenerate: python -m elspais.utilities.doc_tables -->

| Command | Group | What it does |
| --- | --- | --- |
| `checks` | Reports | Verify requirements traceability and configuration |
| `summary` | Reports | Coverage summary by level (Implemented, Tested, Passing, UAT Covered, UAT Passed) |
| `trace` | Reports | Generate traceability matrix |
| `changed` | Reports | Detect git changes to spec files |
| `pdf` | Reports | Compile spec files into a PDF document |
| `search` | Reports | Search requirements by keyword |
| `gaps` | Gaps & Issues | List which requirements fall short of each coverage dimension |
| `uncovered` | Gaps & Issues | List requirements without code coverage |
| `untested` | Gaps & Issues | List requirements without test coverage |
| `unvalidated` | Gaps & Issues | List requirements without UAT (journey) coverage |
| `failing` | Gaps & Issues | List requirements with failing test or UAT results |
| `errors` | Gaps & Issues | List what is wrong with the spec files themselves |
| `unresolved` | Gaps & Issues | List references that name nothing the federation holds |
| `uncited` | Gaps & Issues | List scanned code and test files that cite no requirement |
| `analysis` | Authoring | Analyze foundational requirement importance |
| `fix` | Authoring | Auto-fix spec file issues (hashes, formatting) |
| `edit` | Authoring | Edit requirements in-place (implements, status, move) |
| `example` | Authoring | Display requirement format examples and templates |
| `link` | Authoring | Link suggestion tools |
| `glossary` | Authoring | Generate glossary from defined terms |
| `term-index` | Authoring | Generate term index and collection manifests from defined terms |
| `comments` | Authoring | Comment management commands |
| `viewer` | Viewing | Interactive traceability viewer (live server or static HTML) |
| `graph` | Viewing | Export the traceability graph structure as JSON |
| `init` | Configuration | Create .elspais.toml configuration |
| `config` | Configuration | View and modify configuration |
| `rules` | Configuration | View and manage content rules |
| `associate` | Configuration | Manage associate repository links (link, list, unlink) |
| `doctor` | Install | Diagnose environment and installation health |
| `mcp` | Install | MCP server commands |
| `daemon` | Install | Manage the background daemon (MCP + CLI share one daemon per repo) |
| `install` | Install | Install elspais variants |
| `uninstall` | Install | Revert elspais installation |
| `completion` | Install | Generate and install shell tab-completion scripts (bash, zsh, tcsh) |
| `docs` | Info | Read the user guide |
| `version` | Info | Show version and check for updates |

Each command's own section below says how to use it. `elspais <command>
--help` says the same from the installed program.
<!-- /generated: command-index -->

## Global Options

These options work with all commands:

  `-v, --verbose`    Verbose output with details
  `-q, --quiet`      Suppress non-error output
  `--config PATH`    Path to configuration file
  `--spec-dir PATH`  Override spec directory

## checks

Verify requirements traceability across configuration, spec files, code, and tests.

  $ elspais checks                     # Run all checks
  $ elspais checks --spec              # Spec file checks
  $ elspais checks --code-checks       # Code reference checks
  $ elspais checks --tests             # Test mapping checks
  $ elspais checks --format json       # JSON output

To auto-fix issues, use: `elspais fix`
To see specific errors, use: `elspais errors`
To see unresolved references, use: `elspais unresolved`

**Options:**

  `--spec`         Run spec file checks only
  `--code-checks`  Run code reference checks only
  `--tests`        Run test mapping checks only
  `--terms`        Run defined-term checks only
  `--severity S...`  Report only findings whose check carries these severities
  `--category C...`  Report only findings in these check categories
  `--check NAME...`  Report only these checks by name (what the `unresolved`,
                   `errors` and `uncited` listings are)
  `--code CODE...`   Report only findings carrying these diagnostic codes
  `--file GLOB...`   Report only findings located in matching files
  `--format {text,markdown,json,junit,sarif}`  Output format (default: text)
  `--lenient`      Allow warnings without affecting exit code
  `--treat-active ST ...`  Weigh these statuses as active ones
  `--no-include-passing-details`  Hide details for passing checks (default)
  `--include-passing-details`     Show full details for passing checks
  `--run-tests`    Execute each `[[scanning.test.targets]]` entry that carries a
                   command before evaluating checks, so coverage runs against
                   fresh result files. Exits 2 if no target has a command.
  `--fail-fast`    Stop at the first target failure and skip the checks pass.
                   Requires `--run-tests`.
  `--targets T...` Run and ingest only these test targets rather than the
                   `default` group
  `-o, --output PATH`  Write output to file instead of stdout

`-v, --verbose` is a global option (see Global Options above) and reports each
check individually rather than only the summary.

## errors

List what is wrong with the spec files themselves.

  $ elspais errors                     # Show all spec errors
  $ elspais errors --format markdown   # Markdown table
  $ elspais errors --format json       # JSON output
  $ elspais errors -o errors.txt       # Write to file

This is `elspais checks` narrowed to the spec-file checks — exactly `elspais
checks --check spec.parseable spec.format_rules spec.no_assertions
spec.unfixable_issues`. A file that would not parse is listed here alongside a
format-rule violation, because both are defects in the file rather than in
what it points at.

Every requirement is weighed whatever its status, so the listing accounts for
exactly what `elspais checks` counted. There is no status option here: format
rules bind a requirement whatever its status, so there is nothing to widen and
nothing worth narrowing.

**Options:**

  `--format {text,markdown,json,junit,sarif}`  Output format (default: text)
  `-v, --verbose`                  Show the full detail of every check
  `--lenient`                      Allow warnings without affecting exit code
  `-o, --output PATH`              Write output to file instead of stdout

**Exit code:** 0 when no selected check failed, 1 otherwise.

Follow-up from `elspais checks` when `spec.format_rules` or `spec.no_assertions` fails.

## gaps

List which requirements fall short of each dimension of coverage, one section
per dimension, in a single listing.

  $ elspais gaps                       # Every dimension
  $ elspais gaps --values implemented  # Only what nothing implements
  $ elspais gaps --level dev           # Only the dev level
  $ elspais gaps --format json         # JSON output

Each section reads one dimension and lists what it has not credited, so
`--values` says which sections appear. The four it offers are `implemented`
(uncovered), `tested` (untested), `uat_coverage` (unvalidated) and `verified`
(failing) -- the same keys `summary` and `trace` state as columns, which is why
a `[scopes.NAME]` declaring values works on all three. The single-dimension
commands below are this report under a fixed selection: `gaps --values
implemented` and `uncovered` are the same report, and `uncovered --values
tested` is refused rather than quietly becoming `untested`.

A requirement with no assertions has no dimension to fall short of and is not
listed here; `elspais checks` reports it as `spec.no_assertions`.

Where a requirement declares `Integrates:`, the coverage inherited from the
associate that provides it is credited, and the requirement is listed under
"Covered via external associate" rather than as uncovered.

**Options:**

  `--format {text,markdown,json}`  Output format (default: text)
  `--values KEY,...`               List only these dimensions' shortfalls,
                                   in this order (default: all four)
  `-o, --output PATH`              Write output to file instead of stdout

**Scoping the listing** (see `elspais docs scoping`):

  `--level LVL ...`        List only requirements at these levels
  `--not-level LVL ...`    List no requirement at these levels
  `--status ST ...`        List only requirements carrying these statuses
  `--not-status ST ...`    List no requirement carrying these statuses
  `--match-status-roles`   Read each named status as every status sharing its role
  `--scope NAME`           List under a scope declared in `[scopes.NAME]`
  `--treat-active ST ...`  Weigh these statuses as active ones

Follow-up from `elspais checks` when a coverage check fails. The single-
dimension commands below are this report under a one-dimension selection.

## uncovered

List requirements no code implements -- the `implemented` dimension.

  $ elspais uncovered                  # Requirements with no implementation
  $ elspais uncovered --level dev      # Only the dev level
  $ elspais uncovered --format json    # JSON output

An assertion counts as covered only where a citation names it and the evidence
is complete; whole-requirement evidence elsewhere does not settle it. See
`elspais docs checks` (*Coverage Dimensions*).

**Options:**

  `--format {text,markdown,json}`  Output format (default: text)
  `-o, --output PATH`              Write output to file instead of stdout

**Scoping the listing** (see `elspais docs scoping`):

  `--level LVL ...`        List only requirements at these levels
  `--not-level LVL ...`    List no requirement at these levels
  `--status ST ...`        List only requirements carrying these statuses
  `--not-status ST ...`    List no requirement carrying these statuses
  `--match-status-roles`   Read each named status as every status sharing its role
  `--scope NAME`           List under a scope declared in `[scopes.NAME]`
  `--treat-active ST ...`  Weigh these statuses as active ones

Follow-up from `elspais checks` when `code.implemented` fails.

## untested

List requirements no test exercises -- the `tested` dimension.

  $ elspais untested                   # Requirements with no test
  $ elspais untested --status Active   # Only Active requirements
  $ elspais untested --format markdown # Markdown table

**Options:**

  `--format {text,markdown,json}`  Output format (default: text)
  `-o, --output PATH`              Write output to file instead of stdout

**Scoping the listing** (see `elspais docs scoping`):

  `--level LVL ...`        List only requirements at these levels
  `--not-level LVL ...`    List no requirement at these levels
  `--status ST ...`        List only requirements carrying these statuses
  `--not-status ST ...`    List no requirement carrying these statuses
  `--match-status-roles`   Read each named status as every status sharing its role
  `--scope NAME`           List under a scope declared in `[scopes.NAME]`
  `--treat-active ST ...`  Weigh these statuses as active ones

Follow-up from `elspais checks` when `tests.tested` fails.

## unvalidated

List requirements no user journey validates -- the `uat_coverage` dimension.

  $ elspais unvalidated                # Requirements with no validating journey
  $ elspais unvalidated --format json  # JSON output

Only levels declaring `expects_validation = true` are weighed; where no level
declares it, the listing is empty and nothing is wrong.

**Options:**

  `--format {text,markdown,json}`  Output format (default: text)
  `-o, --output PATH`              Write output to file instead of stdout

**Scoping the listing** (see `elspais docs scoping`):

  `--level LVL ...`        List only requirements at these levels
  `--not-level LVL ...`    List no requirement at these levels
  `--status ST ...`        List only requirements carrying these statuses
  `--not-status ST ...`    List no requirement carrying these statuses
  `--match-status-roles`   Read each named status as every status sharing its role
  `--scope NAME`           List under a scope declared in `[scopes.NAME]`
  `--treat-active ST ...`  Weigh these statuses as active ones

Follow-up from `elspais checks` when `uat.uat_coverage` fails.

## failing

List requirements whose test or UAT results failed.

  $ elspais failing                    # Requirements with a failing result
  $ elspais failing --level dev        # Only the dev level
  $ elspais failing --format json      # JSON output

A requirement is listed where a result naming it returned a failure, so the
listing is empty until results have been ingested (see `elspais docs
test-targets`).

**Options:**

  `--format {text,markdown,json}`  Output format (default: text)
  `-o, --output PATH`              Write output to file instead of stdout

**Scoping the listing** (see `elspais docs scoping`):

  `--level LVL ...`        List only requirements at these levels
  `--not-level LVL ...`    List no requirement at these levels
  `--status ST ...`        List only requirements carrying these statuses
  `--not-status ST ...`    List no requirement carrying these statuses
  `--match-status-roles`   Read each named status as every status sharing its role
  `--scope NAME`           List under a scope declared in `[scopes.NAME]`
  `--treat-active ST ...`  Weigh these statuses as active ones

Follow-up from `elspais checks` when `tests.verified`, `tests.results` or
`uat.uat_verified` fails.

## unresolved

List references that name nothing the federation holds.

  $ elspais unresolved                 # Every unresolved reference
  $ elspais unresolved --format json   # JSON output
  $ elspais unresolved -o refs.txt     # Write to file

This is `elspais checks` narrowed to the five reference checks, and nothing
else — it is exactly `elspais checks --check references.malformed
references.unknown_namespace references.unknown_requirement
references.unknown_assertion references.forbidden`. Each finding therefore
carries what every finding carries: the check that raised it (which names the
class the reference reached), its severity, the diagnostic codes reading it
produced, its location and its remedy.

A reference is *malformed* when it did not read as an identifier at all, and
*unresolved* when it read as one and named nothing. The listing covers both,
which is why it is named for the union.

The listing opens by naming the narrowing and how much of the run it withheld,
so a short list is never mistaken for a clean run.

There is no scoping here: a reference resolves or it does not, whatever the
status of the requirement holding it. What the listing DOES honour is the
severity a project configured: a class set to `"off"` reports as skipped and
lists nothing, and the skipped line says so.

**Options:**

  `--format {text,markdown,json,junit,sarif}`  Output format (default: text)
  `-v, --verbose`                  Show the full detail of every check
  `--lenient`                      Allow warnings without affecting exit code
  `-o, --output PATH`              Write output to file instead of stdout

**Exit code:** 0 when no selected check failed, 1 otherwise. The verdict is
taken over the five reference checks alone, never over the rest of the run.

Follow-up from `elspais checks` when a `references.*` check fails.

## uncited

List scanned code and test files that cite nothing.

  $ elspais uncited                  # Every code and test file citing nothing
  $ elspais uncited --format json    # JSON output, carrying each file node's id
  $ elspais uncited -o uncited.txt   # Write to file

A code file is listed where the scan produced no citation from it at all. A
test file is listed where no test in it links to any requirement; one linked
test is enough to keep the file out of the listing. A test file whose only
citation attached to no test carries a marker, so it is left to
`tests.unbound_citation`, which says what is actually wrong with it.

This is `elspais checks` narrowed to the two uncited-file checks — exactly
`elspais checks --check code.uncited_file tests.uncited_file`. Each finding
names the file it is about, alongside the check that raised it, its severity
and its remedy.

This is not the *unlinked* population. An unlinked node is a single test
function or citation block that exists and reaches no requirement; the MCP
`get_unlinked_nodes` tool answers about those. A file holding one linked test
and nine unlinked ones is full of unlinked nodes and is not uncited.

**Options:**

  `--format {text,markdown,json,junit,sarif}`  Output format (default: text)
  `-v, --verbose`                  Show the full detail of every check
  `--lenient`                      Allow warnings without affecting exit code
  `-o, --output PATH`              Write output to file instead of stdout

**Exit code:** 0 when no selected check failed, 1 otherwise.

Follow-up from `elspais checks` when `code.uncited_file` or
`tests.uncited_file` reports.

## fix

Auto-fix spec file issues (hashes, formatting).

  $ elspais fix                   # Fix all issues
  $ elspais fix --dry-run         # Preview fixes without applying
  $ elspais fix REQ-p00001        # Fix hash for a specific requirement
  $ elspais fix -m "Clarify auth" # Provide changelog reason

**Options:**

  `REQ_ID`        Specific requirement ID to fix (hash only)
  `--dry-run`     Show what would be fixed without making changes
  `-m, --message` Changelog reason for Active requirement hash updates
  `--mode {core,combined,associate}`  Scope of fix (default: combined)

## trace

Generate traceability matrix and reports.

  $ elspais trace                        # Markdown table (default)
  $ elspais trace --format html          # Basic HTML matrix
  $ elspais trace --format csv           # Spreadsheet export
  $ elspais trace --preset full          # Widest default value set

**Options:**

  `--format {text,markdown,html,json,csv}`  Output format (default: markdown)
  `--preset {minimal,standard,full}`        Named default value set
  `--values KEY,KEY,...` State exactly these values, in this order. A coverage figure is also selectable as the numbers behind it -- `implemented.count`, `implemented.total`, `implemented.ratio` -- and `verified.carried` states whether the Passing verdict was carried from a baseline (see `elspais docs traceability`)
  `--body`               Show requirement body text
  `--assertions`         Show individual assertions
  `--tests`              Show test references
  `--output PATH`        Output file path

**Scoping the report** (see `elspais docs scoping`):

  `--level LVL ...`        Report only requirements at these levels
  `--not-level LVL ...`    Report no requirement at these levels
  `--status ST ...`        Report only requirements carrying these statuses
  `--not-status ST ...`    Report no requirement carrying these statuses
  `--match-status-roles`   Read each named status as every status sharing its role
  `--scope NAME`           Report under a scope declared in `[scopes.NAME]`
  `--treat-active ST ...`  Weigh these statuses as active ones

## search

Search requirements by keyword, with ranked results.

  $ elspais search 'authentication'       # Search all fields
  $ elspais search 'auth OR login'        # OR queries
  $ elspais search '"exact phrase"'       # Phrase match
  $ elspais search '-deprecated auth'     # Exclude term
  $ elspais search '=security'            # Exact keyword tag
  $ elspais search 'graph' --field title  # Search titles only
  $ elspais search 'REQ-p' --regex        # Regex mode
  $ elspais search 'graph' -n 10          # Limit results

**Options:**

  `--field {all,id,title,body,keywords}`  Fields to search (default: all)
  `--regex`            Treat query as regex
  `-n, --limit N`      Max results (default: 50)
  `--format {text,json}`  Output format
  `--no-daemon`        Skip daemon, rebuild graph locally

**Performance:** Connects to a running viewer or MCP daemon for instant
results (~0.1s). Auto-starts a daemon on first use if neither is running.
Use `--no-daemon` to force a local graph build (~2-4s).

**Daemon config** (in `.elspais.toml`):

    cli_ttl = 30     # auto-start daemon, exit after 30 min unused (default)
    cli_ttl = 0      # never auto-launch (manual start only)
    cli_ttl = -1     # auto-start daemon, never timeout

`cli_ttl` is the idle timeout for a daemon nobody is using. It does not
end a daemon that still has a recorded client, however quiet that client
has been — an agent that applies a change and then reasons for an hour
sends nothing the whole time, and still has its daemon at the end of it.
A daemon auto-started for a session ends when that session's clients are
gone, whatever `cli_ttl` says — see "Daemon lifetime" below.

## viewer

Interactive traceability viewer (live server or static HTML). The viewer
also serves MCP tools at `/mcp` for AI agent integration.

  $ elspais viewer                  # Start server and open browser
  $ elspais viewer --static         # Generate static HTML file
  $ elspais viewer --server         # Start server without opening browser
  $ elspais viewer --path /my/repo  # Specify repository root
  $ elspais viewer --server --session-lifetime   # Stop once no tab holds it

**Options:**

  `--static`             Generate static HTML file instead of live server
  `--server`             Start server without opening browser
  `--port PORT`          Server port (default: 5001)
  `--embed-content`      Embed full markdown in HTML for offline viewing
  `--path DIR`           Path to repository root (default: auto-detect)
  `--session-lifetime`   Stop the server, saving held changes, once no
                         browser tab has held it open for the grace
                         interval

**Session lifetime.** A viewer tab holds a stream open to the server for
as long as it is open, and the server counts it as a client exactly as it
counts an agent's MCP session (see `daemon`). With `--session-lifetime`
that count is what ends the viewer: it keeps serving while any tab holds
a stream, and once no tab has held one for the grace interval -- counted
from its start, so a viewer no tab ever connects to ends by the same
clock -- it persists whatever changes it holds and stops, by the same
rule and the same grace as a daemon whose clients are gone. The grace
applies whether or not changes are pending, unlike a daemon whose
recorded processes have all died: a tab's stream drops on a reload, a
laptop going to sleep or a tunnel reconnecting, and comes back, so no
stream held at one check is not a session that has ended. Meant for a
viewer started on somebody's behalf, such as one a hub opens for a
browser session. Without the flag the viewer's lifetime is unchanged.

## graph

Export the traceability graph structure as JSON.

  $ elspais graph                   # Print to stdout
  $ elspais graph -o graph.json     # Write to file

## pdf

Compile spec files into a PDF document.

  $ elspais pdf                              # Generate spec-output.pdf
  $ elspais pdf --output review.pdf          # Custom output path
  $ elspais pdf --title "My Project Specs"   # Custom title
  $ elspais pdf --cover spec/cover.tex       # Custom cover page

**Options:**

  `--output PATH`       Output PDF file path (default: spec-output.pdf)
  `--engine ENGINE`     PDF engine: xelatex (default), lualatex, pdflatex
  `--template PATH`     Custom pandoc LaTeX template
  `--title TITLE`       Document title
  `--cover PATH`        Markdown file for custom cover page

**Prerequisites:**

- pandoc: <https://pandoc.org/installing.html>
- xelatex: Install TeX Live, MiKTeX, or MacTeX

**Federated projects:**

One run from the root repository compiles every repository in the graph into a
single document. Each spec file is read from its own repository, and Topic
Index entries for requirements owned by an associate carry a `[<repo-name>]`
prefix so the reader can tell where a section comes from.

**Figures and completeness:**

Image and Mermaid references resolve against the declaring spec file's own
directory, then its owning repository's root, then the resource path (every
repository's root and `spec/` directory) -- so in a federated project each
file's figures come from its own repo. Percent-encoded references resolve on
their decoded form; references inside fenced and indented code blocks are left
alone entirely, and a fence that is never closed is itself reported. A reference no repository
can supply, a Mermaid source that cannot be rendered, a spec file that cannot
be found in its owning repository, or a configured associate repository that
fails to load (each of which takes requirements out of the document) is
reported on stderr with the locations searched and a remedy. Resources pandoc
itself could not fetch -- `.webp`, `.pdf`, reference-style links and other
media outside the compiler's grammar -- are folded into the same report,
deduplicated so one missing file counts once, and the completion line is
qualified `(INCOMPLETE: N references omitted -- see warnings above)`. The exit
code stays `0`: the document is produced, and the degradation is disclosed
rather than fatal. The one exception is a missing absolute image path, which
pandoc cannot survive: it is reported by name, then the run fails non-zero. Raw HTML `<img>` tags are **not** supported and cannot be
reported -- use Markdown image syntax. See `elspais docs pdf`.

## summary

Generate coverage summary reports.

  $ elspais summary                 # Coverage summary
  $ elspais summary --format json   # JSON output

**Options:**

  `--format {text,markdown,json,csv}`  Output format (default: text)
  `--values KEY,KEY,...` State exactly these values, in this order. Its rows
  are levels, so it offers `level`, `requirements`, `assertions` and the five
  coverage dimensions with their four measures each, plus the scalars behind
  every figure (`.count`, `.total`, `.ratio`) -- not the per-requirement
  values, nor `verified.carried` (a level has no per-requirement provenance
  bit), nor the line-coverage ones (a level has no line figure). A table
  states a figure as one cell; `--format json` states it as an object of its
  numbers, in the same row shape `trace` uses. See `elspais docs scoping`.

When `Integrates:` references are present, `summary` adds an "External
integrations (by associate)" section listing inherited coverage grouped by the
owning associate with a federation total, and `gaps` lists integrating
requirements under "Covered via external associate" instead of flagging them as
uncovered.

**Scoping the report** (see `elspais docs scoping`):

  `--level LVL ...`        Report only requirements at these levels
  `--not-level LVL ...`    Report no requirement at these levels
  `--status ST ...`        Report only requirements carrying these statuses
  `--not-status ST ...`    Report no requirement carrying these statuses
  `--match-status-roles`   Read each named status as every status sharing its role
  `--scope NAME`           Report under a scope declared in `[scopes.NAME]`
  `--treat-active ST ...`  Weigh these statuses as active ones

## changed

Detect git changes to spec files.

  $ elspais changed                       # Show all spec changes
  $ elspais changed --format json         # Output as JSON
  $ elspais changed -a                    # Include non-spec files

**Options:**

  `--base-branch BRANCH`  Base branch for comparison (default: main)
  `--format {text,json}`  Output format (default: text)
  `-a, --all`             Include all changed files, not just spec

**What's Detected:**

  Uncommitted changes (modified/new spec files)
  Changes vs main/master branch
  Moved requirements (relocated to different file)

## analysis

Analyze foundational requirement importance using graph metrics.

  $ elspais analysis                          # Default analysis
  $ elspais analysis -n 5 --show foundations  # Top 5 foundations only
  $ elspais analysis --format json            # JSON output

**Options:**

  `-n, --top N`         Number of top results per section (default: 10)
  `--weights W1,W2,W3,W4`  Centrality, fan-in, neighborhood, uncovered weights
  `--format {table,json}`  Output format (default: table)
  `--show {foundations,leaves,all}`  Which sections (default: all)
  `--include-code`      Include CODE nodes in analysis graph
  `-o, --output PATH`   Write output to file instead of stdout

**Scoping the report** (see `elspais docs scoping`):

  `--level LVL ...`        Report only requirements at these levels
  `--not-level LVL ...`    Report no requirement at these levels
  `--status ST ...`        Report only requirements carrying these statuses
  `--not-status ST ...`    Report no requirement carrying these statuses
  `--match-status-roles`   Read each named status as every status sharing its role
  `--scope NAME`           Report under a scope declared in `[scopes.NAME]`
  `--treat-active ST ...`  Weigh these statuses as active ones

## edit

Edit requirements in-place.

  $ elspais edit REQ-d00001 --status Draft
  $ elspais edit REQ-d00001 --implements REQ-p00001,REQ-p00002
  $ elspais edit REQ-d00001 --move-to roadmap/future.md
  $ elspais edit --from-json edits.json

**Options:**

  `REQ_ID`              Requirement ID to edit (positional)
  `--implements REFS`   New Implements (comma-separated, "" to clear)
  `--status STATUS`     New Status value
  `--move-to FILE`      Move to file (relative to spec dir)
  `--from-json FILE`    Batch edit from JSON (- for stdin)
  `--dry-run`           Show changes without applying
  `--validate-refs`     Validate implements references exist

**Batch JSON Format:**

    [
      {"req_id": "REQ-d00001", "status": "Draft"},
      {"req_id": "REQ-d00002", "implements": ["REQ-p00001"]}
    ]

## config

View and modify configuration.

  $ elspais config show           # View all settings
  $ elspais config get patterns.prefix
  $ elspais config set project.name "MyApp"
  $ elspais config path           # Show config file location

**Subcommands:**

  `show [--section] [--format {text,json}]`  Show current configuration
  `get KEY [--format {text,json}]`           Get value (dot-notation: patterns.prefix)
  `set KEY VALUE`          Set value (auto-detects type)
  `unset KEY`              Remove a key
  `add KEY VALUE`          Add value to array
  `remove KEY VALUE`       Remove value from array
  `path`                   Show config file location

## init

Create .elspais.toml configuration.

  $ elspais init                  # Create default config
  $ elspais init --template       # Also create example requirement

**Options:**

  `--type {core,associated}`   Repository type
  `--associated-prefix PREFIX` Prefix for associated repo
  `--force`                    Overwrite existing configuration
  `--template`                 Create example requirement in spec/

## example

Display requirement format examples.

  $ elspais example               # Quick format reference
  $ elspais example --full        # Full specification document
  $ elspais example journey       # User journey template

**Arguments:**

  `requirement`  Full requirement template (default)
  `journey`      User journey template
  `assertion`    Assertion rules and examples
  `ids`          Show ID patterns from current config

**Options:**

  `--full`   Display full requirements specification file

## rules

View and manage content rules.

  $ elspais rules list            # List configured rules
  $ elspais rules show myfile.md  # Show rule file content

**Subcommands:**

  `list`        List configured content rules
  `show FILE`   Show content of a rule file

## docs

Read the user guide.

  $ elspais docs                  # Quickstart guide
  $ elspais docs config           # Configuration reference
  $ elspais docs all              # Complete documentation

**Arguments:**

  `quickstart`     Getting started guide (default)
  `format`         Requirement file format
  `hierarchy`      PRD/OPS/DEV levels
  `assertions`     Writing testable assertions
  `traceability`   Linking to code and tests
  `linking`        Code and test linking details
  `satisfies`      Cross-cutting templates
  `validation`     Running validation
  `git`            Change detection
  `config`         Configuration reference
  `commands`       This CLI reference
  `health`         Health check details
  `mcp`            MCP server for AI integration
  `all`            All topics concatenated

**Options:**

  `--plain`      Plain text output (no ANSI colors)
  `--no-pager`   Disable paging (print to stdout)

## version

Show version information.

  $ elspais version               # Show current version
  $ elspais --version             # Alternative

## doctor

Diagnose your elspais environment and installation.

  $ elspais doctor                # Quick setup check
  $ elspais doctor -v             # Detailed output
  $ elspais doctor --format json  # JSON output for CI

**What it checks:**

  Configuration file exists, syntax, required fields
  ID pattern placeholders and spec directory paths
  Git worktree detection and canonical root
  Associate paths and configurations
  Local configuration (.elspais.local.toml)

**Options:**

  `--format {text,json}`  Output format (default: text)
  `-v, --verbose`         Show detailed information for each check

## associate

Manage links to associated repositories.

  $ elspais associate /path/to/repo    # Link a specific associate
  $ elspais associate --all            # Auto-discover and link all
  $ elspais associate --list           # Show linked associates
  $ elspais associate --unlink NAME    # Remove a link

**Options:**

  `--all`            Auto-discover and link all associates
  `--list`           Show status of linked associates
  `--unlink NAME`    Retire an associate (matches entry key, namespace, or recorded directory)

**Notes:**

  Links are stored in `.elspais.local.toml` (gitignored, not shared)
  Validates target has a `.elspais.toml` that loads under the standard schema (no `project.type` marker required)
  Accepts a path or a name (searches sibling directories)
  Worktree-safe: resolves relative paths from canonical repo root

## link

Link suggestion tools for connecting tests to requirements.

  $ elspais link                    # Suggest links for unlinked tests
  $ elspais link --file test_auth.py  # Suggest for specific file
  $ elspais link --apply            # Auto-apply suggestions

**Options:**

  `--file PATH`          Suggest for a specific file only
  `--format {text,json}` Output format (default: text)
  `--min-confidence {high,medium,low}`  Minimum confidence threshold
  `--limit N`            Maximum suggestions (default: 50)
  `--apply`              Auto-apply suggested links
  `--dry-run`            Show what would be applied without changes

## glossary

Generate a glossary from the defined terms found in the spec, and write it to
standard output.

  $ elspais glossary                       # The glossary, on stdout
  $ elspais glossary --format json         # JSON instead of markdown
  $ elspais glossary > spec/glossary.md    # Redirect it yourself

This command PRINTS; it writes no file. The generated glossary and index files
under `[terms] output_dir` are written by `elspais fix`. See `elspais docs
terms` for how a term is defined, marked up and indexed.

**Options:**

  `--format {markdown,json}`  Output format (default: markdown)
  `--output-dir DIR`          Accepted, and does nothing here -- the output
  goes to stdout whatever it says

## term-index

Generate the term index and the collection manifests from the defined terms,
and write them to standard output.

  $ elspais term-index                     # The term index, on stdout
  $ elspais term-index --format json       # JSON instead of markdown

Companion to `glossary`: the glossary defines each term, the index says where
every term is used. This command prints too -- `elspais fix` is what writes the
files. See `elspais docs terms`.

**Options:**

  `--format {markdown,json}`  Output format (default: markdown)
  `--output-dir DIR`          Accepted, and does nothing here -- the output
  goes to stdout whatever it says

## comments

Manage the review comments stored alongside the spec.

  $ elspais comments compact               # Strip resolved threads, collapse promotes

Comments live as append-only JSONL under `.elspais/comments/`; compacting
rewrites those files, dropping resolved threads and collapsing promote chains.
See `elspais docs comments`.

## mcp

MCP (Model Context Protocol) server commands.

  $ elspais mcp install                      # This repository, every worktree
  $ elspais mcp install --global --desktop   # Every project
  $ eval "$(elspais mcp env)"                # Supplies the address; needed either way
  $ elspais mcp serve                        # Start MCP server

**Note:** Requires `elspais[mcp]` extra.

**Subcommands:**

  `serve`      Start MCP server
  `install`    Register with Claude Code and/or Claude Desktop
  `uninstall`  Remove registration

**Options for install/uninstall:**

  `--global`   Claude Code: user scope (all projects) instead of current project
  `--desktop`  Also write to Claude Desktop config

**Options for serve:**

  `--transport {stdio,sse,streamable-http}`  Transport type (default: stdio)

## daemon

Manage the background daemon. One daemon per repository serves both the
CLI and MCP agents.

  $ elspais daemon                     # Re-read .elspais.toml, fresh graph
  $ elspais daemon --persist \
      --message "why"                  # Save pending mutations first
  $ elspais daemon --discard-changes   # Throw the pending mutations away

**Options:**

  `--persist`           Save unsaved in-memory mutations before restarting
  `--message TEXT`      Changelog reason for `--persist`, required when the
                        mutations touch Active requirements
  `--discard-changes`   Throw the unsaved in-memory mutations away

A restart refuses to run while the daemon holds unsaved in-memory
mutations unless one of those two flags says what to do with them.
`--persist` and `--discard-changes` are mutually exclusive.

`--discard-changes` destroys the mutations: the daemon drops them and
stops, and nothing reaches disk. Without it a stopping daemon writes
what it holds and records that it did so, because nobody has said the
work is unwanted — an unwanted write costs one `git checkout` to undo,
and there is no comparable way back from a discard. `--discard-changes`
is that statement.

The discard covers the mutations that exist when you ask for it. If
another writer applies one in between, the daemon refuses the whole
request rather than throwing away a change you never saw; re-read what
is pending and decide again.

**Lifetime:** a daemon started this way is an explicit start — it records
no session and lives by `cli_ttl` alone. A daemon that a CLI command
auto-started lives only as long as the session it was started for (see
"Daemon lifetime" below).

## Daemon lifetime

A daemon is started one of two ways, and the two have different
lifetimes.

**Started for a session (implicit).** Any CLI command that needs a graph
and finds no daemon running starts one on behalf of the session it is
running in. That daemon records the session's process ID as
`client_pid` in `.elspais/daemon.json`, and shuts itself down once no
client of its is running any more. This is independent of the idle
timeout: a `cli_ttl` of `-1` disables the timeout but not this, so a
daemon cannot outlive every client that ever used it.

**Clients accumulate.** A daemon is shared — it serves several clients at
once, and it deliberately outlives the session that started it so a later
one can pick it up. Any command that reuses a running daemon registers
itself as one of its clients, and the set is published as `clients` in
`.elspais/daemon.json`. Each entry says what kind of handle it is: a
`pid`, or a `session` count for clients present only as a stream they
hold open — an agent connected over MCP that supplies no process ID is
watched through the connection instead. The daemon keeps serving while
any of them is running, so a session that adopted a daemon does not lose
it when the session that originally started it exits. A client with
neither handle — no resolvable identity (the table below) and no held
stream — cannot register, and therefore does not extend the daemon's
life.

The identity is recorded at the moment of the start and never inferred
afterwards — the daemon is detached from its parent as it starts, so
there is nothing left to infer from. It is resolved in this order:

    ELSPAIS_CLIENT_PID      an explicit declaration by a session or IDE
        |                   (always decisive; an unusable value means
        |                    "no identity", not "keep looking")
        v
    nearest ancestor named 'claude', when CLAUDECODE is set
        |
        v
    the controlling-terminal session leader, if it has a tty
        |                   (an interactive shell qualifies; a batch or
        |                    CI shell has no tty and does not)
        v
    no identity recorded -> idle timeout is the only limit

The last two steps read `/proc` and a POSIX session id, so where those are
unavailable only the environment variable can resolve. A guessed identity
would be worse than none, so when nothing resolves the daemon simply keeps
its `cli_ttl` lifetime.

**Declare it — don't rely on inference.** `ELSPAIS_CLIENT_PID` is not just
the first rung of that ladder, it is the thing to set. A CI job, a build
agent, or any harness that runs several `elspais` commands as part of one
longer-lived job should export the process id of that job's own long-lived
process — the runner, the agent, the `make` process — once at setup:

    export ELSPAIS_CLIENT_PID=$$

Every `elspais` command that job runs afterward then inherits a daemon
whose lifetime matches the job, rather than whichever of the three rungs
below it happens to land on.

**A held session counts too.** An agent connected over streamable HTTP
does not need a process id at all: holding the session's GET stream open
for its lifetime is itself a handle the daemon can observe, so it is
counted as a client for as long as the connection is held. A viewer tab
is counted the same way, through the change stream it holds at
`/api/events`. A completed request is not — request traffic never keeps
a daemon alive on its own, only presence does.

**When nothing binds, you are told once.** If no handle can be derived —
none of the three rungs resolves — or a declared `ELSPAIS_CLIENT_PID`
names a process id that is already dead, the daemon is not refused: the
command still runs, but the first time this happens for a given daemon it
prints a `note:` to stderr saying the daemon's lifetime is not bound to
this client and naming `ELSPAIS_CLIENT_PID` as the variable to set. It
does not repeat for that daemon; the same daemon does not warn you twice.

**Started deliberately (explicit).** `elspais daemon`, a manual
`elspais mcp serve`, and the viewer record no session at all. Their
lifetime is governed solely by `cli_ttl`, and `daemon.json` carries no
`client_pid` key. A viewer started with `--session-lifetime` is not an
explicit start in this sense: it is started on behalf of the browser
sessions it serves, records no process id because a page has none, and
is bound to the tabs holding it through the streams they hold (see
`viewer`).

**Termination.** The check runs on the daemon's own clock, about once a
minute, so a client-bound daemon with nothing pending shuts down at the
first check after its last client is gone rather than the instant it
dies. Client requests do not enter into it: they reset the idle timeout,
not this check.

**The idle timeout waits for the clients.** While a daemon has a recorded
client that still exists, `cli_ttl` is not what ends it: the timeout
expires, finds a client, and starts another idle period. That is what
makes a connected-but-quiet client safe — a session sitting at a prompt,
or an agent between mutations, is not a session that has gone. A daemon
with no recorded client is the one `cli_ttl` governs, which is every
explicitly started one and any implicit one whose clients could not be
identified. The trade is deliberate: a daemon with a live client outlives
the timeout configured for it, and the client-liveness check above is
what still bounds it.

**A stopping daemon is replaced, not reused.** Between deciding to stop
and actually going, a daemon still answers — and refuses everything,
because a write accepted into a shutdown would be acknowledged and then
lost. It says so in `daemon.json` (`"stopping": true`) from the moment it
decides. A command that finds that waits for the process to go and then
starts a fresh daemon; it never starts one alongside, because one working
tree is served by one process. If the outgoing daemon has not gone within
20 seconds, the command builds its own graph locally rather than starting
a second server.

**Unsaved work is saved, not dropped.** If a client-bound daemon still
holds pending mutations when its last client is gone, it writes to
`.elspais/daemon.log` naming how many mutations are pending — the real
number, taken from the whole mutation log — and the deadline. It then
waits a bounded grace period (30 minutes) and, if nothing has changed by
then, **saves the pending mutations to disk** and stops.

Nothing is discarded unless you say so. Spec files are under revision
control, where an unwanted write costs one `git diff` and one
`git checkout` to undo, while work that is destroyed has to be redone
from memory and sometimes cannot be — so saving is what happens when
nobody has said the work is unwanted. `elspais daemon --discard-changes`
is how you say it. If the save itself fails, the
daemon keeps the mutations, reports the failure, and retries rather than
dropping them.

    last client gone, nothing pending -> shut down at next check
    last client gone, work pending    -> log the count, hold for 30 min
      a mutation arrives in that window -> keep serving, restart the 30 min
      a client attaches in that window  -> keep serving
      nothing happens                   -> SAVE to disk, record it, stop

**Every way of stopping saves, unless you asked otherwise.** The grace
deadline above is not the only way a daemon stops, and the others hold
the same work. An idle timeout firing on a daemon with no client left, and an
external stop — `elspais daemon`, a `kill`, a container shutting down —
both persist pending mutations and leave the same record before the
process ends. Being told to stop says nothing about what the daemon
happens to be holding. Being told to discard does:

    idle timeout expires, work pending -> SAVE to disk, record it, stop
    stop signal arrives, work pending  -> SAVE to disk, record it, stop
    told to discard, work pending      -> drop it, write nothing, stop
    stopping with nothing pending      -> stop, and write no record

If the save fails on either of the first two, the mutations are kept.
The idle timeout then declines to stop and waits out another idle period,
because the daemon can still be asked to save; an external stop cannot be
declined, so there the failure is reported and the work is lost with the
process.

**A stop is asked for, waited on, and then enforced.** An external stop
writes what the daemon holds the moment the signal arrives, before the
daemon has finished serving; the wait that follows is for the shutdown to
run its course. A client holding an MCP session open keeps a request
in flight, and a shutdown can wait on that for as long as the client
cares to hold it, so a stop that has not completed after 20 seconds ends
the process outright. The deadline belongs to whoever asked for the stop,
which is why the work is written first: by the time it passes there is
nothing left in the process to lose.

**How you find out.** A save the daemon performed is recorded in
`.elspais/automatic-save.json` and reported to the next client in the
ordinary metadata it already reads: `get_workspace_info`,
`get_graph_status`, `/api/dirty` and `/api/check-freshness` all carry an
`automatic_save` block while one is outstanding. It states who saved
(the daemon), when, how many mutations it covered, and what triggered it.
It says nothing about whether that work is finished or wanted — a client
can disappear because it finished, because it crashed, or because a
connection dropped, and the daemon cannot tell those apart. You decide;
it reports.

The record is retired the moment any client saves at its own request
(`save_mutations` over MCP, Save in the viewer, or
`elspais daemon --persist`). A later automatic save replaces it.
Committing or reverting the files does not clear it — the daemon is not
watching your working tree — so save deliberately, or delete the file, if
you want the notice gone.

**A process that dies holding work says so.** While a server holds
changes it has not written, `.elspais/unsaved-changes` exists; it is
created before the change is acknowledged and removed when the last one
is saved, reverted or discarded. Presence is the entire signal — it
records no counts and no ids, and it is not a recovery mechanism: nothing
anywhere keeps the changes themselves.

If a server starts and finds that file, the process that wrote it is gone
and never wrote what it held — a SIGKILL, a machine that slept, a
supervisor with a shorter patience than the save took. The finding
becomes `.elspais/lost-changes` and is reported as a `lost_changes` block
on the same surfaces the automatic-save record uses, so what you learn is
that something was lost, not what. It is retired the next time a client
saves at its own request. A discard you asked for is not a loss and
leaves nothing behind.

**Applied changes restart the clock.** A mutation applied after the last
client was seen gone counts as proof that a writer is present even when
that writer could not register: the daemon keeps serving and the grace
period starts again. Only applied changes count. Reading — search,
queries, the viewer's count probes — moves nothing and never postpones
termination, so a client that merely polls cannot hold an orphaned daemon
open.

**Writes during shutdown are refused.** Once the daemon has decided to
stop, mutations are rejected with `server_shutting_down` (HTTP 409 with
the same body on the viewer's routes) rather than accepted into a
shutdown that would drop them. A refusal you can see beats an
acknowledgement that turns out to be a lie.

## install / uninstall

Manage local development installations.

  $ elspais install local                # Install from local source
  $ elspais install local --tool uv      # Use uv instead of pipx
  $ elspais uninstall local              # Revert to PyPI version

**Options:**

  `--path PATH`    Source path for local install
  `--extras EXTRAS` Extra dependencies to include
  `--tool {pipx,uv}` Installation tool to use

## completion

Generate and install a shell tab-completion script.

  $ elspais completion install             # Install for the current shell
  $ elspais completion install --shell zsh # Install for a named shell
  $ elspais completion uninstall           # Remove a previously installed script

Supported shells are bash, zsh and tcsh. With no `--shell`, the shell named by
`$SHELL` is used; where that names nothing recognised, the command says so and
asks for `--shell` rather than guessing.

**Options:**

  `--shell {bash,zsh,tcsh}`  The shell to install for (default: the current one)
