# Scoping a Report to an Audience

A report is read by an audience, and an audience is rarely served by every
requirement the estate holds. A sponsor reviewer wants product requirements, not
development internals, and wants withdrawn requirements out of the way.

Scoping selects which requirements a report emits. Every format the command
offers emits the same scoped set, so a CSV and a markdown render of the same
question agree.

## Selecting

```sh
elspais trace --level prd
elspais trace --level prd gui             # either level
elspais trace --level prd --level gui     # the same thing, written twice
elspais summary --not-status Deprecated   # everything except
elspais gaps --level prd --status Active
```

Values named for one property are alternatives: `--level prd gui` selects
requirements at either. Different properties are all required at once:
`--level prd --status Active` selects requirements that are both.

A property accumulates every value the invocation names for it. Write them
space-separated behind one flag, repeat the flag, or mix the two — the reading
is the same, so nothing a later occurrence names displaces what an earlier one
did.

`--not-level` and `--not-status` refuse a value outright. Where a value is both
required and refused, the refusal decides.

## Status roles

A project's statuses grow; the roles it assigns them do not. `--match-status-roles`
reads each named status as every status sharing its role, so a scope stays correct
through a status the project has not invented yet:

```sh
elspais summary --status Active --match-status-roles
```

That selects every status carrying the active role, not only `Active` itself. It
applies only where the project actually assigns the named status a role — a
status carried by a requirement but absent from the configuration stands for
itself.

## Named scopes

A scope spelled out when a report is run is known only to whoever spelled it.
Declare it instead, and a reader holding a committed report can look up what
produced it:

```toml
[scopes.sponsor]
level = ["prd"]
not_status = ["Deprecated"]
```

```sh
elspais trace --scope sponsor
elspais trace --scope sponsor --level prd ops   # narrows the named scope
```

A name selects exactly what the same scope stated in full selects. Flags given
alongside `--scope` narrow it rather than replacing it.

A declaration may also name the values a report states under it (`values = [
...]`, see below), so one name answers for a whole audience — the table and the
gap listing both. `summary` and `trace` state the named values as columns;
`gaps` and its single-dimension commands list the shortfalls in those same
dimensions. A report that states nothing about a requirement at all — `checks`
and its narrowings, `changed`, `analysis` — passes the values half over and
reads only the scope.

## Changing a declaration

A declaration is held in the graph as a node of its own, so it can be added,
changed, renamed and removed there. These are ordinary graph mutations: they
join the same mutation log, the same undo and the same count of pending
changes as a change to a requirement, and the configuration document is
written back by the same save. `[scopes.NAME]` is what a graph holds this way
today; a table it holds no declarations for is refused.

No CLI command changes a declaration. A change is made through the MCP
interface -- `mutate_add_declaration`, `mutate_update_declaration`,
`mutate_rename_declaration`, `mutate_delete_declaration` -- or through the
viewer's matching `/api/mutate/*-declaration` routes, which take the same
arguments and answer identically. Either way the change carries a version
token for what it changes, and a stale one is refused rather than allowed to
overwrite a change the caller never saw; see `elspais docs concurrency`.

A change states what the declaration says afterwards, whole. A setting the
change leaves out is a setting the project no longer states, not one carried
over from before. It is written setting by setting, so the note beside a
setting nobody touched and the comment explaining why a setting is what it is
are still there afterwards.

A change is judged before it is made. One that would leave a configuration the
tool cannot load -- a setting the schema does not define, a value of the wrong
type, a name it will not admit -- is refused naming what is wrong, and the
document is left as it was. What is judged is shape: a scope selecting a level
or a status no project declares loads, and goes through.

A repository may hold more than one configuration document: a machine-local
overlay layered over the committed file. Where both declare a scope under the
same name, the overlay's declaration is the one every reader resolves to, so
changing the committed one changes nothing a reader can see. The change still
goes through -- the document says afterwards what it was asked to say -- and
the report names the document the name resolves in instead, so a change that
moved nothing is not mistaken for one that worked. It says where the name
resolves and not what is declared there; read the overlay for that. A name no
other document declares is reported as nothing at all.

