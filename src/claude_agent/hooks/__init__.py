"""
Claude Code Hooks Module
========================

Hook generation and management for Claude Code session detection.

This module provides:
- Hook configuration generator for hooks.json
- Session start/stop script templates (POSIX sh-compatible)
- Hook installation and management utilities

Architecture Decisions
----------------------
Per DR-009: Hooks require explicit installation via 'hooks install' command.
Hooks modify the project's .claude/ directory which may be git-tracked.

Per DR-010: Scripts are POSIX sh-compatible for cross-platform support.
Shebang is #!/bin/sh with no bash-specific syntax.

Per DR-011: Output format matches Claude Code hooks specification:
- session-start.sh outputs {"additionalContext": "..."} or {}
- session-stop.sh always outputs {}
- Both scripts must always exit 0
- Both scripts must complete within 5000ms timeout

Usage
-----
    from claude_agent.hooks import (
        generate_hooks_config,
        generate_session_start_script,
        generate_session_stop_script,
        install_hooks,
        uninstall_hooks,
        get_hooks_status,
    )

    # Generate hooks.json configuration
    config = generate_hooks_config()

    # Install hooks to a project
    install_hooks("/path/to/project")

    # Check hook status
    status = get_hooks_status("/path/to/project")
"""

import json
import logging
import os
import stat
import subprocess
from pathlib import Path
from typing import Optional

from claude_agent.state import get_state_dir, get_workflow_dir


# Module logger
logger = logging.getLogger(__name__)


# =============================================================================
# Hook Execution with Error Handling
# =============================================================================


class HookExecutionError(Exception):
    """Exception raised when hook execution fails."""

    def __init__(self, hook_name: str, message: str, original_error: Optional[Exception] = None):
        self.hook_name = hook_name
        self.message = message
        self.original_error = original_error
        super().__init__(f"Hook '{hook_name}' failed: {message}")


def execute_hook_safely(
    script_path: str | Path,
    timeout_ms: int = 5000,
    cwd: Optional[str | Path] = None,
) -> tuple[bool, str, Optional[str]]:
    """Execute a hook script safely with error handling.

    This function catches all exceptions and ensures the agent can continue
    even if the hook fails. Per DR-011, hook failures should not block
    agent operation.

    Args:
        script_path: Path to the hook script to execute
        timeout_ms: Timeout in milliseconds (default: 5000)
        cwd: Working directory for script execution (default: current directory)

    Returns:
        Tuple of:
        - success: bool - Whether the hook executed successfully
        - output: str - Hook stdout output (or empty JSON "{}" on failure)
        - error: Optional[str] - Error message if failed, None if successful

    Example:
        >>> success, output, error = execute_hook_safely("/path/to/hook.sh")
        >>> if success:
        ...     print(f"Hook output: {output}")
        ... else:
        ...     print(f"Hook failed: {error}")
    """
    script_path = Path(script_path)
    hook_name = script_path.name

    # Validate script exists and is executable
    if not script_path.exists():
        error_msg = f"Hook script not found: {script_path}"
        logger.warning(f"Hook execution failed for '{hook_name}': {error_msg}")
        return False, "{}", error_msg

    if not os.access(script_path, os.X_OK):
        error_msg = f"Hook script is not executable: {script_path}"
        logger.warning(f"Hook execution failed for '{hook_name}': {error_msg}")
        return False, "{}", error_msg

    # Convert timeout from milliseconds to seconds
    timeout_seconds = timeout_ms / 1000.0

    try:
        # Execute the hook script
        result = subprocess.run(
            [str(script_path)],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(cwd) if cwd else None,
            shell=False,  # More secure - don't use shell
        )

        # Get stdout output
        output = result.stdout.strip() if result.stdout else "{}"

        # Validate output is valid JSON
        try:
            json.loads(output)
        except json.JSONDecodeError:
            logger.warning(
                f"Hook '{hook_name}' produced invalid JSON output: {output[:100]}..."
            )
            output = "{}"  # Return empty JSON on invalid output

        # Log if hook exited with non-zero status (unusual since hooks should exit 0)
        if result.returncode != 0:
            logger.warning(
                f"Hook '{hook_name}' exited with code {result.returncode}. "
                f"stderr: {result.stderr[:200] if result.stderr else 'none'}"
            )
            # Still return the output - hook may have output valid JSON before error
            return True, output, None

        logger.debug(f"Hook '{hook_name}' executed successfully")
        return True, output, None

    except subprocess.TimeoutExpired as e:
        error_msg = f"Hook timed out after {timeout_ms}ms"
        logger.warning(f"Hook execution failed for '{hook_name}': {error_msg}")
        return False, "{}", error_msg

    except subprocess.SubprocessError as e:
        error_msg = f"Subprocess error: {str(e)}"
        logger.warning(f"Hook execution failed for '{hook_name}': {error_msg}")
        return False, "{}", error_msg

    except PermissionError as e:
        error_msg = f"Permission denied: {str(e)}"
        logger.warning(f"Hook execution failed for '{hook_name}': {error_msg}")
        return False, "{}", error_msg

    except OSError as e:
        error_msg = f"OS error: {str(e)}"
        logger.warning(f"Hook execution failed for '{hook_name}': {error_msg}")
        return False, "{}", error_msg

    except Exception as e:
        # Catch-all for any unexpected errors - never crash the agent
        error_msg = f"Unexpected error: {type(e).__name__}: {str(e)}"
        logger.error(f"Hook execution failed for '{hook_name}': {error_msg}")
        return False, "{}", error_msg


