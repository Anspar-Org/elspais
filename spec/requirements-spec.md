# Formal Requirements Specification

## Purpose

This document defines the **canonical grammar, structure, and authoring rules** for all formal requirements in the `spec/` directory.

It is the **single source of truth** for how requirements are written, identified, hashed, decomposed, and referenced. Both humans and automated agents MUST follow this specification.

This document intentionally avoids workflow, tooling, or process guidance. Those belong in tooling or developer documentation.

---

## Normative Model

- Requirements define **obligations**, not descriptions.
- Obligations are stated using **SHALL** or **SHALL NOT**.
- Each obligation appears **exactly once** in the repository.
- Traceability is **one-way only**: more specific requirements reference more generic requirements via `Implements:` metadata.

---

## Requirement Identity

### Requirement IDs

Each requirement is uniquely identified by an ID of the form:

```text
REQ-{prefix}{number}[-{assertion}]
```

Where:

- `prefix` indicates audience:
  - `p` = PRD = Product Requirements Documention
  - `d` = DEV = Development Specification
  - `o` = OPS = Operations Documentation
- `number` is a zero-padded integer
- `assertion` is an optional single letter label [A-Z] for an Assertion

Examples:

- `REQ-p00044`
- `REQ-d00123-G`
- `REQ-o00007`

### Sponsor-Scoped Requirements

Sponsor-specific requirements MAY include a sponsor prefix in the numeric
portion of the ID, as defined by repository conventions.

Example:

- `TTN-REQ-p00001-F`.

---

## Requirement Header Grammar

Each requirement MUST begin with a **header line** immediately followed by a **metadata block**.

### Header Line

```text
{#...} REQ-{id}: {Short Descriptive Title}
```

The heading level (number of `#` characters) is unconstrained but SHOULD be consistent within a file.

### Metadata Block

The metadata block immediately follows the header line. It consists of one or more **field declarations**.

**Required fields** — each MUST appear exactly once and carry exactly one value:

| Field | Allowed values |
| ----- | -------------- |
| `Level` | One of: `PRD`, `Dev`, `Ops` |
| `Status` | One of: `Draft`, `Review`, `Active`, `Deprecated` |

**Traceability fields** — each MAY appear zero or more times; each occurrence MAY carry a comma-delimited list of REQ IDs:

| Field | Meaning |
| ----- | ------- |
| `Implements` | Parent requirements this requirement satisfies |
| `Refines` | Parent requirements this requirement specialises |

**Layout rules:**

- Field declarations MAY appear in any order.
- Field declarations MAY appear on the same line (separated by `|` or other punctuation) or on separate lines.
- Any valid Markdown formatting MAY be applied to field names and values (e.g. `**Level**`, `Level`, `` `Level` `` are all equivalent).
- Multiple occurrences of `Implements` or `Refines` are **additive**: all listed references are collected.
- Use `-` to explicitly declare that no references exist (e.g. `Implements: -`).

**Content rules:**

- `Implements` and `Refines` list **only less-specific (parent) requirements**.
- Parent requirements MUST NOT reference children.
- Duplicate references (the same REQ ID appearing more than once across all occurrences of a field) MUST be deduplicated to a single occurrence. A file containing duplicate references is considered malformed; tooling SHALL rewrite it on the next save to remove the redundancy.
- `Addresses` is optional; when present it lists User Journey IDs this requirement supports. It appears after the metadata block, before any section content, and is NOT part of the hashed content.
- `Validates` (on JNY nodes) is optional; when present on a User Journey it lists REQ IDs or assertion references (e.g., `REQ-p00001-A`) that this journey validates. Multi-assertion syntax is supported (e.g., `Validates: REQ-p00001-A+B`). The `Validates:` field contributes to UAT coverage metrics.

### Examples

Traditional single-line form:

```markdown
**Level**: PRD | **Status**: Active | **Implements**: -
```

Split across lines:

```markdown
**Level**: Dev | **Status**: Draft
**Implements**: REQ-p00001, REQ-p00002
**Refines**: REQ-p00003-A, REQ-p00003-B
```

Multiple `Implements` occurrences (additive):

```markdown
**Level**: Dev | **Status**: Draft | **Implements**: REQ-p00001, REQ-p00002
**Implements**: REQ-p00003
```

Minimal formatting:

```markdown
Level: PRD | Status: Active | Implements: -
```

---

## Assertions (Normative Content)

### Assertion Block

All testable obligations MUST appear in an `## Assertions` section.

```markdown
## Assertions

A. The system SHALL ...

B. The system SHALL ...
```

### Assertion Rules

- Each assertion MUST:
  - use SHALL,
  - express exactly one obligation,
  - be independently decidable as true or false.
- Assertion labels:
  - MUST be uppercase letters A–Z,
  - MUST be unique within the requirement,
  - MUST remain stable over time,
  - MUST NOT be reused once removed (**IMPORTANT**)
