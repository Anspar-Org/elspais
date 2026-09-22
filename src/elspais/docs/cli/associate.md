# ASSOCIATE

Manage links to associated repositories.

## Usage

```
elspais associate <path>              # Link a specific associate
elspais associate <path> -f           # Replace the path recorded for it
elspais associate --all               # Auto-discover and link all
elspais associate --list              # Show linked associates
elspais associate --unlink <name>     # Remove a link
```

## What it does

Associates are linked repositories whose requirements are included in combined traceability matrices. The `associate` command manages these links by writing to `.elspais.local.toml` (your local config, not shared with other developers).

### Linking by path

```bash
elspais associate /path/to/callisto
# Linked callisto (CAL) at /path/to/callisto
```

Validates the target has a `.elspais.toml` that loads successfully under the standard config schema. There is no `project.type` marker to opt in or out -- any directory with a loadable config is accepted.

The link records the namespace the target declares for itself, and that namespace has to be the target's alone: a namespace says whose identifiers a given identifier is, so a federation in which two repositories claim one namespace can answer nothing. The rules a federation is built under are checked here, at the moment the registration is made, and a registration that would break the build is refused with the reason the build would give:

```bash
elspais associate ../other
# Refused: other at /home/user/repos/other would not federate, and nothing was changed.
#   Two repositories are federated under the namespace 'CAL': ... give each repository its own.
```

This covers a repository reached indirectly too -- membership follows each associate's own declarations, so a namespace can collide with a repository you never named yourself.

### What a run reports

Every run states the entry and the path the configuration holds when the
command returns, never the path you typed. A run that recorded nothing says
so, so an operator -- or a compile script whose only record is this output --
can tell a registration that happened from one that did not:

```bash
elspais associate /path/to/callisto
# No change: callisto (CAL) stays registered at /path/to/callisto
```

### Registering a name that is already recorded

Registration is keyed by the name the target repository declares for itself.
Pointing it at a different directory that declares the same name is refused,
and nothing is written:

```bash
elspais associate /path/to/callisto-copy
# Refused: callisto is already registered at /path/to/callisto, and nothing was changed.
# Use -f to replace that path with /path/to/callisto-copy.
# Run 'elspais associate --list' to see the current registrations.
```

Refusal is the default because the recorded path is a fact your invocation
does not know it is contradicting -- a copy registered silently means every
later run reads the original while you believe it reads the copy. Pass `-f`
(`--force`) when replacing it is what you meant; the report then names both
paths:

```bash
elspais associate /path/to/callisto-copy -f
# Repointed callisto (CAL): was /path/to/callisto, now registered at /path/to/callisto-copy
```

A refusal exits non-zero, so a script that registers as a build step fails
rather than continuing against a repository it did not intend.

### One namespace, two directories

A namespace is what a reference resolves through, so one namespace names one
member. A second directory declaring a namespace that is already registered is
a second answer to a question that admits one, and it is refused whatever the
two entries are called:

```bash
elspais associate ../callisto-copy
# Refused: the namespace CAL is already registered to callisto at
#   /home/user/repos/callisto, and nothing was changed.
# Use -f to record /home/user/repos/callisto-copy instead, replacing that entry.
```

`-f` leaves one entry, recorded at the directory you named, and the report says
which entry it replaced:

```bash
elspais associate ../callisto-copy -f
# Replaced callisto at /home/user/repos/callisto with clone (CAL) at /home/user/repos/callisto-copy
```

Changing a recorded path works wherever the entry is declared: the change is
written to `.elspais.local.toml`, and the configuration a later run assembles
holds the value you gave. Retiring an entry is the case an overlay cannot do.
Where the entry holding the namespace is declared in `.elspais.toml` -- the
shared configuration, committed and read by everyone -- there is nothing `-f`
could do: removing a local entry would leave that declaration standing and the
next run would read it again. That case is refused naming the file to edit,
with no offer to force it:

```bash
elspais associate ../callisto-copy
# Refused: the namespace CAL is already registered to callisto at ../callisto,
#   and nothing was changed.
# That entry is declared in /home/user/repos/core/.elspais.toml, which this
#   command does not write, so -f cannot replace it.
# Edit ... to point callisto elsewhere, or give this repository a namespace of its own.
```

A copy that declares its own namespace is a different matter and registers
normally: its identifiers cannot be confused with the original's, so holding
both is unambiguous. Nothing here consults git -- the question is answered from
the declarations alone.

### A configuration that already will not federate

The membership rules are checked against the configuration as a whole, so a
configuration that would not federate before your registration refuses it too.
The report says so, and names the entries actually at fault rather than the one
you were registering:

```bash
elspais associate ../gamma
# Refused: this configuration does not federate as it stands, before gamma at
#   /home/user/repos/gamma is considered. Nothing was changed.
#   Two repositories are federated under the namespace 'AAA': ... alpha ... beta ...
```

Unlink one of the two named entries and the registration goes through.

### Linking by name

