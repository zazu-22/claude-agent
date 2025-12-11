"""
Structured Error Classification Module
======================================

Machine-processable error classification for intelligent recovery and persistence.

This module provides:
- ErrorType enum: Classifies error recovery behavior (RETRY, MANUAL, FATAL, TIMEOUT)
- ErrorCategory enum: Categorizes error source/domain (NETWORK, AUTH, LOGIC, etc.)
- StructuredError dataclass: Complete error representation with context and recovery hints

Design Philosophy
-----------------
StructuredError is distinct from ActionableError (in errors.py):
- StructuredError: Machine-processable, for automated recovery and state persistence
- ActionableError: Human-readable, for CLI display with formatting

Bridge between them using StructuredError.to_actionable_error() when display is needed.

Error Type Behaviors
--------------------
- RETRY: Auto-retry up to 3 times (transient errors like network timeouts)
- MANUAL: Pause workflow, display guidance (needs human intervention)
- FATAL: Abort with clear message (cannot proceed)
- TIMEOUT: Log and escalate (timed out waiting)

Error Categories
----------------
- NETWORK: API failures, connection refused
- AUTH: Permission denied, token expired
- LOGIC: Lint/type/test failures
- CONFIG: Invalid configuration values
- RESOURCE: Missing files, branches, dependencies
- SECURITY: Command blocked by security hook
- VALIDATION: Feature validation failures

Usage Example
-------------
    from claude_agent.structured_errors import (
        StructuredError,
        ErrorType,
        ErrorCategory,
        error_security_block,
        error_file_not_found,
    )

    # Using factory functions (preferred)
    error = error_security_block("rm -rf /", "Command not in allowlist")

    # Direct construction
    error = StructuredError(
        type=ErrorType.MANUAL,
        category=ErrorCategory.SECURITY,
        message="Command blocked by security hook",
        recovery_hint="Add command to extra_commands in .claude-agent.yaml",
        timestamp=datetime.now(),
        context={"command": "rm -rf /", "reason": "Not in allowlist"}
    )

    # Check error behavior
    if error.is_retryable():
        # Auto-retry logic
        pass
    elif error.requires_human():
        # Display guidance and pause
        pass

    # Convert for CLI display
    actionable = error.to_actionable_error()
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ErrorType(str, Enum):
    """Enum classifying error recovery behavior.

    Attributes:
        RETRY: Transient error, can retry automatically up to 3 times
        MANUAL: Needs human intervention, pause workflow with guidance
        FATAL: Cannot proceed, abort with clear message
        TIMEOUT: Timed out waiting, log and escalate
    """
    RETRY = "retry"
    MANUAL = "manual"
    FATAL = "fatal"
    TIMEOUT = "timeout"


class ErrorCategory(str, Enum):
    """Enum categorizing error source/domain.

    Each category corresponds to a distinct recovery path and enables
    intelligent recovery hints.

    Attributes:
        NETWORK: API failures, connection refused
        AUTH: Permission denied, token expired
        LOGIC: Lint/type/test failures
        CONFIG: Invalid configuration values
        RESOURCE: Missing files, branches, dependencies
        SECURITY: Command blocked by security hook
        VALIDATION: Feature validation failures
    """
    NETWORK = "network"
    AUTH = "auth"
    LOGIC = "logic"
    CONFIG = "config"
    RESOURCE = "resource"
    SECURITY = "security"
    VALIDATION = "validation"


@dataclass
class StructuredError:
    """Machine-processable error for automated recovery and persistence.

    This dataclass captures complete error context for:
    - Automated recovery decisions (via is_retryable(), requires_human())
    - State persistence across sessions (via to_dict(), from_dict())
    - CLI display (via to_actionable_error())

    Attributes:
        type: Error type determining recovery behavior
        category: Error category for intelligent recovery hints
        message: Human-readable error description
        recovery_hint: Actionable guidance for recovery (optional)
        timestamp: When the error occurred
        context: Additional debugging context (optional)
    """
    type: ErrorType
    category: ErrorCategory
    message: str
    recovery_hint: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    context: dict = field(default_factory=dict)

    def is_retryable(self) -> bool:
        """Check if this error can be automatically retried.

        Returns:
            True only if type == ErrorType.RETRY
        """
        return self.type == ErrorType.RETRY

    def requires_human(self) -> bool:
        """Check if this error requires human intervention.

        Returns:
            True only if type == ErrorType.MANUAL
        """
        return self.type == ErrorType.MANUAL

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dictionary.

        Enum values are serialized as strings, timestamp as ISO format.

        Returns:
            JSON-serializable dictionary representation
        """
        return {
            "type": self.type.value,
            "category": self.category.value,
            "message": self.message,
            "recovery_hint": self.recovery_hint,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StructuredError":
        """Deserialize from dictionary.

        Handles enum parsing and timestamp conversion. Missing optional
        fields are given default values.

        Args:
            data: Dictionary from to_dict() or JSON parsing

        Returns:
            StructuredError instance

        Raises:
            ValueError: If required fields are missing or invalid
            KeyError: If enum values are invalid
        """
        # Parse required fields
        error_type = ErrorType(data["type"])
        error_category = ErrorCategory(data["category"])
        message = data["message"]

        # Parse timestamp
        timestamp_str = data.get("timestamp")
        if timestamp_str:
            # Handle both formats: with and without microseconds
            timestamp = datetime.fromisoformat(timestamp_str)
        else:
            timestamp = datetime.now()

        # Optional fields with defaults
        recovery_hint = data.get("recovery_hint")
        context = data.get("context", {})

        return cls(
            type=error_type,
            category=error_category,
            message=message,
            recovery_hint=recovery_hint,
            timestamp=timestamp,
            context=context,
        )

    def to_actionable_error(self) -> "ActionableError":
        """Convert to ActionableError for CLI display.

        Maps StructuredError fields to ActionableError format:
        - message -> message
        - recovery_hint -> context
        - category -> determines help_command

        Returns:
            ActionableError instance for human-readable CLI output
        """
        # Import here to avoid circular imports
        from claude_agent.errors import ActionableError

        # Map category to appropriate help command
        help_commands = {
            ErrorCategory.SECURITY: "claude-agent --help",
            ErrorCategory.CONFIG: "claude-agent init",
            ErrorCategory.VALIDATION: "claude-agent status",
            ErrorCategory.RESOURCE: "claude-agent --help",
            ErrorCategory.NETWORK: None,
            ErrorCategory.AUTH: None,
            ErrorCategory.LOGIC: "claude-agent status",
        }

        return ActionableError(
            message=self.message,
            context=self.recovery_hint,
            example=None,
            help_command=help_commands.get(self.category),
        )


# =============================================================================
# Factory Functions for Common Error Patterns
# =============================================================================

def error_security_block(command: str, reason: str) -> StructuredError:
    """Create an error for security-blocked commands.

    Args:
        command: The command that was blocked
        reason: Why it was blocked

    Returns:
        StructuredError with type=MANUAL, category=SECURITY
    """
    return StructuredError(
        type=ErrorType.MANUAL,
        category=ErrorCategory.SECURITY,
        message=f"Command blocked by security hook: {reason}",
        recovery_hint="Add the command to 'security.extra_commands' in .claude-agent.yaml",
        timestamp=datetime.now(),
        context={
            "command": command,
            "reason": reason,
        },
    )


def error_validation_failed(feature_index: int, reason: str) -> StructuredError:
    """Create an error for feature validation failures.

    Args:
        feature_index: Index of the feature that failed validation
        reason: Why validation failed

    Returns:
        StructuredError with type=MANUAL, category=VALIDATION
    """
    return StructuredError(
        type=ErrorType.MANUAL,
        category=ErrorCategory.VALIDATION,
        message=f"Feature {feature_index} validation failed: {reason}",
        recovery_hint="Review the feature implementation and test steps",
        timestamp=datetime.now(),
        context={
            "feature_index": feature_index,
            "reason": reason,
        },
    )


def error_file_not_found(path: str) -> StructuredError:
    """Create an error for missing required files.

    Args:
        path: Path to the file that was not found

    Returns:
        StructuredError with type=MANUAL, category=RESOURCE
    """
    return StructuredError(
        type=ErrorType.MANUAL,
        category=ErrorCategory.RESOURCE,
        message=f"Required file not found: {path}",
        recovery_hint="Check that the file exists at the specified path",
        timestamp=datetime.now(),
        context={
            "path": path,
        },
    )


def error_git_operation(operation: str, details: str) -> StructuredError:
    """Create an error for git command failures.

    Git operations are often transient (lock files, network issues) so
    these errors are marked as retryable.

    Args:
        operation: The git operation that failed (e.g., "commit", "push")
        details: Error details from git

    Returns:
        StructuredError with type=RETRY, category=RESOURCE
    """
    return StructuredError(
        type=ErrorType.RETRY,
        category=ErrorCategory.RESOURCE,
        message=f"Git {operation} failed: {details}",
        recovery_hint="Check 'git status' and resolve any conflicts or issues",
        timestamp=datetime.now(),
        context={
            "operation": operation,
            "details": details,
        },
    )


def error_test_failure(test_type: str, details: str) -> StructuredError:
    """Create an error for lint/type/test failures.

    Args:
        test_type: Type of test that failed (e.g., "lint", "typecheck", "unit")
        details: Error details from the test runner

    Returns:
        StructuredError with type=MANUAL, category=LOGIC
    """
    return StructuredError(
        type=ErrorType.MANUAL,
        category=ErrorCategory.LOGIC,
        message=f"{test_type.title()} check failed",
        recovery_hint=f"Review the {test_type} output and fix the reported issues",
        timestamp=datetime.now(),
        context={
            "test_type": test_type,
            "details": details,
        },
    )


def error_agent_timeout(agent_type: str, duration_seconds: float) -> StructuredError:
    """Create an error for agent session timeouts.

    Args:
        agent_type: Type of agent that timed out (e.g., "coding", "validator")
        duration_seconds: How long the agent ran before timing out

    Returns:
        StructuredError with type=TIMEOUT, category=RESOURCE
    """
    return StructuredError(
        type=ErrorType.TIMEOUT,
        category=ErrorCategory.RESOURCE,
        message=f"{agent_type.title()} agent timed out after {duration_seconds:.1f}s",
        recovery_hint="Consider increasing the timeout or simplifying the task",
        timestamp=datetime.now(),
        context={
            "agent_type": agent_type,
            "duration_seconds": duration_seconds,
        },
    )