- If more than 26 assertions are required, the requirement MUST be split.

### Assertion References

Tests and other verification artifacts MAY reference:

- the entire requirement: `REQ-d00032`, or
- a specific assertion: `REQ-d00032-F`.

## Rationale Block (Optional, Non-Normative)

A requirement MAY include a `Rationale`, `Description`, `Discussion` or other non-normative blocks.
These are for context only and are NOT part of the testable requirements.
Rationale blocks MAY exist before and after the Assertion block.
Any section not titled "Assertions" SHALL be treated as a Rationale block.

```markdown
## {Rationale Block Type}
<explanation>
```

Rules:

- Rationale MUST NOT introduce new obligations.
- Rationale MUST NOT restate assertions.
- Rationale MUST NOT use SHALL or MUST language.

---

## Acceptance Criteria

Acceptance Criteria SHALL NOT be used.

Requirements MUST be written such that the assertions themselves constitute the acceptance conditions.

---

## Compositional Requirements

A compositional requirement defines a **normative obligation boundary** that is satisfied through the combined effect of multiple lower-level requirements.

Compositional requirements:

- state a single obligation,
- do not enumerate behaviors,
- do not reference contributing requirements,
- rely on downstream `Implements:` declarations for composition.

Composition is inferred, never declared.

---

## REQ-p00061: Requirement Decomposition Rules

**Level**: prd | **Status**: Active | **Implements**: -

A child requirement refines a parent when it adds specificity, constraints, or commits to mechanisms or guarantees.

## Assertions

A. A child requirement that adds specificity, constraints, or commits to mechanisms or guarantees SHALL declare its parent requirement using `Implements:` or `Refines:` in its metadata block.

B. `Implements:` and `Refines:` declarations apply to requirements only; code references and test nodes use their own linkage mechanisms.

C. Multiple requirements MAY exist at the same Level each declaring a relationship to the same parent requirement.

*End* *Requirement Decomposition Rules* | **Hash**: fc1e85fe

---

## Leaf Requirements

A requirement is a leaf when:

- all obligations are fully expressed as labeled assertions, and
- further decomposition would only restate the same obligations or turn them
  into tests.

Leaf requirements are the attachment points for implementation and verification.

---

## Prescriptive Language Requirement

Requirements MUST be prescriptive, not descriptive.

Allowed:

- "The system SHALL ..."

Forbidden:

- "The system does ..."
- "The system has ..."

Requirements define what must be true, not what currently exists.

---

## When a Section Needs a Requirement ID

A section requires a `REQ-` ID if and only if it introduces at least one
normative obligation.

Explanatory, contextual, or illustrative sections MUST NOT have requirement IDs.

---

## Document Structure Rules

- Requirement documents SHOULD use a flat heading structure.
- `REQ-` blocks SHOULD be a top-level section.
- Subheadings within a requirement are limited to:
  - Assertions
  - Rationale

---

## User Journeys (JNY)

User Journeys describe what a user wants to achieve, step by step, from their perspective. They capture the key interactions and expected outcomes for major flows.

### Purpose

User Journeys exist to:

- communicate the intended user experience,
- provide context for why requirements exist,
- help stakeholders understand the system from the user's point of view.

User Journeys are **non-normative** with respect to obligations — they do not define system requirements and SHALL NOT use normative keywords (SHALL, SHALL NOT, MUST, MUST NOT, REQUIRED).

However, User Journeys MAY declare `Validates:` references that link them to specific requirements or assertions. These links contribute to UAT coverage metrics and represent planned manual acceptance tests.

User Journeys SHALL NOT use normative keywords (SHALL, SHALL NOT, MUST, MUST NOT, REQUIRED).

### User Journey IDs

Each User Journey is uniquely identified by an ID of the form:

```text
JNY-{Descriptor}-{number}
```

Where:

- `JNY` signals this is a User Journey (not a requirement)
- `Descriptor` is a short hyphenated term identifying the journey context (e.g., `Admin-Portal`, `Participant-Diary`, `Site-Enrollment`)
- `number` is a two-digit sequence within that descriptor

Examples:

- `JNY-Admin-Portal-01`
- `JNY-Participant-Diary-03`
- `JNY-Site-Enrollment-02`

### User Journey Structure

A User Journey SHOULD follow this structure:

```markdown
# JNY-{Descriptor}-{number}: {Title}

**Actor**: {Name} ({Role})
**Goal**: {what the user wants to achieve}
**Context**: {situational background that sets up the scenario}

Validates: REQ-pXXXXX-A, REQ-pXXXXX-B+C

## Steps

1. {User action or system response}
2. {User action or system response}
3. ...

## Expected Outcome

{What success looks like from the user's perspective}

*End* *{Title}*
```

Field guidance:

