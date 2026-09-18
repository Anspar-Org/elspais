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

The graph builder clones the template subtree rooted at the target -- the
target REQ with its assertions, plus every template REQ that refines a member,
recursively, with theirs -- into the declaring node's scope with composite IDs
of the form `declaring_id::original_id`. Each clone gets `Stereotype.INSTANCE`
and an INSTANCE edge back to its template original, and the STRUCTURES and
REFINES edges among the originals are recreated among the clones.

## Cross-repo Satisfies

For templates owned by an associated repository, add the upstream repo to
`[associates.*]` in `.elspais.toml` and use the upstream namespace:

```toml
[associates.library]
path = "../library"
namespace = "LIB"
```

The federated graph builder then:

- Clones the template subtree -- the target REQ with its assertions and every
  template REQ refining a member, recursively -- into the declaring repo's
  index with composite IDs (`APP-p00001::LIB-p00001`,
  `APP-p00001::LIB-p00001-A`, ...).
- Wires intra-graph `SATISFIES`, `STRUCTURES`, `REFINES` and `DEFINES` edges
  in the declaring repo.
- Wires cross-graph `INSTANCE` edges from each clone to its template original.
- Records `template_repo` on each clone so viewers can show
  "Template defined in `<repo>`".

A template subtree may span repositories: a template REQ in the declaring
repo that refines a template owned by an associate is a member of that
template's subtree, and a `Satisfies:` against the associate's template
clones it too. Each clone records the repository owning its own original,
so the clones of one subtree may name different repositories.

Federation depth is capped at one: the template's repo must be a direct
associate.

## Cross-cutting evidence

CODE and TEST may target template assertions **directly** -- you do NOT
write the composite ID:

```python
# library/src/dispatch.py
# Implements: LIB-p00001-A
def parse(payload): ...
```

```python
# library/tests/test_dispatch.py
# Verifies: LIB-p00001-A
def test_parse_rejects_empty(): ...
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
`ReferenceFault` diagnostics for each invalid combination:

| Reference                  | Target    | Outcome                                  |
| -------------------------- | --------- | ---------------------------------------- |
| `Satisfies: X`             | TEMPLATE  | OK                                       |
| `Satisfies: X`             | CONCRETE  | Error (target not marked **Template**)   |
| `Satisfies: X`             | INSTANCE  | Error (chained instantiation)            |
| `Satisfies: X` (cross-repo)| missing   | Error -- diagnostic lists associates     |
| `Refines: X` (from a **Template** REQ) | TEMPLATE | OK -- forms the template subtree |
| `Refines: X` (from any other REQ) | TEMPLATE | Error (a template's refiners must be templates) |
| `Refines: X`               | INSTANCE  | Error (instance is read-only)            |
| `Refines: X` (from a **Template** REQ) | CONCRETE | Error (outside its template subtree) |
| `Refines: X` (from any other REQ) | CONCRETE | OK                                     |
| `Implements: X` (CODE)     | TEMPLATE  | OK -- applies to every satisfier         |
| `Implements: X` (CODE)     | CONCRETE  | OK                                       |
| `Implements: X` (CODE)     | INSTANCE  | Error (composite IDs not author syntax)  |
| `Verifies: X` (TEST)       | TEMPLATE  | OK -- applies to every satisfier         |
| `Verifies: X` (TEST)       | CONCRETE  | OK                                       |
| `Verifies: X` (TEST)       | INSTANCE  | Error                                    |

A template is a subtree: a template REQ refines another template REQ to
decompose one cross-cutting obligation into levels of detail, and a
`Satisfies:` against any member clones the subtree rooted there -- the
member with its assertions, every template REQ refining a member,
recursively, with theirs, and the REFINES edges among them. Template REQs
may not declare `Implements:`, nor `Refines:` against a node outside their
own template subtree; a REQ not marked **Template** may not refine a
template (mark it **Template** to decompose the template, or declare
`Satisfies:` to instantiate it). A `Satisfies:` cycle (transitively across SATISFIES and
INSTANCE edges) is reported once per build with a diagnostic containing
the word `cycle` and the cycle path.

The matrix applies to a target owned by an associated repository exactly as
to one in the declaring repository: a reference the matrix forbids is
reported and never wired, whichever repository owns its target.

All diagnostics surface in `elspais checks` and `elspais unresolved`.

## See also

- `elspais docs checks` -- health-check command reference.
- `[associates.*]` in `docs/configuration.md` -- declaring associated repos.
- `REQ-p00014` (Satisfies Relationship) -- the canonical specification.
