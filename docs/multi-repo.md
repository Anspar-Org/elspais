# Multi-Repository Support

elspais supports organizations with multiple repositories that share requirements.

## Repository Types

### Core Repository

The primary repository containing shared platform requirements:

```toml
# .elspais.toml in core repo
[project]
name = "core-platform"
type = "core"
```

- Requirements use base format: `REQ-p00001`, `REQ-d00042`
- Acts as source of truth for shared requirements
- Generates complete traceability matrix

### Associated Repository

Extensions or customizations that reference the core:

```toml
# .elspais.toml in associated repo
[project]
name = "associated-callisto"
type = "associated"

[associated]
prefix = "CAL"

[core]
path = "../core-platform"
```

- Requirements use associated format: `REQ-CAL-d00001`
- Can reference core requirements in "Implements" field
- Validation checks core repo for referenced requirements

## Directory Structure

```text
organization/
├── core-platform/           # Core repository
│   ├── .elspais.toml       # type = "core"
│   ├── spec/
│   │   ├── INDEX.md
│   │   ├── prd-core.md     # REQ-p00001
│   │   ├── ops-deploy.md   # REQ-o00001
│   │   └── dev-impl.md     # REQ-d00001
│   └── ...
│
├── associated-callisto/     # Associated repository
│   ├── .elspais.toml       # type = "associated", prefix = "CAL"
│   ├── .core-repo          # Points to ../core-platform
│   ├── spec/
│   │   ├── INDEX.md
│   │   ├── prd-cal.md      # REQ-CAL-p00001
│   │   └── dev-cal.md      # REQ-CAL-d00001 (implements REQ-p00001)
│   └── ...
│
└── associated-xyz/          # Another associated repo
    ├── .elspais.toml       # type = "associated", prefix = "XYZ"
    └── ...
```

## Cross-Repository References

Associated requirements can implement core requirements:

```markdown
### REQ-CAL-d00001: Callisto Authentication

**Level**: Dev | **Implements**: p00001 | **Status**: Active

Implements core user authentication for Callisto project.
```

Here `Implements: p00001` refers to core `REQ-p00001`.

## Validation

### Validate Associated Repo Against Core

```bash
# In associated repository
cd associated-callisto/

# Validate with explicit core path
elspais validate --core-repo ../core-platform

# Or use configured path
elspais validate
```

### What's Validated

1. **Associated ID format**: IDs must use associated prefix
2. **Core references**: Referenced core IDs must exist
3. **Hierarchy rules**: Associated DEV can implement core PRD
4. **Hash verification**: Both core and associated hashes

### Validation Output

```text
✓ Validating associated requirements (CAL)
✓ Loading core requirements from ../core-platform
✓ 15 associated requirements found
✓ 8 cross-repository references validated

❌ ERROR REQ-CAL-d00003
   Implements REQ-p99999 which does not exist in core
   File: spec/dev-cal.md:42

✓ 14/15 requirements valid
```

## Cross-Repository Hierarchy Traversal

### Reformat Command (v0.11.0+)

The `reformat-with-claude` command supports cross-repository hierarchy traversal using the `--mode` flag:

```bash
# In associated repository that implements core requirements
cd associated-callisto/

# Reformat starting from core PRD, including associated DEV requirements
elspais reformat-with-claude --start-req REQ-p00001 --mode combined

# This will:
# 1. Load requirements from both core and associated repositories
# 2. Build complete hierarchy graph with cross-repo links
# 3. Traverse from REQ-p00001 → REQ-CAL-d00027 and any other children
# 4. Only modify files in the local (associated) repository
```

**Mode Options**:

- `combined` (default): Load both local and core/associated repository requirements
- `core-only`: Load only core/associated repository requirements
- `local-only`: Load only local requirements, ignore cross-repository dependencies

### Combined Traceability

Generate traceability matrices with sponsor/associated repository requirements:

```bash
# Generate trace with sponsor requirements included (default)
elspais trace --mode combined

# Generate trace with only core requirements
elspais trace --mode core

# Filter to specific sponsor
elspais trace --sponsor CAL
```

See [Trace-View documentation](trace-view.md) for enhanced visualization options.

## Configuration Details

### Core Repository

```toml
[project]
name = "core-platform"
type = "core"

[patterns]
id_template = "{prefix}-{type}{id}"
prefix = "REQ"

[patterns.associated]
enabled = true  # Allow associated IDs in traces
```

### Associated Repository

```toml
[project]
name = "associated-callisto"
type = "associated"

[associated]
prefix = "CAL"
id_range = [1, 99999]  # Allowed ID range

[core]
# Local path (relative to repo root)
path = "../core-platform"

# Or remote URL (for CI environments)
# remote = "git@github.com:org/core-platform.git"
# branch = "main"

[rules.hierarchy]
# Associated can implement core requirements
cross_repo_implements = true
```

### `.core-repo` File

Alternative to config, create a `.core-repo` file:

```text
../core-platform
```

This takes precedence over the config file path.

## CLI-Based Associate Registration

Instead of manually editing configuration files, register associate repositories via the CLI. This is especially useful in CI/CD pipelines where repos are cloned to varying paths.

### Register an Associate

```bash
# In the core repository
cd core-platform/

# Register an associate by its filesystem path
elspais config add associates.paths /path/to/associated-callisto
```

This appends the path to the `associates.paths` array in `.elspais.toml`. The tool then auto-discovers the associate's identity (name, prefix, spec directory) by reading that repo's `.elspais.toml`.

### How Discovery Works

When a path is registered, elspais reads `{path}/.elspais.toml` and checks:

1. The file exists
2. `project.type` is `"associated"`
3. `[associated] prefix` is set

If any check fails, a clear error message is returned (e.g., `"Associate path does not exist: /bad/path"`).

### Error Handling

Invalid paths produce structured errors that callers can inspect:

```bash
# This registers the path but discovery will fail at validate time
elspais config add associates.paths /nonexistent/repo
elspais validate --mode combined
# Error: Associate path does not exist: /nonexistent/repo
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Validate Requirements

on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # Checkout associate repos for combined validation
      - uses: actions/checkout@v4
        with:
          repository: org/associated-callisto
          path: associated-callisto

      - name: Install elspais
        run: pip install elspais==${{ vars.ELSPAIS_VERSION }}

      # Register associates by path (auto-discovers identity)
      - name: Register associates
        run: elspais config add associates.paths associated-callisto

      - name: Validate
        run: elspais validate --mode combined
```

## Manifest Mode (Future)

For organizations with many repositories:

```yaml
# ~/.config/elspais/manifest.yml
core:
  path: ~/repos/core-platform
  remote: git@github.com:org/core-platform.git

associated:
  - prefix: CAL
    path: ~/repos/associated-callisto
    remote: git@github.com:org/associated-callisto.git

  - prefix: XYZ
    path: ~/repos/associated-xyz
    remote: git@github.com:org/associated-xyz.git
```

Commands will operate across all repositories:

```bash
# Planned commands (not yet implemented):
# elspais validate --all
# elspais trace --combined
# elspais analyze cross-repo
```

## Best Practices

1. **Core requirements are immutable**: Once published, don't change core REQ IDs
2. **Version your core**: Use git tags to version core requirements
3. **Document cross-references**: Make associated → core links explicit
4. **Separate ID ranges**: Give each associated repo a distinct ID range
5. **CI validation**: Always validate against core in CI/CD
6. **Sync core updates**: Regularly pull core updates to associated repos