def execute_session_start_hook(
    project_dir: Optional[str | Path] = None,
    timeout_ms: int = 5000,
) -> dict:
    """Execute the session-start hook and return its context.

    This is a convenience function that executes the session-start.sh hook
    and parses its output. On any failure, returns an empty dict rather
    than raising an exception.

    Args:
        project_dir: Project directory (defaults to current directory)
        timeout_ms: Timeout in milliseconds (default: 5000)

    Returns:
        Dictionary with additionalContext if hook succeeded, empty dict otherwise.

    Example:
        >>> context = execute_session_start_hook("/path/to/project")
        >>> if "additionalContext" in context:
        ...     print(context["additionalContext"])
    """
    if project_dir is None:
        project_dir = os.getcwd()
    project_path = Path(project_dir).resolve()

    script_path = project_path / ".claude" / "hooks" / "session-start.sh"

    success, output, error = execute_hook_safely(
        script_path, timeout_ms=timeout_ms, cwd=project_path
    )

    if not success:
        logger.debug(f"Session start hook returned empty context: {error}")
        return {}

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        logger.warning(f"Could not parse session-start hook output: {output[:100]}...")
        return {}


def execute_session_stop_hook(
    project_dir: Optional[str | Path] = None,
    timeout_ms: int = 5000,
) -> bool:
    """Execute the session-stop hook.

    This is a convenience function that executes the session-stop.sh hook.
    The hook output is always {} so this just returns success status.

    Args:
        project_dir: Project directory (defaults to current directory)
        timeout_ms: Timeout in milliseconds (default: 5000)

    Returns:
        True if hook executed successfully, False otherwise.
    """
    if project_dir is None:
        project_dir = os.getcwd()
    project_path = Path(project_dir).resolve()

    script_path = project_path / ".claude" / "hooks" / "session-stop.sh"

    success, _, error = execute_hook_safely(
        script_path, timeout_ms=timeout_ms, cwd=project_path
    )

    if not success:
        logger.debug(f"Session stop hook failed: {error}")

    return success


# =============================================================================
# Hook Configuration Generator
# =============================================================================


def generate_hooks_config(timeout_ms: int = 5000) -> dict:
    """Generate hooks.json configuration matching Claude Code specification.

    Creates configuration for SessionStart and Stop events with the
    specified timeout.

    Args:
        timeout_ms: Timeout in milliseconds for each hook (default: 5000)

    Returns:
        Dictionary matching Claude Code hooks.json schema:
        {
            "hooks": [
                {"event": "SessionStart", "script": "...", "timeout": 5000},
                {"event": "Stop", "script": "...", "timeout": 5000}
            ]
        }
    """
    return {
        "hooks": [
            {
                "event": "SessionStart",
                "script": ".claude/hooks/session-start.sh",
                "timeout": timeout_ms,
            },
            {
                "event": "Stop",
                "script": ".claude/hooks/session-stop.sh",
                "timeout": timeout_ms,
            },
        ]
    }


# =============================================================================
# Session Start Script Generator
# =============================================================================