```bash
elspais associate callisto
# Linked callisto (CAL) at /home/user/repos/callisto
```

Searches sibling directories of your main repository for a matching name.

### Auto-discovery

```bash
elspais associate --all
# Linked callisto (CAL) at /home/user/repos/callisto
# Linked 1 associate(s), 0 unchanged, 0 refused
```

Scans sibling directories for any repository whose `.elspais.toml` loads successfully (excluding the current repo itself).

Sibling directories without a `.elspais.toml` are silently ignored (they are not candidates). A candidate whose `.elspais.toml` exists but fails to load (stale schema, missing namespace, TOML syntax error) is skipped with a printed reason instead of aborting the scan:

```bash
elspais associate --all
#   Skipping: Cannot load associate config in /home/user/repos/old-proj: <reason>
#   Linked callisto (CAL) at /home/user/repos/callisto
# Linked 1 associate(s), 0 unchanged, 0 refused
```

Auto-discovery reports and refuses on the same terms as a single
registration. A candidate that would be refused is reported and the scan
carries on to the ones after it, so the state of every candidate is on the
screen together; the run exits non-zero if any was refused. Two candidates
of one scan standing for one entry are settled before anything is written:
neither is recorded, and each is reported naming the other, so which the scan
reached first decides nothing. `--all -f`
repoints each candidate whose recorded path differs.

Two candidates of one scan that stand for the same entry -- they declare one
name, or one namespace -- are a case `-f` cannot
settle, since it was given about neither of them. Neither is recorded, and
each is reported naming the others, so which one the scan reached first
decides nothing. Register the one you meant by path.

### Listing links

```bash
elspais associate --list
# Name                 Prefix     Status       Local   Path
# callisto             CAL        OK           -       /home/user/repos/callisto
# titan                TTN        OK           yes     /home/user/repos/titan
```

`Local` says whether that repository's own configuration was assembled with a
`.elspais.local.toml` of its own. It answers one question -- was a machine-local
file involved -- and deliberately not which values it contributed: an overlay
changes nothing about the graph, so what it holds is a fact about this machine
rather than about the federation. Read the file when you need the detail.

### Unlinking

```bash
elspais associate --unlink callisto
# Unlinked callisto (was callisto: /path/to/callisto)
```

The name addresses an entry of the assembled configuration by its entry key, by the namespace it declares, or by the last segment of the path it records. Key and namespace are matched without regard to case:

```bash
elspais associate --unlink callisto                       # entry key, or the directory it records
elspais associate --unlink CAL                            # the namespace it declares
```

Which file declares the entry decides what a run can do about it, because only `.elspais.local.toml` is written:

```bash
elspais associate --unlink beta
# Refused: beta is declared in .elspais.toml at ../beta, and nothing was changed.
# Remove it there; a machine-local write cannot retire a committed declaration.
```

An entry declared in both files is overridden locally rather than created locally, so removing the local entry withdraws the override and leaves the committed declaration standing:

```bash
elspais associate --unlink beta
# Removed the local override for beta (was /home/user/moved/beta)
# beta remains declared in .elspais.toml at ../beta. Remove it there to retire it.
```

## Who is in the federation

Every repository reachable from this one, not only the ones named here. Each
associate's own `[associates]` declarations are read too, and theirs in turn,
depth-first from the repository the command was run in — so a repository you
never named joins the federation because something you did name declares it,
and the tool answers the same way from any repository in the chain.

A member is identified by the namespace its declaration names, not by where
it sits or what the entry is called. Two chains reaching one namespace at one
directory converge on a single member, so declaring something a sibling
already declares is harmless; two directories claiming one namespace are a
collision the build reports, naming both. A member reached through itself is
a cycle, reported as an error naming the declaration chain that formed it.

Because that is one rule with one authority, `elspais associate` admits a
declaration exactly when a build would admit it -- a registration that
succeeds cannot produce a federation that then refuses to build.

`elspais checks` and `elspais doctor` report on every member, including the
ones reached indirectly.

## Changing a member's configuration

A configuration document is changeable only in the repository the tool is
serving. A federation holds one for every member, so a change can be aimed at
an associate's -- a repository the tool reads rather than serves -- and that is
refused, naming the document's own repository and the one being served:

```text
.elspais.toml is the configuration of 'CAL', and this tool is serving 'REQ'.
A configuration document is changeable only in the repository being served;
change it from a tool serving that repository instead.
```

Nothing is changed, on disk or in the graph, and nothing joins the pending
changes. Writing into another repository's checkout is surprising wherever it
happens, and where the checkout was made by a host for a session, an edit to it
would be discarded without anyone noticing; a tool serving that repository is
where such an edit belongs.

Reading is unrestricted. Every member's configuration is held and readable, and
a declaration is read in the project that makes it -- an associate's
declarations are invisible to the host and the host's to the associate. What a
declaration change is and what it reports is in `elspais docs scoping`.

## Changing a member's requirements

