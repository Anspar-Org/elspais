# Known Issues

[ ] Feature: change ID of a Requirement
- All references are updated, creating a complete list of graph mutation operations to do so
- The list of before / after IDs are written/appended to a file (`elspais-renumbering-<before-hash>.csv`)
- This file is intended to allow updating references in non-graph locations, such as:
- docs/
- database/ (although this will eventually be a code/ dir, with filetypes .sql
- infrastructure/ (although that will eventually be a code/ dir, with filetypes .tf, .tfvars, .yaml, .sh, etc.
infra

[ ] Bug: Viewer does not display the Tree with items sorted by ID.
- e.g. p00001 should be above p00002, etc.

[x] Bug: Viewer Push button (in edit mode) isn't active unless changes were made in the viewer. But there could be changes on-disk (and therefore in memory) that could be pushed.
- The push-able state should depend on the actual file states, not on elspais activity.

[x] Feature: select branch to view and reload the graph.
- triggered by clicking on the branch name
- Both local and remote branches can be selected.
- If a remote branch, pull it local first, of course.
- If there a conflicts on the pull, just show an error and don't change anything.
- obviously refresh the GUI after loading a new branch.
- warn if unsaved in-memory edits will be lost

[ ] Feature: Add the ability to select a different commit on the current branch
- as part of the 'select branch' modal
- this is like a 'rewind' for the user - or an 'undo save'
- there are many ways this could be complicated, but let's keep it simple: if they check out the non-HEAD of a branch, then any future commits will be a force and non merge with the intermediate commits

[ ] Feature: **Dart/Flutter parser support** (function detection strategy, result parser)

[ ] Chore: review specs for accuracy

---

[ ] Feature: **Assertion reordering** with automatic label recomputation and reference updating
- Also handle Assertion deletion re-numbering (when state is 'prospective'), or marking 'deprecated' (active states)
- Don't allow editing of state = retired REQs

[ ] Major Project: In elspais repo, udpdate spec file naming convention
- Rename spec/ files more sensibly  and consistently
- Renumber REQs to follow a pre-fix-per-file convention (not enforced, just for convenience)
- The file mutators should be renumbering easy- just make sure it also catches the code and test file references, not just REQ/JNY refs.

[ ] Chore: start using Changelog in REQs

[ ] Wishlist **Drag-and-drop reordering** in the UI (render_order mutation) - prospective only
