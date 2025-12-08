"""
Claude Agent Errors Module
==========================

Provides consistent, actionable error formatting for CLI output.

Error Format Pattern
--------------------
All errors follow a consistent 4-section format (with optional sections):

    Error: [what went wrong]

    Context: [why it matters / additional context]

    Example: [correct usage example]

    Help: [link to docs or help command]

Only non-empty sections are displayed. This keeps simple errors concise
while allowing complex errors to include full guidance.

Usage Example
-------------
    from claude_agent.errors import ActionableError, print_error

    # Full error with all sections
    error = ActionableError(
        message="--auto-spec requires --goal",
        context="The auto-spec workflow needs a goal to generate a specification from.",
        example='claude-agent --auto-spec --goal "Build a REST API for user management"',
        help_command="claude-agent --help"
    )
    print_error(error)

    # Simple error with just message
    error = ActionableError(message="File not found")
    print_error(error)

Helper Functions
----------------
For common error patterns, use the helper functions:

    - missing_file_error(filename, create_command) - file not found errors
    - missing_option_error(option, example) - missing CLI option errors
    - workflow_error(step, suggestion) - workflow/state errors

When to Use ActionableError
---------------------------
Use ActionableError for:
    - User-facing errors at CLI entry points
    - Errors where the user can take specific action to fix the issue
    - Validation failures with clear next steps
    - Fatal errors that terminate the program

Do NOT use ActionableError for:
    - Real-time progress indicators during execution
    - Diagnostic info during agent sessions (use print() instead)
    - Internal errors that require stack traces for debugging
    - Informational messages that are part of normal output flow
"""

from dataclasses import dataclass, field
from typing import Optional

import click


class ConfigParseError(Exception):
    """Exception raised when config file parsing fails.

    Attributes:
        config_path: Path to the config file that failed to parse
        original_error: The original YAML parse error message
        line_number: Line number where the error occurred (if available)
        actionable_error: Pre-formatted ActionableError for display
    """

    def __init__(
        self,
        config_path: str,
        original_error: str,
        line_number: Optional[int] = None,
    ):
        self.config_path = config_path
        self.original_error = original_error
        self.line_number = line_number
        location = f" at line {line_number}" if line_number else ""
        super().__init__(f"Failed to parse {config_path}{location}: {original_error}")

    def get_actionable_error(self) -> "ActionableError":
        """Get an ActionableError for display."""
        # Call config_parse_error directly - it's in this same module
        return config_parse_error(
            self.config_path,
            self.original_error,
            self.line_number,
        )


class ConfigValidationError(Exception):
    """Exception raised when config values fail validation.

    Attributes:
        config_path: Path to the config file with invalid values
        field: The field that failed validation
        message: Description of the validation failure
    """

    # Field-specific examples for actionable error messages
    FIELD_EXAMPLES = {
        "evaluation weights": "Ensure evaluation weights sum to 1.0 (coverage + testability + granularity + independence = 1.0)",
        "model": "Use a valid model name like 'claude-opus-4-5-20251101' or 'claude-sonnet-4-5-20250929'",
        "features": "Specify a positive integer for feature count (e.g., features: 50)",
        "stack": "Use a valid stack name: 'python' or 'node'",
    }

    DEFAULT_EXAMPLE = "Check the field value in your .claude-agent.yaml configuration file"

    def __init__(
        self,
        config_path: str,
        field: str,
        message: str,
    ):
        self.config_path = config_path
        self.field = field
        self.message = message
        super().__init__(f"Invalid {field} in {config_path}: {message}")

    def get_actionable_error(self) -> "ActionableError":
        """Get an ActionableError for display."""
        # Look up field-specific example, fall back to default
        example = self.FIELD_EXAMPLES.get(self.field, self.DEFAULT_EXAMPLE)

        return ActionableError(
            message=f"Invalid {self.field} in {self.config_path}",
            context=self.message,
            example=example,
            help_command="claude-agent init",
        )


@dataclass
class ActionableError:
    """Structured error with actionable guidance.

    Attributes:
        message: What went wrong (required)
        context: Why it matters or additional context (optional)
        example: Correct usage example (optional)
        help_command: Help command to run for more info (optional)
    """
    message: str
    context: Optional[str] = None
    example: Optional[str] = None
    help_command: Optional[str] = None

    def format(self, use_color: bool = True) -> str:
        """Format the error for display.

        Args:
            use_color: Whether to use click.style for coloring.
                       Respects NO_COLOR environment variable.

        Returns:
            Formatted error string ready for display.
        """
        import os

        # Respect NO_COLOR environment variable
        if os.environ.get("NO_COLOR"):
            use_color = False

        lines = []

        # Error line - always present, optionally styled
        if use_color:
            error_prefix = click.style("Error:", fg="red", bold=True)
            lines.append(f"{error_prefix} {self.message}")
        else:
            lines.append(f"Error: {self.message}")

        # Context section - optional
        if self.context:
            lines.append("")
            lines.append(f"  {self.context}")

        # Example section - optional
        if self.example:
            lines.append("")
            if use_color:
                example_label = click.style("Example:", bold=True)
                lines.append(f"  {example_label} {self.example}")
            else:
                lines.append(f"  Example: {self.example}")

        # Help section - optional
        if self.help_command:
            lines.append("")
            if use_color:
                help_label = click.style("Help:", bold=True)
                lines.append(f"  {help_label} Run '{self.help_command}' for more options")
            else:
                lines.append(f"  Help: Run '{self.help_command}' for more options")

        return "\n".join(lines)

    def __str__(self) -> str:
        """Return formatted error without colors for logging/testing."""
        return self.format(use_color=False)


