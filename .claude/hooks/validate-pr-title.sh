#!/bin/bash
# Pre-tool hook: validate PR titles contain [CUR-XXX] ticket reference
# Mirrors the CI check in .github/workflows/pr-validation.yml

INPUT=$(cat /dev/stdin)

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only check gh pr create commands
if ! echo "$COMMAND" | grep -qE 'gh\s+pr\s+create'; then
  exit 0
fi

# Extract --title value (handles both --title "value" and --title 'value')
TITLE=$(echo "$COMMAND" | grep -oP -- '--title\s+["'"'"']\K[^"'"'"']+')

if [ -z "$TITLE" ]; then
  exit 0
fi

if echo "$TITLE" | grep -qE '\[CUR-[0-9]+\]'; then
  exit 0
fi

jq -n --arg title "$TITLE" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: ("PR title must include [CUR-XXX] ticket reference.\nGot: " + $title + "\nExpected: [CUR-XXX] description")
  }
}'
