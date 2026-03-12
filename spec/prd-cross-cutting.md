# Cross-Cutting Requirements: Template Classes and Satisfies

This document specifies the design for cross-cutting requirement templates ("classes") and the `Satisfies:` reference type that enables reusable, multi-instance compliance tracking without requirement duplication.

---

# REQ-p00014: Cross-Cutting Requirement Templates

**Level**: PRD | **Status**: Draft | **Implements**: REQ-p00001

## Rationale

Regulatory and organizational standards (FDA 21 CFR Part 11, SOC 2, HIPAA, internal security policies) define obligations that apply identically across multiple applications or subsystems. Today, teams either:

1. **Duplicate requirements** — copy the standard's obligations into each app's spec tree, creating sync problems when the standard changes.
2. **Share a single requirement** — multiple apps point to one requirement, losing per-app coverage visibility.

Neither is satisfactory. What's needed is a **template** mechanism:

- Define obligations once as a reusable class.
- Declare that an application "satisfies" that class.
- Track coverage independently per application, using the existing graph.
- When the template changes (hash changes), all implementors are flagged for review — using the existing change detection system.

The template is the single source of truth. No requirements are generated or duplicated. Instances are a graph-level concept created at build time from the combination of `Satisfies:` declarations and code-level `Implements:` references to template assertions.

## Assertions

A. The system SHALL support a template requirement type (class) that defines reusable obligations as assertions, using the same format as regular requirements.

B. The system SHALL support a `Satisfies:` metadata field on requirements, declaring that the requirement's subtree must cover all assertions in the referenced template(s).

C. The system SHALL attribute code-level `Implements:` references to template assertions to the correct application instance by following the code's sibling `Implements:` edges up to the `Satisfies:` declaration.

D. The system SHALL report coverage gaps when a `Satisfies:` declaration exists but the subtree does not cover all template assertions.

E. The system SHALL support explicit N/A declarations for template assertions that do not apply to a specific instance, using assertions on the declaring requirement.

F. The system SHALL flag all implementors for review when a template's content hash changes, using the existing hash-based change detection mechanism.

*End* *Cross-Cutting Requirement Templates* | **Hash**: 00000000
---

# REQ-p00015: Implements as Cross-Hierarchy Reference

**Level**: PRD | **Status**: Draft | **Implements**: REQ-p00001

## Rationale

The existing requirement hierarchy uses `Refines:` for parent-child decomposition (DEV refines OPS refines PRD) and `Implements:` for coverage-contributing references. Currently, `Implements:` is used primarily by code and test nodes.

DEV-level specifications describe implementation choices that may cut across multiple PRD assertions. A DEV spec like "Use PostgreSQL with row-level security" is not a refinement of any single PRD requirement — it's an architectural decision relevant to data isolation, audit logging, and access control simultaneously.

Forcing such a DEV spec into a single `Refines:` relationship loses information. Instead, DEV specs should be able to use `Implements:` to reference multiple PRD or OPS requirements, establishing traceability links that contribute to coverage. `Refines:` remains the structural relationship (single parent in the hierarchy tree). `Implements:` becomes the coverage relationship (many-to-many).

This distinction cleanly separates two concerns:
- **Structure**: Where does this requirement live in the decomposition tree? (`Refines:`)
- **Coverage**: What higher-level obligations does this requirement help satisfy? (`Implements:`)

## Assertions

A. The system SHALL allow requirement nodes (not just code/test nodes) to use `Implements:` references targeting multiple requirements at any level.

B. `Implements:` edges from requirement nodes SHALL contribute to coverage rollup of the target requirement's assertions.

C. `Refines:` edges SHALL remain structural (tree hierarchy) and SHALL NOT contribute to coverage rollup.

D. A requirement MAY have both a `Refines:` edge (structural parent) and `Implements:` edges (coverage targets) simultaneously.

*End* *Implements as Cross-Hierarchy Reference* | **Hash**: 00000000
---

## Design Details

The sections below are non-normative design notes that elaborate on how the assertions above map to implementation.