In a federation the documents of every member are held, and a change may be
aimed only at the one belonging to the repository the tool is serving; see
`elspais docs associate`.

A declared name is matched without regard to case, so `sponsor` and `Sponsor`
are one name. Declaring the second while the first stands is refused, naming
the one already there. Renaming a declaration to another casing of its own
name is a recasing, and goes through.

An undo restores the document's text rather than the values it held. A
configuration is written by hand, and reversing the values would reflow the
comments, spacing and key order written around them.

One consequence is worth knowing before removing a declaration. A comment
written above one belongs, in TOML's own model, to the item before it, so
removing a declaration leaves that comment in the document, where it now sits
above whatever followed:

```text
# what the sponsor sees
[scopes.sponsor]
level = ["prd"]

# what the auditor sees
[scopes.auditor]
level = ["prd", "ops"]
```

Remove `sponsor` and `auditor` keeps the comment introducing it: what is
written between a declaration's last setting and the next header describes
what follows, and goes back where it was written. The blank line that
separated `sponsor` from it goes with the removal, since that blank belonged
to the declaration being removed and leaving it would open a gap where a
declaration used to be.

Remove `auditor` instead and the comment describing it stays in the document,
now above whatever came after, because nothing in the file says it described
the declaration that was removed rather than the one before it. That is the
comment to look for after removing a declaration. A rename does not raise the
question at all -- the name is respelled where it stands.

## What a scoped report tells you

A report narrowed on purpose and one that lost requirements on the way are the
same artifact unless the narrowing is declared, so every scoped report says what
it was scoped to and how many requirements that selected:

```text
Scope: level prd; status excluding Deprecated
Scope selected 12 of 47 requirements
```

Two further disclosures are worth recognising.

A name no vocabulary admits selects nothing there and is reported:

```text
Scope: assoc: 'prd' is not a level in this vocabulary; it admits req
```

In a federation this is ordinary. Each member declares its own levels and
statuses, and a name is read in the vocabulary of the member that owns the
requirement being judged — never one merged from several. So `--level prd`
selects the product requirements of every member that declares a `prd` level,
says so for each member that does not, and goes on selecting for the rest.

A scope that matches nothing is an answer, not an empty estate:

```text
Scope: no requirement matches this scope; the estate holds 47
```

## Where the disclosure appears

Inside the report, in whatever format it is rendered in — never only on the
terminal. A report redirected to a file with `--output` carries its own scope,
so the artifact still answers the question months after the terminal that
produced it was closed:

- text and markdown — the lines beneath the title, in italics
- csv — leading `# Scope: ...` comment rows, one field each, ahead of the header
- html — a subtitle beneath the heading
- json — a `scope` array beside the report's own content

A report narrowed by nothing declares nothing, and its text, markdown, csv and
html renders carry no scope line at all. JSON is the exception: the `scope`
array is always there, empty when there is nothing to state, so a consumer
reads one shape whether the report was narrowed or not.
`trace --format json` is accordingly always the object
`{"scope": [...], "nodes": [...]}`, never a bare array of requirements.

## What scoping does not change

Scoping selects what a report emits. It does not change the coverage figures
that report states for a requirement it emits: a requirement's own coverage is a
fact about the whole estate — what implements it, what tests it, what refines it
— and none of that moves because a reader asked to see fewer requirements.
Evidence held by a requirement the scope excludes still conducts to one it emits.

Figures aggregated *across* requirements are a different kind of fact. They
answer "how far along is this set", and the set is the one the reader asked for.

## Which commands take a scope

`trace`, `summary`, `gaps` (and the individual gap listings `uncovered`,
`untested`, `unvalidated`, `failing`) and `analysis`.

`checks` does not. It reaches a verdict over the whole estate, and a flag it
could not honour would be worse than its absence.

## The other axis: which values a report states

