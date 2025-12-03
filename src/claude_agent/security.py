"""
Security Hooks for Claude Agent
===============================

Pre-tool-use hooks that validate bash commands for security.
Uses an allowlist approach - only explicitly permitted commands can run.
"""

import os
import re
import shlex
from dataclasses import dataclass, field
from typing import Optional

from claude_agent.detection import (
    get_stack_commands,
    get_stack_pkill_targets,
)


@dataclass
class SecurityConfig:
    """Security configuration for a specific tech stack."""

    stack: str
    commands: set[str] = field(default_factory=set)
    pkill_targets: set[str] = field(default_factory=set)
    allowed_scripts: set[str] = field(default_factory=lambda: {"init.sh", "setup.sh"})

    def __post_init__(self):
        """Initialize from stack if commands not provided."""
        if not self.commands:
            self.commands = get_stack_commands(self.stack)
        if not self.pkill_targets:
            self.pkill_targets = get_stack_pkill_targets(self.stack)

    def extend(self, extra_commands: Optional[list[str]] = None) -> None:
        """Extend allowlist with additional commands."""
        if extra_commands:
            self.commands.update(extra_commands)


# Module-level configuration - set by CLI before running agent
_security_config: Optional[SecurityConfig] = None

# Module-level logger - set by agent.py before running sessions
# This is an AgentLogger instance (or None if logging is disabled)
_security_logger: Optional[any] = None


def set_security_logger(logger) -> None:
    """
    Set the logger for security decision logging.

    Args:
        logger: AgentLogger instance or None to disable logging
    """
    global _security_logger
    _security_logger = logger


def get_security_logger():
    """Get the current security logger (may be None)."""
    global _security_logger
    return _security_logger


def configure_security(
    stack: str,
    extra_commands: Optional[list[str]] = None,
) -> SecurityConfig:
    """
    Configure security for a specific stack.

    Args:
        stack: Tech stack name ("node", "python", etc.)
        extra_commands: Additional commands to allow

    Returns:
        The configured SecurityConfig
    """
    global _security_config
    _security_config = SecurityConfig(stack=stack)
    if extra_commands:
        _security_config.extend(extra_commands)
    return _security_config


def get_security_config() -> SecurityConfig:
    """Get current security config, defaulting to node if not configured."""
    global _security_config
    if _security_config is None:
        _security_config = SecurityConfig(stack="node")
    return _security_config


def split_command_segments(command_string: str) -> list[str]:
    """
    Split a compound command into individual command segments.

    Handles command chaining (&&, ||, ;) but not pipes (those are single commands).
    """
    # Split on && and || while preserving the ability to handle each segment
    segments = re.split(r"\s*(?:&&|\|\|)\s*", command_string)

    # Further split on semicolons
    result = []
    for segment in segments:
        sub_segments = re.split(r'(?<!["\'])\s*;\s*(?!["\'])', segment)
        for sub in sub_segments:
            sub = sub.strip()
            if sub:
                result.append(sub)

    return result


def extract_commands(command_string: str) -> list[str]:
    """
    Extract command names from a shell command string.

    Handles pipes, command chaining (&&, ||, ;), and subshells.
    Returns the base command names (without paths).
    """
    commands = []

    # Split on semicolons that aren't inside quotes
    segments = re.split(r'(?<!["\'])\s*;\s*(?!["\'])', command_string)

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        try:
            tokens = shlex.split(segment)
        except ValueError:
            # Malformed command - fail safe by blocking
            return []

        if not tokens:
            continue

        # Track when we expect a command vs arguments
        expect_command = True

        for token in tokens:
            # Shell operators indicate a new command follows
            if token in ("|", "||", "&&", "&"):
                expect_command = True
                continue

            # Skip shell keywords
            if token in (
                "if",
                "then",
                "else",
                "elif",
                "fi",
                "for",
                "while",
                "until",
                "do",
                "done",
                "case",
                "esac",
                "in",
                "!",
                "{",
                "}",
            ):
                continue

            # Skip flags/options
            if token.startswith("-"):
                continue

            # Skip variable assignments (VAR=value)
            if "=" in token and not token.startswith("="):
                continue

            if expect_command:
                cmd = os.path.basename(token)
                commands.append(cmd)
                expect_command = False

    return commands


def validate_pkill_command(command_string: str) -> tuple[bool, str]:
    """Validate pkill commands - only allow killing dev-related processes."""
    config = get_security_config()

    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse pkill command"

    if not tokens:
        return False, "Empty pkill command"

    # Separate flags from arguments
    args = []
    for token in tokens[1:]:
        if not token.startswith("-"):
            args.append(token)

    if not args:
        return False, "pkill requires a process name"

    # The target is typically the last non-flag argument
    target = args[-1]

    # For -f flag, extract the first word as process name
    if " " in target:
        target = target.split()[0]

    if target in config.pkill_targets:
        return True, ""
    return False, f"pkill only allowed for dev processes: {config.pkill_targets}"


