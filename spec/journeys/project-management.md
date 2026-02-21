# Project Management and DevOps Journeys

Journeys for the internal project manager coordinating delivery and the DevOps engineer automating quality gates.

---

# JNY-PM-Sprint-01: Track Requirement Status During a Sprint

**Actor**: Elvira (Internal Project Manager)
**Goal**: Monitor which requirements are implemented, changed, or orphaned during a two-week sprint
**Context**: Elvira is managing a sprint focused on the reporting module. She needs to track progress against the planned requirements and identify any issues before the sprint review.
Addresses: REQ-p00003, REQ-p00004, REQ-p00006

## Steps

1. Elvira runs `elspais trace --view` to generate an interactive HTML traceability view.
2. She opens the HTML file in her browser and navigates to the reporting module requirements.
3. She expands the hierarchy for REQ-p00005 to see all OPS and DEV children.
4. She runs `elspais changed` to see which spec files have been modified during the sprint.
5. She cross-references the changed requirements with the sprint plan to confirm progress.
6. She runs `elspais analyze orphans` to check for any requirements that lost their parent link during refactoring.
7. She finds one orphaned requirement and notifies the developer to fix the implements reference.
8. She generates an HTML report with `elspais trace --format html -o sprint-review.html` for the sprint review meeting.

## Expected Outcome

Elvira has a clear picture of sprint progress: which requirements are complete, which changed, and whether any structural issues need attention. She has an HTML report ready for the sprint review.

*End* *Track Requirement Status During a Sprint*

---

# JNY-PM-Review-01: Run a Stakeholder Review Session

**Actor**: Elvira (Internal Project Manager)
**Goal**: Facilitate a structured requirement review meeting with sponsor stakeholders using the collaborative review server
**Context**: The sponsor QA team wants to review the latest batch of requirements before the next milestone. Elvira sets up the review server so participants can comment on specific requirements in real time.
Addresses: REQ-p00006, REQ-p00007

## Steps

1. Elvira starts the review server with `elspais trace --server --port 8080`.
2. She shares the review URL with the sponsor QA lead and auditor.
3. Participants open the review interface in their browsers and see the interactive traceability view.
4. The sponsor QA lead adds a comment thread on REQ-p00007: "Assertion B needs a specific timeout value."
5. The auditor flags REQ-d00003 for clarification on data retention policy.
6. Elvira monitors the incoming comments during the meeting and assigns action items to developers.
7. After the meeting, she exports the review comments as a JSON package for record-keeping.
8. She creates follow-up tasks from the flagged requirements and tracks them to resolution.

## Expected Outcome

The review session produced structured, requirement-level feedback from all stakeholders. Comments are linked to specific requirements and exported for traceability. Action items are captured and tracked.

*End* *Run a Stakeholder Review Session*

---

# JNY-PM-MultiRepo-01: Coordinate Cross-Repository Requirements

**Actor**: Elvira (Internal Project Manager)
**Goal**: Manage requirements that span the core platform and a sponsor-specific associated repository
**Context**: The platform serves multiple sponsors. One sponsor needs custom features that extend the core platform requirements. Elvira needs to ensure the sponsor-specific requirements properly implement core PRD requirements and that the combined hierarchy is valid.
Addresses: REQ-p00001, REQ-p00002, REQ-p00005

## Steps

1. Elvira reviews the `sponsors.yml` configuration to confirm the sponsor repository is properly registered.
2. She verifies the associated repository uses the correct ID prefix (e.g., `REQ-CAL-d00001`) for its requirements.
3. She runs `elspais validate --mode combined` to validate both the core and sponsor requirements together.
4. The validator reports a broken link: a sponsor DEV requirement references a core PRD that was recently renamed.
5. She coordinates with the sponsor development team to update the implements reference.
6. She re-runs combined validation and confirms all cross-repository links are intact.
7. She generates a combined traceability matrix with `elspais trace --mode combined --format html` showing the full hierarchy.

## Expected Outcome

The core platform and sponsor-specific requirements are validated together with no broken links. The combined traceability matrix shows the complete hierarchy spanning both repositories, giving Elvira confidence in cross-repo consistency.

*End* *Coordinate Cross-Repository Requirements*

---

# JNY-DevOps-CI-01: Set Up CI/CD Requirement Validation

**Actor**: Alex (DevOps Engineer)
**Goal**: Add automated requirement validation to the CI/CD pipeline so invalid specifications cannot be merged
**Context**: The team wants to catch requirement formatting errors, broken links, and hash mismatches before they reach the main branch. Alex is adding Elspais validation as a required check in the pull request workflow.
Addresses: REQ-p00001, REQ-p00002, REQ-p00004

## Steps

1. Alex installs Elspais in the CI container image with `pip install elspais`.
2. He adds a validation step to the CI pipeline: `elspais validate -v`.
3. He adds a hash verification step: `elspais validate`.
4. He configures the pipeline to fail the pull request if either step returns a non-zero exit code.
5. A developer submits a PR with a new requirement missing its content hash.
6. The CI pipeline runs, the hash verification step fails, and the PR is blocked.
7. The developer sees the error message, fixes the hash with `elspais fix`, and pushes an update.
8. The pipeline re-runs, all checks pass, and the PR is unblocked for review.

## Expected Outcome

The CI/CD pipeline automatically catches requirement errors before merge. Developers get clear feedback about what to fix, and the main branch is protected from invalid specifications.

*End* *Set Up CI/CD Requirement Validation*