def generate_session_start_script() -> str:
    """Generate POSIX sh-compatible session-start.sh script.

    The script:
    1. Checks XDG state directory for workflow-state.json
    2. If active workflow found (phase != "complete"), outputs context
    3. Context includes: project path, phase, progress, last error
    4. Returns empty {} if no active workflow

    Returns:
        POSIX sh-compatible script content with #!/bin/sh shebang
    """
    # Get XDG state directory for use in the script
    state_dir = get_state_dir()

    return f'''#!/bin/sh
# Claude Code Session Start Hook
# Generated by claude-agent
#
# Detects active claude-agent workflows and injects context.
# POSIX sh-compatible for cross-platform support.
# Must always exit 0 and output valid JSON.

set -e

# XDG state directory (matches claude-agent configuration)
STATE_DIR="${{XDG_STATE_HOME:-$HOME/.local/state}}/claude-agent"

# Get current project directory
PROJECT_DIR="$(pwd)"

# Compute project hash (12-char SHA256 of absolute path)
# Use Python as a portable way to compute SHA256
PROJECT_HASH=$(printf '%s' "$PROJECT_DIR" | python3 -c "import sys, hashlib; print(hashlib.sha256(sys.stdin.read().encode()).hexdigest()[:12])")

# Check if workflow state exists
WORKFLOW_FILE="$STATE_DIR/workflows/$PROJECT_HASH/workflow-state.json"

if [ ! -f "$WORKFLOW_FILE" ]; then
    # No workflow state - output empty JSON
    printf '{{}}'
    exit 0
fi

# Read workflow state using Python for reliable JSON parsing
# This is more portable than jq which may not be installed
CONTEXT=$(python3 << 'PYTHON_SCRIPT'
import json
import sys
import os

workflow_file = os.environ.get('WORKFLOW_FILE', '')
if not workflow_file or not os.path.exists(workflow_file):
    print('{{}}')
    sys.exit(0)

try:
    with open(workflow_file, 'r') as f:
        state = json.load(f)

    phase = state.get('phase', '')

    # If workflow is complete, no context needed
    if phase == 'complete':
        print('{{}}')
        sys.exit(0)

    # Build context markdown table
    project_dir = state.get('project_dir', 'Unknown')
    features_completed = state.get('features_completed', 0)
    features_total = state.get('features_total', 0)
    last_error = state.get('last_error')

    lines = [
        "## Active Claude-Agent Workflow",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Project | `{{project_dir}}` |",
        f"| Phase | **{{phase}}** |",
        f"| Progress | {{features_completed}}/{{features_total}} features |",
    ]

    if last_error:
        error_type = last_error.get('type', 'unknown')
        error_msg = last_error.get('message', 'No details')[:50]
        lines.append(f"| Last Error | {{error_type}}: {{error_msg}} |")

    context_text = "\\n".join(lines)

    # Output JSON with additionalContext
    output = {{"additionalContext": context_text}}
    print(json.dumps(output))

except Exception as e:
    # On any error, output empty JSON (don't fail the hook)
    print('{{}}')
    sys.exit(0)
PYTHON_SCRIPT
)

# Output the context (or empty JSON on failure)
printf '%s' "$CONTEXT"
exit 0
'''


# =============================================================================
# Session Stop Script Generator
# =============================================================================


def generate_session_stop_script() -> str:
    """Generate POSIX sh-compatible session-stop.sh script.

    The script:
    1. Checks for active workflow
    2. If incomplete, appends warning to hooks.log
    3. Always outputs empty {} JSON
    4. Always exits 0

    Returns:
        POSIX sh-compatible script content with #!/bin/sh shebang
    """
    return '''#!/bin/sh
# Claude Code Session Stop Hook
# Generated by claude-agent
#
# Logs incomplete workflow warnings.
# POSIX sh-compatible for cross-platform support.
# Must always exit 0 and output empty JSON {}.

set -e

# XDG state directory (matches claude-agent configuration)
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/claude-agent"
LOGS_DIR="$STATE_DIR/logs"

# Get current project directory
PROJECT_DIR="$(pwd)"

# Compute project hash (12-char SHA256 of absolute path)
PROJECT_HASH=$(printf '%s' "$PROJECT_DIR" | python3 -c "import sys, hashlib; print(hashlib.sha256(sys.stdin.read().encode()).hexdigest()[:12])" 2>/dev/null || echo "unknown")

# Check if workflow state exists
WORKFLOW_FILE="$STATE_DIR/workflows/$PROJECT_HASH/workflow-state.json"

if [ -f "$WORKFLOW_FILE" ]; then
    # Read phase using Python for reliable JSON parsing
    PHASE=$(python3 -c "
import json
import sys
try:
    with open('$WORKFLOW_FILE', 'r') as f:
        state = json.load(f)
    print(state.get('phase', ''))
except:
    print('')
" 2>/dev/null || echo "")

    # If workflow is incomplete, log warning
    if [ -n "$PHASE" ] && [ "$PHASE" != "complete" ]; then
        # Ensure logs directory exists
        mkdir -p "$LOGS_DIR" 2>/dev/null || true

        # Log with ISO timestamp
        TIMESTAMP=$(python3 -c "from datetime import datetime; print(datetime.now().isoformat())" 2>/dev/null || date -u +"%Y-%m-%dT%H:%M:%SZ")

        # Append to hooks log
        printf '[%s] [WARN] [HOOK] Session ended in phase: %s (project: %s)\\n' "$TIMESTAMP" "$PHASE" "$PROJECT_DIR" >> "$LOGS_DIR/hooks.log" 2>/dev/null || true
    fi
fi

# Always output empty JSON
printf '{}'
exit 0
'''


# =============================================================================
# Hook Installation Functions
# =============================================================================


