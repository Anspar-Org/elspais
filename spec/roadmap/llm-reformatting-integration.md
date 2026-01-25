# LLM-Assisted Reformatting Integration

**Parent**: [requirements-format-enhancements.md](./requirements-format-enhancements.md)
**Date**: 2026-01-04
**Ticket**: CUR-514

---

## Decision

Integrate reformatting capability into elspais with custom handler fallback.

## Problem

The `reformat_reqs` tool currently requires Claude Code. Users may want to use different LLMs or traditional scripts.

---

## Solution Architecture

```
elspais reformat REQ-p00043
         │
         ├── Claude Code available? → Use built-in Claude integration
         │
         └── Not available? → Check for custom handler
                    │
                    ├── Handler configured? → Load and execute
                    │
                    └── Not configured? → Emit helpful error with options
```

---

## Configuration

```toml
# .elspais.toml
[reformat]
# Default: use Claude Code if available
# Custom: provide path to Python module with handler function
handler = "tools/custom_reformatter.py:reformat_requirement"
```

---

## Custom Handler Interface

```python
# tools/custom_reformatter.py
def reformat_requirement(
    req_id: str,
    title: str,
    body: str,
    rationale: str | None
) -> dict:
    """
    Transform requirement content to assertion-based format.

    Args:
        req_id: Requirement ID (e.g., "REQ-p00043")
        title: Requirement title
        body: Current requirement body text
        rationale: Existing rationale if present

    Returns:
        {
            "rationale": str,  # New or refined rationale
            "assertions": list[str]  # List of assertion statements
        }
    """
    # Implementation using any method:
    # - Different LLM API (OpenAI, local model, etc.)
    # - Rule-based transformation
    # - Template-based approach
    pass
```

---

## Error Message When No Handler

```
Error: Claude Code not configured and no custom handler specified.

To use LLM-assisted reformatting, either:
1. Configure Claude Code (see: https://claude.ai/code)
2. Provide a custom handler in .elspais.toml:

   [reformat]
   handler = "path/to/handler.py:function_name"

   The handler function should accept (req_id, title, body, rationale)
   and return {"rationale": str, "assertions": list[str]}

   See: docs/elspais-custom-handlers.md for examples.
```

---

## Implementation Phase

**Phase 4** (8-16 hours):

1. Integrate reformat_reqs functionality into elspais
2. Add custom handler fallback mechanism
3. Implement helpful error messages
4. Document custom handler interface

**Deliverables**:
- `elspais reformat` command
- Custom handler documentation
- Example handlers (OpenAI, rule-based)
