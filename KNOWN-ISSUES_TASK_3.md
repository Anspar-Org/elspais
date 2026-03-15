# Task 3: Viewer refresh-from-disk button

## Description

Add a "Refresh" button to the header that reloads the graph from disk.
Add client-side polling (30s) that checks file freshness and shows a
non-intrusive banner when spec files change on disk.

## APPLICABLE_ASSERTIONS

- **REQ-p00006-A**: "The tool SHALL generate an interactive HTML view with clickable requirement navigation."
  - Refresh-from-disk is part of interactive viewer functionality.
- No existing assertion covers disk freshness detection specifically.

## Manual Test Plan

1. Open viewer, edit spec file externally
2. Verify stale banner appears within 30s
3. Click Refresh button, verify graph reloads
4. Verify mutation warning if unsaved mutations exist
