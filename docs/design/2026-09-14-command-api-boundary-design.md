# Command API Boundary: parse once, derive once, pass final values

**Date:** 2026-09-14
**Branch:** TOOL-82-cite-reqs
**Status:** Design approved; implementation plan to follow

## The rule

The command line is read **exactly once**. Reading it produces a structure. That
structure is derived **exactly once** into final values. Subcommands receive the
final values and nothing else.

A subcommand is an operation, not a CLI handler. It is invoked identically from
the CLI, from MCP, and over HTTP, and it cannot tell which one called it.

A rule about how a reader *types* a command is a CLI rule and belongs in the
parser. A repeated flag, a comma-separated list, an abbreviation, a scope name
standing for a selection -- the parser resolves all of it. No subcommand ever
asks how a value was spelled.

## Why this is being written

Three reported defects share one cause, and tracing that cause found two
architectural faults above them.

### The defects

1. **`summary.py:357`** -- a project-declared `--scope` selection is refused
   instead of narrowed (REQ-d00280-D). `elspais summary --scope board` with
   `[scopes.board] values = ["id","title","tested"]` prints
   `Error: No value named id, title`.
2. **`trace.py:1189`** (raised at `:222`) -- the same defect. `_resolve_values_or_report`
   computes the correct values, then returns the raw declared keys beside them.
3. **`routes_api.py:1312`** -- `api_run_gaps` lacks the `UnofferedValues` guard
   its sibling routes carry, so `/api/run/gaps?values=id` returns 500 rather
   than 400.

### The cause

`ValueSelection` carries a `written` flag recording whether a **reader** wrote a
selection or a **project** declared it. The two are read differently and nothing
else tells them apart (`values.py:630`).

The wire format cannot carry it. `values_to_params` (`_values.py:123`)
serializes `selection.keys` only; `values_from_params` rebuilds through
`parse_value_selection` (`values.py:682`), which constructs `ValueSelection` without it and takes the dataclass default `written: bool = True`
(`values.py:643`). `written=False` goes in; `written=True` comes out.

That loss is by design. `gaps.py:613` states the contract:

> What travels is the selection AS RESOLVED here, not as it was written: a
> declaration's values are read against what each report offers, and a compute
> path handed the raw declaration would judge it a second time with no way to
> know a project had declared it.

A resolved selection has no provenance question left, so the wire has no slot
for one. `summary` and `trace` send an **unresolved** selection over a wire that
can only carry a resolved one.

The evidence is decisive: wherever `args` passes through directly the behaviour
is correct; the defect appears only where the selection crosses the wire.

| Path | How values arrive | Result |
|---|---|---|
| `summary.render_section` | `_stamp_values(data, args, config)` | correct |
| `trace.render_section` | `resolve_report_values(args, ...)` | correct |
| `summary.run` -> `compute_summary` | `args` -> params string -> `values_from_params` | **broken** |
| `trace.run` -> `compute_trace` | `args` -> params string -> `values_from_params` | **broken** |

### The architectural faults found above it

**The command line is parsed twice, by two libraries, on two branches of
`main()`.** `cli.py:306`:

```python
if len(sections) > 1:
    return report.run(sections, argv[i:])   # raw argv, parsed by argparse
# Single command - Tyro parsing
global_args = tyro.cli(GlobalArgs, args=argv)
```

A composed report (`elspais checks summary trace`) never reaches tyro. It is
parsed by `report.parse_shared_args` (`report.py:63`), a separate
`argparse.ArgumentParser` with its own defaults for the same flags.

**The parse result is typed, then flattened into an untyped bag.**
`_to_namespace` (`cli.py:111`) merges 58 typed `*Args` dataclasses into one
`argparse.Namespace`, "which is the shape every command's `run()` reads its
arguments from". Commands then read it with `getattr`: 31 times in `health.py`,
18 in `fix_cmd.py`, 16 in `trace.py`.

Consequences, each observed:

- **Defaults are declared two and three times.** `SummaryArgs.format = "text"`
  (`args.py:554`) is restated at `summary.py:334` as
  `getattr(args, "format", "text") or "text"`.
- **A misspelled key is silent.** `getattr(args, name, default)` cannot tell
  absent from renamed from typo'd.
- **Non-CLI callers forge CLI artifacts.** `compute_checks` -- an API function
  called by an HTTP route -- builds `fake_args = argparse.Namespace()`
  (`health.py:4733`) because the helpers it needs can only read a CLI bag.
- **It is what made `args_or_params: Any` thinkable.** A function branching on
  `isinstance(x, dict)` to decide how to read its own argument is only possible
  because both shapes are anonymous.

