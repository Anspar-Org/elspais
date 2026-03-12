# Cross-Cutting Requirements: Satisfies Relationship

This document specifies the `Satisfies:` edge type and the NOT APPLICABLE status for template assertions. Coverage model assertions are in REQ-d00069; change detection is in REQ-p00004-G.

---

## REQ-p00014: Satisfies Relationship

**Level**: PRD | **Status**: Draft | **Implements**: REQ-p00001

## Rationale

Cross-cutting concerns — regulatory compliance frameworks, security policies, accessibility standards, operational baselines — define obligations that multiple independent subsystems must satisfy. The `Satisfies:` relationship enables a template-instance pattern: a set of requirements is defined once as a reusable template, and individual subsystems declare that they satisfy it. When a requirement declares `Satisfies: X`, the graph builder clones the template's REQ subtree with composite IDs, creating instance nodes that participate in normal coverage computation. A `Stereotype` enum (`CONCRETE`, `TEMPLATE`, `INSTANCE`) classifies nodes, and an `INSTANCE` edge connects each clone to its template original.

## Assertions

A. The system SHALL support a `Satisfies:` metadata field on requirements. The target MAY be a requirement or a specific assertion.

B. When a requirement declares `Satisfies: X`, the graph builder SHALL clone the template's REQ subtree (all descendant REQs and their assertions) with composite IDs of the form `declaring_id::original_id`. The cloned root SHALL be linked to the declaring requirement via a SATISFIES edge. Internal edges and assertions SHALL be preserved exactly as in the original. Coverage of cloned nodes SHALL use the standard coverage mechanism — no special computation is needed.

C. The system SHALL classify nodes using a `Stereotype` field: `CONCRETE` (default), `TEMPLATE` (original nodes targeted by Satisfies), or `INSTANCE` (cloned copies). Each instance node SHALL have an INSTANCE edge to its template original.

D. The system SHALL attribute `Implements:` references to template assertions to the correct instance by finding a sibling `Implements:` reference to a CONCRETE node in the same source file, walking that node's ancestors to the first node with a `Satisfies:` declaration matching the template, and constructing the instance ID from the declaring node's ID and the referenced node's ID.

*End* *Satisfies Relationship* | **Hash**: a5edc1b2
---

## REQ-p00016: NOT APPLICABLE Status

**Level**: PRD | **Status**: Draft | **Implements**: REQ-p00001

## Rationale

When a cross-cutting template assertion does not apply to a specific subsystem, the declaring requirement must be able to explicitly exclude it. This uses normative assertion language consistent with the rest of the spec system, and follows the same semantics as deprecated status — the assertion is excluded from the coverage denominator.

## Assertions

A. The system SHALL support explicit N/A declarations for template assertions using normative assertions on the declaring requirement (e.g., `REQ-p80001-D SHALL be NOT APPLICABLE`).

B. N/A assertions SHALL be treated the same as deprecated status: they SHALL NOT count toward the coverage target for the relevant template instance.

C. Any `Implements:` references to a N/A assertion SHALL NOT count toward coverage and SHALL produce errors.

*End* *NOT APPLICABLE Status* | **Hash**: b026a15f
---

## Design Details

The sections below are non-normative design notes that elaborate on how the requirements above map to implementation.

### 1. Template Requirements

Templates are ordinary requirements — same format, same parser, same everything. A requirement becomes a template implicitly when another requirement references it via `Satisfies:`. Templates can have internal hierarchy (sub-requirements connected by `Refines:`):

```text
REQ-p80001 (Electronic Signature Standard)
+-- REQ-o80001 (Authentication Requirements) [Refines: REQ-p80001]
|   +-- A: validate signer identity
|   +-- B: two-factor for high-risk operations
+-- REQ-o80002 (Record Integrity) [Refines: REQ-p80001]
|   +-- A: link records to signing events
|   +-- B: tamper-evident storage
+-- REQ-o80003 (Timing) [Refines: REQ-p80001]
    +-- A: include date/time of signature
```

No special ID prefix is required. Any requirement can serve as a template.

### 2. Satisfies Declaration

A requirement declares template compliance using `Satisfies:` in its metadata:

```markdown
## REQ-p00044: Document Management System

**Level**: PRD | **Status**: Active | **Implements**: -

Satisfies: REQ-p80001
```

Multiple templates: `Satisfies: REQ-p80001, REQ-p80010`.

