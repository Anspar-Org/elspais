# Plan: one findings system, then the parsing directions

Source: `needed.md` (Callisto UAT dry-run findings against 0.121.233).
Method: four read-only surveys (finding machinery, spec ownership, parsing/scanning
internals, config severity + doc surfaces). Nothing has been edited.

---

## What the surveys changed about the framing

Four items in `needed.md` are **not** what they look like. Each correction moves work
from "build something" to "make an existing thing reachable", which is cheaper and
lower-risk:

- **#2 (scope disclosure)** is a *stream split*, not a dropped argument.
  `_print_scope` writes to stderr on purpose (`trace.py:1083-1087`); `cli.py:384-386`
  redirects only stdout into `-o`. The renderer never had the lines to lose.
  Worse instance found next door: `analysis_cmd.py:53` resolves a scope, filters by it,
  and never calls `scope_disclosure` at all — a scoped foundations report discloses
  nothing on any surface. `summary.py:879-889` omits it from csv only.
- **#5 (identifier absorbs prose)** — nothing absorbs anything. The right diagnosis
  (`E_IDENTIFIER_WITH_TRAILING_TEXT`) already exists and already fires; a whitespace
  early-return at `patterns.py:1390` short-circuits ahead of it and downgrades every
  spaced case to `E_NOT_AN_IDENTIFIER`. Verified: `REQ-x-A(gloss)` diagnoses correctly,
  `REQ-x-A (gloss)` does not.
- **#6 (comma list)** — the bare `I` is classified `UNKNOWN_NAMESPACE`, default severity
  **info**, not `malformed`. And `broken.py` discards `fault_class` and `codes` in all
  four output paths, which is precisely why the listing's origins are opaque. The
  vocabulary is already rich enough; the renderer throws it away.
- **#9 (`unmatched_results` names nothing)** — the check already computes each unmatched
  result's identity, file and line (`health.py:3811-3862`, landed in the HEAD commit).
  The names are in hand and dropped at render.

That last one generalises into the single worst defect found, which `needed.md` does not
name: **`HealthFinding`s never render in `text` or `markdown` at any verbosity**, while
the hint printed at `health.py:4402` says *"Run 'elspais -v checks' for details"*.
`-v` threads through to exactly one place: shortening that hint. Findings reach json and
sarif only. Every "the report gives a count and no names" complaint is one instance of it.

---

## Workstream A — make finding reporting a regular system

### A0. The spec already governs this, and the code does not

- **REQ-d00271** *Diagnostic Code Vocabulary* — A: "Every finding SHALL carry a code
  naming its defect, and the codes SHALL be documented with an example of input that
  produces each." B: may carry more than one. C: a code meaning "undetermined", which is
  not the absence of a diagnosis. D: issue a code only where the input determines it.
  E: adding a code changes no category and no configured severity.
- **REQ-d00212-P** — "The configuration schema SHALL make the severity of every health
  check configurable under a single consistent convention." Its rationale deliberately
  leaves the mechanism open and calls today's shape *"conformance-defect territory for
  later implementation tickets."*
- **REQ-p00019** (Satisfies catalog) — G: a failure report identifies operation, cause and
  remedy (or says none is known). H: suppression only with recorded justification.
  J/K: a description true of every finding it covers; reported once, so a count of
  findings is a count of distinct facts.

**Exactly one family conforms** — the reference-fault family (`graph/reference_faults.py`),
which is therefore the model to generalise rather than replace.

### A1. What the survey found instead

Measured across the estate: a dozen finding dataclasses sharing no serializer; several
severity models; several identity conventions; several exit-code policies. The
load-bearing specifics:

- **Severity is a bare `str` with no validator.** A typo'd value matches none of
  `"ok"`/`"error"`/`"warning"`, so the check counts as neither failed nor warned,
  `is_healthy` stays true, and the run exits 0. SARIF is the only surface that maps it.
- **Sentinels are family-local.** `"ok"` means pass — for reference checks only.
  `"off"` means skip — for term checks only. Coverage, format and doctor honour neither.
- **Two config keys answer one user question.** `rules.coverage.<dim>.<tier>` drives the
  viewer badge (`html/generator.py:159`); the health coverage check hardcodes
  `"error" if has_any_failures else "info"` and never reads it. Setting it changes the
  badge and not the check.