Which requirements a report is about and which facts it states about them are
two separate choices. `--scope`/`--level`/`--status` make the first; `--values`
makes the second. They do not interfere: selecting fewer values never drops a
requirement, and selecting fewer requirements never drops a value, so you can
reach the same report by narrowing either first. The value vocabulary is in
`elspais docs traceability` under *Choosing Values*.

```sh
elspais summary --format csv --values implemented,tested
elspais summary --format csv --values uat_coverage.immediate_direct
elspais summary --values verified --level prd
elspais gaps --values implemented        # only what nothing implements
```

A report either states a value about each requirement or lists the requirements
one value has not credited — and both read the same dimension, so both take a
selection. `summary --values implemented` states the Implemented column;
`gaps --values implemented` lists what Implemented has not credited, which is
what `uncovered` is. `gaps` offers the four dimension keys and nothing beneath
them: a listing can be asked for or left out, but it cannot be narrowed to
`implemented.immediate_direct.count`.

`summary` aggregates, so its rows are levels rather than requirements. Its
identity value is `level` — always stated, whatever the selection names — and
it offers the five coverage dimensions with their four measures each, plus
`requirements` and `assertions`: the count of requirements in the group the run
weighs as active — the column is headed *Active Requirements* — and the count
of assertions they confer. It does not offer the per-requirement identity
values (`id`, `title`, ...), nor `verified.carried` (a level has no
per-requirement provenance bit), nor the line-coverage values, which are
measured in lines and have no level figure.

One named value is one value, in every format, stated in that format's own
kind. A coverage figure carries its own denominator and its own proportion
inside one table cell — `102/187 (54.5%)` — rather than spilling into companion
columns, and the Tested breakdown (passed / failed / awaiting a result) rides
inside the Tested cell, qualifying that figure rather than standing beside it.
A structured format states that same figure as an object of its numbers. So
`--values implemented` gives a two-column table, `Level` and `Implemented`, and
the same selection under `--format json` gives every row an `implemented`
object.

### Asking for the numbers instead of the cell

That composite is what a table wants. A program wants the numbers, and having
to recover them from `5/5 (100%)` with a regular expression is worse than not
having them — the proportion in the string is rounded, so a consumer that
parses it disagrees with one that re-derives it. So every coverage figure also
offers the three scalars it was built from, each selectable in its own right:

| Suffix | States |
|--------|--------|
| `.count` | the assertions credited |
| `.total` | the assertions the credit was counted over |
| `.ratio` | their proportion, as a number between 0 and 1 |

They are offered beneath a dimension's total and beneath each of its four
measures alike, so `implemented`, `implemented.count`, `implemented.ratio`,
`implemented.immediate_direct` and `implemented.immediate_direct.total` are all
names a selection may use.

```sh
elspais trace   --format json --values implemented.count,implemented.total,implemented.ratio
elspais trace   --format csv  --values implemented.count,implemented.ratio
elspais summary --format json --values implemented.count,implemented.ratio
elspais trace   --format json --values tested.immediate_direct.ratio
```

A scalar is a number, and JSON states it as one. A value key is a path and the
object mirrors it: asking for `implemented.count` states
`{"implemented": {"count": 5.0}}`, and `implemented.immediate_direct.total`
nests one level deeper again. The proportion is never rounded in the value, so
it always equals `.count` divided by `.total`; a table renders it rounded to
three places because that is a cell, not the value. Which values a selection
states does not depend on the format: `implemented.count` states that one value
in CSV, markdown, HTML and JSON alike, as a number where the format has numbers
and as a cell where it has cells.

`trace` and `summary` state a figure the same way, so one row shape answers
both: `summary --format json --values implemented` gives each entry of its
`levels` array the same `implemented` object that `trace` gives each
requirement.

The three counts behind the Tested figure are selectable the same way, and are
counts only — there is nothing for a proportion of a returned verdict to be of,
so no `.ratio` is offered beneath them and asking for one is refused:

```sh
elspais trace --format json --values tested.passed,tested.failed,tested.awaiting
elspais trace --format json --values tested.failed   # only the failures
```

They sit inside the same `tested` object as the figure they break down, so
`--values tested` states `count`, `total` and `ratio` beside `passed`, `failed`
and `awaiting`.

