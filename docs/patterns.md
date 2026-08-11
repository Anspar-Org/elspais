# Requirement ID Patterns

elspais supports flexible requirement ID formats to match your organization's conventions.

## Pattern Template

The `canonical` key in `[id-patterns]` defines the structure of requirement IDs
using tokens:

| Token | Description | Example Value |
|-------|-------------|---------------|
| `{namespace}` | Base namespace from `project.namespace` | `REQ`, `PROJ` |
| `{level.letter}` | The `letter` declared by the matching `[levels.*]` section | `p`, `P`, `d` |
| `{type}` | The `[levels.*]` section name itself | `prd`, `PRD`, `dev` |
| `{component}` | Unique identifier (number or name) | `00001`, `123`, `UserAuth` |

## Common Patterns

### Pattern 1: Standard (`REQ-p00001`)

```toml
[project]
namespace = "REQ"
name = "my-project"

[levels.prd]
rank = 1
letter = "p"
implements = ["prd"]

[levels.ops]
rank = 2
letter = "o"
implements = ["ops", "prd"]

[levels.dev]
rank = 3
letter = "d"
implements = ["dev", "ops", "prd"]

[id-patterns]
canonical = "{namespace}-{level.letter}{component}"

[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true
```

**Examples:**

- `REQ-p00001` - Product requirement
- `REQ-o00015` - Operations requirement
- `REQ-d00127` - Development requirement

### Pattern 2: With Associated Prefix (`REQ-CAL-d00001`)

```toml
[project]
namespace = "REQ"
name = "my-project"

[id-patterns]
canonical = "{namespace}-{level.letter}{component}"

[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true

[id-patterns.associated]
enabled = true
position = "after_prefix"
format = "uppercase"
length = 3
separator = "-"
```

**Examples:**

- `REQ-CAL-p00001` - Callisto product requirement
- `REQ-XYZ-d00042` - XYZ associated dev requirement
- `REQ-p00001` - Core requirement (no associated prefix)

### Pattern 3: Type-Prefix Style (`PRD-00001`)

```toml
[project]
namespace = "REQ"
name = "my-project"

[levels.PRD]
rank = 1
letter = "P"
implements = ["PRD"]

[levels.OPS]
rank = 2
letter = "O"
implements = ["OPS", "PRD"]

[levels.DEV]
rank = 3
letter = "D"
implements = ["DEV", "OPS", "PRD"]

[id-patterns]
canonical = "{type}-{component}"

[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true
```

**Examples:**

- `PRD-00001` - Product requirement
- `OPS-00042` - Operations requirement
- `DEV-00127` - Development requirement

### Pattern 4: Jira-Like (`PROJ-123`)

```toml
[project]
namespace = "PROJ"       # Change per project
name = "my-project"

[levels.req]
rank = 1
letter = "r"
implements = ["req"]

[id-patterns]
canonical = "{namespace}-{component}"

[id-patterns.component]
style = "numeric"
digits = 0            # Variable length
leading_zeros = false
```

**Examples:**

- `PROJ-1` - First requirement
- `PROJ-42` - Requirement 42
- `PROJ-1234` - Requirement 1234

### Pattern 5: Named Requirements (`REQ-UserAuth`)

```toml
[project]
namespace = "REQ"
name = "my-project"

[levels.req]
rank = 1
letter = "r"
implements = ["req"]

[id-patterns]
canonical = "{namespace}-{component}"

[id-patterns.component]
style = "PascalCase"
```

**Examples:**

- `REQ-UserAuthentication`
- `REQ-DataExport`
- `REQ-AuditLog`

### Pattern 6: Custom Regex (`REQ-PAB123`)

```toml
[project]
namespace = "REQ"
name = "my-project"

[levels.prd]
rank = 1
letter = "P"
implements = ["prd"]

[levels.dev]
rank = 3
letter = "D"
implements = ["dev", "prd"]

[id-patterns]
canonical = "{namespace}-{level.letter}{component}"

[id-patterns.component]
style = "regex"
pattern = "[A-Z]{2}[0-9]{3}"  # 2 letters + 3 digits
```