**CLI spelling rules reach the command layer.** `_scope.flag_values`
(`_scope.py:37`) is, by its own docstring, "the ONE place a repeated flag is
gathered back into the one list it names" -- a statement about typing at a
terminal. It is called from 11 sites across `health.py`, `gaps.py`,
`_targets.py` and `_scope.py`. The leak is visible in the type:
`severity: Annotated[list[list[str]], tyro.conf.UseAppendAction]`
(`args.py:109`). The outer list is not data; it records which occurrence a value
came from.

## Design

### Two structures, and why that is forced

Expanding a `--scope` name requires config. The argv parser does not have
config. So the edge performs two steps, and only the second crosses into a
subcommand:

```
CLI   argv      --tyro-->  SummaryArgs   --derive(config)-->  |
HTTP  query     ----------------------- derive(config)----->  +--> SummaryRequest --> compute_summary
MCP   tool args ----------------------- derive(config)----->  |      (final values only)
```

- **`*Args`** is a typed transcript of what was typed: `list[list[str]]` for
  repeated flags, `values: str | None` holding raw comma text, `scope: str | None`
  holding a name. It is an internal detail of the CLI edge.
- **`*Request`** holds final values: flattened tuples, a resolved
  `tuple[str, ...]` of value keys, an expanded `ReportScope`.

No subcommand sees a `*Args`. Neither MCP nor HTTP ever touches a CLI type.

### How many request types, and why not one per subcommand

Field counts across the 58 `*Args` classes:

| Fields | Classes |
|---|---|
| >=10 | 9 (`Checks` 18, `Trace` 16, `Analysis` 12, `Summary` 11, five gap variants 10 each) |
| 3-7 | 23 |
| <=2 | 26 (17 have exactly one field; 3 have none) |

The skew is not noise. The nine heaviest are the report commands, and the report
commands are exactly the ones reachable from more than one surface. Field count
is the symptom; **the number of surfaces that construct the input is the
discriminator.**

- **Multi-surface** -> the input needs a name: three callers must independently
  build the same thing, defaults must live in one place, and validation needs
  somewhere to hang.
- **CLI-only** -> `def run(*, verbose: bool = False)` already satisfies the rule.
  A second single-field wrapper around `VersionArgs` adds nothing.

**Decision: one request type per `compute_*`, not per subcommand. Six total** --
`ChecksRequest`, `TraceRequest`, `AnalysisRequest`, `SummaryRequest`,
`GapsRequest`, `SearchRequest` -- composed from shared mixins the way
`SummaryArgs(ScopeOptions)` already is, so `ScopeOptions`' six fields are
declared once.

`gaps`, `uncovered`, `untested`, `unvalidated` and `failing` are five
subcommands with identical shapes routing to one `compute_gaps`. They are five
CLI spellings of one API operation and share one request type. Counting per
subcommand would have produced five copies of one thing.

The other ~50 subcommands take explicit keyword parameters.

### Resolution needs no new machinery

`resolve_values` already does double duty:

- on a **declared** selection (`written=False`) it **derives** -- passing over
  what this report does not offer;
- on an **already-resolved** list (`written=True`) it **validates** -- every key
  is offered so nothing raises, and the identity-key insertion is idempotent
  (`values.py:723` inserts only `if identity_key not in chosen`).

So this design changes *where* it is called, never what it does:

| Edge | Builds the request | `written` |
|---|---|---|
| CLI | `values_from_args` -> `resolve_values` | consumed here; never travels |
| HTTP | `values_from_params` -> `resolve_values` | `True`; `UnofferedValues` -> 400 |
| MCP | direct construction | never exists |

`compute_*` resolves nothing. `params: dict[str, str]` survives only as the HTTP
query a route reads *before* building a request; it stops being an input to the
command layer.

### One shared HTTP translator

All six routes build their request through one helper owning the
`UnofferedValues -> 400` mapping. Defect 3 then becomes unrepresentable rather
than fixed: `api_run_gaps` cannot forget a guard it no longer writes.

### `values` distinguishes unset from default

`_stamp_values` (`summary.py:246`) stamps the payload only when a selection was
named; an unstamped payload *is* the default report. The request therefore
carries `values: tuple[str, ...] | None`, where `None` means "nothing named".
Collapsing that would make a daemon-served default report disagree with a
locally computed one.

## Scope

### A. Resolve declared names at the edge

The only true second parse: `resolve_scope_for_report` and
`resolve_report_values` consult **config** inside a compute path to expand a
`--scope` name. Every other param (`treat_active`, `top`, `q`, `weights`) is
derived once at the edge and merely read at compute -- that is the wire doing
its job.