- **Actor**: Include a persona name and role in parentheses for readability (e.g., "Dr. Lisa Chen (Principal Investigator)")
- **Goal**: A single sentence describing what the user wants to achieve
- **Context**: Optional but recommended; provides situational background (e.g., "Trial sponsor's IT team has deployed the portal. Dr. Chen has been designated as the first administrator.")
- **Validates**: Optional; lists REQ IDs or assertion references this journey validates (e.g., `Validates: REQ-p00001-A, REQ-p00002-A+B`). Multi-assertion syntax is supported. Contributes to UAT coverage metrics.
- **Steps**: Numbered sequence of user actions and system responses
- **Expected Outcome**: Brief statement of success from the user's perspective
- **End marker**: Required for parsing; uses format `*End* *{Title}*` (no hash since JNYs are non-normative)

### Referencing User Journeys in Requirements

Requirements MAY reference User Journeys they address. This reference appears after the REQ header line but before the body content (outside the hashed area):

```markdown
# REQ-pXXXXX: Admin Site Management

**Level**: PRD | **Status**: Active | **Implements**: REQ-pYYYYY

Addresses: JNY-Admin-Portal-01, JNY-Admin-Portal-02

## Assertions
...
```

The `Addresses:` line:

- is optional,
- lists one or more JNY IDs separated by commas,
- indicates which user journeys this requirement supports,
- is NOT part of the hashed content.

### User Journeys Declaring Validation Relationships

User Journeys MAY declare which requirements or assertions they validate using the `Validates:` field. This is the primary mechanism for UAT coverage:

```markdown
# JNY-Admin-Portal-01: Manage Admin Users

**Actor**: Dr. Lisa Chen (Principal Investigator)
**Goal**: Add a new administrator to the portal

Validates: REQ-p00001-A, REQ-p00002-A+B

## Steps
...

*End* *JNY-Admin-Portal-01*
```

The `Validates:` line:

- is optional,
- appears after the JNY header block but before the `## Steps` section,
- lists REQ IDs or assertion references separated by commas,
- supports multi-assertion syntax (e.g., `REQ-p00001-A+B` expands to `REQ-p00001-A` and `REQ-p00001-B`),
- creates `VALIDATES` edges in the traceability graph,
- contributes to UAT coverage metrics (separate from automated test coverage),
- is NOT part of the hashed content (JNYs have no hash).

### Do's and Don'ts

**DO:**

- Focus on major flows and happy paths
- Write from the user's perspective using natural language
- Describe what the user sees and does
- Keep steps at a high level of abstraction
- Include the expected outcome

**DON'T:**

- Enumerate all validation rules or error cases
- Use normative keywords (SHALL, MUST, REQUIRED, etc.) — this is enforced
- Include implementation details or technical specifics
- Duplicate content that belongs in assertions
- Create journeys for every minor variation

### Relationship to Requirements

| Aspect | User Journey (JNY) | Requirement (REQ) |
| ------ | ------------------ | ----------------- |
| Purpose | Describe user experience | Define obligations |
| Language | Descriptive ("User clicks...") | Prescriptive ("System SHALL...") |
| Validation | Manual walkthrough (`Validates:`) | Automated/formal verification |
| Granularity | Major flows only | Every testable obligation |
| Normative | No | Yes |
| Coverage role | UAT coverage via `Validates:` | Subject of coverage |

User Journeys provide **context** and **UAT validation paths**; Requirements provide **contracts**.

---

## Hash Definition

Each requirement MUST end with a Footer including a content hash:

```markdown
*End* *{Title}* | **Hash**: {value}
```

The hash calculation mode is configurable via `[validation].hash_mode` in `.elspais.toml`. Two modes are supported:

### `full-text` Mode

The hash SHALL be calculated from:

- every line AFTER the Header line
- every line BEFORE the Footer line

No normalization is applied. The hash is computed from the raw text between the header and footer lines.

### `normalized-text` Mode (Default)

The hash SHALL be calculated from **assertion text only**. Non-assertion body text (context, definitions, explanations) is excluded from the hash.

Any material behavioral constraint SHALL be expressed as an Assertion. Non-assertion text is supplementary context and does not affect the content hash.

**Normalization rules** — for each assertion, in physical file order (assertions are NOT sorted by label before hashing):

1. Collect the assertion line and any continuation lines (until the next assertion or end of body)
2. Join into a single line, collapsing internal newlines to spaces
3. Collapse multiple internal spaces to a single space
4. Strip trailing whitespace from the line
5. Normalize line endings to `\n`

All normalized assertion lines are joined with `\n`, then hashed.

**Invariances** — the following changes do NOT affect the hash:

- Trailing whitespace on assertion lines
- Line wrapping within a single assertion (multiline vs single-line)
- Multiple spaces between words
- Changes to non-assertion body text (context, definitions, rationale)
- Blank lines between assertions

**Sensitive changes** — the following changes DO affect the hash:

- Any change to assertion wording (including case changes)
- Adding, removing, or reordering assertions
