# Known Issues

[ ] Bug: run elspais viewer in ~/cure-hht/hht_diary/.
- It prompts to enter a branch, since that's on main (good)
- It makes the branch, but the modal to name the branch doesn't disappear
- Click Cancel: modal disappears. But the new branch shows "!".

[ ] Chore: Clarify that top search bar is for finding things and the other search bar is a filter for the tree view.
- Add "hide filtered items" checkbox.

[ ] Feature: "More Help" mode, where the hover-help text shows in a fixed part of the header bar (so it doesn't obscure data being viewed), and is more descriptive.

[ ] Feature: Need a way to change a REQ -> REQ link to a REQ -> Assertion link.

[ ] Feature: Need a way to show the "importance" of a requirement, based on how much it is referenced.

[ ] Feature: drag handles in the hierarchy, to move requirements to be children of other requirements.

[ ] Project: Spec file naming convention
Rename spec/ files more sensibly  and consistently
Renumber REQs to follow a pre-fix-per-file convention (not enforced, just for convenience)
Maybe a tool to help with renumber REQs (it will have to check all code, test, doc, etc files and make approte replacements.
