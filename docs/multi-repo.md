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

### Sponsor Repository

Extensions or customizations that reference the core:

```toml
# .elspais.toml in sponsor repo
[project]
name = "sponsor-callisto"
type = "sponsor"

[sponsor]
prefix = "CAL"

[core]
path = "../core-platform"
```

- Requirements use sponsor format: `REQ-CAL-d00001`
- Can reference core requirements in "Implements" field
- Validation checks core repo for referenced requirements

## Directory Structure

```
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
├── sponsor-callisto/        # Sponsor repository
│   ├── .elspais.toml       # type = "sponsor", prefix = "CAL"
│   ├── .core-repo          # Points to ../core-platform
│   ├── spec/
│   │   ├── INDEX.md
│   │   ├── prd-cal.md      # REQ-CAL-p00001
│   │   └── dev-cal.md      # REQ-CAL-d00001 (implements REQ-p00001)
│   └── ...
│
└── sponsor-xyz/             # Another sponsor
    ├── .elspais.toml       # type = "sponsor", prefix = "XYZ"
    └── ...
```

## Cross-Repository References

Sponsor requirements can implement core requirements:

```markdown
### REQ-CAL-d00001: Callisto Authentication

**Level**: Dev | **Implements**: p00001 | **Status**: Active

Implements core user authentication for Callisto sponsor.
```

Here `Implements: p00001` refers to core `REQ-p00001`.

## Validation

### Validate Sponsor Against Core

```bash
# In sponsor repository
cd sponsor-callisto/

# Validate with explicit core path
elspais validate --core-repo ../core-platform

# Or use configured path
elspais validate
```

### What's Validated

1. **Sponsor ID format**: IDs must use sponsor prefix
2. **Core references**: Referenced core IDs must exist
3. **Hierarchy rules**: Sponsor DEV can implement core PRD
4. **Hash verification**: Both core and sponsor hashes

### Validation Output

```
✓ Validating sponsor requirements (CAL)
✓ Loading core requirements from ../core-platform
✓ 15 sponsor requirements found
✓ 8 cross-repository references validated

❌ ERROR REQ-CAL-d00003
   Implements REQ-p99999 which does not exist in core
   File: spec/dev-cal.md:42

✓ 14/15 requirements valid
```

## Combined Traceability

Generate a combined matrix across repositories:

```bash
# From core or any repo
elspais trace --combined --core-repo ../core-platform

# Output includes:
# - Core requirements
# - All sponsor requirements
# - Cross-repo implementation links
```

## Configuration Details

### Core Repository

```toml
[project]
name = "core-platform"
type = "core"

[patterns]
id_template = "{prefix}-{type}{id}"
prefix = "REQ"

[patterns.sponsor]
enabled = true  # Allow sponsor IDs in traces
```

### Sponsor Repository

```toml
[project]
name = "sponsor-callisto"
type = "sponsor"

[sponsor]
prefix = "CAL"
id_range = [1, 99999]  # Allowed ID range

[core]
# Local path (relative to repo root)
path = "../core-platform"

# Or remote URL (for CI environments)
# remote = "git@github.com:org/core-platform.git"
# branch = "main"

[rules.hierarchy]
# Sponsor can implement core requirements
cross_repo_implements = true
```

### `.core-repo` File

Alternative to config, create a `.core-repo` file:

```
../core-platform
```

This takes precedence over the config file path.

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

      # Checkout core repo for cross-validation
      - uses: actions/checkout@v4
        with:
          repository: org/core-platform
          path: core-platform

      - name: Install elspais
        run: pip install elspais==${{ vars.ELSPAIS_VERSION }}

      - name: Validate
        run: elspais validate --core-repo core-platform
```

## Manifest Mode (Future)

For organizations with many repositories:

```yaml
# ~/.config/elspais/manifest.yml
core:
  path: ~/repos/core-platform
  remote: git@github.com:org/core-platform.git

sponsors:
  - prefix: CAL
    path: ~/repos/sponsor-callisto
    remote: git@github.com:org/sponsor-callisto.git

  - prefix: XYZ
    path: ~/repos/sponsor-xyz
    remote: git@github.com:org/sponsor-xyz.git
```

Commands can operate across all repositories:

```bash
# Validate all repos
elspais validate --all

# Generate combined traceability
elspais trace --combined

# Analyze cross-repo dependencies
elspais analyze cross-repo
```

## Best Practices

1. **Core requirements are immutable**: Once published, don't change core REQ IDs
2. **Version your core**: Use git tags to version core requirements
3. **Document cross-references**: Make sponsor → core links explicit
4. **Separate ID ranges**: Give each sponsor a distinct ID range
5. **CI validation**: Always validate against core in CI/CD
6. **Sync core updates**: Regularly pull core updates to sponsors