### 1. Template Requirement Format

Templates use the existing requirement format. No new syntax is needed for the template itself. A template is distinguished by convention (e.g., `CLASS-` prefix) or by being referenced in a `Satisfies:` declaration. The key property is that templates define assertions that multiple applications must satisfy.

```markdown
# CLASS-esig-001: FDA 21 CFR Part 11 Electronic Signatures

**Level**: PRD | **Status**: Active | **Implements**: -

## Assertions

A. The system SHALL validate the identity of the signer before accepting an electronic signature.

B. Signed records SHALL be linked to their respective electronic signatures such that the signatures cannot be excised, copied, or otherwise transferred to falsify an electronic record.

C. Electronic signatures SHALL include the printed name of the signer, the date and time when the signature was executed, and the meaning of the signature.

D. Systems that support batch signing SHALL require additional authentication for each batch.

*End* *FDA 21 CFR Part 11 Electronic Signatures* | **Hash**: a1b2c3d4
```

Templates can have internal hierarchy (sub-templates that `Refines:` the top-level template). The template tree is organizational — it structures the standard's own decomposition.

```
CLASS-esig-001 (top-level)
├── CLASS-esig-002 (Refines: CLASS-esig-001, auth subtree)
│   ├── A: validate identity
│   └── B: two-factor for high-risk
├── CLASS-esig-003 (Refines: CLASS-esig-001, record integrity)
│   ├── A: link to signing event
│   └── B: tamper-evident storage
└── CLASS-esig-004 (Refines: CLASS-esig-001, timing)
    └── A: include date/time
```

### 2. Satisfies Declaration

A requirement declares template compliance using `Satisfies:` in its metadata:

```markdown
# REQ-p00020: HHT Diary Application

**Level**: PRD | **Status**: Active | **Implements**: -

Satisfies: CLASS-esig-001

## Assertions

A. The HHT Diary SHALL provide electronic patient-reported outcomes.

B. CLASS-esig-001-D is not applicable: the HHT Diary does not support batch signing workflows.

*End* *HHT Diary Application* | **Hash**: e5f6a7b8
```