def print_error(error: ActionableError, err: bool = True) -> None:
    """Print an ActionableError to the console.

    Gracefully degrades if formatting fails - will always output something
    rather than crashing silently.

    Args:
        error: The ActionableError to print.
        err: If True, prints to stderr; otherwise stdout.
    """
    try:
        click.echo(error.format(), err=err)
    except Exception:
        # Graceful degradation: if formatting fails, output basic error message
        # This ensures the user always sees something useful
        try:
            click.echo(f"Error: {error.message}", err=err)
        except Exception:
            # Last resort: raw print to stderr
            import sys
            print(f"Error: {error.message}", file=sys.stderr if err else sys.stdout)


def fatal_error(
    message: str,
    context: Optional[str] = None,
    example: Optional[str] = None,
    help_command: Optional[str] = None,
    exit_code: int = 1,
) -> None:
    """Print an actionable error and exit the program.

    Convenience function for fatal CLI errors that should terminate execution.
    Combines creating an ActionableError, printing it, and calling sys.exit().

    Args:
        message: What went wrong (required)
        context: Why it matters or additional context (optional)
        example: Correct usage example (optional)
        help_command: Help command to run for more info (optional)
        exit_code: Exit code to use (default: 1)

    Note:
        This function never returns - it always calls sys.exit().
    """
    import sys

    error = ActionableError(
        message=message,
        context=context,
        example=example,
        help_command=help_command,
    )
    print_error(error)
    sys.exit(exit_code)


def format_error(
    message: str,
    context: Optional[str] = None,
    example: Optional[str] = None,
    help_command: Optional[str] = None,
) -> str:
    """Format an error message with optional sections.

    Convenience function for one-off error formatting without
    creating an ActionableError instance.

    Gracefully degrades if formatting fails - will always return
    at least a basic error message rather than raising an exception.

    Args:
        message: What went wrong (required)
        context: Why it matters or additional context (optional)
        example: Correct usage example (optional)
        help_command: Help command to run for more info (optional)

    Returns:
        Formatted error string.
    """
    try:
        error = ActionableError(
            message=message,
            context=context,
            example=example,
            help_command=help_command,
        )
        return error.format()
    except Exception:
        # Graceful degradation: return basic error format
        return f"Error: {message}"


def format_error_with_context(
    message: str,
    context_dict: dict,
    context: Optional[str] = None,
    example: Optional[str] = None,
    help_command: Optional[str] = None,
) -> str:
    """Format an error with template variable substitution.

    Supports template variables like {path}, {command}, {file} in all
    string fields. Missing context values are left as-is (no crash).

    Args:
        message: What went wrong (may contain {variables})
        context_dict: Dict of variable names to values
        context: Why it matters (may contain {variables})
        example: Correct usage (may contain {variables})
        help_command: Help command (may contain {variables})

    Returns:
        Formatted error string with variables substituted.

    Example:
        >>> format_error_with_context(
        ...     "File {path} not found",
        ...     {"path": "/foo/bar.txt"},
        ...     example="Check path: {path}"
        ... )
    """
    import re

    def safe_substitute(s: Optional[str]) -> Optional[str]:
        if s is None:
            return None
        # Use regex to find all {variable} patterns and substitute only if present
        def replace_var(match):
            var_name = match.group(1)
            if var_name in context_dict:
                return str(context_dict[var_name])
            return match.group(0)  # Return original if not found

        return re.sub(r"\{(\w+)\}", replace_var, s)

    return format_error(
        message=safe_substitute(message) or message,
        context=safe_substitute(context),
        example=safe_substitute(example),
        help_command=safe_substitute(help_command),
    )


# =============================================================================
# Helper Functions for Common Error Patterns
# =============================================================================


