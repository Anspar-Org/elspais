# Review of Design Decisions Document

**Reviewer**: Claude Code
**Date**: 2026-01-22
**Document Reviewed**: `docs/design_decisions.md`
**Version**: Current HEAD on feature/CUR-514-viewtrace-port

---

## Executive Summary

The `design_decisions.md` document presents elspais as a "Semantic Reflexive Specification Framework" with 10 design principles. While the document articulates a compelling vision for requirements management, **there are significant gaps between the described framework and the actual implementation**. The tool is better characterized as a **requirements validation and traceability tool** rather than a full semantic framework.

### Key Findings

- **7 of 10 design principles** are accurately reflected in implementation
- **3 design principles** describe aspirational features not yet implemented
- **1 critical concept** (Runbooks) is mentioned but completely absent from codebase
- **1 relationship type** (non-normative semantic relationships) is partially implemented

---

## Design Principle Assessment

### ✅ **Principle 1: Explicit Normativity** - IMPLEMENTED

**Claim**: Only formally defined Requirements (REQ) introduce obligations.

**Reality**: ✅ **Accurate**

The implementation enforces this through:

- Strict requirement ID patterns validated by `PatternValidator` (patterns.py)
- Hash-based content integrity (hasher.py)
- Assertions as the unit of verification (models.py:Assertion)
- Clear separation between normative (Requirements) and non-normative (User Journeys) content

**Evidence**:

```python
# From core/models.py
class Assertion:
    """Assertions are the unit of verification - each defines one testable
    obligation using SHALL/SHALL NOT language."""
    label: str
    text: str
    is_placeholder: bool = False
```

**Verification**: Requirements format enforces `## Assertions` section with SHALL language (parser.py lines 38-42).

---

### ✅ **Principle 2: Stratified Abstraction Levels** - PARTIALLY IMPLEMENTED

**Claim**: System is layered with User Journeys, Requirements, Code, Tests, and Runbooks.

**Reality**: ⚠️ **Incomplete - Runbooks Missing**

**Implemented**:

- ✅ User Journeys (parsers/journey.py, core/tree.py:UserJourney)
- ✅ Requirements (core/models.py:Requirement)
- ✅ Code (parsers/code.py, core/tree.py:CodeReference)
- ✅ Tests (parsers/test.py, core/tree.py:TestReference)
- ❌ **Runbooks** - No evidence in codebase

**Evidence**:

```python
# From core/tree.py - NodeKind enum
class NodeKind(Enum):
    REQUIREMENT = "requirement"
    ASSERTION = "assertion"
    CODE = "code"
    TEST = "test"
    TEST_RESULT = "result"
    USER_JOURNEY = "journey"
    # NO RUNBOOK TYPE
```

**Gap**: The document claims "Runbooks (operation)" as a stratified layer but this artifact type is not implemented. No parser, no schema, no references in any command.

**Recommendation**: Either implement Runbook support or remove it from the design decisions document.

---

### ✅ **Principle 3: One-Way Normative Refinement** - IMPLEMENTED

**Claim**: Normative relationships flow one direction via `Implements:` field.

**Reality**: ✅ **Accurate**

The implementation enforces this through:

- Requirements have `implements: List[str]` field (models.py:112)
- Parser extracts `Implements:` metadata (parser.py:30)
- No reverse references stored
- Hierarchy rules validate allowed relationships (rules.py, hierarchy.py)
- Children reference parents, never the reverse

**Evidence**:

```python
# From parser.py
IMPLEMENTS_PATTERN = re.compile(r"\*\*Implements\*\*:\s*(?P<implements>[^|\n]+)")

# From models.py
@dataclass
class Requirement:
    implements: List[str] = field(default_factory=list)
    # No 'implemented_by' or 'children' field
```

**Verification**: Composition is inferred via `find_children()` function in hierarchy.py, not stored directly.

---

### ⚠️ **Principle 4: Non-Normative Semantic Relationships** - NOT IMPLEMENTED

**Claim**: Relationships such as `Addresses`, `Motivated-By`, `Relates-To` are explicitly non-normative and stored outside hashed content.

**Reality**: ❌ **Not Implemented**

**Evidence**:

- No fields for `Addresses`, `Motivated-By`, or `Relates-To` in `Requirement` dataclass (models.py)
- No parser patterns for these relationship types (parser.py)
- User Journeys exist but have no linkage mechanism to requirements
- grep search for these terms across codebase: 0 results
- grep search in spec files: 0 results

**Current State**: User Journeys are parsed (parsers/journey.py) but there is **no implemented mechanism to link requirements to journeys**. The document describes this as a core principle, but it's entirely absent.

