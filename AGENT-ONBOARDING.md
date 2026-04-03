# Adopting elspais — Agent Onboarding Guide

This document tells an AI coding agent everything it needs to adopt
**elspais** for a project: install it, configure it, write requirements,
link code, and keep the traceability graph healthy.

---

## What elspais Does

elspais is a requirements traceability tool. It validates that product
requirements are traced through implementation code and tests — the automated
equivalent of maintaining a Requirements Traceability Matrix (RTM).

Requirements form a hierarchy:

```text
PRD-p00001: User Authentication          (what the system must do)
  |
  +-- DEV-d00001: Password Hashing       (how — Refines PRD-p00001-A)
  |     +-- src/auth/hash.py            (Implements DEV-d00001-A)
  |     +-- tests/test_hash.py          (Verifies DEV-d00001-A)
  |
  +-- DEV-d00002: Account Lockout        (how — Refines PRD-p00001-B)
        +-- src/auth/lockout.py         (Implements DEV-d00002-A)
        +-- tests/test_lockout.py       (Verifies DEV-d00002-A)
```

`elspais checks` verifies the chain is complete — every requirement has
assertions, every assertion is implemented, every implementation is tested.

---

## 1. Install

```shell
pip install elspais            # core (validation, tracing, CLI)
pip install elspais[mcp]       # + MCP server for AI agent integration
pip install elspais[all]       # + HTML viewer, review server, MCP
```

## 2. Initialize the Project

From the repository root:

```shell
elspais init              # creates .elspais.toml with commented defaults
elspais init --template   # also creates spec/EXAMPLE-requirement.md
```

Review `.elspais.toml` and adjust:

- **`[project]`** — name, description
- **`[levels]`** — hierarchy tiers (default: PRD -> OPS -> DEV)
- **`[id-patterns]`** — requirement ID format and assertion labels
- **`[scanning]`** — which directories contain spec, code, test, and result files

## 3. Register the MCP Server

The MCP server gives you ~30 tools for searching, navigating, and mutating
the requirement graph without touching files directly.

```shell
elspais mcp install       # registers with Claude Code / Claude Desktop
```

Or add manually to `.mcp.json`:

```json
{
  "mcpServers": {
    "elspais": {
      "command": "elspais",
      "args": ["mcp", "serve"]
    }
  }
}
```

### Essential MCP Tools

| Task                        | Tool                                          |
|-----------------------------|-----------------------------------------------|
| Orient yourself             | `get_workspace_info()`, `get_project_summary()`|
| Find requirements           | `search(query)`, `discover_requirements()`     |
| Read a requirement          | `get_requirement(id)`, `get_hierarchy(id)`     |
| Find coverage gaps          | `get_uncovered_assertions()`                   |
| Get authoring rules         | `agent_instructions()`                         |
| Browse documentation        | `docs(topic)`, `faq(topic)`                    |
| Draft changes (in-memory)   | `mutate_add_requirement()`, `mutate_add_assertion()` |
| Persist changes to disk     | `save_mutations()`                             |
| Undo a mistake              | `undo_last_mutation()`                         |

## 4. Add elspais Guidance to Your Project's CLAUDE.md

Paste something like this into the project's `CLAUDE.md` (or equivalent
agent-instructions file):

```markdown
## Requirements Traceability

This project uses elspais for requirements traceability.
Read `AGENT-ONBOARDING.md` for the full guide and assertion style guide.

- **Requirements are the sole source of truth** for what the system must
  do. Do not duplicate obligations in wikis, tickets, or inline comments.
  If it is normative, it belongs in a REQ file in `spec/`.
- **Non-normative content belongs inside requirements too.** Requirements
  can contain Rationale sections, examples, diagrams, and other
  explanatory prose outside `## Assertions`. This keeps context
  co-located with the obligations it supports — no separate design docs
  needed. Only assertions (using SHALL) are normative.
- **Before writing requirements**: call `agent_instructions()` via MCP
- **To search requirements**: use MCP tools (`search`, `get_requirement`,
  `get_hierarchy`), not grep
