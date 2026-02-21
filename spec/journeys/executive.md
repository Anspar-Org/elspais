# Executive Journeys

Journeys for the CEO preparing project health summaries, sponsor evidence packages, and regulatory inspection support.

---

# JNY-CEO-Dashboard-01: Assess Project Health for a Board Meeting

**Actor**: Priya (CEO)
**Goal**: Prepare a visual summary of project compliance and requirement coverage for a board presentation
**Context**: A board meeting is scheduled next week. Priya needs to demonstrate that the development project is on track, requirements are well-managed, and the team is ready for upcoming regulatory milestones.
Addresses: REQ-p00003, REQ-p00006

## Steps

1. Priya asks the project manager to generate the interactive traceability view with `elspais trace --view --embed-content`.
2. She opens the HTML dashboard in her browser and reviews the high-level statistics: total requirements, coverage percentage, and status breakdown.
3. She navigates to the regulatory compliance section and confirms all relevant PRD requirements have Active status.
4. She drills down into the authentication module to spot-check that DEV requirements trace back to the PRD.
5. She runs `elspais analyze coverage` to get the aggregate coverage number for her slides.
6. She captures key metrics: 47 PRD requirements, 98% implementation coverage, 100% test coverage on active DEV requirements.
7. She exports the HTML report for distribution to board members who want to explore the details.

## Expected Outcome

Priya has concrete, tool-generated evidence of project health. Her board presentation includes specific coverage metrics and a navigable traceability view, demonstrating rigorous requirements management.

*End* *Assess Project Health for a Board Meeting*

---

# JNY-CEO-Sponsor-01: Prepare Evidence for Sponsor Contract Renewal

**Actor**: Priya (CEO)
**Goal**: Demonstrate delivery quality and requirements traceability to justify a sponsor contract renewal
**Context**: A sponsor contract is up for renewal. Priya needs to show that her company has delivered on every contracted requirement, maintained quality throughout, and has the infrastructure for continued delivery.
Addresses: REQ-p00003, REQ-p00004, REQ-p00005, REQ-p00006

## Steps

1. Priya asks the project manager to generate a sponsor-filtered report with `elspais trace --sponsor foundation-x --format html`.
2. She reviews the sponsor-specific traceability matrix showing all contracted requirements and their implementation status.
3. She requests a change history summary using `elspais changed --base-branch v1.0` to show the evolution of the sponsor's requirements over the contract period.
4. She asks the QA lead to provide the latest test coverage report scoped to the sponsor's requirements.
5. She packages the traceability matrix, coverage report, and change history into a contract renewal evidence package.
6. She presents the package to the sponsor's leadership, walking through the traceability from PRD requirements down to verified test results.
7. The sponsor's leadership can drill into any requirement using the HTML report to see the full hierarchy and test coverage.

## Expected Outcome

Priya has a comprehensive evidence package demonstrating that every contracted requirement was implemented, tested, and traceable. The sponsor has confidence in delivery quality, supporting contract renewal and potential scope expansion.

*End* *Prepare Evidence for Sponsor Contract Renewal*

---

# JNY-CEO-Audit-01: Support a Regulatory Inspection

**Actor**: Priya (CEO)
**Goal**: Provide complete requirements documentation and traceability evidence for a regulatory pre-approval inspection
**Context**: A regulatory agency has scheduled a pre-approval inspection. The inspector will want to see the requirements documentation, traceability to tests, and evidence of change control. Priya coordinates with her team to prepare the evidence package.
Addresses: REQ-p00001, REQ-p00002, REQ-p00003, REQ-p00004, REQ-p00006

## Steps

1. Priya asks the DevOps engineer to run the full validation suite: `elspais validate -v` on the tagged release.
2. She asks the validation consultant to independently verify hash integrity with `elspais validate`.
3. The team generates a complete traceability matrix in multiple formats: HTML for interactive review and CSV for the inspector's spreadsheet.
4. They generate the coverage report showing test-to-requirement mapping with pass/fail status.
5. The validation consultant confirms: zero orphaned requirements, all hashes match, all hierarchy links valid.
6. During the inspection, the inspector uses the interactive HTML view to navigate from a PRD requirement through its DEV decomposition to the test results.
7. The inspector requests the CSV export for their records, and the team provides it alongside the validation output logs.

## Expected Outcome

The inspection proceeds smoothly with immediate access to traceability evidence in the inspector's preferred format. The tool-generated validation results provide objective evidence of requirements integrity, supporting a positive inspection outcome.

*End* *Support a Regulatory Inspection*
