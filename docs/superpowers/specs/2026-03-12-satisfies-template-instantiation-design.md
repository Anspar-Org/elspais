# Satisfies Template Instantiation Design

## Problem

The `Satisfies:` relationship was designed to enable a template-instance pattern for cross-cutting requirements (regulatory compliance, security policies, etc.). The current implementation uses an annotator-based approach (`_compute_satisfies_coverage()`) that computes per-instance coverage metrics on the declaring requirement. This approach:

- Does not create structural nodes for template instances, so the viewer cannot display them
- Requires special coverage computation separate from the standard mechanism
- Cannot be navigated in the graph like normal requirement hierarchies

## Solution

Replace the annotator-based approach with **template instantiation**: when a requirement declares `Satisfies: X`, the graph builder clones the template's REQ subtree with composite IDs. The cloned nodes are standard graph nodes that participate in normal coverage computation, viewer navigation, and health checks.

## Data Model Changes

### Stereotype Enum

A new enum classifies node roles:

```python
class Stereotype(Enum):
    CONCRETE = "concrete"    # default -- normal requirement
    TEMPLATE = "template"    # original node targeted by Satisfies
    INSTANCE = "instance"    # cloned copy of a template node
```

Stored as a field on GraphNode via `set_field("stereotype", Stereotype.TEMPLATE)`. Defaults to `CONCRETE`.

### New EdgeKind: INSTANCE

```python
class EdgeKind(Enum):
    ...
    INSTANCE = "instance"    # clone -> original template node
```

Each cloned node has an INSTANCE edge to its template original, enabling bidirectional navigation between templates and their instances.

### EdgeKind: SATISFIES (existing)

Connects the declaring requirement to the cloned template root. Already exists in the codebase.

## Builder Phase Changes

The builder's `build()` method gains a new phase between REQ tree construction and link resolution:

```text
Phase 1: Parse all content (existing, unchanged)
         SATISFIES refs collected separately from _pending_links

Phase 2: Instantiate templates (_instantiate_satisfies_templates)
         Sub-pass 1: Mark templates
           - For each SATISFIES ref, set stereotype=TEMPLATE on
             the target REQ and all descendant REQs and assertions

         Sub-pass 2: Clone & link
           - Clone each template subtree with composite IDs
           - Cloned nodes get stereotype=INSTANCE
           - INSTANCE edge from each clone to its original
           - SATISFIES edge from declaring REQ to cloned root
           - Internal edges preserved exactly (REFINES, etc.)
           - Source location preserved from template originals

Phase 3: Resolve remaining links (existing, enhanced with attribution)
         - If target has stereotype=TEMPLATE, use file-based
           attribution algorithm to redirect to correct INSTANCE

Phase 4: Root/orphan detection (existing, unchanged)
```

## Cloning Details

When cloning a template subtree for a declaring requirement (e.g., `REQ-p00044` satisfies `REQ-p80001`):

**What gets cloned:**
- All REQ nodes in the template's subtree (following REFINES edges down)
- All assertion children of those REQs (satellites)
- All internal edges between them (whatever kind they are)

**What does NOT get cloned:**
- CODE, TEST, or other non-REQ nodes that reference the template
- Edges from external nodes into the template

**Composite ID format:** `declaring_id::original_id`
- `REQ-p00044::REQ-p80001` (cloned root)
- `REQ-p00044::REQ-o80001` (cloned child REQ)
- `REQ-p00044::REQ-o80001-A` (cloned assertion)

**Cloned node properties:**
- Same label/title, body text, level, status, hash as original
- `stereotype = INSTANCE`
- Source location: preserved from original template node

**Resulting graph structure:**

```text
REQ-p00044
  +--SATISFIES--> REQ-p00044::REQ-p80001 (INSTANCE)
                    +--INSTANCE--> REQ-p80001 (TEMPLATE)
                    +--REFINES--> REQ-p00044::REQ-o80001 (INSTANCE)
                    |               +--INSTANCE--> REQ-o80001
                    |               +-- REQ-p00044::REQ-o80001-A
                    |               +-- REQ-p00044::REQ-o80001-B
                    +--REFINES--> REQ-p00044::REQ-o80002 (INSTANCE)
                                    +--INSTANCE--> REQ-o80002
                                    +-- REQ-p00044::REQ-o80002-A
                                    +-- REQ-p00044::REQ-o80002-B
```

## Coverage Attribution Algorithm

When resolving `Implements:` references in Phase 3, if the target has `stereotype=TEMPLATE`, the system must determine which instance clone the reference belongs to.

**Algorithm:**

1. Target node (e.g., `REQ-o80001-A`) has `stereotype=TEMPLATE` -- attribution required.
2. Find the template root that the target belongs to (walk up REFINES edges to reach `REQ-p80001`).
3. Find all other `Implements:` references **in the same source file** that target CONCRETE nodes.
4. For each concrete target, walk up its ancestors to find the first node with a `Satisfies:` declaration matching the template root.
5. **First match wins** -- construct the instance ID: `declaring_id::target_id` (e.g., `REQ-p00044::REQ-o80001-A`).
6. Redirect the edge to the instance node.

**Edge cases:**
- No concrete sibling in the same file: warning (cannot attribute)
- Multiple concrete siblings lead to different SATISFIES ancestors: first match, short-circuit
- Multiple templates on same declaring requirement (`Satisfies: REQ-FDA, REQ-GDPR`): each template reference is matched independently to the correct template root

## Code Removal

The following are replaced by the structural approach and should be removed:

- `_compute_satisfies_coverage()` in `graph/annotators.py`
- `check_template_coverage()` in `commands/health.py`
- `satisfies_coverage` and `satisfies_na_errors` metric storage

## Viewer Impact

Template instances are standard graph nodes, so the viewer displays them with no special handling needed:

- SATISFIES parent link on a requirement card opens the instance node card
- Existing card navigation lets users explore the instance subtree (child REQs, assertions, coverage)
- INSTANCE edges enable navigation from template originals to see all their instances
- The "Implements / Refines" section label and edit controls need updating to include SATISFIES and INSTANCE edge kinds

## Spec Changes Made

Updated `spec/prd-cross-cutting.md`:
- REQ-p00014: assertions B-D rewritten for template instantiation, Stereotype, file-based attribution
- Design details sections 3-11: fully rewritten

Updated `spec/07-graph-architecture.md`:
- REQ-o00050-C: added satisfies, instance to relationship list
- REQ-d00069-H: structural cloning replaces metric-based coverage
- REQ-d00069-I: coverage targets cloned subtree assertions
- REQ-d00069-K: gap reporting via standard coverage on instance nodes