def install_hooks(project_dir: Optional[str] = None) -> tuple[bool, str]:
    """Install Claude Code hooks to a project directory.

    Creates .claude/hooks/ directory with:
    - hooks.json: Hook configuration
    - session-start.sh: Session start detection script
    - session-stop.sh: Session stop logging script

    Per DR-009: Hooks are NOT installed automatically. This function
    must be called explicitly via 'claude-agent hooks install'.

    Args:
        project_dir: Project directory path (defaults to current directory)

    Returns:
        Tuple of (success: bool, message: str)
    """
    # Resolve project directory
    if project_dir is None:
        project_dir = os.getcwd()
    project_path = Path(project_dir).resolve()

    if not project_path.is_dir():
        return False, f"Directory not found: {project_path}"

    # Create hooks directory
    hooks_dir = project_path / ".claude" / "hooks"
    try:
        hooks_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return False, f"Failed to create hooks directory: {e}"

    # Write hooks.json
    hooks_json_path = hooks_dir / "hooks.json"
    try:
        config = generate_hooks_config()
        with open(hooks_json_path, "w") as f:
            json.dump(config, f, indent=2)
    except OSError as e:
        return False, f"Failed to write hooks.json: {e}"

    # Write session-start.sh
    start_script_path = hooks_dir / "session-start.sh"
    try:
        start_script = generate_session_start_script()
        with open(start_script_path, "w") as f:
            f.write(start_script)
        # Set executable permission (0o755)
        os.chmod(start_script_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
    except OSError as e:
        return False, f"Failed to write session-start.sh: {e}"

    # Write session-stop.sh
    stop_script_path = hooks_dir / "session-stop.sh"
    try:
        stop_script = generate_session_stop_script()
        with open(stop_script_path, "w") as f:
            f.write(stop_script)
        # Set executable permission (0o755)
        os.chmod(stop_script_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
    except OSError as e:
        return False, f"Failed to write session-stop.sh: {e}"

    return True, f"Hooks installed to {hooks_dir}"


def uninstall_hooks(project_dir: Optional[str] = None) -> tuple[bool, str]:
    """Remove Claude Code hooks from a project directory.

    Removes the entire .claude/hooks/ directory.

    Args:
        project_dir: Project directory path (defaults to current directory)

    Returns:
        Tuple of (success: bool, message: str)
    """
    # Resolve project directory
    if project_dir is None:
        project_dir = os.getcwd()
    project_path = Path(project_dir).resolve()

    if not project_path.is_dir():
        return False, f"Directory not found: {project_path}"

    # Check for hooks directory
    hooks_dir = project_path / ".claude" / "hooks"

    if not hooks_dir.exists():
        return True, "Hooks not installed (nothing to remove)"

    # Remove hooks directory and contents
    try:
        import shutil
        shutil.rmtree(hooks_dir)
    except OSError as e:
        return False, f"Failed to remove hooks directory: {e}"

    return True, f"Hooks uninstalled from {project_path}"


def get_hooks_status(project_dir: Optional[str] = None) -> dict:
    """Get status of installed Claude Code hooks.

    Args:
        project_dir: Project directory path (defaults to current directory)

    Returns:
        Dictionary with:
        - installed: bool - Whether hooks are installed
        - hooks_dir: str - Path to hooks directory
        - files: list[str] - List of installed hook files
        - errors: list[str] - Any issues found
    """
    # Resolve project directory
    if project_dir is None:
        project_dir = os.getcwd()
    project_path = Path(project_dir).resolve()

    status = {
        "installed": False,
        "hooks_dir": str(project_path / ".claude" / "hooks"),
        "files": [],
        "errors": [],
    }

    if not project_path.is_dir():
        status["errors"].append(f"Directory not found: {project_path}")
        return status

    hooks_dir = project_path / ".claude" / "hooks"

    if not hooks_dir.exists():
        return status

    status["installed"] = True

    # Check for expected files
    expected_files = ["hooks.json", "session-start.sh", "session-stop.sh"]
    for filename in expected_files:
        filepath = hooks_dir / filename
        if filepath.exists():
            status["files"].append(str(filepath))
            # Check executable permission for scripts
            if filename.endswith(".sh"):
                if not os.access(filepath, os.X_OK):
                    status["errors"].append(f"{filename} is not executable")
        else:
            status["errors"].append(f"Missing: {filename}")

    return status


# Module exports
__all__ = [
    # Hook execution with error handling
    "HookExecutionError",
    "execute_hook_safely",
    "execute_session_start_hook",
    "execute_session_stop_hook",
    # Hook configuration and scripts
    "generate_hooks_config",
    "generate_session_start_script",
    "generate_session_stop_script",
    # Hook installation and management
    "install_hooks",
    "uninstall_hooks",
    "get_hooks_status",
]