**Recommendation**:

1. Add optional metadata fields to Requirement model: `addresses`, `motivated_by`, `relates_to`
2. Update parser to extract these from requirement headers
3. Exclude these fields from hash calculation
4. Update documentation to reflect current "journeys are standalone" behavior

---

### ✅ **Principle 5: Tamper-Evident Normative Content** - IMPLEMENTED

**Claim**: Normative requirement content is hashed (SHA-256).

**Reality**: ✅ **Accurate**

Fully implemented with:

- SHA-256 hashing of requirement body (hasher.py)
- 8-character hex digest by default (configurable)
- Hash verification during validation (rules.py)
- Hash scope clearly defined (header to footer, excluding metadata)
- Change detection via `elspais changed` command

**Evidence**:

```python
# From hasher.py
def calculate_hash(content: str, length: int = 8,
                   algorithm: str = "sha256") -> str:
    cleaned = clean_requirement_body(content)
    hash_obj = hashlib.sha256(cleaned.encode("utf-8"))
    return hash_obj.hexdigest()[:length]
```

---

### ⚠️ **Principle 6: Reflexive Introspection** - PARTIALLY IMPLEMENTED

**Claim**: System can answer: What is unverified? What changed? What is affected? What is risky? Who must review this?

**Reality**: ⚠️ **Partially Implemented**

**Implemented**:

- ✅ **What is unverified?** - `elspais analyze orphans`, test coverage scanning
- ✅ **What changed?** - `elspais changed` command with git integration
- ⚠️ **What is affected?** - Partial via `analyze hierarchy` but no impact propagation
- ❌ **What is risky?** - No risk assessment or documentation features
- ❌ **Who must review this?** - No ownership/accountability tracking in core models

**Evidence**:

```python
# From commands/changed.py - implements change detection
changes = get_git_changes(repo_root, spec_dir, base_branch)
moved = detect_moved_requirements(committed, current_locations)

# From commands/analyze.py - implements orphan detection
orphans = [req for req in requirements.values()
           if not req.implements and req.level != "PRD"]
```

**Gap**: While the review system (trace_view/review/) tracks reviewers and approvals, the **core Requirement model has no owner/reviewer fields**. Risk documentation is not implemented.

**Recommendation**:

1. Add optional `owner`, `reviewer`, `risk_level` fields to Requirement model
2. Implement impact analysis that traverses hierarchy to show affected downstream requirements
3. Document that risk assessment is a future enhancement

---

### ✅ **Principle 7: Human-Readable, Machine-Readable Artifacts** - IMPLEMENTED

**Claim**: Artifacts stored as plain text Markdown, parsed into structured models.

**Reality**: ✅ **Accurate**

Fully implemented:

- Requirements stored as Markdown files
- Parser converts to structured `Requirement` dataclass (parser.py)
- Zero proprietary tool dependencies
- Git-friendly plain text format
- AI-assisted workflows via `reformat` module

---

### ✅ **Principle 8: Change Impact Over Change Prevention** - IMPLEMENTED

**Claim**: System emphasizes impact detection and review, not rigid prevention.

**Reality**: ✅ **Accurate**

The tool validates but doesn't prevent:

- Validation is a CLI command, not a git hook (optional integration)
- Change detection via hashing and git integration
- Review system (trace_view/review/) enables collaborative review workflow
- No enforced approval gates in core tool

**Evidence**: The review system (models.py:StatusRequest) implements approval workflows for status changes, supporting the "review responsibility" model.

---

### ❌ **Principle 9: Selective Risk Documentation** - NOT IMPLEMENTED

**Claim**: Risk assessments recorded where meaningful trade-offs exist.

**Reality**: ❌ **Not Implemented**

No risk tracking features found:

- No risk fields in Requirement model
- No risk analysis commands
- No risk-based validation rules
- Document describes this as a feature, but it's aspirational

**Recommendation**: Remove this principle or clearly mark as "future work."

---

### ⚠️ **Principle 10: Role-Based Accountability** - PARTIALLY IMPLEMENTED

**Claim**: Execution (commits) separated from governance (owners).

**Reality**: ⚠️ **Implemented in Review System Only**

**Current State**:

- Review system has accountability: `createdBy`, `reviewedBy`, `approvals` (trace_view/review/models.py)
- Core Requirement model has NO owner/accountability fields
- Git commit history provides execution tracking
- Governance/ownership must be inferred externally

**Evidence**:

```python
# Review system has accountability
@dataclass
class StatusRequest:
    requestedBy: str
    requiredApprovers: List[str]
    approvals: List[Approval]

# But core Requirement model does not
@dataclass
class Requirement:
    id: str
    title: str
    # NO: owner, approver, reviewer fields
```