`.count`, `.total` and `.ratio` are offered under the five assertion-counted
coverage dimensions and under `lcov_tested`, which credits assertions from line
evidence and so is counted over assertions like any other dimension. None of
them carries measures except the five: nothing conducts `lcov_tested` up a
`Refines:` chain, so it has no conducted measure to name.

`code_tested` is the one figure measured in LINES rather than assertions, and it
decomposes the same way:

```sh
elspais trace --format json --values code_tested
# { "id": "REQ-d00081",
#   "code_tested": { "count": 16.0, "total": 20.0, "ratio": 0.8,
#                    "attributed": null } }

elspais summary --format csv --values level,code_tested.count,code_tested.total
```

`.count` is the lines covered, `.total` the lines measured, `.ratio` their
proportion. `.attributed` is a further reading of the same lines — how many of
them a verifying test can be named for — and it is stated only where the
coverage tooling recorded per-test contexts; aggregate-only coverage states
`null` there while the other three stand. `trace` and `summary` offer it
identically, the second summing over the requirements of each level under the
same status gate `checks --code-checks` uses, so the two reconcile.

A value in which a report states no figure is never written as zero. A `trace`
table marks it `n/a`, a `summary` table `-`, and JSON states `null`. A level
whose requirements confer no *Assertion* has no coverage figure to state at
all, which is a different fact from a figure of zero — the text report says
that once for the group rather than repeating the mark across every column of
the row. The same distinction holds under `--targets`: a requirement carrying
test references but no result record at all has taken no verdict, so its
`trace` cell reads `—` and its `verified.count`, `verified.ratio` and
`verified.carried` are `null` rather than `0`.

`--values` is offered by `trace` and `summary`, which state facts about each
row, and by `gaps` and its single-dimension listings (`uncovered`, `untested`,
`unvalidated`, `failing`), which read a selection as which shortfalls to list
rather than which facts to show. `analysis` and `checks` (and its narrowings,
and `changed`) do not offer it: they report findings or files rather than a
dimension, and a flag a command cannot honour is worse than its absence.

A `--values` a reader TYPED for one of those, or for a composed report
reaching a section that offers none, is refused outright — a report is never
produced under a selection it cannot honour. The values half of a named
declaration is different: one name is read against every report the audience
takes, so it constrains whichever of those reports has values to select among
and passes over the ones that do not, leaving them to state what they would
have anyway.

## Not the same as `--treat-active`

`--treat-active` widens what COUNTS: it promotes a status so requirements
carrying it are measured alongside active ones. Scoping selects what is EMITTED:
which requirements the report is about at all. They compose, and neither
substitutes for the other.

`--treat-active` is available on every report that takes a scope — `summary`,
`trace`, `gaps` and its shorthands (`uncovered`, `untested`, `unvalidated`,
`failing`), `analysis` — and on `checks`. It is declared once, beside the scope
flags, for the reason those are: a report a reader cannot ask would answer a
different question from its neighbours.

It is **run-scoped**. It overlays this invocation's configuration and never the
built graph, so one serving process can answer readers who weigh different
statuses as active without one reader's question changing another's answer. For
the coverage figures it is the same thing as setting
`[statuses.<S>] expects_implementation = true` in `.elspais.toml`, for the
duration of the run.

Any report it changes **discloses it**, in every format, alongside the scope
and in the same place:

```
Weighed as active: Review (--treat-active)
```

That disclosure is what keeps the figures honest. The requirements still read
`Status: Review` in the spec, so a reader who cannot see the invocation cannot
otherwise tell why they were counted. `checks` states the same fact in its
trailing `Flags:` line.

Two reports accept the flag and read the same either way, for different
reasons. `trace` states facts about each requirement, one row each, and takes
nothing over a population, so no choice about the population decides what it
says. `analysis` ranks requirements against each other and withholds the
statuses excluded from *analysis*, which is a different question from whether a
status expects implementation — weighing a status as active does not change
which statuses are scored. Neither report discloses the flag, because in
neither did it decide anything.
