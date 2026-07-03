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

## Notes

- Links are stored in `.elspais.local.toml` (gitignored)
- Use `elspais doctor` to check if your associate paths are valid
- Duplicate detection resolves relative paths from the canonical repo root, so `--all` won't create duplicates when run from a worktree
- `--list` resolves relative paths from the canonical root for worktree compatibility