A member the tool reads rather than serves is read-only by default, and that
holds from either surface: a mutation aimed at a node an associate owns is
refused by the MCP tools and by the viewer's mutation routes alike, before the
version token is judged, naming the associate and the setting that would open
it. Nothing is changed, in memory or on disk.

A change can still reach the pending work another way -- a command that mutates
the graph directly, for instance -- and the save is where it is answered. A save
writes only the repository being served while `write_associates` is false, so a
change queued for an associate's file is not written; it is not discarded
either. The save names the file it held back and why, in what it reports as
skipped and as an error:

```text
file:CAL:spec/reqs.md: owned by an associate, so it is not written
(federation.write_associates is false). The changes queued for it are kept
rather than discarded.
```

Because the change is still pending, the save did not do what it was asked and
does not report success: pending changes are cleared only once a save has
performed them. Work queued for the repository being served is written as
usual, and the pending record is kept whole, so a later save re-renders that
file harmlessly. Declining one member's file is not a reason to abandon
another's, so a save that wrote the served repository's file reports that
alongside the decline.

The unsuccessful save says which kind of unsuccessful it was. It carries
`code: "write_scope_declined"` and an `error` naming the held-back files in
full, so a caller can tell a decline -- a policy answer a further save will
repeat -- from a write that failed and might succeed next time. A save that
also failed to write something is reported as a failure carrying no decline
code, because that is the part a caller can do least about. The MCP save tool
and the viewer both report the code the save wrote; over HTTP, `POST /api/save`
maps it to **403**, the status the mutation routes already give for an
associate-owned target, rather than the 500 a failed write gets.

To write the change, set `write_associates = true` under `[federation]`, or
make it from a tool serving the repository that owns the file.

A file that is merely untidy -- formatting `elspais fix` would canonicalize,
which nobody asked for -- is held back without a word, so an ordinary `fix` run
in a federation is unaffected.

## Options

| Flag | Description |
|------|-------------|
| `--all` | Auto-discover and link all associates |
| `--list` | Show status of linked associates |
| `--unlink NAME` | Retire an associate recorded in `.elspais.local.toml`, addressed by entry key, namespace, or recorded directory |
| `-f`, `--force` | Replace the path recorded for an associate that is already registered |

## Referencing an associate's requirements

Once an associate is linked, a consumer requirement can declare that its
implementation is provided by a requirement in that external library with
the `Integrates:` keyword:

```markdown
## REQ-d00010: Event Sourcing Adapter

**Level**: DEV | **Status**: Active

**Integrates**: REQ-evs-0007
```

`Integrates:` is external-only -- the target must resolve to an associate
repo (a same-repo target is an unresolved reference), the library is never
modified and contains no reference back, and the consumer inherits the
library requirement's implemented/verified coverage. See
`elspais docs graph-model` (INTEGRATES edge) and `elspais docs format`.

In coverage reporting, `elspais summary` shows an "External integrations (by
associate)" section grouping inherited coverage by the owning associate with a
federation total, and `elspais gaps` lists integrating requirements under
"Covered via external associate" rather than reporting them as uncovered.

## Annotating code and tests across repositories

An identifier owned by any repository in the federation is recognised in the
code and test annotations of every repository in it. A sponsor repo's test may
name a platform requirement directly:

```python
# Verifies: CAL-d00007-B
def test_scheduling_window(): ...
```

Each repository keeps its own identifier configuration; the scan simply
applies every member's grammar and reads the reference under the grammar of
the repository that owns it. A comment is the only thing that names a
requirement -- a test function's own name never does, in any repository of
the federation.

An unresolved reference is always reported, carrying the text as written
rather than being dropped. Which report it lands in depends on whether any
member's grammar admits the identifier — not on whether the requirement
exists:

```python
# Implements: CAL-d99999-A     -> references.unknown_requirement (error)
# Implements: ZZZ-d00001-A     -> references.unknown_namespace (severity is yours)
```

`CAL-d99999-A` is spelled the way the `CAL` repository spells its
identifiers, so that repository is the one that would own it — it simply has
not authored it. That is `references.unknown_requirement`, and its severity
is fixed at error: the repository that would answer for the target is in the
federation and does not have it.

`ZZZ-d00001-A` is spelled the way no member spells anything, so no member
would own it. That is `references.unknown_namespace`, reported at the
severity the project configures in `[rules.references].unknown_namespace`
(`info` by default) — a sibling repository that has not been written yet is
advisory to one project and a build failure to another. Set it to `"off"` to
silence expected cross-repository references entirely — the check then reports
as skipped and lists nothing.

List both with `elspais unresolved`. A requirement with no evidence and a
requirement whose evidence could not be resolved otherwise read identically in
every report.

## Notes

- Links are stored in `.elspais.local.toml` (gitignored)
- Use `elspais doctor` to check if your associate paths are valid
- Duplicate detection resolves relative paths from the canonical repo root, so `--all` won't create duplicates when run from a worktree
- `--list` resolves relative paths from the canonical root for worktree compatibility
