# Known Issues

[ ] Design: does Addresses support REQ->JNY, JNY->REQ, or both? I think we only use JNT->REQ?

[ ] Chore: review specs for accuracy
[ ] Chore: start using Changelog in REQs

[ ] Feature: drag handles in the hierarchy, to move requirements to be children of other requirements.

[ ] Feature: **Assertion reordering** with automatic label recomputation and reference updating
- **Drag-and-drop reordering** in the UI (render_order mutation)

[ ] Major Project: In elspais repo, udpdate spec file naming convention
- Rename spec/ files more sensibly  and consistently
- Renumber REQs to follow a pre-fix-per-file convention (not enforced, just for convenience)
- Maybe a tool to help with renumber REQs (it will have to check all code, test, doc, etc files and make approte replacements.

[ ] Feature: **Dart/Flutter parser support** (function detection strategy, result parser)

[x] Chore: DRY: search for every instance of string matching using regex or character indexing, splitting on chars, etc. Determine if they are doing something unique or if they should be using a defined library function like IdResolver. We don't want to implement the same parsing or rendering code more than once, for maintainability.
