#!/usr/bin/env bash
# Claude Code hook to block invalid 'stm status' command
# PreToolUse hook - receives JSON on stdin, exits 2 to block

set -euo pipefail

# Read JSON input
INPUT=$(cat)

# Extract tool name and command
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only check Bash commands
if [[ "$TOOL_NAME" != "Bash" ]]; then
    exit 0
fi

# Check for 'stm status' pattern (with various spacing/quoting)
if echo "$COMMAND" | grep -qE '(^|[;&|])[ ]*stm[ ]+status'; then
    cat >&2 << 'EOF'
BLOCKED: 'stm status' is not a valid command.

STM does NOT have a 'status' subcommand. Valid STM commands are:
  - stm init    - Initialize STM in current directory
  - stm list    - List all tasks (use this to check if STM is initialized)
  - stm add     - Add a new task
  - stm show    - Show task details
  - stm update  - Update a task
  - stm delete  - Delete a task

To check if STM is initialized, run: stm list
EOF
    exit 2
fi

# Command is valid, allow it
exit 0