- Requirement files live in `spec/` (PRD, OPS, DEV levels)
- Code links: `# Implements: REQ-xxx-A` in source files
- Test links: `# Verifies: REQ-xxx-A` in test files
- After changes: run `elspais fix` then `elspais checks`
```

---

## The Agent Workflow

### Orient

```
get_workspace_info()        # project config, ID patterns, hierarchy
get_project_summary()       # counts by level, coverage stats, health
```

### Find

```
search("authentication")    # keyword search across all requirements
discover_requirements("login", scope_id="REQ-p00001")  # scoped + minimized
```

### Read

```
get_requirement("REQ-p00001")   # full text, assertions, relationships
get_hierarchy("REQ-p00001")     # ancestors to roots + direct children
```

### Write

Author requirements following the format below, or use MCP mutation tools:

```
mutate_add_requirement(req_id, title, level, ...)
mutate_add_assertion(req_id, label, text)
save_mutations()            # persist to spec files
```

> **Recommendation: Use a subagent for writing requirements.**
>
> Requirements authoring is detail-heavy work with its own rules, style
> guide, and validation cycle. Delegating it to a dedicated subagent
> keeps the main conversation focused on the feature task while giving
> the requirement work the attention it needs.
>
> **Why a subagent?**
>
> - **Context isolation** — the subagent loads the style guide,
>   `requirements-spec.md`, existing parent requirements, and the
>   assertion self-check into its own context without cluttering the
>   main session.
> - **Iterative refinement** — the subagent can draft, run
>   `elspais fix` + `elspais checks`, fix validation errors, and
>   re-check in a tight loop without blocking the caller.
> - **Consistency** — a subagent briefed once with the full authoring
>   rules produces more uniform output than an agent context-switching
>   between code and spec work.
>
> **How to brief the subagent:**
>
> 1. Tell it to read `AGENT-ONBOARDING.md` (this document) and
>    `spec/AI-AGENT.md` for authoring rules.
> 2. If the MCP server is available, tell it to call
>    `agent_instructions()` for project-specific conventions.
> 3. Give it the specific task: which requirements to create or revise,
>    which parent assertions they refine, and at what level (PRD/OPS/DEV).
> 4. Tell it to run `elspais fix` and `elspais checks` before
>    reporting back, so it returns clean, validated output.
>
> **Example prompt:**
>
> ```
> You are a requirements author for this project. Read
> AGENT-ONBOARDING.md and spec/AI-AGENT.md for authoring rules.
> Call agent_instructions() via the elspais MCP server for
> project-specific conventions.
>
> Task: Write a DEV requirement that refines REQ-p00003-A
> (session timeout). It should specify the idle-timeout mechanism
> and token invalidation behavior. Use EARS syntax for assertions.
>
> After writing, run `elspais fix` then `elspais checks` and fix
> any errors before reporting back.
> ```

### Validate

```shell
elspais fix          # auto-fix hashes and formatting
elspais checks       # verify traceability chain
elspais gaps         # list requirements missing coverage
```

### Link Code

```python
# In source files:
# Implements: REQ-d00001-A
def hash_password(plaintext: str) -> str:
    ...

# In test files:
# Verifies: REQ-d00001-A
def test_password_uses_bcrypt():
    ...
```

---

## Requirements Are the Source of Truth

Requirement files in `spec/` are the **sole authoritative source** for what
the system must do. Do not duplicate obligations in wikis, Jira tickets,
Slack threads, or inline code comments. If a statement is normative — if
the system must satisfy it — it belongs in a REQ file as an assertion.

**Non-normative content belongs inside requirements too.** A requirement is
not just its assertions. It can (and should) contain:

- **Rationale** sections explaining *why* the obligation exists
- **Examples** showing expected inputs, outputs, or interactions
- **Diagrams** illustrating workflows or state machines
- **Design notes** capturing context that future readers will need
- **Regulatory references** linking to standards or regulations

This non-normative prose lives alongside the assertions in the same REQ
file, keeping context co-located with the obligations it supports. There
is no need for separate design documents or specification wikis — the
requirement file is the single artifact. Only content inside
`## Assertions` using the SHALL keyword is normative and tracked by
elspais; everything else is supporting documentation.

---

## Requirement Format Reference

A requirement looks like this:

```markdown
# REQ-p00001: User Authentication

**Level**: PRD | **Status**: Active

**Purpose:** Enable secure user login.

## Assertions

A. The system SHALL authenticate users via email and password.
B. The system SHALL lock accounts after 5 failed login attempts.

*End* *User Authentication* | **Hash**: 00000000
```

### Key Structural Rules

