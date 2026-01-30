# MASTER PLAN: CLI Auto-Fix Commands + Documentation

## Phase 0: Document [ignore] Pattern Syntax

### Background

The `[ignore]` config uses Python's `fnmatch` module, which requires patterns to match from the start of the path. This differs from gitignore behavior where patterns match anywhere.

**Decision**: Document fnmatch behavior rather than change code (simpler, more explicit).

### Correct Pattern Usage

| Pattern | Matches | Notes |
|---------|---------|-------|
| `roadmap/**` | ❌ `spec/roadmap/file.md` | fnmatch matches from start |
| `**/roadmap/**` | ✅ `spec/roadmap/file.md` | Explicit "anywhere" pattern |
| `spec/roadmap/**` | ✅ `spec/roadmap/file.md` | Full path from repo root |

### Implementation

**Create**: `docs/cli/ignore.md`

```markdown
# Ignore Configuration

The `[ignore]` section controls which files are skipped during scanning.

## Pattern Syntax

Patterns use Python's `fnmatch` module (similar to shell globs):
- `*` matches any characters within a path component
- `**` matches across directory separators
- `?` matches a single character

**Important**: Patterns match from the START of the path, not anywhere.

## Examples

```toml
[ignore]
# Skip files anywhere named "README.md"
spec = ["README.md", "INDEX.md"]

# Skip a directory at any depth - use **/ prefix
spec = ["**/roadmap/**"]

# Skip a specific path from repo root
spec = ["spec/archive/**"]

# Skip by extension
global = ["*.pyc", "*.tmp"]
```

## Scopes

- `global` - Applied to all scanning
- `spec` - Applied when scanning spec directories
- `code` - Applied when scanning code directories
- `test` - Applied when scanning test directories
```

### Verification

```bash
# Run doc sync test
pytest tests/test_doc_sync.py -v
```

### Commit Message

```
[CUR-240] docs: Document [ignore] pattern syntax (fnmatch behavior)

Added docs/cli/ignore.md explaining:
- fnmatch pattern syntax (matches from start of path)
- Correct patterns for matching anywhere (**/dir/**)
- Scope-specific ignore rules (global, spec, code, test)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

---

## Overview

Add CLI commands that leverage the existing MCP file mutation infrastructure to auto-fix common issues.

**Prerequisite**: MCP File Mutation Tools (v0.39.0) already provide:
- `change_reference_type()` - Modify Implements/Refines in spec files
- `move_requirement()` - Relocate requirements between files
- Safety branch utilities for rollback

## Feature 1: `elspais hash update`

Update requirement hashes to match current body content.

### Use Cases
- After editing requirement body text
- Bulk update after format migration
- CI/CD to verify hashes are current

### CLI Interface
```bash
# Update all stale hashes
elspais hash update

# Update specific requirement
elspais hash update REQ-d00001

# Dry-run: show what would change
elspais hash update --dry-run

# JSON output for scripting
elspais hash update --json
```

### Implementation

**File:** `src/elspais/commands/hash_cmd.py` (already exists, needs `_update_hashes` implementation)

```python
def _update_hashes(graph, args) -> int:
    """Update hashes in spec files."""
    from elspais.utilities.hasher import calculate_hash
    from elspais.mcp.file_mutations import update_hash_in_file  # New function

    dry_run = getattr(args, "dry_run", False)
    req_id = getattr(args, "req_id", None)

    updates = []
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if req_id and node.id != req_id:
            continue

        stored_hash = node.get_field("hash")
        body = _get_requirement_body(node)  # Extract body text
        computed_hash = calculate_hash(body)

        if stored_hash != computed_hash:
            updates.append({
                "id": node.id,
                "old_hash": stored_hash,
                "new_hash": computed_hash,
                "file": node.source.path,
            })

    if dry_run:
        for u in updates:
            print(f"{u['id']}: {u['old_hash']} -> {u['new_hash']}")
        return 0

    for u in updates:
        update_hash_in_file(u["file"], u["id"], u["new_hash"])

    print(f"Updated {len(updates)} hash(es)")
    return 0
