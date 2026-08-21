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
elspais summary --not-status Deprecated   # everything except
elspais gaps --level prd --status Active
```

Values named for one property are alternatives: `--level prd gui` selects
requirements at either. Different properties are all required at once:
`--level prd --status Active` selects requirements that are both.

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

## The other axis: which columns a report states

Which requirements a report is about and which facts it states about them are
two separate choices. `--scope`/`--level`/`--status` make the first; `--columns`
makes the second. They do not interfere: selecting fewer columns never drops a
requirement, and selecting fewer requirements never drops a column, so you can
reach the same report by narrowing either first. The column vocabulary is in
`elspais docs traceability` under *Choosing Columns*.

```sh
elspais summary --format csv --columns implemented,tested
elspais summary --format csv --columns uat_coverage.immediate_direct
elspais summary --columns verified --level prd
```

`summary` aggregates, so its rows are levels rather than requirements. Its
identity column is `level` — always stated, whatever the selection names — and
it offers the five coverage dimensions with their four measures each, plus
`requirements` and `assertions`: the count of requirements in the group and the
count of assertions they confer. It does not offer the per-requirement identity
columns (`id`, `title`, ...), nor the line-coverage columns, which are measured
in lines and have no level figure.

One named column is one column, in every format. A coverage figure carries its
own denominator and its own proportion inside its cell — `102/187 (54.5%)` —
rather than spilling into companion columns, and the Tested breakdown (passed /
failed / awaiting a result) rides inside the Tested cell, qualifying that figure
rather than standing beside it. So `--columns implemented` states two columns,
`Level` and `Implemented`, whether it is rendered as text, markdown, CSV or
JSON.

A column in which a report states no figure is never written as zero. In a
table it is marked `-`, and in JSON it is `null`. A level whose requirements
confer no *Assertion* has no coverage figure to state at all, which is a
different fact from a figure of zero — the text report says that once for the
group rather than repeating the mark across every column of the row.

`--columns` is offered by `trace` and `summary`, the two reports that state
facts in columns. The gap listings (`gaps`, `uncovered`, `untested`,
`unvalidated`, `failing`) and `analysis` do not offer it: they list what is
missing rather than tabulating facts about requirements, and a flag a command
cannot honour is worse than its absence. A composed report is refused outright
if `--columns` reaches a section that states no columns.

## Not the same as `--treat-active`

`--treat-active` widens what COUNTS: it promotes a status so requirements
carrying it are measured alongside active ones. Scoping selects what is EMITTED:
which requirements the report is about at all. They compose, and neither
substitutes for the other.