- **No check registry exists.** Names are string literals at nearly every construction site in health.py,
  assembled by six sibling functions. `docs/cli/checks.md` is a hand-maintained mirror of
  a list that exists nowhere in code, and nothing tests that they agree.
- **Remedy is a render-time side table** (`_FOLLOWUP_COMMANDS`), text-output only, covering
  most but not all names, missing every dynamically-composed name, and currently carrying a
  stale hint pointing at `elspais health --untested` (renamed to `checks`).
- **Words carry two conditions each.** `unlinked` names two *disjoint populations* (CLI:
  FILE nodes with no traceability children; MCP: CODE/TEST nodes with no requirement edge).
  Also colliding: `orphan`, `stale`, `error`, `warning`, `violation`, `finding`, `retired`.
- **Silent discards.** Malformed result artifacts, unknown reporters, unreadable files,
  and cwd-escaping targets are swallowed at debug level or by bare `except: pass` —
  indistinguishable from "never ran".

### A2. Spec work (small — most is already owned)

Add beside the existing owners, in the house form *"at a severity the project configures,
and SHALL be `<default>` where the project configures nothing"*:

| Obligation | Owner to extend | Note |
|---|---|---|
| A finding carries the location of what it is about, where one exists | REQ-d00271 | today stated per-check (d00274-D, d00276-D, d00268-A); no general form |
| A finding carries its remedy, or states none is known | REQ-d00271 (concretizing p00019-G) | moves remedy off the render-time side table |
| A finding is reported identically whatever format the report is rendered in | REQ-d00271 | mirrors the REQ-p00084-C property that already exists for scope |
| One severity vocabulary, with every admitted value named and an unadmitted value refused | REQ-d00212-P | closes the silent-typo hole |
| One authority decides a finding's severity from its category | REQ-d00212-P | closes badge-vs-check divergence |
| Each distinct condition is reported under a distinct name | REQ-p00019-J/K (concretize) | governs `unlinked`/`orphan`/`stale` collisions |

Deliberately **not** specified: the class hierarchy, the encoder, the migration order.
Those are code.

### A3. Implementation (delegable, ordered by risk)

1. **Validated severity type + one resolution authority.** Literal-typed values, defined
   sentinels for every family, one category→severity lookup. Fixes the typo hole.
2. **`checks` becomes the one findings surface.** Render findings in text and markdown
   under `-v` — which is what its own hint has been promising all along — and add filters
   over the shared finding fields: `--severity`, `--category`, `--code`, `--path`, beside
   the scope filters it already has (`--spec`, `--code`, `--tests`, `--terms`). Smallest
   change with the largest truthfulness gain: it retires items 6, 9 and most of "the
   report gives a count and no names". Every per-class listing that exists today exists
   because this renderer does not render.
3. **Generalise the reference-fault model** (category + open codes + location + remedy)
   into a shared finding, and give it one encoder feeding text/markdown/json/junit/sarif/
   MCP/HTTP.
4. **Migrate producers in bounded batches**, one batch per subagent: format violations →
   terms → coverage → doctor/config → assembly → ingestion/stderr sites.
5. **Turn the silent discards into findings** — this is where the invisible conditions get
   names at all.
6. **Resolve the colliding words**, one condition per word, with `unlinked` first.
7. **Re-implement the per-class commands as shortcuts.** `unresolved`, `errors` and
   `unlinked` keep their names and their place in the docs and in `_FOLLOWUP_COMMANDS`,
   but each becomes a preset filter over the one stream — never its own renderer. This is
   what stops the class-and-codes loss recurring: `broken.py` drops `fault_class` and
   `codes` in all four of its output paths today precisely because it is an independent
   second renderer. Same rule for MCP and the viewer, which closes the three-way
   `get_broken_references` split.

### A4. The boundary: findings are not work lists

Two different questions, and folding them together would be a category error:

- **Findings** — something is *wrong* with the content or the configuration.
  `unresolved`, `errors`, `unlinked`, and everything reachable only as a check today.
- **Work lists** — nothing is wrong; this is not done yet. `gaps`, `uncovered`,
  `untested`, `unvalidated`, `failing`. CLAUDE.md already binds these to the immediate
  direct measure (REQ-d00258-M).

`gaps` is not a finding and does not appear in a findings report. The work-list commands
keep their current shape and are out of scope for the A3 migration.

---

## Workstream B — specs for the new parsing directions