- **Header**: `# REQ-{id}: {Title}` — one requirement per heading
- **Metadata**: Level (PRD/OPS/DEV), Status (Draft/Review/Active/Deprecated)
- **Traceability**: `Implements:` or `Refines:` references to parent assertions
- **Assertions**: Labeled A-Z in `## Assertions` section
- **Footer**: `*End* *{Title}* | **Hash**: {value}` — hash managed by `elspais fix`
- **No Acceptance Criteria sections** — assertions ARE the acceptance criteria

### Audience Discipline

| Level | Audience           | Content                                      |
|-------|--------------------|----------------------------------------------|
| PRD   | Stakeholders       | Externally visible behavior, regulatory needs |
| OPS   | Operations/Process | Runtime, deployment, operational obligations  |
| DEV   | Engineers          | Architectural and technical commitments       |

Do not mix levels. PRD says *what*; DEV says *how*; OPS says *under what
operational constraints*.

### Traceability Direction

Traceability is **one-way only** — children reference parents:

```text
  PRD-p00001-A           (defines the obligation)
       ^
       |  Refines:
       |
  DEV-d00001             (refines the obligation into specifics)
       ^
       |  Implements:
       |
  src/auth/hash.py       (satisfies the obligation in code)
       ^
       |  Verifies:
       |
  tests/test_hash.py     (proves the obligation is met)
```

Parents NEVER reference children. Never add reverse links.

---

## Assertion Style Guide

Good assertions are the foundation of a useful traceability graph.
A bad assertion — vague, compound, or untestable — makes the entire
chain from requirement through code to test meaningless.

### The Golden Rule

> Every assertion must be independently decidable as **pass** or **fail**
> by a single test, with no additional context required.

### Use EARS Syntax

The **Easy Approach to Requirements Syntax** (EARS) eliminates ambiguity
by classifying the condition type before stating the obligation:

| Pattern           | Keyword      | Template                                                 |
|-------------------|--------------|----------------------------------------------------------|
| Ubiquitous        | *(none)*     | The system SHALL [response].                             |
| Event-Driven      | **When**     | When [trigger], the system SHALL [response].             |
| State-Driven      | **While**    | While [state], the system SHALL [response].              |
| Unwanted Behavior | **If / Then**| If [unwanted event], then the system SHALL [response].   |
| Optional Feature  | **Where**    | Where [optional feature], the system SHALL [response].   |

Triggers can be combined for complex conditions:

> "While in a user session, when the admin modifies a role, the system
> SHALL require a secondary electronic signature to commit the change."

### Use Prescriptive Language

Assertions describe what the system **SHALL** do, not what it *does* or
*has*.

| Wrong (descriptive)                    | Right (prescriptive)                                 |
|----------------------------------------|------------------------------------------------------|
| "The system encrypts data at rest."    | "The system SHALL encrypt all data at rest using AES-256." |
| "Users can reset passwords."           | "When a user requests a password reset, the system SHALL send a reset link within 60 seconds." |
| "The API has rate limiting."           | "The system SHALL reject requests exceeding 100 per minute per API key with HTTP 429." |

### One Obligation Per Assertion

Each assertion must express exactly **one** testable claim. If you can
imagine one part passing and another failing, split it.

**Bad** — compound:

> A. The system SHALL validate the email format AND check that the domain has valid MX records.

**Good** — split:

> A. The system SHALL reject email addresses that do not conform to RFC 5322 syntax.
> B. The system SHALL reject email addresses whose domain lacks a valid MX record.

Watch for these compound-assertion signals:

| Signal        | Example                                 |
|---------------|-----------------------------------------|
| AND           | "SHALL log the event AND notify admin"  |
| semicolons    | "SHALL encrypt data; SHALL rotate keys" |
| "as well as"  | "SHALL validate input as well as sanitize output" |
| "in addition" | "SHALL store the record in addition to sending a confirmation" |

**Exception**: A list of items governed by one predicate is fine — it is
one obligation applied to multiple values:

> A. Passwords SHALL NOT contain the user's name, email address, or date of birth.

This is one check ("password must not contain PII"), not three independent
obligations.

### No Ambiguous Adjectives

Auditors and test engineers need objective criteria. Replace subjective
terms with measurable thresholds.

