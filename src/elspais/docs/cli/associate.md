# ASSOCIATE

Manage links to associated repositories.

## Usage

```
elspais associate <path>              # Link a specific associate
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

The link records the namespace the target declares for itself, and that namespace has to be the target's alone: a namespace says whose identifiers a given identifier is, so a federation in which two repositories claim one namespace can answer nothing and fails to build rather than guessing. If the repository you are linking declares the same namespace as one already in the federation, change one of them in `[project].namespace` before linking. The same applies to a repository reached indirectly -- membership follows each associate's own declarations, so a namespace can collide with a repository you never named yourself.

### Linking by name

```bash
elspais associate callisto
# Linked callisto (CAL) at /home/user/repos/callisto
```

Searches sibling directories of your main repository for a matching name.

### Auto-discovery

```bash
elspais associate --all
# Found: /home/user/repos/callisto (CAL)
# Linked 1 associate
```

Scans sibling directories for any repository whose `.elspais.toml` loads successfully (excluding the current repo itself).

Sibling directories without a `.elspais.toml` are silently ignored (they are not candidates). A candidate whose `.elspais.toml` exists but fails to load (stale schema, missing namespace, TOML syntax error) is skipped with a printed reason instead of aborting the scan:

```bash
elspais associate --all
# Found: /home/user/repos/callisto (CAL)
#   Skipping: Cannot load associate config in /home/user/repos/old-proj: <reason>
# Linked 1 associate
```

### Listing links

```bash
elspais associate --list
# Name                 Prefix     Status       Path
# callisto             CAL        OK           /home/user/repos/callisto
```

### Unlinking

```bash
elspais associate --unlink callisto
# Unlinked callisto
```

The `--unlink` argument matches by (in order): exact path, directory name, path component substring, project name, or prefix code. This means all of these work:

```bash
elspais associate --unlink ../callisto                    # exact path
elspais associate --unlink callisto                       # directory name or project name
elspais associate --unlink CAL                            # prefix code
```

Even when the linked path is a worktree (e.g., `callisto-worktrees/some-branch`), `--unlink callisto` still matches via path component substring.

## Who is in the federation

Every repository reachable from this one, not only the ones named here. Each
associate's own `[associates]` declarations are read too, and theirs in turn,
depth-first from the repository the command was run in — so a repository you
never named joins the federation because something you did name declares it,
and the tool answers the same way from any repository in the chain.

Repositories are identified by git origin rather than by path or declared
name. Two chains reaching the same repository converge on one member rather
than federating it twice, so declaring something a sibling already declares
is harmless. A repository reached through itself is a cycle, and the build
reports it as an error naming the declaration chain that formed it.

`elspais checks` and `elspais doctor` report on every member, including the
ones reached indirectly.

## Options

| Flag | Description |
|------|-------------|
| `--all` | Auto-discover and link all associates |
| `--list` | Show status of linked associates |
| `--unlink NAME` | Remove a linked associate by name, path, or prefix code |

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
repo (a same-repo target is a broken reference), the library is never
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
def test_scheduling_window():
    ...
```

Each repository keeps its own identifier configuration; the scan simply
applies every member's grammar and reads the reference under the grammar of
the repository that owns it. Test function names work the same way in
underscore notation (`def test_window_CAL_d00007_B()`).

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
advisory to one project and a build failure to another. Set it to `"ok"` to
silence expected cross-repository references entirely.

List both with `elspais broken`. A requirement with no evidence and a
requirement whose evidence could not be resolved otherwise read identically in
every report.

## Notes

- Links are stored in `.elspais.local.toml` (gitignored)
- Use `elspais doctor` to check if your associate paths are valid
- Duplicate detection resolves relative paths from the canonical repo root, so `--all` won't create duplicates when run from a worktree
- `--list` resolves relative paths from the canonical root for worktree compatibility
