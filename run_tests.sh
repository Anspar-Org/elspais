#!/usr/bin/env bash
# Run the full test suite and write a concise summary to stdout.
# Designed to produce LLM-friendly output regardless of test count.
set -euo pipefail

OUTFILE=$(mktemp)
trap 'rm -f "$OUTFILE"' EXIT

python -m pytest "$@" --tb=short -q --no-header 2>&1 > "$OUTFILE" || true

# Print only the summary lines (last 5 lines capture pass/fail/skip counts)
echo "=== Test Results ==="
tail -5 "$OUTFILE"