Assertion-level targeting: `Satisfies: REQ-p80001-A` (only that assertion's Refines: subtree must be covered).

### 3. EdgeKind: SATISFIES and INSTANCE

Two edge kinds support the template-instance pattern:

```python
class EdgeKind(Enum):
    IMPLEMENTS = "implements"
    REFINES = "refines"
    VALIDATES = "validates"
    ADDRESSES = "addresses"
    CONTAINS = "contains"
    SATISFIES = "satisfies"    # declaring REQ -> cloned template root
    INSTANCE = "instance"      # cloned node -> original template node
```

`SATISFIES` connects the declaring requirement to the cloned template root. `INSTANCE` connects each cloned node to its original, enabling navigation from templates to their instances. Neither `SATISFIES` nor `INSTANCE` contributes to coverage (`contributes_to_coverage() -> False`) — coverage flows through `Implements:` edges on the cloned instance assertions.

### 4. Stereotype Classification

Nodes are classified using a `Stereotype` enum stored as a field:

```python
class Stereotype(Enum):
    CONCRETE = "concrete"    # default — normal requirement
    TEMPLATE = "template"    # original node targeted by Satisfies
    INSTANCE = "instance"    # cloned copy of a template node
```

A requirement becomes `TEMPLATE` when it is the target of a `Satisfies:` declaration. All REQs and assertions in the template's subtree are also marked `TEMPLATE`. Cloned nodes are marked `INSTANCE`.

### 5. Template Instantiation

When the graph builder processes `Satisfies: REQ-p80001` on `REQ-p00044`:

1. Mark `REQ-p80001` and all descendant REQs and assertions as `stereotype=TEMPLATE`.
2. Clone the template subtree with composite IDs:

```text
REQ-p00044 --SATISFIES--> REQ-p00044::REQ-p80001 (INSTANCE)
                            +--INSTANCE--> REQ-p80001 (TEMPLATE)
                            +--REFINES--> REQ-p00044::REQ-o80001 (INSTANCE)
                            |               +--INSTANCE--> REQ-o80001
                            |               +-- REQ-p00044::REQ-o80001-A
                            |               +-- REQ-p00044::REQ-o80001-B
                            +--REFINES--> REQ-p00044::REQ-o80002 (INSTANCE)
                                            +--INSTANCE--> REQ-o80002
                                            +-- REQ-p00044::REQ-o80002-A
                                            +-- REQ-p00044::REQ-o80002-B
```

3. Coverage works through normal mechanisms — `Implements:` references to instance assertions contribute coverage like any other node.

### 6. Coverage Attribution Algorithm

When code references a template assertion, the system must determine which instance the reference belongs to:

```python
# document_mgmt/auth.py
# Implements: REQ-d00044-A
# Implements: REQ-o80001-A
```

Attribution:

1. `REQ-o80001-A` has `stereotype=TEMPLATE` — attribution is required.
2. Find the template root that `REQ-o80001-A` belongs to (walk up REFINES to `REQ-p80001`).
3. Find all other `Implements:` references in the same source file that target CONCRETE nodes.
4. For each concrete target, walk up its ancestors to find the first node with a `Satisfies:` declaration matching `REQ-p80001`.
5. First match wins — construct the instance ID: `REQ-p00044::REQ-o80001-A`.
6. Redirect the edge to the instance node.

If no attribution path is found -> warning.
If multiple paths match -> use the first match (short-circuit).

### 7. N/A Declarations

When a template assertion does not apply, the declaring requirement includes a normative assertion:

```markdown
## Assertions

A. The system SHALL provide document signing workflows.

F. REQ-o80001-D SHALL be NOT APPLICABLE. This system does not support batch signing.
```

N/A assertions are treated identically to deprecated status:

- Excluded from the coverage denominator for this instance.
- Stray `Implements:` references produce errors.
- The N/A assertion itself is a traceable, auditable artifact.

### 8. Health Reporting

Coverage gaps on template instances are reported through normal coverage mechanisms. Instance nodes are standard graph nodes, so existing health checks (uncovered assertions, coverage percentages) apply to them directly. The composite IDs (e.g., `REQ-p00044::REQ-o80001-A`) make it clear which template instance has gaps.

### 9. Configuration

Configuration in `.elspais.toml`:

```toml
[references.defaults]
keywords = ["implements", "validates", "refines", "satisfies"]
```

### 10. What Changes

- **EdgeKind enum** -- new `SATISFIES` and `INSTANCE` values.
- **Stereotype enum** -- new enum: `CONCRETE`, `TEMPLATE`, `INSTANCE`.
- **GraphNode** -- new `stereotype` field (defaults to `CONCRETE`).
- **RequirementParser** -- parse `Satisfies:` metadata field.
- **TraceGraphBuilder** -- template instantiation phase: clone template subtrees with composite IDs, mark stereotypes, create INSTANCE edges.
- **Link resolution** -- attribution algorithm redirects `Implements:` references to template nodes to the correct instance using file-based sibling lookup.

### 11. What Does NOT Change

- **Existing coverage semantics** -- `Implements:` and `Validates:` still contribute to coverage. `Refines:` still does not. Instance nodes participate in the same coverage computation as any other node.
- **Hash-based change detection** -- works as-is.
- **Parser line-claiming** -- templates parsed by RequirementParser like any other requirement.