```

### New File Mutation Helper

**File:** `src/elspais/mcp/file_mutations.py` (new)

```python
def update_hash_in_file(file_path: Path, req_id: str, new_hash: str) -> bool:
    """Update the hash in a spec file for a requirement.

    Finds the end marker line: *End* *REQ-xxx* | **Hash**: old_hash
    And updates to: *End* *REQ-xxx* | **Hash**: new_hash
    """
    content = file_path.read_text()

    # Pattern: *End* *REQ-xxx* | **Hash**: xxxxxxxx
    pattern = re.compile(
        rf"(\*End\*\s+\*{re.escape(req_id)}\*\s*\|\s*\*\*Hash\*\*:\s*)([a-fA-F0-9]+)"
    )

    new_content, count = pattern.subn(rf"\g<1>{new_hash}", content)

    if count > 0:
        file_path.write_text(new_content)
        return True
    return False
```

---

## Feature 2: `elspais validate --fix`

Auto-fix validation issues that can be corrected programmatically.

### Fixable Issues
- Missing hash → compute and insert
- Outdated hash → recompute from body content
- Missing `Status:` field → add default "Active"

### Non-Fixable Issues (report only)
- Broken references to non-existent requirements
- Orphaned requirements (no parent)
- Circular dependencies
- Malformed requirement IDs

### CLI Interface
```bash
# Show what would be fixed
elspais validate --fix --dry-run

# Fix all auto-fixable issues
elspais validate --fix

# Fix and show details
elspais validate --fix -v
```

### Implementation

**File:** `src/elspais/commands/validate.py`

Add `--fix` argument and fix logic:

```python
def add_arguments(parser: argparse.ArgumentParser) -> None:
    # ... existing args ...
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix issues that can be corrected programmatically",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be fixed without making changes",
    )

def _auto_fix_issues(graph, issues, dry_run: bool) -> list[dict]:
    """Apply automatic fixes for supported issue types."""
    from elspais.mcp.file_mutations import update_hash_in_file, add_status_to_file

    fixed = []
    for issue in issues:
        if issue["type"] == "missing_hash":
            if not dry_run:
                update_hash_in_file(issue["file"], issue["req_id"], issue["computed_hash"])
            fixed.append(issue)
        elif issue["type"] == "outdated_hash":
            if not dry_run:
                update_hash_in_file(issue["file"], issue["req_id"], issue["computed_hash"])
            fixed.append(issue)
        elif issue["type"] == "missing_status":
            if not dry_run:
                add_status_to_file(issue["file"], issue["req_id"], "Active")
            fixed.append(issue)
    return fixed
```

---

## Files to Create/Modify

### New Files
1. `src/elspais/mcp/file_mutations.py` - File mutation helper functions
   - `update_hash_in_file()`
   - `add_status_to_file()`
   - `insert_hash_line()` (for missing hash)

### Modified Files
1. `src/elspais/commands/hash_cmd.py` - Implement `_update_hashes()`
2. `src/elspais/commands/validate.py` - Add `--fix` and `--dry-run` flags
3. `docs/cli/hash.md` - Document hash update command
4. `docs/cli/validate.md` - Document --fix flag

### Tests
1. `tests/commands/test_hash_update.py` - Hash update tests
2. `tests/commands/test_validate_fix.py` - Validate --fix tests

---

## Verification

```bash
# Test hash update
elspais hash update --dry-run
elspais hash update
elspais hash verify  # Should show no mismatches

# Test validate --fix
elspais validate --fix --dry-run
elspais validate --fix
elspais validate  # Should show fewer issues

# Full test suite
pytest tests/ -x --tb=short
```

---

## Commit Messages

### Phase 1: Hash Update
```
[CUR-240] feat: Implement elspais hash update command

Add ability to update requirement hashes in spec files:
- elspais hash update: Update all stale hashes
- elspais hash update REQ-xxx: Update specific requirement
- --dry-run: Show changes without applying
- --json: Machine-readable output

Uses new file_mutations.py helper for safe file updates.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

### Phase 2: Validate --fix
```
[CUR-240] feat: Add --fix flag to elspais validate

Auto-fix validation issues that can be corrected programmatically:
- Missing hash: Compute and insert
- Outdated hash: Recompute from body
- Missing Status: Add default "Active"

Non-fixable issues (broken refs, orphans) are reported only.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```
