# Task 6: More Help mode in viewer

## Description

Replace native browser tooltips with a fixed help bar below the header.
When help mode is active, native `title` attributes are temporarily removed
to prevent browser tooltip overlap, then restored when help mode is toggled off.

## APPLICABLE_ASSERTIONS

- **REQ-p00006-A**: "The tool SHALL generate an interactive HTML view with clickable requirement navigation."
  - Help mode is part of interactive viewer usability.

## Manual Test Plan

1. Open viewer, click "? Help" in hamburger menu
2. Verify help bar appears below header
3. Hover over buttons -- verify help text in bar, NO native browser tooltips
4. Toggle off -- verify bar disappears and native tooltips return
