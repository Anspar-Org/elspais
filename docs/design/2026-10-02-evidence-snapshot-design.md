# Evidence Snapshot -- Design

## Purpose

A project commits the results of its test suites with each change, and CI
confirms that those results describe that change. elspais writes these
results as an *Evidence Snapshot*, reads it back, verifies it against a new
run, and renders the traceability report from it. A consumer that pins a
commit can cite that commit's report as evidence without running the suites.
In a federation, a member's *Evidence Snapshot* supplies that member's
results, so a consumer's report credits a pinned library's tests.

The first consumer is event_sourcing. Its suites run a scenario declared once
against several backends, run in parallel CI jobs, and depend on Postgres and
a browser.

## Defined Term

**Evidence Snapshot**: the normalized results of one test run of one tree,
bound to that tree by its digest, and stored in the repository with the
traceability report derived from it.

## Requirements the design serves

- A re-run on the same tree with the same outcomes produces an identical
  *Evidence Snapshot*, byte for byte.
- The *Evidence Snapshot* names the tree it describes. A reader of a
  snapshot that describes another tree is told so.
- A new run can be verified against a committed *Evidence Snapshot*, test by
  test. This is the primary use.
- The report credits an assertion as passing only where elspais's Passing
  dimension credits it.
- A skipped test is recorded as skipped.
- Measurements are kept, and are never part of what a verification compares.
- The report can be rendered from the *Evidence Snapshot* and the spec alone.
- A federation member's *Evidence Snapshot* supplies that member's results
  where the member has no results of its own.
- A run executes a federation member's test targets only where it names them.

## How it relates to the target output areas

| | `.results/<target>/` | *Evidence Snapshot* (`test-evidence/`) |
| --- | --- | --- |
| Holds | The raw output of one target's last run, its coverage, and its *Result Fingerprint* | The normalized results of every selected target, and the report |
| Lifetime | Local; ignored by git; emptied when a run starts | Committed with the change it describes |
| Valid while | Its *Result Fingerprint* matches the current inputs | Its tree digest matches the current tree |
| Role | The input to `evidence write` and `evidence verify` | Their output, and the reference a verification compares against |

A target with results of its own in its output area reads those. A target
with none reads the *Evidence Snapshot*'s results for it, tagged carried.

## The snapshot's files

The project names the directory in its configuration (`[scanning.test]
evidence = "test-evidence"`).

### `results.jsonl` -- compared

One line for each result that elspais ingested from the selected targets.
Each line is a JSON object with sorted keys:

| Key | Value |
| --- | --- |
| `target` | The test target that produced the result |
| `file` | The repo-relative file where the test is declared |
| `line` | The line where the test is declared, where the reporter gives one |
| `name` | The test name as the reporter gives it |
| `runner` | The repo-relative file that executed the test, where it differs from `file` |
| `outcome` | `passed`, `failed` or `skipped` |
| `skip_reason` | The reason a skipped test gives, where it gives one |

The lines are sorted by `target`, `file`, `line`, `name`, `runner` and
`outcome`. Identical lines are kept, because two runs of one test that agree
are still two runs. The file excludes durations, timestamps, invocation ids,
absolute paths, failure messages and printed output. Each of these varies
between runs of an unchanged tree.

### `snapshot.json` -- compared

| Key | Value |
| --- | --- |
| `tree` | The digest of the tree the results describe |
| `targets` | A list of `{target, digest}` objects: each selected target and the digest of its *Result Fingerprint*'s inputs |
| `facts` | The facts the project declares about the run, as `name: value` pairs |
| `elspais` | The elspais version that wrote the snapshot |

No name is ever a JSON key beside a digest. A secret scanner that looks for
a secret-like key beside a long hex value then finds nothing, whatever a
target is called. The *Result Fingerprint* follows the same rule.

The tree digest is a SHA-256 over the sorted list of `(path, content
digest)` for every file that git tracks or has staged, excluding the
snapshot directory. The same computation runs in a working tree before a
commit and in CI on a checkout of that commit. A snapshot written over
uncommitted changes therefore does not match in CI.

The project supplies facts on the command line (`--fact
backends=vm,postgres,chrome --fact flutter=3.44.7`). elspais does not infer
them, because it cannot know which toolchain a target's command used.

### `timings.jsonl` -- not compared

One line for each result, with the same identifying keys as `results.jsonl`,
plus the duration and the output the test printed. The throughput guard and
the pause-bound tests report their measurements by printing them. Reporters
that carry printed output pass it through; `flutter-machine` gains this.

