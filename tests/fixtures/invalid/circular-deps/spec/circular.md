# Circular Dependencies Test

This file contains circular dependencies that should be detected.

---

### REQ-d00001: First Requirement

**Level**: DEV | **Implements**: d00003 | **Status**: Active

This implements d00003, creating a cycle.

**Acceptance Criteria**:
- Some criterion

*End* *First Requirement* | **Hash**: circ0001
---

### REQ-d00002: Second Requirement

**Level**: DEV | **Implements**: d00001 | **Status**: Active

This implements d00001.

**Acceptance Criteria**:
- Some criterion

*End* *Second Requirement* | **Hash**: circ0002
---

### REQ-d00003: Third Requirement

**Level**: DEV | **Implements**: d00002 | **Status**: Active

This implements d00002, completing the cycle: d00001 -> d00003 -> d00002 -> d00001

**Acceptance Criteria**:
- Some criterion

*End* *Third Requirement* | **Hash**: circ0003
---