**Examples:**

- `REQ-PAB123` - Product requirement AB123
- `REQ-DXY456` - Dev requirement XY456

## Level Configuration

Each level is its own `[levels.<name>]` section. The section name is the level's
canonical code (the `{type}` token).

| Property | Description | Required |
|----------|-------------|----------|
| `rank` | Hierarchy rank (1 = highest) | Yes |
| `letter` | Single-character code used in IDs (the `{level.letter}` token) | Yes |
| `implements` | Level names this level may implement | Yes |
| `display_name` | Display name | No |
| `color` | Hex color for the viewer | No |
| `expects_validation` | Requirements at this level are expected to have UAT validation | No |

```toml
[levels.prd]
rank = 1
letter = "p"
display_name = "Product Requirement"
implements = ["prd"]

[levels.ops]
rank = 2
letter = "o"
display_name = "Operations Requirement"
implements = ["ops", "prd"]

[levels.dev]
rank = 3
letter = "d"
display_name = "Development Requirement"
implements = ["dev", "ops", "prd"]
```

### Level Rules

Each level's `implements` list names the levels it is allowed to reference. In
the configuration above, `dev` may implement `dev`, `ops`, and `prd`, while
`prd` may implement only `prd` — so "DEV can implement PRD" is allowed and
"PRD can implement DEV" is not.

## Component Format Options

`[id-patterns.component]` accepts `style`, plus the keys the chosen style uses:

| Key | Applies to | Description |
|-----|------------|-------------|
| `style` | all | `numeric`, `camelCase`, `PascalCase`, `snake_case`, `kebab-case`, or `regex` |
| `digits` | `numeric` | Maximum number of digits (0 = variable) |
| `leading_zeros` | `numeric` | Pad with zeros: `00001` vs `1` |
| `pattern` | `regex` | Regex the component must match (required for `regex`) |
| `max_length` | all | Accepted but not currently enforced |

### Numeric (`style = "numeric"`)

```toml
[id-patterns.component]
style = "numeric"
digits = 5           # Maximum number of digits (0 = variable)
leading_zeros = true # Pad with zeros: 00001 vs 1
```

### Named (`style = "PascalCase"`)

Also available: `camelCase`, `snake_case`, `kebab-case`.

```toml
[id-patterns.component]
style = "PascalCase"
```

### Custom Regex (`style = "regex"`)

```toml
[id-patterns.component]
style = "regex"
pattern = "[A-Z]{2}[0-9]{3}"  # Required for this style
```

## Associated Prefix Configuration

For multi-repository setups with associated namespaces:

```toml
[id-patterns.associated]
enabled = true            # Enable associated prefixes
position = "after_prefix" # "after_prefix" | "before_prefix"
format = "uppercase"      # "uppercase" | "lowercase" | "mixed"
length = 3                # Fixed length
separator = "-"           # Separator character
```

## Validation

elspais validates IDs against the configured pattern:

```text
# Valid IDs (with the standard pattern above)
REQ-p00001  ✓
REQ-d00042  ✓
REQ-o99999  ✓
REQ-p1      ✓  # Accepted and normalized to REQ-p00001

# Invalid IDs
REQ-x00001  ✗  # Unknown level letter 'x'
REQ-p123456 ✗  # More digits than `digits` allows
REQ00001    ✗  # Missing separator
req-p00001  ✗  # Wrong case
```

## Migration Between Patterns

When changing ID patterns, use the `elspais migrate` command (future feature) to update existing requirements:

```bash
# Preview migration
elspais migrate --from "REQ-{type}{id}" --to "{type}-{id}" --dry-run

# Execute migration
elspais migrate --from "REQ-{type}{id}" --to "{type}-{id}"
```

For now, manual migration is required when changing patterns.
