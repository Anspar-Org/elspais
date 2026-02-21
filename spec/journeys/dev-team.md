# Developer and QA Engineer Journeys

Journeys for developers writing requirements and QA engineers mapping test coverage.

---

# JNY-Dev-Setup-01: Set Up Requirements for a New Feature

**Actor**: Sarah (Developer)
**Goal**: Create a validated DEV requirement that implements an existing PRD requirement, with proper format and hash
**Context**: Sarah is starting work on a new feature. The product team has already defined the PRD-level requirement, and Sarah needs to create the corresponding DEV specification before writing code.
Addresses: REQ-p00001, REQ-p00002, REQ-p00004

## Steps

1. Sarah creates a feature branch from the main development branch.
2. She opens the existing PRD spec file and reads REQ-p00012 to understand what the feature needs to accomplish.
3. She creates a new file `spec/dev-reporting.md` and writes a DEV requirement header with `Implements: REQ-p00012`.
4. She writes the Assertions section with specific, testable obligations using prescriptive language.
5. She runs `elspais validate` to check the requirement format.
6. The validator reports errors: missing hash and a malformed status field.
7. She fixes the status field and runs `elspais fix REQ-d00042` to generate the content hash.
8. She re-runs `elspais validate` and confirms all checks pass.
9. She commits the new requirement file to her feature branch.

## Expected Outcome

Sarah has a validated DEV requirement properly linked to the parent PRD requirement, with a generated content hash. All validation checks pass, confirming the requirement follows project standards and is ready for implementation.

*End* *Set Up Requirements for a New Feature*

---

# JNY-Dev-MCP-01: Use AI Assistant to Query and Author Requirements

**Actor**: Sarah (Developer)
**Goal**: Use an AI coding assistant with the Elspais MCP server to search existing requirements and draft a new one
**Context**: Sarah is working on a complex feature that touches several existing requirements. Rather than manually searching spec files, she wants to use her AI assistant to navigate the requirement graph and help draft a new requirement.
Addresses: REQ-p00001, REQ-p00050, REQ-p00060

## Steps

1. Sarah starts the Elspais MCP server with `elspais mcp serve` in her project directory.
2. She configures her AI coding assistant to connect to the MCP server.
3. She asks the assistant: "Find all requirements related to authentication."
4. The assistant queries the MCP search tool and returns a list of matching requirements with their IDs, titles, and hierarchy.
5. She asks the assistant to show the full details of REQ-p00003 including its assertions and child requirements.
6. She asks the assistant to draft a new DEV requirement implementing REQ-p00003, covering API token validation.
7. The assistant creates the requirement in the correct format with assertions, implements reference, and placeholder hash.
8. Sarah reviews the draft, adjusts the wording, and runs `elspais validate` to confirm correctness.

## Expected Outcome

Sarah has efficiently navigated the requirement hierarchy and authored a well-structured requirement with AI assistance. The MCP integration allowed her to stay in her development environment while querying and creating requirements.

*End* *Use AI Assistant to Query and Author Requirements*

---

# JNY-QA-Coverage-01: Map Tests to Requirements for Coverage

**Actor**: Marcus (QA Engineer)
**Goal**: Verify that all requirement assertions have corresponding test coverage before a release
**Context**: The team is preparing for a release milestone. Marcus needs to confirm that every assertion in the DEV requirements is covered by at least one test, and produce a coverage report for the project manager.
Addresses: REQ-p00001, REQ-p00003, REQ-p00004

## Steps

1. Marcus adds requirement references to test docstrings and names (e.g., `test_REQ_d00042_A_validates_token_format`).
2. He runs the test suite with `pytest --junitxml=test-results.xml` to generate structured results.
3. He runs `elspais analyze coverage` to generate the coverage report.
4. The report shows 94% assertion coverage, with three assertions in REQ-d00015 lacking test references.
5. He writes additional tests for the uncovered assertions, adding the appropriate REQ references.
6. He re-runs the test suite and coverage analysis.
7. The updated report shows 100% assertion coverage across all DEV requirements.
8. He exports the coverage report and shares it with the project manager.

## Expected Outcome

Marcus has a complete test-to-requirement mapping showing 100% assertion coverage. The coverage report provides evidence that every testable obligation has been verified, ready for inclusion in the release documentation.

*End* *Map Tests to Requirements for Coverage*
