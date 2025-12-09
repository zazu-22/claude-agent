"""
Security Hooks for Claude Agent
===============================

Pre-tool-use hooks that validate bash commands for security.
Uses an allowlist approach - only explicitly permitted commands can run.

Also includes evaluation validation hooks for drift mitigation.
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


# =============================================================================
# Evaluation Validation Hook for Drift Mitigation
# =============================================================================


@dataclass
class ValidationResult:
    """
    Result from evaluation validation.

    Used to communicate validation outcomes and guide retry behavior.
    """

    is_valid: bool
    error_message: Optional[str] = None
    action: str = "proceed"  # "proceed" | "retry" | "abort"
    evaluation_data: Optional[dict] = field(default_factory=dict)

    def __post_init__(self):
        """Ensure evaluation_data is never None."""
        if self.evaluation_data is None:
            self.evaluation_data = {}


# Agent-specific required evaluation sections
# Each agent type has different mandatory sections that must be present
AGENT_REQUIRED_SECTIONS: dict[str, set[str]] = {
    "coding": {"context", "regression", "plan"},
    "initializer": {"spec_decomposition", "feature_mapping", "coverage_check"},
    "validator": {"spec_alignment", "test_execution", "aggregate_verdict"},
}

# Regex patterns for each evaluation section type
# These match structured headers in agent output (e.g., "### Step A - CONTEXT VERIFICATION")
# Patterns support various formatting: different heading levels, step prefixes, dash variants
EVALUATION_SECTION_PATTERNS: dict[str, re.Pattern] = {
    # Coding agent sections
    "context": re.compile(
        r"^\s*#{2,3}\s*(?:Step\s*[A-Z0-9]*\s*[-–—]?\s*)?CONTEXT\s+VERIFICATION",
        re.MULTILINE | re.IGNORECASE,
    ),
    "regression": re.compile(
        r"^\s*#{2,3}\s*(?:Step\s*[A-Z0-9]*\s*[-–—]?\s*)?REGRESSION\s+VERIFICATION",
        re.MULTILINE | re.IGNORECASE,
    ),
    "plan": re.compile(
        r"^\s*#{2,3}\s*(?:Step\s*[A-Z0-9]*\s*[-–—]?\s*)?IMPLEMENTATION\s+PLAN",
        re.MULTILINE | re.IGNORECASE,
    ),
    # Initializer agent sections
    "spec_decomposition": re.compile(
        r"^\s*#{2,3}\s*(?:Step\s*[0-9]*\s*[-–—]?\s*)?SPEC\s+DECOMPOSITION",
        re.MULTILINE | re.IGNORECASE,
    ),
    "feature_mapping": re.compile(
        r"^\s*#{2,3}\s*(?:Step\s*[0-9]*\s*[-–—]?\s*)?FEATURE\s+MAPPING",
        re.MULTILINE | re.IGNORECASE,
    ),
    "coverage_check": re.compile(
        r"^\s*#{2,3}\s*(?:Step\s*[0-9]*\s*[-–—]?\s*)?COVERAGE\s+CHECK",
        re.MULTILINE | re.IGNORECASE,
    ),
    # Validator agent sections
    "spec_alignment": re.compile(
        r"^\s*#{2,3}\s*(?:Step\s*[A-Z]*\s*[-–—]?\s*)?SPEC\s+ALIGNMENT\s+CHECK",
        re.MULTILINE | re.IGNORECASE,
    ),
    "test_execution": re.compile(
        r"^\s*#{2,3}\s*(?:Step\s*[A-Z]*\s*[-–—]?\s*)?TEST\s+EXECUTION\s+WITH\s+EVIDENCE",
        re.MULTILINE | re.IGNORECASE,
    ),
    "aggregate_verdict": re.compile(
        r"^\s*#{2,3}\s*(?:Step\s*[A-Z]*\s*[-–—]?\s*)?AGGREGATE\s+VERDICT",
        re.MULTILINE | re.IGNORECASE,
    ),
}

# Pattern to match fenced code blocks (``` ... ```)
# Used to strip code blocks before pattern matching to prevent false positives
CODE_BLOCK_PATTERN = re.compile(
    r"```[^\n]*\n.*?```",
    re.DOTALL,
)


def _strip_code_blocks(text: str) -> str:
    """
    Remove fenced code blocks from text to prevent false positive matches.

    Code examples in agent output might contain evaluation section headers
    as documentation/examples, which should not count as actual sections.

    Args:
        text: Input text potentially containing code blocks

    Returns:
        Text with all fenced code blocks removed
    """
    return CODE_BLOCK_PATTERN.sub("", text)


# Section content extraction patterns (captures content after header until next section or end)
# Use \Z for end-of-string in MULTILINE mode ($ matches end-of-line in that mode)
SECTION_CONTENT_PATTERNS: dict[str, re.Pattern] = {
    "context": re.compile(
        r"(?:^\s*#{2,3}\s*(?:Step\s*[A-Z0-9]*\s*[-–—]?\s*)?CONTEXT\s+VERIFICATION.*?\n)"
        r"(.*?)(?=^\s*#{2,3}\s|\Z)",
        re.DOTALL | re.MULTILINE | re.IGNORECASE,
    ),
    "regression": re.compile(
        r"(?:^\s*#{2,3}\s*(?:Step\s*[A-Z0-9]*\s*[-–—]?\s*)?REGRESSION\s+VERIFICATION.*?\n)"
        r"(.*?)(?=^\s*#{2,3}\s|\Z)",
        re.DOTALL | re.MULTILINE | re.IGNORECASE,
    ),
    "plan": re.compile(
        r"(?:^\s*#{2,3}\s*(?:Step\s*[A-Z0-9]*\s*[-–—]?\s*)?IMPLEMENTATION\s+PLAN.*?\n)"
        r"(.*?)(?=^\s*#{2,3}\s|\Z)",
        re.DOTALL | re.MULTILINE | re.IGNORECASE,
    ),
    "spec_decomposition": re.compile(
        r"(?:^\s*#{2,3}\s*(?:Step\s*[0-9]*\s*[-–—]?\s*)?SPEC\s+DECOMPOSITION.*?\n)"
        r"(.*?)(?=^\s*#{2,3}\s|\Z)",
        re.DOTALL | re.MULTILINE | re.IGNORECASE,
    ),
    "feature_mapping": re.compile(
        r"(?:^\s*#{2,3}\s*(?:Step\s*[0-9]*\s*[-–—]?\s*)?FEATURE\s+MAPPING.*?\n)"
        r"(.*?)(?=^\s*#{2,3}\s|\Z)",
        re.DOTALL | re.MULTILINE | re.IGNORECASE,
    ),
    "coverage_check": re.compile(
        r"(?:^\s*#{2,3}\s*(?:Step\s*[0-9]*\s*[-–—]?\s*)?COVERAGE\s+CHECK.*?\n)"
        r"(.*?)(?=^\s*#{2,3}\s|\Z)",
        re.DOTALL | re.MULTILINE | re.IGNORECASE,
    ),
    "spec_alignment": re.compile(
        r"(?:^\s*#{2,3}\s*(?:Step\s*[A-Z]*\s*[-–—]?\s*)?SPEC\s+ALIGNMENT\s+CHECK.*?\n)"
        r"(.*?)(?=^\s*#{2,3}\s|\Z)",
        re.DOTALL | re.MULTILINE | re.IGNORECASE,
    ),
    "test_execution": re.compile(
        r"(?:^\s*#{2,3}\s*(?:Step\s*[A-Z]*\s*[-–—]?\s*)?TEST\s+EXECUTION\s+WITH\s+EVIDENCE.*?\n)"
        r"(.*?)(?=^\s*#{2,3}\s|\Z)",
        re.DOTALL | re.MULTILINE | re.IGNORECASE,
    ),
    "aggregate_verdict": re.compile(
        r"(?:^\s*#{2,3}\s*(?:Step\s*[A-Z]*\s*[-–—]?\s*)?AGGREGATE\s+VERDICT.*?\n)"
        r"(.*?)(?=^\s*#{2,3}\s|\Z)",
        re.DOTALL | re.MULTILINE | re.IGNORECASE,
    ),
}


def extract_evaluation_sections(output: str, agent_type: str) -> dict[str, str]:
    """
    Extract evaluation section content from agent output.

    Parses markdown output to retrieve structured evaluation information
    for the specified agent type. Returns a dictionary mapping section
    names to their content.

    Note: Code blocks are stripped before pattern matching to prevent
    false positives from example headers in documentation/code.

    Args:
        output: Agent output text (markdown format)
        agent_type: Type of agent ("coding", "initializer", "validator")

    Returns:
        Dictionary mapping section names to extracted content.
        Empty dict if no sections found or invalid agent type.
    """
    if agent_type not in AGENT_REQUIRED_SECTIONS:
        return {}

    # Strip code blocks to prevent false positives from example headers
    cleaned_output = _strip_code_blocks(output)

    required_sections = AGENT_REQUIRED_SECTIONS[agent_type]
    extracted = {}

    for section_name in required_sections:
        pattern = SECTION_CONTENT_PATTERNS.get(section_name)
        if pattern:
            match = pattern.search(cleaned_output)
            if match:
                content = match.group(1).strip()
                if content:
                    extracted[section_name] = content

    return extracted


def _check_section_present(output: str, section_name: str) -> bool:
    """
    Check if a specific evaluation section header is present in output.

    Note: Code blocks are stripped before pattern matching to prevent
    false positives from example headers in documentation/code.

    Args:
        output: Agent output text
        section_name: Section identifier (e.g., "context", "regression")

    Returns:
        True if section header pattern is found
    """
    # Strip code blocks to prevent false positives from example headers
    cleaned_output = _strip_code_blocks(output)

    pattern = EVALUATION_SECTION_PATTERNS.get(section_name)
    if pattern:
        return pattern.search(cleaned_output) is not None
    return False


def evaluation_validation_hook(
    output: str,
    agent_type: str,
    strict_mode: bool = False,
) -> ValidationResult:
    """
    Validate that agent output includes mandatory evaluation sections.

    This hook enforces compliance with the drift-mitigation design framework
    by checking for required evaluation sections in agent output. When sections
    are missing, it can trigger retry operations with emphasis on the missing
    content.

    Lenient Mode Rollout Plan:
    --------------------------
    The default `strict_mode=False` is intentional for gradual rollout:

    1. **Phase 1 (Current)**: Lenient mode - log and display missing sections
       but allow sessions to proceed. This establishes baseline metrics.

    2. **Phase 2**: Monitor validation failure rates via drift-metrics.json.
       When failure rate stabilizes below 30%, consider enabling strict mode.

    3. **Phase 3**: Enable strict mode (strict_mode=True) which triggers
       retry action when sections are missing, forcing agents to complete
       evaluation sequences before proceeding.

    Metrics to track (in drift-metrics.json):
    - validation_failure_rate: % of sessions missing required sections
    - sections_most_often_missing: Which sections are commonly skipped
    - completeness_score_distribution: Track improvement over time

    Args:
        output: Agent output text to validate
        agent_type: Type of agent ("coding", "initializer", "validator")
        strict_mode: If True, missing sections trigger "retry" action.
                    If False, missing sections are logged but allow "proceed".

    Returns:
        ValidationResult with:
        - is_valid: True if all required sections present
        - error_message: Description of missing sections (if any)
        - action: "proceed" (valid), "retry" (missing sections), or "abort" (invalid agent type)
        - evaluation_data: Dict with keys:
            - "sections_found": List of present section names
            - "sections_missing": List of missing section names
            - "section_content": Dict mapping section names to extracted content
            - "completeness_score": Float 0.0-1.0 indicating coverage
    """
    # Validate agent type
    if agent_type not in AGENT_REQUIRED_SECTIONS:
        return ValidationResult(
            is_valid=False,
            error_message=f"Invalid agent type: {agent_type}. "
            f"Must be one of: {list(AGENT_REQUIRED_SECTIONS.keys())}",
            action="abort",
            evaluation_data={
                "sections_found": [],
                "sections_missing": [],
                "section_content": {},
                "completeness_score": 0.0,
            },
        )

    required_sections = AGENT_REQUIRED_SECTIONS[agent_type]
    sections_found = []
    sections_missing = []

    # Check which sections are present
    for section_name in required_sections:
        if _check_section_present(output, section_name):
            sections_found.append(section_name)
        else:
            sections_missing.append(section_name)

    # Extract content from found sections
    section_content = extract_evaluation_sections(output, agent_type)

    # Calculate completeness score
    completeness_score = len(sections_found) / len(required_sections) if required_sections else 1.0

    # Build evaluation data
    evaluation_data = {
        "sections_found": sections_found,
        "sections_missing": sections_missing,
        "section_content": section_content,
        "completeness_score": completeness_score,
    }

    # Determine validation result
    if not sections_missing:
        # All sections present - valid
        return ValidationResult(
            is_valid=True,
            error_message=None,
            action="proceed",
            evaluation_data=evaluation_data,
        )

    # Some sections missing
    missing_str = ", ".join(sorted(sections_missing))
    error_message = (
        f"Missing required evaluation sections for {agent_type} agent: {missing_str}. "
        f"Found {len(sections_found)}/{len(required_sections)} sections "
        f"(completeness: {completeness_score:.0%})."
    )

    if strict_mode:
        # In strict mode, trigger retry for missing sections
        retry_emphasis = _build_retry_emphasis(sections_missing, agent_type)
        return ValidationResult(
            is_valid=False,
            error_message=error_message + "\n\n" + retry_emphasis,
            action="retry",
            evaluation_data=evaluation_data,
        )
    else:
        # In lenient mode, warn but allow proceeding
        return ValidationResult(
            is_valid=False,
            error_message=error_message,
            action="proceed",
            evaluation_data=evaluation_data,
        )


def _build_retry_emphasis(missing_sections: list[str], agent_type: str) -> str:
    """
    Build retry emphasis message for missing evaluation sections.

    Generates specific guidance based on which sections are missing,
    helping the agent understand what content is required.

    Args:
        missing_sections: List of missing section names
        agent_type: Type of agent

    Returns:
        Formatted string with retry guidance
    """
    emphasis_lines = ["RETRY REQUIRED - Please output the following missing sections:"]

    section_guidance = {
        # Coding agent sections
        "context": (
            "### Step A - CONTEXT VERIFICATION\n"
            "Include: feature_list.json quote, progress notes quote, architectural constraints"
        ),
        "regression": (
            "### Step B - REGRESSION VERIFICATION\n"
            "Include: Test results for previously passing features with PASS/FAIL verdicts"
        ),
        "plan": (
            "### Step C - IMPLEMENTATION PLAN\n"
            "Include: What you will build, files to modify, constraints to honor"
        ),
        # Initializer agent sections
        "spec_decomposition": (
            "### Step 1 - SPEC DECOMPOSITION\n"
            "Include: Section headers quoted, key requirements listed, ambiguities noted"
        ),
        "feature_mapping": (
            "### Step 2 - FEATURE MAPPING\n"
            "Include: Each feature with spec text traceability quote"
        ),
        "coverage_check": (
            "### Step 3 - COVERAGE CHECK\n"
            "Include: Requirements covered count, any uncovered requirements listed"
        ),
        # Validator agent sections
        "spec_alignment": (
            "### Step A - SPEC ALIGNMENT CHECK\n"
            "Include: Feature description, spec requirement quote, 'working' criteria"
        ),
        "test_execution": (
            "### Step B - TEST EXECUTION WITH EVIDENCE\n"
            "Include: Steps performed, expected/actual results, screenshot reference, PASS/FAIL"
        ),
        "aggregate_verdict": (
            "### Step C - AGGREGATE VERDICT WITH REASONING\n"
            "Include: Features tested count, pass/fail counts, verdict reasoning"
        ),
    }

    for section in missing_sections:
        guidance = section_guidance.get(section, f"Output section: {section}")
        emphasis_lines.append(f"\n{guidance}")

    return "\n".join(emphasis_lines)