Written as invariants, not mechanism. The user's standard applies: *"SHALL support comments
appropriate to the file type" is sufficient; the exact parsing details are code, not spec.*

### B1. Identifier termination and what may follow a reference — **owner exists**

REQ-d00272-E already requires: *"An item that opens with an acceptable reference and
continues into content no grammar accounts for SHALL be reported naming both the reference
found and the content unaccounted for."* -L ranks trailing content beneath every named
relaxation. -B bars an item containing a space from being read as an identifier.

New ground is only the **comment-after-reference** rule. The user's direction, verbatim:

> New: If the there is an ID followed by whitespace, and the next thing is a
> a comment pattern associated with the file type, then treat it as a valid comment for that line.
>
> New: If the there is an ID followed by whitespace, and the next thing is NOT a comma and NOT ID and
```text
NOT the configured comment pattern, then treat it as a `malformed comment` finding with configurable severity.
```

Proposed as one or two assertions on REQ-d00272: content following a reference that opens a
comment in that file's language terminates the reference and is not read; content following
a reference that opens nothing the file's language admits is reported at a configured
severity. Note this is a *narrowing* of B — B currently forbids the whole item, and the new
rule lets a well-formed prefix bind. That interaction must be stated, not left implied.

### B2. Comment patterns per file type — **unowned for citations**

The user's direction, verbatim:

```text
New: Each scannable file type declares an associated comment pattern:
  C-like: //
  shell-like: #
  function-like: --
  lisp-like: ;
  math-like: %
  basic-like: '

A file-type is associated with only a single comment pattern.
The file-type declarations use this enumerated set by name. The specific set and names
must appear in the help docs, and should only be defined in one place (DRY).

To simplify parsing, the C-like block comment /* */ is not supported.
```

Terrain: the accepted marker set is spelled independently in several places
(`lark/__init__.py:90`, `transformers/reference.py:61`, `:780`, `:824`, `prescan.py:230`) with a wider set for forward-look eligibility,
and a differently-shaped set exists for *term* scanning under REQ-d00236
(`term_scanner.py:28-86`). `config_helpers.is_empty_comment` takes the set as a parameter
and has no callers — dead code. `FileType` (SPEC/JOURNEY/CODE/TEST/RESULT) is a domain role,
not a language, so it cannot host this.

**Spec trap to avoid:** REQ-d00082-F is a *removed* assertion reading "[Removed — named
per-file reference overrides that do not exist. One set of acceptance rules applies in every
context that accepts a reference, per REQ-p00014-T.]" A per-file-type comment mapping must
state that comment syntax is a property of the language while the identifier grammar stays
one set of rules everywhere — or it will read as reversing F.

Proposed: extend REQ-d00236 with the named enumeration (one authority, exposed in help docs)
and add a citation-side assertion beside REQ-d00269-E binding a file type to exactly one
pattern. Block comments stay unsupported, and REQ-d00082-H already records that as a known
limitation rather than a defect.

### B3. Which files are looked at, and reporting the ones that are not — **half owned**

REQ-d00212-Q already requires *"exactly one configuration surface determines whether any
given file is scanned"*, and its rationale already calls the current state a conformance
defect. The survey confirms it is worse than `needed.md` says: `[scanning.code].file_patterns`
is neither additive nor a filter but an **independent third mechanism** (globbed from the
repo root, defaulting to empty, with the default pattern walk running unconditionally
afterwards). `should_ignore` is never called for test scanning at all, and never for the
root-glob step, so `[scanning.test].skip_files` is inert.

The user's direction, verbatim:

```text
The proper behavior for both is:
within the directories declared {
   scan the files which are not in the 'ignore' list
   if the file name matches the pattern given {
     include its citations normally
   }
   Otherwise {
     if the file contains citation keywords like implements:, verifies:, etc {
       then report it with a configuratble severity (info/warn/error)
     }
   }
}
```

**Unowned and needed:** a file inside a scanned directory, not ignored, that carries a
citation keyword but matches no pattern SHALL be reported at a configured severity; an
ignored file SHALL be passed over silently. Design precedent to follow rather than invent:
`references.undeclared` (REQ-d00272-O) already says "a relationship appears to be intended
and is not declared" for a keyword-less identifier in a scanned file. This is the same
statement one level out.

