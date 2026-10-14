# Coverage Record and Reports: Design

## Goal

After every finished run, elspais holds and publishes the complete current
line coverage of each test target and of the whole repository. A consumer
such as Codecov or a pull-request coverage table reads a file elspais wrote.
No repository maintains its own merge of fresh and retained coverage.

One module owns line coverage: reading a tool's coverage file, merging,
judging whether a measurement still describes the tree, and writing the
record and the reports.

## Problems this design removes

- Reading a coverage file is implemented twice, in the graph build and in
  retention. Both detect the format, place source paths and place test
  contexts, and the two copies already differ.
- Coverage is merged twice: retention merges the last run into the retained
  file, and every build merges fresh and retained coverage again.
- No file holds the complete coverage of a partial run. The tool's own file
  holds what executed, and `.elspais-retained-coverage.json` holds what was
  retained.
- The retained file is a reduced coverage.py JSON form with an elspais key.
  It reduces lcov hit counts to hit or not hit.
- The format of a coverage file is chosen by its name, and no setting names
  it.

## Files

| File | Location | Written by | Holds | Read by |
| --- | --- | --- | --- | --- |
| The tool's coverage file | the target's output area, at its `coverage` path | the test tool | what this run measured | the coverage module, once, when the run finishes |
| `.elspais-coverage.json` | the target's output area | elspais, when a run finishes | the target's complete coverage record | the graph build, the next run's retention, the combined report |
| `.elspais-coverage.info` | the target's output area | elspais, when a run finishes | the target's current coverage, in lcov | consumers only |
| `.elspais-coverage.info` | the output root | elspais, when any run finishes | the repository's current coverage, in lcov | consumers only |

`.elspais-retained-coverage.json` is removed.

The record is primary data, not a cache. Its retained entries were measured
by runs whose output areas no longer exist, so nothing can rebuild them.

## The coverage record

The record holds, for each measured source file, with its path relative to
the repository root:

- the hit count of each line;
- the executable lines;
- the per-test contexts, where the tool recorded them;
- the content digest of the file when it was measured;
- the runs that measured it.

The record stores the digest itself. A measured file outside the target's
inputs therefore keeps its digest, which a look-up in the target's input
manifest does not give.

## The current-tree rule

A measurement counts only while its source file holds the content it held
when it was measured: the file's digest now equals the recorded digest.
Retention, the graph build and both reports apply this one rule, through the
coverage module.

## Configuration

A target that declares `coverage` declares `coverage_format`: `lcov`,
`coverage-json` or `coverage-sqlite`. A configuration that declares
`coverage` without it is refused, naming the key. Format detection by file
name is removed.

## When a run finishes

`finish_run()` in `utilities/fingerprint.py` is the one point where every
finished run passes, whether elspais's runner started it or
`elspais fingerprint finish` ended it. For a target that declares
`coverage`, it:

1. Builds the new record.
   - It reads the tool's coverage file once, through the coverage module,
     and stamps each measured file with its digest now and with this run.
   - A stale-only run that retained test files also takes the previous
     record's entries whose digest still matches. `plan_run()` reads the
     previous record before `start_run()` empties the output area, and
     carries it to the finish.
   - A run that executes every test starts from no previous record.
   - A run that started no command consists of the previous record's
     matching entries alone.
2. Writes `.elspais-coverage.json` and the target's `.elspais-coverage.info`.
   Each file is written to a temporary name and renamed into place.
3. Rewrites the combined report. It reads every target's record in the
   federation member, applies the current-tree rule, merges them by the
   larger hit count of each line, and writes the output root's
   `.elspais-coverage.info`. A file lock serializes this step, because
   concurrent targets can finish together.

Failures:

- A tool coverage file that cannot be read fails the run. The fault is
  recorded in the fingerprint, and no record is written, so the area never
  holds a record of another run.
- A combined report that cannot be written produces a warning naming the
  cause. The run's outcome is unchanged, because the combined report holds
  no primary data.

## Readers of the record

- **The graph build** reads each target's record and nothing else from the
  area. It parses no tool coverage file and merges nothing. It applies the
  current-tree rule. A file reads as fresh where the target is fresh and the
  run its fingerprint records measured the file. Otherwise it reads as
  carried, and its stale reason names the runs that measured it.
- **Retention** reads the previous record through the coverage module.
- **The served-graph watch** watches each target's record in place of the
  tool's coverage file. The record is written last, so a graph rebuilds once
  per finished run. The reports are not watched.
- **Baseline packs** carry the output area whole, record included. Paths are
  repo-relative, so an adopted area reads correctly at another checkout.
- **The Evidence Snapshot** is unchanged: it carries no coverage.

Each federation member reads and writes its own records and its own
combined report.

## Areas written by an older elspais

A finished output area that holds a tool coverage file and no record is an
ingestion fault naming the target and the remedy: run the target again. No
older file is read.

## Specification

Each obligation goes through the `requirement-structure` skill and Jev
before any text is written:

1. After every finished run of a target that declares coverage, its output
   area holds the target's complete current line coverage in a standard
   format.
2. The output root holds the combined current line coverage of every
   target.
3. A measurement counts only while its source file holds the content that
   was measured.
4. A target names the format of its coverage file.

The likely requirements to amend are REQ-d00333-J+L, REQ-d00254, REQ-d00323-I+J
and REQ-d00313-B. Assertions that describe the retained coverage file are
retired.

## Tests

A subagent writes the tests.

- The coverage module: each format read; the current-tree rule; merges that
  keep hit counts; lcov rendering; the combined report when two targets
  finish together; the refusal of an older area; the refusal of a target
  without `coverage_format`.
- Retention across a chain of runs: a full run, a partial run, and a run that
  starts no command each leave a complete report.
- e2e: `elspais fingerprint finish` writes the record and both reports;
  `elspais checks --run-tests --stale-only` leaves a complete combined
  report.

## Rollout

1. An elspais pull request with the `publish` label. elspais's own
   `.elspais.toml` declares `coverage_format` for each target that declares
   coverage.
2. hht_diary, in one commit: the elspais pin moves to the release; each
   coverage target declares `coverage_format`; Codecov and the coverage table
   read the combined report or each target's report.
3. Each sponsor repository makes the same change when it moves its pin.

## Out of scope

- Other report formats, such as Cobertura, and an export command.
- A report spanning federation members.
- Branch and function coverage.
