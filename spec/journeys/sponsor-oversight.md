# Sponsor Oversight Journeys

Journeys for the sponsor project manager overseeing deliverables and the validation consultant conducting compliance audits.

---

# JNY-Sponsor-PM-01: Review Milestone Deliverables

**Actor**: Dr. Chen (Sponsor Project Manager)
**Goal**: Verify that a milestone delivery meets the contracted requirement coverage before approving payment
**Context**: The development team has submitted a milestone delivery. Dr. Chen needs to confirm that all requirements committed to for this milestone are implemented, tested, and traceable before signing off.
Addresses: REQ-p00003, REQ-p00004, REQ-p00006

## Steps

1. Dr. Chen receives notification that the milestone branch is ready for review.
2. She clones the delivery branch and runs `elspais trace --format html -o milestone-3-trace.html` to generate the traceability matrix.
3. She opens the HTML report and reviews the PRD requirements committed to in the milestone statement of work.
4. She runs `elspais analyze coverage` to check that all PRD requirements have corresponding DEV implementations.
5. She runs `elspais changed --base-branch v2.0` to see what changed since the last accepted milestone.
6. She reviews the list of new and modified requirements to confirm they align with the milestone scope.
7. She identifies one PRD requirement with no DEV children and requests clarification from the project manager.
8. After the gap is addressed, she signs off on the milestone.

## Expected Outcome

Dr. Chen has verified that the milestone delivery meets contractual obligations. The traceability matrix and coverage report provide documented evidence of requirement fulfillment for the project record.

*End* *Review Milestone Deliverables*

---

# JNY-Sponsor-PM-02: Filter Sponsor-Specific Requirements

**Actor**: Dr. Chen (Sponsor Project Manager)
**Goal**: Generate a report showing only the requirements specific to her sponsorship, separate from the shared platform
**Context**: The platform serves multiple sponsors. Dr. Chen wants to see only the requirements relevant to her organization's project, without being distracted by other sponsors' customizations or the full core platform.
Addresses: REQ-p00005, REQ-p00006

## Steps

1. Dr. Chen runs `elspais trace --sponsor foundation-x --format html -o foundation-x-trace.html` to filter the traceability matrix to her sponsor's scope.
2. She opens the filtered report and reviews the sponsor-prefixed requirements (e.g., `REQ-FDX-d00001`).
3. She also runs `elspais trace --sponsor foundation-x --format csv -o foundation-x-trace.csv` to get a spreadsheet-friendly export.
4. She opens the CSV in a spreadsheet to annotate requirements with her own status tracking and notes.
5. She compares the sponsor-specific requirements against the original statement of work to track scope coverage.
6. She shares the annotated spreadsheet with her leadership team as part of the quarterly progress report.

## Expected Outcome

Dr. Chen has a clean, sponsor-scoped view of the requirements relevant to her project. The CSV export integrates with her existing reporting workflow, and the HTML provides a navigable overview for stakeholders.

*End* *Filter Sponsor-Specific Requirements*

---

# JNY-Auditor-Validate-01: Conduct a Compliance Audit

**Actor**: Janet (Validation Consultant)
**Goal**: Verify requirement integrity, traceability, and hash consistency for a regulatory submission package
**Context**: The system is being prepared for regulatory review. Janet, an independent validation consultant engaged by the sponsor, needs to verify that the requirements meet documentation standards: complete traceability, no orphaned requirements, and tamper-evident content hashes.
Addresses: REQ-p00001, REQ-p00002, REQ-p00003, REQ-p00004

## Steps

1. Janet receives access to the project repository at the tagged release commit.
2. She runs `elspais hash verify` to confirm all content hashes match their requirement bodies. No tampering or undocumented changes are detected.
3. She runs `elspais analyze orphans` to identify any requirements without valid parent links. The tool reports zero orphans.
4. She runs `elspais validate -v` to perform a comprehensive validation. All format, hierarchy, and traceability checks pass.
5. She generates a complete traceability matrix with `elspais trace --format csv -o audit-trace.csv` for inclusion in the validation package.
6. She generates the HTML version with `elspais trace --view --embed-content` to review the full requirement text in context.
7. She reviews the git history for the spec directory to confirm all changes follow the project's change control process.
8. She documents her findings in the validation report, attaching the traceability matrix and validation output as evidence.

## Expected Outcome

Janet has independently verified the integrity and completeness of the requirements documentation. Her validation report includes machine-generated evidence (hash verification, validation output, traceability matrix) supporting the regulatory submission.

*End* *Conduct a Compliance Audit*

---

# JNY-Auditor-Change-01: Investigate Requirement Changes

**Actor**: Janet (Validation Consultant)
**Goal**: Trace and evaluate requirement modifications between two releases to assess their impact
**Context**: A new release candidate is being prepared. Janet needs to identify every requirement that changed since the last validated release, understand the nature of each change, and verify that downstream requirements were updated accordingly.
Addresses: REQ-p00003, REQ-p00004

## Steps

1. Janet runs `elspais changed --base-branch v2.0 --json` to get a machine-readable list of all requirement changes since the last release.
2. The output shows three modified requirements and one new requirement.
3. She runs `elspais hash verify` and identifies that REQ-p00008 has a hash mismatch, confirming its content changed.
4. She uses git diff to review the exact changes to REQ-p00008's assertions: one assertion was strengthened with a more specific threshold.
5. She checks the hierarchy with `elspais analyze hierarchy` to identify all DEV requirements that implement REQ-p00008.
6. She verifies that the downstream DEV requirements were updated to reflect the tighter threshold.
7. She confirms the new requirement (REQ-d00045) has proper implements links and a valid hash.
8. She documents her change impact assessment, noting that all modifications are properly propagated and justified.

## Expected Outcome

Janet has a complete audit trail of every requirement change between releases. Each modification is traced to its downstream impact, providing confidence that no changes were made without proper propagation and documentation.

*End* *Investigate Requirement Changes*