| Banned Term   | Replacement Example                                      |
|---------------|----------------------------------------------------------|
| fast          | "within 200 ms at the 95th percentile"                   |
| secure        | "using TLS 1.3 with a minimum 2048-bit RSA key"         |
| user-friendly | "completable by a first-time user within 3 minutes"     |
| efficient     | "using no more than 512 MB of heap memory"               |
| reliable      | "achieving 99.9% uptime measured over 30-day windows"    |
| robust        | "recovering to operational state within 60 seconds of a single-node failure" |
| intuitive     | *(describe the specific interaction or workflow)*         |
| scalable      | "supporting 10,000 concurrent sessions"                  |

### No Implementation Details at PRD Level

PRD assertions describe *what* the system must do for its users, not
*how* it achieves it. Technology choices belong at DEV level.

**Bad** (PRD):

> A. The system SHALL store user profiles in PostgreSQL 16 with pgcrypto column-level encryption.

**Good** (PRD):

> A. The system SHALL encrypt user profile data at rest.

The database choice and encryption library go in the DEV requirement that
refines this assertion.

### Self-Contained Assertions

An assertion must be understandable and testable from its own text alone.
Do not reference other assertions, requirements, or validation IDs.

**Bad**:

> A. The system SHALL satisfy the criteria defined in REQ-p00003-B.

**Good**:

> A. The system SHALL retain audit log entries for a minimum of 7 years from the date of creation.

### Use Defined Terms Consistently

Domain-specific terms should match the project glossary. Bold glossary
terms on first use in a requirement to signal that the word has a
controlled definition.

> A. When a **Subject** withdraws consent, the system SHALL delete all **Electronic Records** associated with that **Subject** within 30 calendar days.

### Keyword Discipline

- **SHALL** / **SHALL NOT** — the only normative keywords; use them
  exclusively inside the `## Assertions` section
- **MUST** / **MUST NOT** / **MAY** — do not use these anywhere
- Outside `## Assertions`, use plain language (the rationale section
  explains *why*, not *what*)

### Variables and Placeholders

Enclose configurable values in double curly braces so they are visually
distinct from literal text:

> A. The system SHALL lock a user account after `{{max_failed_attempts}}` consecutive failed login attempts.

### Assertion Labels

- Labels run A through Z (maximum 26 per requirement)
- Labels are **stable** — once assigned, a label is never reused even
  if the assertion is deleted
- If you delete assertion C, the next new assertion is the next unused
  letter, not C again

### Quick Self-Check

Before finalizing an assertion, verify:

1. **Single obligation?** Can you write exactly one test for it?
2. **Pass/fail clear?** Could a stranger determine pass or fail from
   the text alone?
3. **No banned words?** Search for: fast, secure, efficient, reliable,
   robust, intuitive, user-friendly, scalable.
4. **No compound signals?** Search for: AND, semicolons, "as well as",
   "in addition to".
5. **Prescriptive?** Does it say "SHALL", not "does", "has", "can",
   or "will"?
6. **Self-contained?** Does it avoid referencing other requirement IDs?
7. **Right level?** PRD = behavior, DEV = mechanism, OPS = operations.

---

## Common Mistakes

| Mistake                                | Fix                                              |
|----------------------------------------|--------------------------------------------------|
| Writing "Acceptance Criteria" sections | Use labeled assertions (A, B, C...) instead      |
| Parent requirement lists its children  | Remove reverse references; children use `Implements:` |
| Restating a parent's assertion in a child | Refine it — add specificity, don't repeat       |
| Manually editing hash values           | Run `elspais fix` — it manages hashes            |
| Using grep to find requirements        | Use MCP tools: `search()`, `get_requirement()`   |
| Mixing PRD and DEV concerns            | Split into separate requirements at proper levels |
| Forgetting to link code                | Add `# Implements:` comments; run `elspais gaps`  |
| Writing tests without `# Verifies:`   | Add the comment; otherwise the test is invisible  |

---

## Reference

| Command              | Purpose                                    |
|----------------------|--------------------------------------------|
| `elspais init`       | Create `.elspais.toml` config              |
| `elspais checks`     | Validate traceability chain                |
| `elspais fix`        | Auto-fix hashes and formatting             |
| `elspais gaps`       | List requirements missing coverage         |
| `elspais trace`      | Generate traceability matrix               |
| `elspais viewer`     | Interactive HTML traceability viewer       |
| `elspais search`     | Find requirements by keyword               |
| `elspais changed`    | Show requirements with uncommitted changes |
| `elspais docs`       | Browse built-in documentation              |
| `elspais mcp serve`  | Start the MCP server                       |
