# Sponsor Quality Assurance Journeys

Journeys for the sponsor QA lead verifying test coverage, reviewing requirement quality, and validating bug fixes.

---

# JNY-SponsorQA-Coverage-01: Verify Test Coverage Before Release

**Actor**: Rita (Sponsor QA Lead)
**Goal**: Confirm that every requirement assertion has passing test coverage before accepting a delivery
**Context**: The development team has submitted a release candidate with test results. Rita needs to verify that all assertions across every requirement are covered by at least one test, and that all referenced tests passed.
Addresses: REQ-p00001, REQ-p00003

## Steps

1. Rita receives the release candidate branch along with the JUnit XML test results file.
2. She runs `elspais analyze coverage` with the test results loaded to generate a coverage report.
3. The report shows 96% assertion coverage, with two assertions in REQ-d00015 uncovered.
4. She identifies the uncovered assertions: REQ-d00015-D (error handling) and REQ-d00015-E (logging).
5. She sends the coverage gap report back to the development team with a request for additional tests.
6. The development team adds the missing tests and resubmits with an updated test results file.
7. Rita re-runs the coverage analysis and confirms 100% assertion coverage with all tests passing.
8. She signs off on the release candidate, attaching the coverage report as evidence.

## Expected Outcome

Rita has verified that every testable obligation in the requirements is covered by a passing test. The coverage report serves as formal evidence of verification completeness for the release record.

*End* *Verify Test Coverage Before Release*

---

# JNY-SponsorQA-Review-01: Provide Structured Feedback on Requirements

**Actor**: Rita (Sponsor QA Lead)
**Goal**: Review requirement specifications for testability and clarity, providing structured feedback the development team can act on
**Context**: The project manager has requested Rita's input on a new batch of requirements before they are finalized. Rita wants to review each requirement for testability, identify ambiguous assertions, and provide comments that are linked directly to specific requirements.
Addresses: REQ-p00006, REQ-p00007

## Steps

1. Rita opens the interactive traceability view generated with `elspais trace --view --review-mode`.
2. She navigates to the first requirement in the batch, REQ-p00015, and reads through its assertions.
3. She finds Assertion A ambiguous: "The system responds within a reasonable time" lacks a specific threshold.
4. She adds a comment thread on REQ-p00015: "Assertion A needs a measurable value, e.g., 'within 2 seconds'."
5. She continues reviewing the remaining requirements, flagging REQ-d00022-C as untestable in its current form.
6. She checks if previous review comments on other requirements have been addressed by the team.
7. She resolves two comment threads where the team incorporated her earlier feedback.
8. She exports a summary of open comments for her QA review log.

## Expected Outcome

Rita has provided traceable, requirement-level feedback that the development team can address directly. Open comments are tracked to resolution, and the review history is preserved for audit purposes.

*End* *Provide Structured Feedback on Requirements*

---

# JNY-SponsorQA-Regression-01: Validate a Bug Fix Has Requirement Updates

**Actor**: Rita (Sponsor QA Lead)
**Goal**: Verify that a bug fix includes the necessary requirement updates and corresponding test coverage
**Context**: A bug was discovered in production: session timeouts are inconsistent. The development team has fixed the bug and updated the relevant requirement assertion. Rita needs to verify that the requirement change is properly documented and tested.
Addresses: REQ-p00001, REQ-p00002, REQ-p00004

## Steps

1. Rita runs `elspais changed` to see which requirements were modified in the bug fix branch.
2. The output shows REQ-d00008 was modified. She reviews the change: Assertion C was updated to specify a consistent 30-minute timeout.
3. She runs `elspais validate` and confirms that REQ-d00008's hash was updated to reflect the content change.
4. She checks the test results to confirm that a test references REQ-d00008-C specifically.
5. She verifies the test passes with the new timeout value.
6. She runs `elspais validate` to confirm the requirement still passes all format and hierarchy checks.
7. She reviews the parent requirements to confirm the timeout change is compatible with the higher-level obligations.
8. She approves the bug fix, noting in her QA log that the requirement, test, and hash were all properly updated.

## Expected Outcome

Rita has confirmed that the bug fix followed the proper process: the requirement was updated, the hash reflects the change, a specific test covers the modified assertion, and the hierarchy remains consistent. The fix is approved with a complete audit trail.

*End* *Validate a Bug Fix Has Requirement Updates*