def validate_chmod_command(command_string: str) -> tuple[bool, str]:
    """Validate chmod commands - only allow making files executable with +x."""
    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse chmod command"

    if not tokens or tokens[0] != "chmod":
        return False, "Not a chmod command"

    mode = None
    files = []

    for token in tokens[1:]:
        if token.startswith("-"):
            return False, "chmod flags are not allowed"
        elif mode is None:
            mode = token
        else:
            files.append(token)

    if mode is None:
        return False, "chmod requires a mode"

    if not files:
        return False, "chmod requires at least one file"

    # Only allow +x variants
    if not re.match(r"^[ugoa]*\+x$", mode):
        return False, f"chmod only allowed with +x mode, got: {mode}"

    return True, ""


def validate_init_script(command_string: str) -> tuple[bool, str]:
    """Validate init script execution."""
    config = get_security_config()

    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse init script command"

    if not tokens:
        return False, "Empty command"

    script = tokens[0]

    # Check against allowed scripts
    for allowed in config.allowed_scripts:
        if script == f"./{allowed}" or script.endswith(f"/{allowed}"):
            return True, ""

    return False, f"Script not in allowed list: {script}"


def get_command_for_validation(cmd: str, segments: list[str]) -> str:
    """Find the specific command segment that contains the given command."""
    for segment in segments:
        segment_commands = extract_commands(segment)
        if cmd in segment_commands:
            return segment
    return ""


# Commands that need additional validation
COMMANDS_NEEDING_EXTRA_VALIDATION = {"pkill", "chmod", "init.sh", "setup.sh"}


async def validator_stop_hook(input_data, tool_use_id=None, context=None):
    """
    Stop hook for validator agent that enforces JSON verdict output.

    On first stop attempt, blocks and reminds Claude to output verdict.
    On second attempt (stop_hook_active=True), allows stop to prevent infinite loops.
    """
    # Check if we've already blocked once - allow stop to prevent infinite loop
    if input_data.get("stop_hook_active", False):
        return {}

    # First stop attempt - block and require verdict
    return {
        "decision": "block",
        "reason": (
            "STOP! You have not output your JSON verdict yet. "
            "Before ending your session, you MUST output a JSON code block with your verdict:\n\n"
            "```json\n"
            "{\n"
            '  "verdict": "APPROVED",\n'
            '  "rejected_tests": [],\n'
            '  "tests_verified": <number>,\n'
            '  "summary": "<what you tested>"\n'
            "}\n"
            "```\n\n"
            "Output this JSON block NOW, then you may stop."
        ),
    }


async def bash_security_hook(input_data, tool_use_id=None, context=None):
    """
    Pre-tool-use hook that validates bash commands using an allowlist.

    Only commands in the configured allowlist are permitted.
    Logs all security decisions when a logger is configured.
    """
    if input_data.get("tool_name") != "Bash":
        return {}

    command = input_data.get("tool_input", {}).get("command", "")
    if not command:
        return {}

    config = get_security_config()
    logger = get_security_logger()
    commands = extract_commands(command)

    if not commands:
        reason = f"Could not parse command for security validation: {command}"
        # Log security block
        if logger:
            logger.log_security_block(command, reason, config.stack)
        return {
            "decision": "block",
            "reason": reason,
        }

    segments = split_command_segments(command)

    for cmd in commands:
        if cmd not in config.commands:
            reason = f"Command '{cmd}' is not in the allowed commands list for {config.stack} stack"
            # Log security block
            if logger:
                logger.log_security_block(command, reason, config.stack)
            return {
                "decision": "block",
                "reason": reason,
            }

        # Additional validation for sensitive commands
        if cmd in COMMANDS_NEEDING_EXTRA_VALIDATION:
            cmd_segment = get_command_for_validation(cmd, segments)
            if not cmd_segment:
                cmd_segment = command

            if cmd == "pkill":
                allowed, reason = validate_pkill_command(cmd_segment)
                if not allowed:
                    # Log security block
                    if logger:
                        logger.log_security_block(command, reason, config.stack)
                    return {"decision": "block", "reason": reason}
            elif cmd == "chmod":
                allowed, reason = validate_chmod_command(cmd_segment)
                if not allowed:
                    # Log security block
                    if logger:
                        logger.log_security_block(command, reason, config.stack)
                    return {"decision": "block", "reason": reason}
            elif cmd in ("init.sh", "setup.sh"):
                allowed, reason = validate_init_script(cmd_segment)
                if not allowed:
                    # Log security block
                    if logger:
                        logger.log_security_block(command, reason, config.stack)
                    return {"decision": "block", "reason": reason}

    # Log security allow (only in verbose mode - handled by logger)
    if logger:
        logger.log_security_allow(command, config.stack)

    return {}