Dockerfiles (`needed.md` #3) then become a default-set question, not a defect class —
worth doing, but the report is the load-bearing half.

### B4. A citation that binds to nothing — **unowned, and this is the load-bearing fix**

Today a citation that finds no test still creates a TEST node anchored at *the comment's own
line* (`builder.py:4449-4457`). It can never receive a result, so its assertion reads Tested
and never Passing, permanently — indistinguishable from a stale result.

Note the asymmetry that keeps it invisible: `tests.unmatched_results` checks RESULT nodes
with no YIELDS **parent**. Nothing checks TEST nodes with no YIELDS **child**.

Proposed beside REQ-d00276 (a set reported in its own right, crediting nothing): a citation
in a scanned test file that binds to no test SHALL be reported and SHALL contribute no
evidence. Note the candidate set is wrong as well as the window: `group(` never enters
`span_starts` (`prescan.py:43-44`, `:606-622`), so a citation describing a whole group
orphans regardless of distance — removing the line limit alone would not fix it.
The attachment rule itself is code — the user's direction (bind forward to the next test
declaration bounded by the enclosing span rather than by a line count) is an implementation
directive, not an assertion.

Related and worth folding in: the same hard window is reimplemented in `dart_prescan`,
`ast_prescan` and `build_line_context`, and is absent from `text_prescan` and
`external_prescan` — so a `.js`/`.go`/`.rb` test file has no forward-look at all today.

### B5. A test file nothing can run — **unowned**

*"This file is scanned as a test, and nothing in your configuration can ever run it"* is a
statement the tool can make and the author cannot. Nothing maps scanned test files against
the set of targets that carry a `command`. Belongs beside REQ-d00276 / REQ-d00274.

### B6. Exit-code-only results — **unowned; the largest new capability**

REQ-d00254-E's reporter registry presumes a per-test record. A genuine class of tests
(module-level asserts, exit non-zero on first failure, run in a bare interpreter) cannot
produce one. Proposed: extend REQ-d00254-E so a reporter may credit at file granularity from
a command's exit status — which is exactly the granularity such a test can honestly offer.

### B7. `broken` vs `malformed` — vocabulary, not behaviour

The spec's real vocabulary is **failure class** (REQ-p00014-R: five classes distinguished by
how far the reference got, and *"A diagnostic SHALL NOT report a class further along than the
one the reference reached"*). `needed.md`'s definition — broken = valid ID matching nothing;
malformed = doesn't match the ID pattern — is consistent with actual usage but is stated
nowhere. `broken.py` already comments that the command name is a legacy label and prints
`UNRESOLVED REFERENCES`. Cheapest correct move: state the two words against the existing
classes in REQ-d00272-A / REQ-d00271-A, and stop there.

---

## Workstream C — conformance defects, no new spec required

Each is delegable to a subagent as-is.

| # | Defect | Governing assertion | Fix |
|---|---|---|---|
| C1 | Scoped `-o` artifact carries no disclosure | REQ-p00084-D | the disclosure must reach the artifact, not only the terminal; then `analysis_cmd` (discloses nowhere) and `summary` csv |
| C2 | Spaced trailing prose downgrades the diagnosis | REQ-d00272-E/L | make the existing better diagnosis reachable past `patterns.py:1390` |
| C3 | `broken` listing drops class and codes | REQ-p00014-R | carry them through all four output paths |
| C4 | `unmatched_results` computes names and drops them | REQ-d00284-C | rendering (subsumed by A3.2); add its follow-up entry and read its severity from config |
| C5 | Findings never render in text/markdown | REQ-p00019-G, REQ-d00271 | A3.2 — listed here because it is the root of C4 and of `needed.md` 6 and 9 |
| C6 | Coverage severity config drives the badge but not the check | REQ-d00212-P | A3.1 |
| C7 | `docs/rules.md:290-293` documents an inline-suppression feature that does not exist | — | correct the doc |
| C8 | `terms.severity.changed` is documented and read by nothing | — | wire it or withdraw it |

---

## Sequencing

```text
   A2 spec: finding shape, severity, location, remedy
        |
        v
   A3.1 severity type + one resolution  --.
   A3.2 checks = the one findings surface |-- retires C4, C5, C6 and
        |                                 |    most of needed.md 6 and 9
        v                                 |
   A3.3 shared finding + one encoder  <---'
        |
        +--> A3.4 migrate producers (batched, parallel subagents)
        +--> A3.5 silent discards become findings
        +--> A3.6 one condition per word
        +--> A3.7 per-class commands become preset filters (needs A3.3)

   B1/B2 spec ---> parser work (C2, C3 land here)
   B3    spec ---> one file-selection mechanism + unmatched-keyword report (+ Dockerfiles)
   B4/B5 spec ---> binding check + runnability check
   B6    spec ---> exit-code reporter          [largest; separable]
```

