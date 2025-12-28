# Requirement ID Patterns

elspais supports flexible requirement ID formats to match your organization's conventions.

## Pattern Template

The `id_template` configuration defines the structure of requirement IDs using tokens:

| Token | Description | Example Value |
|-------|-------------|---------------|
| `{prefix}` | Base prefix from `patterns.prefix` | `REQ`, `PROJ` |
| `{type}` | Requirement type identifier | `p`, `PRD`, `dev` |
| `{associated}` | Associated repo namespace (if enabled) | `CAL`, `XYZ` |
| `{id}` | Unique identifier (number or name) | `00001`, `123`, `UserAuth` |

## Common Patterns

### Pattern 1: HHT Default (`REQ-p00001`)

```toml
[patterns]
id_template = "{prefix}-{type}{id}"
prefix = "REQ"

[patterns.types]
prd = { id = "p", name = "Product Requirement", level = 1 }
ops = { id = "o", name = "Operations Requirement", level = 2 }
dev = { id = "d", name = "Development Requirement", level = 3 }

[patterns.id_format]
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
[patterns]
id_template = "{prefix}-{associated}{type}{id}"
prefix = "REQ"

[patterns.associated]
enabled = true
position = "after_prefix"
format = "uppercase"
length = 3
separator = "-"

[patterns.types]
prd = { id = "p", level = 1 }
ops = { id = "o", level = 2 }
dev = { id = "d", level = 3 }

[patterns.id_format]
style = "numeric"
digits = 5
leading_zeros = true
```

**Examples:**
- `REQ-CAL-p00001` - Callisto product requirement
- `REQ-XYZ-d00042` - XYZ associated dev requirement
- `REQ-p00001` - Core requirement (no associated prefix)

### Pattern 3: Type-Prefix Style (`PRD-00001`)

```toml
[patterns]
id_template = "{type}-{id}"

[patterns.types]
PRD = { id = "PRD", name = "Product Requirement", level = 1 }
OPS = { id = "OPS", name = "Operations Requirement", level = 2 }
DEV = { id = "DEV", name = "Development Requirement", level = 3 }
TST = { id = "TST", name = "Test Requirement", level = 3 }

[patterns.id_format]
style = "numeric"
digits = 5
leading_zeros = true
```

**Examples:**
- `PRD-00001` - Product requirement
- `OPS-00042` - Operations requirement
- `DEV-00127` - Development requirement
- `TST-00003` - Test requirement

### Pattern 4: Jira-Like (`PROJ-123`)

```toml
[patterns]
id_template = "{prefix}-{id}"
prefix = "PROJ"  # Change per project

[patterns.types]
req = { id = "", name = "Requirement", level = 1 }

[patterns.id_format]
style = "numeric"
digits = 0  # Variable length
leading_zeros = false
```

**Examples:**
- `PROJ-1` - First requirement
- `PROJ-42` - Requirement 42
- `PROJ-1234` - Requirement 1234

### Pattern 5: Named Requirements (`REQ-UserAuth`)

```toml
[patterns]
id_template = "{prefix}-{id}"
prefix = "REQ"

[patterns.types]
req = { id = "", name = "Requirement", level = 1 }

[patterns.id_format]
style = "named"
pattern = "[A-Z][a-zA-Z0-9]+"  # PascalCase
max_length = 32
```

**Examples:**
- `REQ-UserAuthentication`
- `REQ-DataExport`
- `REQ-AuditLog`

### Pattern 6: Alphanumeric (`REQ-AB123`)

```toml
[patterns]
id_template = "{prefix}-{type}{id}"
prefix = "REQ"

[patterns.types]
prd = { id = "P", level = 1 }
ops = { id = "O", level = 2 }
dev = { id = "D", level = 3 }

[patterns.id_format]
style = "alphanumeric"
pattern = "[A-Z]{2}[0-9]{3}"  # 2 letters + 3 digits
```

**Examples:**
- `REQ-PAB123` - Product requirement AB123
- `REQ-DXY456` - Dev requirement XY456

## Type Configuration

Each requirement type needs:

| Property | Description | Required |
|----------|-------------|----------|
| `id` | Identifier used in IDs | Yes |
| `name` | Display name | No |
| `level` | Hierarchy level (1=highest) | Yes |

```toml
[patterns.types]
prd = { id = "p", name = "Product Requirement", level = 1 }
ops = { id = "o", name = "Operations Requirement", level = 2 }
dev = { id = "d", name = "Development Requirement", level = 3 }
```

### Level Rules

- **Level 1**: Root requirements (can only implement other level 1)
- **Level 2**: Mid-level (can implement level 1 and 2)
- **Level 3**: Leaf requirements (can implement levels 1, 2, and 3)

This enables validation rules like "DEV can implement PRD" while forbidding "PRD can implement DEV".

## ID Format Options

### Numeric (`style = "numeric"`)

```toml
[patterns.id_format]
style = "numeric"
digits = 5           # Number of digits (0 = variable)
leading_zeros = true # Pad with zeros: 00001 vs 1
```

### Named (`style = "named"`)

```toml
[patterns.id_format]
style = "named"
pattern = "[A-Z][a-zA-Z0-9]+"  # Regex pattern
max_length = 32                 # Maximum characters
allowed_chars = "A-Za-z0-9-"    # Alternative to pattern
```

### Alphanumeric (`style = "alphanumeric"`)

```toml
[patterns.id_format]
style = "alphanumeric"
pattern = "[A-Z]{2}[0-9]{3}"  # Strict regex pattern
```

## Associated Prefix Configuration

For multi-repository setups with associated namespaces:

```toml
[patterns.associated]
enabled = true           # Enable associated prefixes
position = "after_prefix" # Where to place associated prefix
format = "uppercase"     # "uppercase" | "lowercase" | "mixed"
length = 3              # Fixed length (null for variable)
separator = "-"         # Separator character
```

### Associated Position Options

- `after_prefix`: `REQ-CAL-d00001` (prefix-associated-type-id)
- `before_type`: `REQ-CAL-d00001` (same effect, semantic difference)
- `none`: `REQ-d00001` (no associated prefix in ID)

## Validation

elspais validates IDs against the configured pattern:

```python
# Valid IDs (with HHT default pattern)
REQ-p00001  ✓
REQ-d00042  ✓
REQ-o99999  ✓

# Invalid IDs
REQ-x00001  ✗  # Unknown type 'x'
REQ-p1      ✗  # Wrong digit count
REQ00001    ✗  # Missing separator
req-p00001  ✗  # Wrong case (if configured)
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