Touches `summary`, `trace`, `gaps`, `analysis`, and the same defect's third
instance at `report.py:185-190` (resolve for the exception, discard the result,
hand `args` down). Fixes defects 1-3.

### B. Final values only, CLI-wide

1. **One parse.** The composed-report branch (`cli.py:306`) goes through tyro.
   `report.parse_shared_args` is deleted. Requires deciding how a composed
   report is expressed to tyro (see Open question).
2. **The parser emits final values.** `list[list[str]]` never leaves the parser;
   repeated and space-separated flags are flattened at the edge. Comma-separated
   text is split there. `_scope.flag_values` moves to the CLI edge or disappears;
   it is not callable from a command.
3. **`_to_namespace` is deleted.** Subcommands take a `*Request` (the six) or
   explicit keyword parameters (the rest).
4. **`fake_args` constructions go.** `_status_flags` (`health.py:2723`) reads
   only `treat_active`; `_resolve_exclude_status` reads only config plus that.
   Both become plain functions over `tuple[str, ...]`.
5. **The four `render_section` functions** take final values instead of a
   Namespace.

## Deleted by this work

- `cli.py:_to_namespace`
- `report.py:parse_shared_args` and the second argparse parser
- `_values.py:resolve_report_values(args_or_params, ...)` dual shape
- `_scope.py:resolve_scope_for_report(graph, args_or_params, ...)` dual shape
- `summary.py:_resolve_values_for` / `_stamp_values` dual shapes
- `health.py` `fake_args` construction
- `_scope.flag_values` as a command-layer helper
- `list[list[str]]` as a field type

## Testing

**Red first.** Extend `test_report_values.py`'s `_run_listing` (`:1767`), which
today reaches only `analysis` and `gaps`, to cover `summary` and `trace`. The
declared-scope fixture at `:1707` already exists. Both defects must fail before
anything moves. This is the gap that let the defects ship: one test file
declares a scope carrying values, and it exercises one command family.

**Per-surface parity.** For each of the six operations, the same request built
from CLI, from HTTP params and directly must produce identical output
(REQ-d00282-E, REQ-d00279-C).

**Spelling invariance.** `--level a --level b`, `--level "a b"` and the mixed
form produce one identical request (REQ-d00278-C). Asserted at the parser, not
at a command.

**Silent-read regression.** After `_to_namespace` is gone, a renamed field is an
`AttributeError`, not a default. Expect latent bugs to surface; that is the
point.

Tiers: unit for the parser and request construction; `-m e2e` for CLI parity;
existing stress battery unaffected.

## Sequencing

1. Failing tests for defects 1-3 (`summary`, `trace` under a declared scope).
2. **A**: request types for the four report axes; edges resolve; `compute_*`
   stops resolving; shared HTTP translator; dual shapes deleted. Defects fixed.
3. **B1**: parser emits final values; `flag_values` moves; `list[list[str]]` retired.
4. **B2**: one parse -- composed reports through tyro; `parse_shared_args` deleted.
5. **B3**: `_to_namespace` deleted; remaining subcommands take explicit
   parameters; `fake_args` and `render_section` Namespaces go.

Each step is one commit per the repo's commit discipline. Steps 2-5 are
independently shippable; 1 gates 2.

## Out of scope

- **Routing MCP report tools through `compute_*`.** This design makes them
  *callable* from MCP, which is what the principle requires. Whether
  `get_project_summary` and friends switch to calling them is a separate
  decision with an agent-facing payload cost, and REQ-d00258-C is already
  satisfied by both paths reading `graph/aggregation.py`.
- Backwards compatibility. Per CLAUDE.md it is not a goal; an input no longer
  admitted is refused with a message naming what to change.

## Open question

`report.run()` receives `argv_remaining`, not a typed object, and there is no
`ReportArgs` class. Making composed reports go through tyro requires choosing
one of:

- a `ReportArgs` carrying the shared flags, with sections as a field;
- the CLI edge building N `*Request` objects and handing them all down.

Resolve before step B2. It does not block A or B1.

## Decisions recorded, including reversals

1. **Explicit keyword parameters, not a request object** -- approved when scope
   was four commands sharing two axes.
2. **Reversed to "one request dataclass per subcommand"** when B entered scope.
   **Wrong**: 58 types, 26 of them wrapping <=2 fields.
3. **Settled: one request type per `compute_*` (six), explicit parameters
   elsewhere.** Decision 1 holds for ~50 subcommands; decision 2 was too broad.
4. **One shared HTTP translator** for all six routes -- approved, unchanged.
