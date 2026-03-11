# Known Issues

[x] CLI: Why does --help work, but help does does not

[x] CLI: when given bad arg, give a more readable error message. Perhaps just clearly suggest 'help'

[x] Chore: remove non-REQ files from spec/ directory.
- docs/superpowers/specs/2026-03-09-graph-analysis-design.md
- add spec/plans/ to gitignore

[x] Chore: remove all extraneous docs/ files and dirs
- docs/plans/*
- docs/superpowers/*
- add those to gitignore

[ ] Chore: start using Changelog in REQs

[x] Chore: review docs for accuracy

[ ] Chore: review specs for accuracy

[ ] Design: does Addresses support REQ->JNY, JNY->REQ, or both?

[ ] Feature: "More Help" mode, where the hover-help text shows in a fixed part of the header bar (so it doesn't obscure data being viewed), and is more descriptive.

[ ] Feature: Need a way to change a REQ -> REQ link to a REQ -> Assertion link.

[ ] Feature: drag handles in the hierarchy, to move requirements to be children of other requirements.

[ ] Project: Spec file naming convention
Rename spec/ files more sensibly  and consistently
Renumber REQs to follow a pre-fix-per-file convention (not enforced, just for convenience)
Maybe a tool to help with renumber REQs (it will have to check all code, test, doc, etc files and make approte replacements.
