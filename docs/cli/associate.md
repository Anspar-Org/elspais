# associate

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

Validates the target has a valid `.elspais.toml` with `project.type = "associated"`.

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

Scans sibling directories for any repository with `project.type = "associated"` in its config.

### Listing links

```bash
elspais associate --list
# callisto  CAL  /home/user/repos/callisto  OK
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

## Notes

- Links are stored in `.elspais.local.toml` (gitignored)
- Use `elspais doctor` to check if your associate paths are valid
- Duplicate detection resolves relative paths from the canonical repo root, so `--all` won't create duplicates when run from a worktree
- `--list` resolves relative paths from the canonical root for worktree compatibility
