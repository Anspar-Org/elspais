# MASTER PLAN — JNY Trace View Enhancements

**Branch**: `user-journeys`
**Ticket**: CUR-837
**CURRENT_ASSERTIONS**: REQ-o00050-C

## Goal

Wire up JNY→REQ linking in the trace view so user journeys connect to the requirements they address. Add an `Addresses:` field to JNY blocks (parsed into ADDRESSES edges), render those links as clickable badges on journey cards, and include JNY nodes in `elspais index regenerate` output.

## Context

User journeys (JNY nodes) appear in the trace view as island nodes with no connections to requirements. In the Callisto project, JNY→REQ associations are hand-maintained in INDEX.md but aren't parseable by the graph. The `EdgeKind.ADDRESSES` edge type already exists in `relations.py` but nothing creates these edges.

## What Already Exists

| Component | Status |
|-----------|--------|
| `EdgeKind.ADDRESSES` in `relations.py` | Exists, non-coverage |
| `JourneyParser` in `parsers/journey.py` | Parses id/title/actor/goal only |
| `_add_journey()` in `builder.py:1695` | Creates nodes, no edges |
| `JourneyItem` in `html/generator.py:53` | No referenced_reqs field |
| Trace view journey tab | Cards with search/grouping, no REQ links |
| `elspais index regenerate` | REQ only, no JNY section |

## Implementation Steps

### Step 1: JourneyParser — Parse `Addresses:` field

`src/elspais/graph/parsers/journey.py`:
- [x] Add `ADDRESSES_PATTERN` regex to match `Addresses: REQ-xxx, REQ-yyy`
- [x] Extract addresses list in `_parse_journey()`, store in `data["addresses"]`

Supports JNY block format:
```markdown
# JNY-Dev-Setup-01: Set Up Requirements for a New Feature

**Actor**: Sarah (Developer)
**Goal**: Create a validated DEV requirement
Addresses: REQ-p00012, REQ-d00042
```

### Step 2: GraphBuilder — Create ADDRESSES edges from JNY→REQ

`src/elspais/graph/builder.py`:
- [x] In `_add_journey()` (~line 1709), queue pending links for each address ref:
  `self._pending_links.append((journey_id, addr_ref, EdgeKind.ADDRESSES))`
- [x] Existing `_resolve_pending_links()` handles target resolution and missing-target warnings

### Step 3: JourneyItem — Add referenced requirements to HTML data

`src/elspais/html/generator.py`:
- [x] Add `referenced_reqs: list[str]` field to `JourneyItem` dataclass (~line 62)
- [x] In `_collect_journeys()`, extract outgoing ADDRESSES edges from each journey node
- [x] Pass `referenced_reqs` to `JourneyItem`

### Step 4: Trace view template — Render linked REQs on journey cards

`src/elspais/html/templates/trace_view.html.j2`:
- [x] **HTML**: Add `journey-refs` section to each card showing "Addresses: REQ-xxx" as clickable links
- [x] **CSS**: Style `.journey-refs` as inline pill badges
- [x] **JS**: Add `switchToReqTab(reqId)` — switches tab, scrolls to row, applies flash-highlight
- [x] **Data attr**: Add `data-refs` to journey cards, update `filterJourneys()` to search it

### Step 5: Index regenerate — Add JNY section

`src/elspais/commands/index.py`:
- [x] In `_regenerate_index()` (~line 142), add User Journeys table with columns: ID, Title, File, Addresses
- [x] Populate Addresses column from outgoing ADDRESSES edges
- [x] Update `_validate_index()` to also check JNY IDs

### Step 6: Tests

- [x] New tests for JourneyParser `Addresses:` parsing
- [x] New tests for ADDRESSES edge creation in builder
- [x] New tests for index regenerate JNY section
- [x] Existing tests still pass: `pytest tests/core/test_parsers/test_journey_parser.py`

### Step 7: Add `Addresses:` to Elspais JNY files

- [x] Add `Addresses:` lines to the 17 journeys in `spec/journeys/*.md` referencing relevant REQs

## Files to Modify

| File | Change |
|------|--------|
| `src/elspais/graph/parsers/journey.py` | Parse `Addresses:` field |
| `src/elspais/graph/builder.py` | Queue ADDRESSES edges in `_add_journey()` |
| `src/elspais/html/generator.py` | Add `referenced_reqs` to `JourneyItem` |
| `src/elspais/html/templates/trace_view.html.j2` | Render REQ links on cards, click-to-navigate |
| `src/elspais/commands/index.py` | Add JNY section to `regenerate`, validate JNY IDs |
| `spec/journeys/*.md` | Add `Addresses:` lines to journey blocks |

## What Stays the Same

- `relations.py` — `EdgeKind.ADDRESSES` already exists
- `GraphNode.py` — no new node kinds
- `factory.py` — parsers already registered
- `requirement.py` — REQ `Addresses:` field (REQ→JNY direction) is a separate concern

## Verification

1. Add `Addresses: REQ-p00012` to JNY-Dev-Setup-01
2. Build graph and confirm JNY-Dev-Setup-01 has outgoing ADDRESSES edge
3. `elspais trace --view` — journey card shows clickable "Addresses: REQ-p00012"
4. Click link — switches to requirements tab, highlights REQ-p00012
5. Search "p00012" in journey search bar — matches JNY-Dev-Setup-01
6. `elspais index regenerate` — JNY section appears with Addresses column
7. `pytest tests/` — all pass
8. `elspais validate` — no breakage

## Archive

- [x] Mark phase complete in MASTER_PLAN.md
- [x] Archive completed plan: `mv MASTER_PLAN.md ~/archive/YYYY-MM-DD/MASTER_PLANx.md`
- [x] Promote next plan: `mv MASTER_PLAN[lowest].md MASTER_PLAN.md`
- **CLEAR**: Reset checkboxes for next phase