def missing_file_error(
    filename: str,
    create_command: Optional[str] = None,
    context: Optional[str] = None,
) -> ActionableError:
    """Create an error for a missing file.

    Args:
        filename: Name of the file that was not found
        create_command: Command to create the file (optional)
        context: Additional context about why the file is needed (optional)

    Returns:
        ActionableError configured for missing file scenario.

    Example:
        >>> error = missing_file_error(
        ...     "spec-draft.md",
        ...     create_command="claude-agent spec create --goal '...'"
        ... )
    """
    # Quote paths with spaces
    display_name = f'"{filename}"' if " " in filename else filename

    return ActionableError(
        message=f"{display_name} not found",
        context=context,
        example=create_command,
        help_command="claude-agent --help",
    )


def missing_option_error(
    option: str,
    example: str,
    context: Optional[str] = None,
    help_command: Optional[str] = None,
) -> ActionableError:
    """Create an error for a missing CLI option.

    Args:
        option: Name of the missing option (e.g., "--goal")
        example: Example of correct usage
        context: Why the option is needed (optional)
        help_command: Help command for more info (optional)

    Returns:
        ActionableError configured for missing option scenario.

    Example:
        >>> error = missing_option_error(
        ...     "--goal",
        ...     example='claude-agent --auto-spec --goal "Build a REST API"'
        ... )
    """
    return ActionableError(
        message=f"{option} is required",
        context=context,
        example=example,
        help_command=help_command or "claude-agent --help",
    )


def workflow_error(
    step: str,
    suggestion: str,
    context: Optional[str] = None,
) -> ActionableError:
    """Create an error for workflow/state issues.

    Args:
        step: Which step failed or is in an invalid state
        suggestion: What to do to fix it
        context: Additional context about the workflow state (optional)

    Returns:
        ActionableError configured for workflow error scenario.

    Example:
        >>> error = workflow_error(
        ...     "Validation",
        ...     suggestion="Run 'claude-agent spec validate' to retry"
        ... )
    """
    return ActionableError(
        message=f"{step} failed",
        context=context,
        example=suggestion,
        help_command="claude-agent spec status",
    )


def config_parse_error(
    config_path: str,
    error_message: str,
    line_number: Optional[int] = None,
) -> ActionableError:
    """Create an error for YAML config parsing failures.

    Args:
        config_path: Path to the config file that failed to parse
        error_message: The parse error message from YAML library
        line_number: Line number where the error occurred (optional)

    Returns:
        ActionableError configured for config parse error scenario.

    Example:
        >>> error = config_parse_error(
        ...     ".claude-agent.yaml",
        ...     "expected <block end>, but found '<scalar>'",
        ...     line_number=15
        ... )
    """
    location = f" at line {line_number}" if line_number else ""
    return ActionableError(
        message=f"Failed to parse {config_path}{location}",
        context=f"YAML syntax error: {error_message}",
        example="Check YAML syntax: proper indentation, colons after keys, quoted strings with special characters",
        help_command="claude-agent init",
    )


def permission_error(
    path: str,
    operation: str = "access",
    context: Optional[str] = None,
) -> ActionableError:
    """Create an error for permission/access denied issues.

    Args:
        path: Path to the file/directory with permission issues
        operation: What operation failed (read, write, access)
        context: Additional context about the operation (optional)

    Returns:
        ActionableError configured for permission error scenario.

    Example:
        >>> error = permission_error(
        ...     "/etc/config.yaml",
        ...     operation="write"
        ... )
    """
    # Quote paths with spaces
    display_path = quote_path(path)

    return ActionableError(
        message=f"Permission denied: cannot {operation} {display_path}",
        context=context or f"Check that you have {operation} permissions for this path.",
        example=f"ls -la {display_path}  # Check current permissions",
        help_command=None,
    )


def network_error(
    operation: str,
    error_message: Optional[str] = None,
    suggestion: Optional[str] = None,
) -> ActionableError:
    """Create an error for network/connectivity issues.

    Args:
        operation: What network operation failed
        error_message: The original error message (optional)
        suggestion: Custom suggestion for recovery (optional)

    Returns:
        ActionableError configured for network error scenario.

    Example:
        >>> error = network_error(
        ...     "API connection",
        ...     error_message="Connection refused"
        ... )
    """
    context_parts = []
    if error_message:
        context_parts.append(error_message)
    context_parts.append("This may be a temporary network issue.")

    return ActionableError(
        message=f"{operation} failed due to network error",
        context=" ".join(context_parts),
        example=suggestion or "Check your network connection and try again",
        help_command=None,
    )


def quote_path(path: str) -> str:
    """Quote a path if it contains special characters.

    Args:
        path: File path to potentially quote

    Returns:
        Quoted path if it contains spaces/special chars, otherwise unchanged.
    """
    special_chars = " '\"()[]{}$&;|<>\\`"
    if any(c in path for c in special_chars):
        # Use double quotes and escape any existing quotes
        escaped = path.replace('"', '\\"')
        return f'"{escaped}"'
    return path