Key properties:
- `Satisfies:` appears after the metadata line (same position as `Addresses:`).
- Multiple templates: `Satisfies: CLASS-esig-001, CLASS-audit-001`.
- `Satisfies:` can target a sub-template: `Satisfies: CLASS-esig-002` (only that subtree's assertions must be covered).
- `Satisfies:` is NOT part of the hashed content (same as `Addresses:`).

### 3. N/A Declarations

When a template assertion does not apply to a specific instance, the declaring requirement includes an assertion explaining why:

```markdown
B. CLASS-esig-001-D is not applicable: the HHT Diary does not support batch signing workflows.
```

This assertion:
- Is a first-class assertion on the declaring requirement (traceable, reviewable, auditable).
- References the specific template assertion being excluded.
- Provides justification (auditors can review why it was excluded).
- Is detected by the graph builder as an N/A declaration for coverage purposes.

Pattern: an assertion whose text matches `{template-assertion-id} is not applicable` (case-insensitive).

### 4. Coverage Attribution

When code references a template assertion:

```python
# hht_diary/auth.py
# Implements: REQ-dev-hht-login
# Implements: CLASS-esig-001-A
```

The graph builder attributes `CLASS-esig-001-A` coverage to the correct instance:

1. Find the code node's sibling `Implements:` edges (other edges from this code node).
2. For each sibling edge target (e.g., `REQ-dev-hht-login`), walk ancestors via `Refines:`/`Implements:` edges.
3. Find an ancestor with `Satisfies: CLASS-esig-001`.
4. Attribute the template coverage to that ancestor's instance.

If no ancestor has a matching `Satisfies:` declaration → warning: "CLASS-esig-001-A in `hht_diary/auth.py` has no attribution path."

If multiple ancestors have matching `Satisfies:` → attribute to the nearest ancestor (most specific scope).

### 5. Graph Building

During `build()`, the graph builder:

1. **Collects `Satisfies:` declarations** — records which requirement nodes declare template compliance.
2. **Resolves template trees** — for each `Satisfies:` target, collects all leaf assertions in that template's subtree.
3. **Creates virtual instance nodes** — for each (declaring-requirement, template-assertion) pair, creates a lightweight tracking entry. These are NOT new GraphNode instances — they are entries in the declaring requirement's metrics.
4. **Attributes code references** — uses the attribution algorithm (Section 4) to map code-level template references to instances.
5. **Processes N/A declarations** — scans the declaring requirement's assertions for N/A patterns, marking those template assertions as explicitly excluded.
6. **Computes coverage** — for each instance, coverage = (attributed + N/A) / total template assertions.

Coverage data is stored in the declaring requirement's metrics:

```python
node.set_metric("satisfies", {
    "CLASS-esig-001": {
        "total": 4,
        "covered": ["A", "B", "C"],     # attributed via code
        "not_applicable": ["D"],          # explicit N/A
        "missing": [],                    # coverage gaps
        "coverage_pct": 100.0,
    }
})
```

### 6. Health Reporting

The health command reports template coverage gaps:

```
REQ-p00021 (Other App): CLASS-esig-001 coverage gaps:
  CLASS-esig-002 (Authentication):
    ✓ A: validate identity
    ✗ B: two-factor for high-risk     ← missing
  CLASS-esig-003 (Record Integrity):
    ✓ A: link to signing event
    ✓ B: tamper-evident storage
  CLASS-esig-004 (Timing):
    ✗ A: include date/time            ← missing

  Coverage: 3/5 (60%) — 2 gaps, 0 N/A
```

The template's internal hierarchy structures the report but does not affect the coverage calculation.

### 7. Implements for DEV-to-PRD Cross-References

DEV specs can reference multiple PRD/OPS requirements via `Implements:`:

```markdown
# REQ-d00100: PostgreSQL Row-Level Security

**Level**: DEV | **Status**: Active | **Refines**: REQ-ops-data-layer
**Implements**: REQ-p00020-A, REQ-p00021-C, REQ-p00022-B

## Assertions

A. The system SHALL use PostgreSQL row-level security policies for tenant data isolation.

B. The system SHALL log all data access events via pg_audit extension.

C. The system SHALL use role-based connection pooling with per-tenant credentials.

*End* *PostgreSQL Row-Level Security* | **Hash**: 00000000
```

Here `Refines:` sets the structural parent (where it lives in the tree). `Implements:` declares which higher-level assertions this DEV spec helps satisfy. Coverage flows through `Implements:` edges — when code covers `REQ-d00100-A`, that coverage propagates to `REQ-p00020-A`.

The existing `Implements:` edge semantics (`contributes_to_coverage() → True`) already support this. The change is allowing requirement-to-requirement `Implements:` edges at all levels, not just code/test → requirement.

### 8. Configuration

New configuration in `.elspais.toml`:

```toml
[references.defaults]
keywords = ["implements", "validates", "refines", "satisfies"]

[templates]
# Optional: ID prefix patterns that identify template requirements
# If empty, any requirement referenced by Satisfies: is treated as a template
prefixes = ["CLASS-"]

# Pattern for N/A declarations in assertions
na_pattern = "is not applicable"
```

### 9. What Does NOT Change

- **GraphNode structure** — no new fields. Template coverage uses `set_metric()`.
- **TraceGraph structure** — no new collections. Virtual instances are metric entries.
- **GraphBuilder structure** — extended, not restructured.
- **EdgeKind enum** — `Satisfies:` is parsed as metadata, not as a new edge kind. It creates a metric annotation, not a graph edge.
- **Existing coverage semantics** — `Implements:` and `Validates:` still contribute to coverage. `Refines:` still does not.
- **Hash-based change detection** — template content changes trigger the same review flagging as any other requirement change.
- **Parser line-claiming** — templates are parsed by RequirementParser like any other requirement.
