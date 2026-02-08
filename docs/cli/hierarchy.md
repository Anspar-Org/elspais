# REQUIREMENT HIERARCHY

## The Three Levels

elspais enforces a **PRD -> OPS -> DEV** hierarchy:

  **PRD (Product)**    - Business needs, user outcomes
                     "What the product must achieve"

  **OPS (Operations)** - Operational constraints, compliance
                     "How the system must behave operationally"

  **DEV (Development)** - Technical specifications
                     "How we implement it technically"

## Implements Relationships

Lower levels **implement** higher levels:

  DEV -> OPS   (DEV implements OPS)
  DEV -> PRD   (DEV implements PRD)
  OPS -> PRD   (OPS implements PRD)

**Never** the reverse: PRD cannot implement DEV.

Example chain:

  `REQ-p00001`: Users can reset passwords (PRD)
       ^
  `REQ-o00001`: Reset tokens expire in 1 hour (OPS)
       ^           Implements: REQ-p00001
  `REQ-d00001`: Tokens use HMAC-SHA256 (DEV)
                   Implements: REQ-o00001

## Implements vs Refines

  **Implements** - Claims to satisfy the parent requirement
               Coverage rolls up in traceability reports

  **Refines**    - Adds detail to parent without claiming satisfaction
               No coverage rollup; just shows relationship

Use `Refines` when you're adding constraints but the parent still
needs its own implementation.

## Assertion-Specific Implementation

Implement specific assertions, not the whole requirement:

```
**Implements**: REQ-p00001-A    # Just assertion A
**Implements**: REQ-p00001-A-B  # Assertions A and B
```

This gives precise traceability coverage.

## Viewing the Hierarchy

  $ elspais analyze hierarchy  # ASCII tree view
  $ elspais trace --view       # Interactive HTML
