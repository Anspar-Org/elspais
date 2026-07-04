# REQUIREMENT HIERARCHY

## The Levels

The built-in default hierarchy is **PRD -> OPS -> DEV**:

  **PRD (Product)**    - Business needs, user outcomes
                     "What the product must achieve"

  **OPS (Operations)** - Operational constraints, compliance
                     "How the system must behave operationally"

  **DEV (Development)** - Technical specifications
                     "How we implement it technically"

## Levels Are Configurable

PRD/OPS/DEV is a **default exemplar**, not a fixed law. Levels are
defined in `[levels]` in `.elspais.toml` (each with a rank and an
`implements` list), so a project can add tiers -- e.g. an apex framing
level above PRD, or a presentation level between PRD and DEV -- or use an
entirely different set. Choose the schema that fits your project.

A level is an **altitude and audience**, not a measure of testability.
Leaf-ness (whether an obligation is directly testable) is independent of
level: a high-level obligation can be a directly testable leaf. For the
judgment of when to create a requirement at which level -- and when a
test may cite an abstract parent -- see `elspais docs authoring`.

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

  **Integrates** - Satisfaction is provided by a requirement in a
               configured associate (external library) repo. Coverage
               (implemented/verified) is inherited from that library
               requirement. The library is never modified. See
               `elspais docs graph-model` for the INTEGRATES edge.

Use `Refines` when you're adding constraints but the parent still
needs its own implementation.

## Assertion-Specific Implementation

Implement specific assertions, not the whole requirement:

```
**Implements**: REQ-p00001-A    # Just assertion A
**Implements**: REQ-p00001-A+B  # Assertions A and B
```

This gives precise traceability coverage.

## Viewing the Hierarchy

  $ elspais viewer             # Interactive HTML tree (live server)
  $ elspais viewer --static    # Interactive HTML tree (static file)