### `TRACEABILITY.md` -- compared

The output of `elspais trace --format markdown`, rendered from the snapshot
and the spec only. For each requirement and assertion, the report names the
code that implements it, the tests that verify it, and each test's outcome
in the snapshot's run.

Two properties of `trace` today stop this file from being byte-stable or
complete, and the elspais change fixes both:

- `test:` and `code:` identifiers carry an absolute path, so the report would
  differ on every machine. The report names a test or a code location by its
  repo-relative file and line.
- The markdown matrix gives per-requirement counts. Its verbose form lists
  each assertion's tests without their outcomes, and lists no implementing
  code. The report lists both for each assertion, with each test's outcome.

## Commands

### `elspais evidence write [--targets ...] [--fact NAME=VALUE ...]`

1. Resolves the selection through the one selection authority (`--targets`
   reads as in `checks --run-tests`).
2. Refuses, naming the target, if any selected target's results are absent,
   stale or still running. A snapshot must describe a finished run of the
   tree.
3. Builds the graph from the targets' own results.
4. Writes `results.jsonl`, `snapshot.json` and `timings.jsonl` from the
   RESULT nodes. Because it reads results through the graph, each result's
   binding and outcome are elspais's own.
5. Builds the graph again with the snapshot as the only source of results,
   and writes `TRACEABILITY.md` from it.

Exit 0 when written, 2 when refused.

### `elspais evidence verify [--run] [--targets ...] [--fact NAME=VALUE ...]`

The primary check. It derives a snapshot in memory from the current results,
exactly as `write` would, and compares it with the committed snapshot. With
`--run`, it first executes the selected targets as `elspais test` does.

It reports, by test:

- each test whose outcome differs between the two;
- each result present on one side only;
- a tree digest that does not match the current tree;
- a declared fact that differs;
- a `TRACEABILITY.md` that differs from the report the snapshot renders.

Exit 0 when the two agree, 1 when they differ, 2 when refused. CI runs
`elspais evidence verify --run --fact ...` with the facts the snapshot
claims, so CI covers every backend the snapshot names.

### Reading the snapshot back

A target with no results of its own takes the snapshot's results for it.
These results are tagged carried, as a selective run already tags results it
did not produce. `trace`, `summary` and `checks` then work from a checkout
that has run nothing.

Where the snapshot's tree digest does not match the current tree, the
snapshot describes another tree. The results are still read, and
`tests.results_stale` reports the snapshot as stale, naming the snapshot
directory. A matching digest reads as fresh.

## Federation

- Each member is built with its own configuration and repository root, as
  today. A member's snapshot is read only from a linked member: an associate
  declared by namespace alone, with no path, is refused before any check
  runs, so no snapshot is read for it. A member that declares an *Evidence Snapshot* and has no results of
  its own reads its snapshot. A consumer that integrates the member then
  inherits coverage from the member's recorded run.
- The member's snapshot is judged against the member's own tree.
- `elspais test`, `checks --run-tests` and `evidence verify --run` execute a
  member's target only where the selection names it as `NAMESPACE:NAME`. The
  target runs with the member's repository root as its bound, and writes
  into the member's own output area. A bare run, and the `default` group,
  never reach a member. Running a member's targets executes commands that
  the member's configuration declares, so the reader names them explicitly.
- `evidence verify --targets NAMESPACE:NAME` verifies a member's snapshot
  against a new run of the member's targets.

## The consumer's workflow

```text
developer:  make evidence    # run every target, then elspais evidence write
            git add test-evidence && git commit

CI:         jobs run the targets in parallel; the gate job collects their results
            elspais evidence verify --fact ...   # the facts the snapshot claims
```

## Out of scope

- Signing the snapshot.
- Comparing `timings.jsonl`.
- Choosing which targets a project records. The project selects them.

## Sequencing

1. elspais: requirements first, then `evidence write`, `evidence verify`, the
   snapshot reader, the federation member runs, the report changes, and
   `flutter-machine` print events. One PR, stacked on TOOL-125.
2. event_sourcing: move to elspais 0.125.37 (target names without `/`,
   results written into `$ELSPAIS_TARGET_OUTPUT`). This needs no new elspais
   feature.
3. event_sourcing, after the elspais release: `make evidence`, the CI gate
   job, the strict gate, and the consumer documentation.