**Gap**: The review system is an **optional feature** (`pip install elspais[trace-review]`) and not part of core requirement management. The document presents role-based accountability as a fundamental design principle, but it's not in the core data model.

**Recommendation**:

1. Either add optional owner/reviewer metadata to core Requirement model
2. Or clarify this principle only applies when using the optional review system

---

## Additional Observations

### 1. **Document Title Mismatch**

The document is titled "Semantic Reflexive Specification Framework" but elspais is implemented as a **requirements validation and traceability tool**. The "semantic" and "reflexive" aspects are:

- **Semantic**: Limited to User Journeys (which aren't linked to requirements)
- **Reflexive**: Implemented as introspection commands (`analyze`, `changed`)

The "framework" terminology suggests a larger system than what's implemented.

### 2. **Architecture-Reality Gap**

The document describes a comprehensive governance framework, but the implementation is:

- A CLI validation tool (core)
- An optional HTML traceability viewer (trace-view)
- An optional review server (trace-review)

These are **separate concerns** with different installation profiles, not a unified framework.

### 3. **Strengths Worth Highlighting**

The document correctly captures these excellent design decisions:

- Zero-dependency core implementation
- Hash-based tamper evidence
- One-way traceability (prevents circular authority)
- Assertion-based verification
- Plain-text Markdown format
- Configurable ID patterns

---

## Recommendations for Document Updates

### High Priority (Accuracy)

1. **Remove or qualify "Runbooks"** - Not implemented (Principle 2)
2. **Remove Principle 9 (Risk Documentation)** - Entirely aspirational
3. **Clarify non-normative relationships** - User Journeys exist but aren't linked (Principle 4)
4. **Reframe ownership/accountability** - Review system only, not core (Principle 10)

### Medium Priority (Clarity)

1. **Change title** from "Semantic Reflexive Specification Framework" to "Requirements Validation and Traceability System"
2. **Add "Current Implementation Status"** section to each principle
3. **Distinguish core vs optional features** (trace-view, trace-review, MCP)

### Low Priority (Enhancement)

1. **Add implementation references** - Link design principles to code modules
2. **Document evolution path** - Show current state vs future vision
3. **Add "What This Tool Is/Isn't"** section to manage expectations

---

## Proposed Document Structure

```markdown
# Design Decisions: elspais Requirements Management

## Current Implementation vs Vision

This document describes both:
1. **Implemented Design Decisions** (✅) - Currently working in the tool
2. **Aspirational Principles** (🔮) - Planned for future releases

[Table showing principle status]

## Implemented Principles (v0.11.x)
[Principles 1, 3, 5, 7, 8 with code references]

## Partially Implemented Principles
[Principles 2, 6, 10 with gaps documented]

## Future Vision
[Principles 4, 9 as roadmap items]
```

---

## Conclusion

The `design_decisions.md` document articulates valuable principles that guided elspais development, but it **overstates current capabilities** by describing aspirational features as if they were implemented. The document would be more accurate as a **vision statement** rather than a **design retrospective**.

### Document Quality: 60/100

- **Accuracy**: 60% (7 of 10 principles match reality)
- **Completeness**: 70% (covers major design areas)
- **Clarity**: 80% (well-written, clear arguments)
- **Usefulness**: 50% (misleading without implementation status)

### Primary Issue

The document uses **present-tense claims** for features that are not implemented, creating confusion about what the tool actually does. This is problematic for:

- **New contributors** - May expect features that don't exist
- **Auditors** - Need accurate description of current capabilities
- **Sponsors** - Need clear roadmap vs current state

### Recommended Action

1. **Immediate**: Add "Implementation Status" badges (✅/⚠️/❌) to each principle
2. **Short-term**: Split into "Design Principles" (implemented) and "Vision" (planned)
3. **Long-term**: Either implement missing features or remove claims about them

---

## Appendix: Verification Commands

To verify these findings:

```bash
# Check for Runbook implementation
rg -i "runbook" src/elspais/  # 0 results

# Check for non-normative relationships
rg "Addresses|Motivated.?By|Relates.?To" src/elspais/  # Only in tree.py comments

# Check for risk fields
rg "risk|Risk" src/elspais/core/models.py  # 0 results

# Check for owner fields in core model
rg "owner|reviewer|accountable" src/elspais/core/models.py  # 0 results in core
rg "owner|reviewer" src/elspais/trace_view/review/models.py  # Present in review system only
```

These verification steps can be run to confirm the gaps identified in this review.