A3.2 is the highest value per unit of risk in the whole plan and does not depend on the
spec work. C1 is independent of everything and is a regulated-artifact correctness issue.

## Delegation

Suited to subagents as written: C1, C2, C3, C7, C8; each A3.4 producer batch; the B3
default-pattern addition. Each carries a named governing assertion, so a subagent can be
handed the assertion and the file list without re-deriving the design.

Not delegable without a decision first: A2 and B1–B6 spec drafting (house rules — find the
owner, one SHALL per assertion, never renumber, invariant over mechanism), and the A3.3
model change.

## Verification

Per the estate's own rules: unit tier during development; `pytest -m ""` before push, with
the worktree venv first on PATH; `pytest -m stress` if graph mutation or server state is
touched. Every new check needs `docs/cli/checks.md`, `docs/configuration.md`,
`init.py` `_FIELD_COMMENTS`, and a regenerated `config/elspais-schema.json` (CI-enforced).
A change here is proven against the real estate — callisto and hht_diary — not the unit
suite alone.

## Open decisions

1. ~~Branch scope.~~ **DECIDED: all on TOOL-66.** Workstreams A, B and C land on this
   branch together. Consequence accepted: a refactor reaching health.py, the MCP surface
   and the viewer rides a parse-fix ticket, and the pre-push full-tier run carries it.
   Commit discipline therefore matters more, not less — one commit per phase.
2. ~~Depth of A.~~ **DECIDED: the full regular system, A3.1 through A3.6.** Every
   producer migrates, the silent discards become named findings, and each colliding
   word is resolved to one condition. Half of A leaves the system irregular, which is
   the state that produced these findings in the first place.
3. ~~B6 (exit-code reporter).~~ **DECIDED: deferred; B5 lands here instead.** The check
   "this file is scanned as a test and nothing in your configuration can ever run it"
   is built on this branch, which stops the silent harm — adding a test directory can no
   longer raise Tested while Passing stays put. The reporter itself is a note-and-defer,
   NOT a filed ticket. Its spec assertion is not written here either; it goes with the
   implementation.
4. ~~broken/malformed vocabulary.~~ **DECIDED: the words are `unresolved` and
   `malformed`; spec them and align the surfaces.** `unresolved` replaces `broken`
   throughout. Definitions: *malformed* — did not read as an identifier at all;
   *unresolved* — read as an identifier and named nothing the federation holds. The five
   failure classes stay as the fine-grained vocabulary; these two are the grouping terms.
   Scope of the alignment: spec wording (REQ-d00269-D records "a broken reference"),
   the `broken` command and its heading (which already prints `UNRESOLVED REFERENCES`),
   `graph.broken_references()` / `_broken_references` / `has_broken_references`, the MCP
   `get_broken_references` tool, `_FOLLOWUP_COMMANDS`, and the docs. The config key
   `rules.references.malformed` is already correct and does not move.
   The CLI command renames `broken` -> `unresolved`, a clean break with NO alias
   (an alias would be exactly the fallback the estate's own rule bars). Before pushing,
   check callisto, hht_diary and hht_workflows for CI invocations of `elspais broken`,
   and write the release note.
5. ~~Dockerfiles.~~ **DECIDED: both, on this branch.** B3's unmatched-keyword report is
   the load-bearing half and lands here; `Dockerfile`, `*.Dockerfile` and `Containerfile`
   join the default code patterns alongside it.

## Decision log

All five open decisions are settled. Numbering stays stable; a reversal is recorded
against the entry rather than replacing it.

1. All workstreams on TOOL-66.
2. Workstream A in full — A3.1 through A3.6.
3. B6 exit-code reporter deferred (note, not a ticket); B5 runnability check lands here.
4. Vocabulary is `unresolved` / `malformed`; surfaces aligned; command renamed, no alias.
5. B3 report and the Dockerfile default patterns both land here.
6. `checks` is the general findings surface, with filters over the shared finding fields.
   `unresolved`, `errors` and `unlinked` are kept, re-implemented as preset filters over
   the one stream rather than as separate renderers. Work-list commands stay separate.
