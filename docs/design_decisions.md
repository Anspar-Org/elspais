# Design Decisions: Semantic Reflexive Specification Framework

## Purpose of This Document

This document explains the **key design decisions** behind the Semantic Reflexive Specification Framework.
It is intended to answer *why* the system is structured the way it is, not merely *how* it works.

This document is non-normative. It provides rationale, trade-off analysis, and guiding principles
for future contributors, reviewers, auditors, and system designers.

---

## Foundational Problem Statement

Modern software development—especially in regulated or high-integrity contexts—faces a fundamental tension:

- Software is inherently a **discovery process**
- Yet regulators, sponsors, and users require **stability, traceability, and proof**

This system was designed to reconcile those two realities:
to allow discovery and evolution **without loss of intent, meaning, or accountability**.

---

## Design Principle 1: Explicit Normativity

### Decision

Only formally defined **Requirements (REQ)** introduce obligations.

### Rationale

In many systems, obligations are unintentionally introduced through:

- documentation,
- acceptance criteria,
- tickets,
- diagrams,
- or test cases.

This creates ambiguity during audits and change review.

By making normativity explicit and isolated:

- obligations are easy to identify,
- scope is unambiguous,
- and compliance questions are answerable by inspection.

### Trade-off

This requires discipline in writing requirements and resisting the urge to embed obligations elsewhere.
The benefit is long-term clarity and auditability.

---

## Design Principle 2: Stratified Abstraction Levels

### Decision

The system is intentionally **layered**, with different artifact classes serving different purposes:

- User Journeys (intent)
- Requirements (obligation)
- Code (implementation)
- Tests (verification)
- Runbooks (operation)

### Rationale

Collapsing these layers leads to:

- redundancy,
- contradiction,
- and brittle systems where change becomes risky.

Stratification allows each artifact to:

- remain focused,
- evolve independently,
- and interact through well-defined relationships.

### Trade-off

More artifact types means more concepts to learn.
This is mitigated by strict rules and automation.

---

## Design Principle 3: One-Way Normative Refinement

### Decision

Normative relationships flow in one direction only:
more specific requirements implement less specific ones.

### Rationale

Bidirectional normative links create:

- circular authority,
- unclear ownership,
- and unpredictable change impact.

One-way refinement ensures:

- stable authority chains,
- predictable decomposition,
- and safe evolution.

### Trade-off

Composition must be inferred rather than explicitly declared.
This shifts complexity to tooling rather than authors.

---

## Design Principle 4: Non-Normative Semantic Relationships

### Decision

Relationships such as requirement-to-journey mappings are **explicitly non-normative**.

Examples include:

- Addresses
- Motivated-By
- Relates-To

These are stored outside hashed normative content.

### Rationale

Discovery artifacts (like journeys) evolve frequently.
Making them normative would destabilize the system.

Non-normative relationships:

- preserve navigability,
- support impact analysis,
- without contaminating authority.

### Trade-off

Authors must understand the difference between normative and non-normative links.
Tooling enforces this distinction.

---

## Design Principle 5: Tamper-Evident Normative Content

### Decision

Normative requirement content is hashed.

### Rationale

This provides:

- integrity guarantees,
- change detection,
- and strong audit evidence.

Hashes make it impossible to silently change obligations.

### Trade-off

Hash stability requires careful definition of what is normative.
This is addressed through strict grammar rules.

---

## Design Principle 6: Reflexive Introspection

### Decision

The system is designed to reason about itself.

It can answer questions such as:

- What is unverified?
- What changed?
- What is affected?
- What is risky?
- Who must review this?

### Rationale

Static documentation systems cannot scale with system complexity.
Reflexive introspection turns governance into a continuous process.

### Trade-off

Requires upfront investment in parsers and validators.
Pays off by dramatically reducing manual oversight burden.

---

## Design Principle 7: Human-Readable, Machine-Readable Artifacts

### Decision

All artifacts are stored as plain text (Markdown), but parsed into structured models.

### Rationale

This avoids:

- proprietary tooling lock-in,
- opaque representations,
- and future migration risk.

At the same time, machine-readability enables:

- automation,
- validation,
- AI-assisted workflows.

### Trade-off

Markdown is less visually rich than some modeling tools.
The benefit is longevity, accessibility, and diffability.

---

## Design Principle 8: Change Impact Over Change Prevention

### Decision

The system emphasizes **impact detection and review**, not rigid change prevention.

### Rationale

Preventing change slows discovery.
Unreviewed change creates risk.

By surfacing impact and assigning review responsibility:

- change remains fast,
- but never invisible.

### Trade-off

Requires cultural discipline to complete reviews meaningfully.
Tooling supports but does not replace judgment.

---

## Design Principle 9: Selective Risk Documentation

### Decision

Risk assessments are recorded **only where meaningful trade-offs exist**.

### Rationale

Risk documentation everywhere becomes noise.
Risk documentation where decisions were made becomes signal.

This aligns with regulatory expectations for risk-based validation.

### Trade-off

Requires judgment to decide when risk is worth documenting.
Guidelines and ownership help maintain consistency.

---

## Design Principle 10: Role-Based Accountability

### Decision

Execution responsibility (commits) is separated from governance responsibility (owners).

### Rationale

Commit history shows who changed something.
Governance requires knowing who is accountable for correctness and risk.

Role-based ownership enables:

- periodic review,
- explicit sign-off,
- and organizational clarity.

### Trade-off

Adds minimal metadata overhead.
Provides strong accountability benefits.

---

## Summary

Every major design decision in this system reflects a single goal:

> Enable discovery without losing meaning, control, or trust.

The framework prioritizes:

- clarity over convenience,
- structure over ceremony,
- and long-term maintainability over short-term speed.

It is designed to scale not just with system size,
but with **time, people, and intelligence**—human and artificial alike.
