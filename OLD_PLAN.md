# OLD_PLAN.md - Completed Enhancement Phases

This file contains completed phases moved from MASTER_PLAN.md for historical reference.

---

## User Journeys GUI Improvements (Completed 2026-01-28)

- [x] User journeys need a better trace --view GUI
  - [x] Group journeys by topic / name / file / actor
    - Added "Group by" dropdown in journey toolbar (None, Descriptor, Actor, File)
    - Implemented collapsible group sections with expand/collapse state
    - Groups are sorted alphabetically with "(none)" at the end
  - [x] Improve journey card layout and searchability
    - Extended JourneyItem with `descriptor` (extracted from JNY-{descriptor}-{number}) and `file` fields
    - Added Topic and Source metadata to journey cards
    - Search now includes descriptor and file fields
    - Journey state persists to cookie (groupBy, search, collapsed groups)
    - Added compact card variant for grouped view with truncated descriptions

**Files Modified:**
- `src/elspais/html/generator.py`: Extended JourneyItem dataclass, updated _collect_journeys()
- `src/elspais/html/templates/trace_view.html.j2`: Added CSS for groups, grouping controls, JavaScript for dynamic regrouping
