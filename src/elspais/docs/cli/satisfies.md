# Satisfies (cross-cutting templates)

`Satisfies: <TEMPLATE_ID>` declares that the current requirement is a
sponsor- or app-specific instance of a templated cross-cutting requirement
(regulatory compliance, security policy, accessibility standard, operational
baseline). One template is authored once; every downstream subsystem
"satisfies" it by reference.

## Marking templates

A template REQ must be marked at the source with the no-value `**Template**`
flag on the metadata line. Markdown decoration is optional; the parser
matches the bare word `Template` after a separator:

```text
# LIB-p00001: Action Dispatch
**Level**: PRD | **Status**: Approved | **Template**

A. SHALL parse, validate, authorize.
B. SHALL deny duplicate submissions.

*End* *Action Dispatch*
```

The parser sets `Stereotype.TEMPLATE` on the REQ and on each of its
*Assertions*. The render protocol emits the flag verbatim on the metadata
line for any template node, so it round-trips through `elspais fix`.

## In-repo Satisfies

In the same repo, declare `Satisfies:` on the downstream concrete REQ:

```text
# APP-p00001: Concrete Action
**Level**: PRD | **Status**: Approved
**Satisfies**: LIB-p00001

A. SHALL require admin role.

*End* *Concrete Action*
```

The graph builder clones the template REQ subtree (root plus directly-attached
assertions) into the declaring node's scope with composite IDs of the form
`declaring_id::original_id`. Each clone gets `Stereotype.INSTANCE` and an
INSTANCE edge back to its template original.

## Cross-repo Satisfies

For templates owned by an associated repository, add the upstream repo to
`[associates.*]` in `.elspais.toml` and use the upstream namespace:

```toml
[associates.library]
path = "../library"
namespace = "LIB"
```

The federated graph builder then:

- Clones the template REQ + assertions into the declaring repo's index with
  composite IDs (`APP-p00001::LIB-p00001`, `APP-p00001::LIB-p00001-A`, ...).
- Wires intra-graph `SATISFIES`, `STRUCTURES`, and `DEFINES` edges in the
  declaring repo.
- Wires cross-graph `INSTANCE` edges from each clone to its template original.
- Records `template_repo` on each clone so viewers can show
  "Template defined in `<repo>`".

Federation depth is capped at one: the template's repo must be a direct
associate.

## Cross-cutting evidence

CODE and TEST may target template assertions **directly** -- you do NOT
write the composite ID:

```python
# library/src/dispatch.py
# Implements: LIB-p00001-A
def parse(payload):
    ...
```

```python
# library/tests/test_dispatch.py
# Verifies: LIB-p00001-A
def test_parse_rejects_empty():
    ...
```

This evidence applies to **every satisfier** of the template. Every instance
assertion across every downstream repo inherits the covered status via the
INSTANCE edge that connects each clone to its template original. The library
author writes the contract test once; every satisfier inherits coverage.

When you need instance-specific behaviour on top of the template (admin-role
check, confirmation token, tenant-id provenance), add an own concrete
assertion to your satisfier and implement/verify it directly:

```text
# APP-p00001: Concrete Action
**Level**: PRD | **Status**: Approved
**Satisfies**: LIB-p00001

A. SHALL require admin role.
```

```python
# app/src/create_user.py
# Implements: APP-p00001-A
def create_user(payload):
    require_admin()
    ...
```

The satisfier rollup combines own coverage with the inherited template
coverage: a satisfier with one uncovered own assertion and a fully covered
template reports partial coverage until the own assertion is implemented.

## Coverage semantics

Coverage on an INSTANCE *Assertion* is computed as a query over the
INSTANCE edge -- it is NOT a separate metric stored on the clone:

- `inherited_coverage_for(instance)` walks the outbound INSTANCE edge to
  the template original and returns its direct coverage.
- A satisfier REQ's rollup combines its own concrete-assertion coverage
  with the inherited coverage of each clone's assertions.

This invariant means edits to the template's covering CODE/TEST flow
through to every satisfier on the next build, with no per-instance
re-implementation.

## Validation matrix

The builder enforces this matrix at build time, raising typed
`BrokenReference` diagnostics for each invalid combination:

| Reference                  | Target    | Outcome                                  |
| -------------------------- | --------- | ---------------------------------------- |
| `Satisfies: X`             | TEMPLATE  | OK                                       |
| `Satisfies: X`             | CONCRETE  | Error (target not marked **Template**)   |
| `Satisfies: X`             | INSTANCE  | Error (chained instantiation)            |
| `Satisfies: X` (cross-repo)| missing   | Error -- diagnostic lists associates     |
| `Refines: X`               | TEMPLATE  | Error (compositing templates)            |
| `Refines: X`               | INSTANCE  | Error (instance is read-only)            |
| `Refines: X`               | CONCRETE  | OK                                       |
| `Implements: X` (CODE)     | TEMPLATE  | OK -- applies to every satisfier         |
| `Implements: X` (CODE)     | CONCRETE  | OK                                       |
| `Implements: X` (CODE)     | INSTANCE  | Error (composite IDs not author syntax)  |
| `Verifies: X` (TEST)       | TEMPLATE  | OK -- applies to every satisfier         |
| `Verifies: X` (TEST)       | CONCRETE  | OK                                       |
| `Verifies: X` (TEST)       | INSTANCE  | Error                                    |

Template REQs may not declare their own `Implements:` / `Refines:` against
nodes outside their template subtree, and they may not be the target of an
inbound `Refines:`. A `Satisfies:` cycle (transitively across SATISFIES and
INSTANCE edges) is reported once per build with a diagnostic containing
the word `cycle` and the cycle path.

All diagnostics surface in `elspais health` and `elspais checks`.

## See also

- `elspais docs checks` -- health-check command reference.
- `[associates.*]` in `docs/configuration.md` -- declaring associated repos.
- `REQ-p00014` (Satisfies Relationship) -- the canonical specification.
