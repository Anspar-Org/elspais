# Known Issues

[ ] Bug: the 'scroll-to' feature in the REQ Card column is scrolling to the wrong place.

[ ] Bug: in the viewer, mutations of the graph are not always reflected in all parts of the GUI. Sometimes a refresh of the page is necessary.

[ ] Feature: viewer refresh from disk button.
- Optional / config: have a file watcher detect changes.
-- and prompt for reload (max once per 30s).
-- If there are in-memory changes and on-disk changes, then raise a warning. Save the list of non-persisted mutations to "conflict.something" for the user to deal with later.

[ ] Feature: Need a way to change a REQ -> REQ link to a REQ -> Assertion link without creating whole new link and deleting the old one.

[ ] Feature: Is it possible to override one or more .toml config values from the command line? Perhaps using a 'here doc' or just passing N config names and values.

[ ] Feature: "More Help" mode, where the hover-help text shows in a fixed part of the header bar (so it doesn't obscure data being viewed), and is more descriptive.

[ ] Feature: The following are enabled by this architecture but not yet implemented:
- **File rename** as a graph mutation (update FILE node path, persist)
- **Move requirement between files** as a graph mutation (change CONTAINS edge from one FILE to another)
- Expose these capabilities in the Viewer

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
