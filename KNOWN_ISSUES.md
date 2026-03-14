# Known Issues

[ ] Chore: start using Changelog in REQs

[ ] Chore: review specs for accuracy

[ ] Design: does Addresses support REQ->JNY, JNY->REQ, or both?

[ ] Feature: "More Help" mode, where the hover-help text shows in a fixed part of the header bar (so it doesn't obscure data being viewed), and is more descriptive.

[ ] Feature: Need a way to change a REQ -> REQ link to a REQ -> Assertion link.

[ ] Feature: drag handles in the hierarchy, to move requirements to be children of other requirements.

[ ] Project: In elspais repo, udpdate spec file naming convention
- Rename spec/ files more sensibly  and consistently
- Renumber REQs to follow a pre-fix-per-file convention (not enforced, just for convenience)
- Maybe a tool to help with renumber REQs (it will have to check all code, test, doc, etc files and make approte replacements.

## 8. Deferred Features

The following are enabled by this architecture but deferred to future plans:

- **Assertion reordering** with automatic label recomputation and reference updating
- **Drag-and-drop reordering** in the UI (render_order mutation)
- **File rename** as a graph mutation (update FILE node path, persist)
- **Move requirement between files** as a graph mutation (change CONTAINS edge from one FILE to another)
- **Dart/Flutter parser support** (function detection strategy, result parser)
