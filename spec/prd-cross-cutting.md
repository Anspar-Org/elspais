# Cross-Cutting Requirements: Satisfies Relationship

This document specifies the `Satisfies:` edge type and the NOT APPLICABLE status for template assertions. Coverage model assertions are in REQ-d00069; change detection is in REQ-p00004-G.

---

## REQ-p00014: Satisfies Relationship

**Level**: PRD | **Status**: Draft | **Implements**: REQ-p00001

## Rationale

Cross-cutting concerns — regulatory compliance frameworks, security policies, accessibility standards, operational baselines — define obligations that multiple independent subsystems must satisfy. The `Satisfies:` relationship enables a template-instance pattern: a set of requirements is defined once as a reusable template, and individual subsystems declare that they satisfy it. No new node types are introduced — `Satisfies:` is simply a new edge kind connecting a declaring requirement to a template requirement. Per-instance coverage metrics are stored on the declaring requirement, keyed by template ID.

## Assertions

A. The system SHALL support a `Satisfies:` metadata field on requirements. The target MAY be a requirement or a specific assertion.

B. `Satisfies:` SHALL be parsed as a new edge kind (SATISFIES) connecting the declaring requirement to the template target. A SATISFIES edge SHALL be treated as an assertion on the declaring requirement for coverage purposes: its coverage is the fractional coverage of the referenced template's leaf assertions within the declaring requirement's subtree.

C. The system SHALL attribute code-level `Implements:` references to template assertions to the correct declaring requirement by following the code's sibling `Implements:` edges up to the ancestor with the matching `Satisfies:` declaration.

*End* *Satisfies Relationship* | **Hash**: 00000000
---

## REQ-p00016: NOT APPLICABLE Status

**Level**: PRD | **Status**: Draft | **Implements**: REQ-p00001

## Rationale

When a cross-cutting template assertion does not apply to a specific subsystem, the declaring requirement must be able to explicitly exclude it. This uses normative assertion language consistent with the rest of the spec system, and follows the same semantics as deprecated status — the assertion is excluded from the coverage denominator.

## Assertions

A. The system SHALL support explicit N/A declarations for template assertions using normative assertions on the declaring requirement (e.g., `REQ-p80001-D SHALL be NOT APPLICABLE`).

B. N/A assertions SHALL be treated the same as deprecated status: they SHALL NOT count toward the coverage target for the relevant template instance.

C. Any `Implements:` references to a N/A assertion SHALL NOT count toward coverage and SHALL produce errors.

*End* *NOT APPLICABLE Status* | **Hash**: 00000000
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

### 3. EdgeKind: SATISFIES

A new edge kind is added:

```python
class EdgeKind(Enum):
    IMPLEMENTS = "implements"
    REFINES = "refines"
    VALIDATES = "validates"
    ADDRESSES = "addresses"
    CONTAINS = "contains"
    SATISFIES = "satisfies"    # NEW
```

`SATISFIES` contributes to coverage (`contributes_to_coverage() -> True`). The SATISFIES edge behaves like an assertion on the declaring requirement: its coverage is fractional, based on the proportion of the template's leaf assertions that are covered within the declaring requirement's subtree. This means a requirement with `Satisfies: X` includes the template compliance as part of its own coverage metric.

### 4. Coverage Storage

Per-instance coverage is stored on the declaring requirement as a keyed metric:

```python
req_p00044.set_metric("satisfies_coverage", {
    "REQ-p80001": {
        "total": 5,
        "covered": 4,
        "na": 1,
        "missing": ["REQ-o80002-B"],
        "coverage_pct": 100.0,    # (4) / (5 - 1) = 100%
    }
})
```

No new node types or graph structures are needed. The SATISFIES edge plus this metric provide full traceability.

### 5. Coverage Attribution Algorithm

When code references a template assertion:

```python
# document_mgmt/auth.py
# Implements: REQ-d00044-A
# Implements: REQ-o80001-A
```

Attribution:

1. Code node has edges to `REQ-d00044-A` and `REQ-o80001-A`.
2. `REQ-o80001-A` is an assertion under the template tree (descendant of REQ-p80001).
3. Walk the code's other `Implements:` targets: `REQ-d00044-A` -> parent `REQ-d00044` -> ancestors via `Refines:` -> find `REQ-p00044` which has a SATISFIES edge to `REQ-p80001`.
4. `REQ-o80001-A` belongs to the REQ-p80001 template tree. Match found.
5. Attribute `REQ-o80001-A` coverage to `REQ-p00044`'s satisfies_coverage for REQ-p80001.

If no attribution path is found -> warning.
If multiple paths match -> attribute to the nearest ancestor (most specific scope).

### 6. N/A Declarations

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

### 7. Health Reporting

The health command reports template coverage gaps:

```
REQ-p00045 (Other System): REQ-p80001 coverage gaps:
  REQ-o80001 (Authentication):
    + A: validate identity
    - B: two-factor for high-risk     <- missing
  REQ-o80002 (Record Integrity):
    + A: link records to signing events
    + B: tamper-evident storage

  Coverage: 3/4 (75%) -- 1 gap, 0 N/A
```

### 8. Configuration

New configuration in `.elspais.toml`:

```toml
[references.defaults]
keywords = ["implements", "validates", "refines", "satisfies"]
```

### 9. What Changes

- **EdgeKind enum** -- new `SATISFIES` value.
- **RequirementParser** -- parse `Satisfies:` metadata field.
- **Coverage annotator** -- compute per-instance template coverage, store on declaring node.
- **Health command** -- report template coverage gaps.

### 10. What Does NOT Change

- **GraphNode structure** -- no new node types or fields.
- **TraceGraph structure** -- no new collections.
- **Existing coverage semantics** -- `Implements:` and `Validates:` still contribute to coverage. `Refines:` still does not.
- **Hash-based change detection** -- works as-is, extended to follow SATISFIES edges.
- **Parser line-claiming** -- templates parsed by RequirementParser like any other requirement.
