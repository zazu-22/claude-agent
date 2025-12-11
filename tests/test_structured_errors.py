"""
Tests for Structured Errors Module
==================================

Tests for the structured error classification system.
"""

from datetime import datetime
from unittest.mock import patch

import pytest

from claude_agent.structured_errors import (
    ErrorCategory,
    ErrorType,
    StructuredError,
    error_agent_timeout,
    error_file_not_found,
    error_git_operation,
    error_security_block,
    error_test_failure,
    error_validation_failed,
)


class TestErrorTypeEnum:
    """Tests for ErrorType enum."""

    def test_all_values_exist(self):
        """Test all four enum values exist."""
        assert ErrorType.RETRY.value == "retry"
        assert ErrorType.MANUAL.value == "manual"
        assert ErrorType.FATAL.value == "fatal"
        assert ErrorType.TIMEOUT.value == "timeout"

    def test_string_representation(self):
        """Test string representation is lowercase."""
        assert str(ErrorType.RETRY) == "ErrorType.RETRY"
        assert ErrorType.RETRY.value == "retry"

    def test_enum_comparison(self):
        """Test enum comparison works correctly."""
        assert ErrorType.RETRY == ErrorType.RETRY
        assert ErrorType.RETRY != ErrorType.MANUAL
        assert ErrorType("retry") == ErrorType.RETRY

    def test_enum_iteration(self):
        """Test enum iteration covers all types."""
        types = list(ErrorType)
        assert len(types) == 4
        assert ErrorType.RETRY in types
        assert ErrorType.MANUAL in types
        assert ErrorType.FATAL in types
        assert ErrorType.TIMEOUT in types


class TestErrorCategoryEnum:
    """Tests for ErrorCategory enum."""

    def test_all_values_exist(self):
        """Test all seven category values exist."""
        assert ErrorCategory.NETWORK.value == "network"
        assert ErrorCategory.AUTH.value == "auth"
        assert ErrorCategory.LOGIC.value == "logic"
        assert ErrorCategory.CONFIG.value == "config"
        assert ErrorCategory.RESOURCE.value == "resource"
        assert ErrorCategory.SECURITY.value == "security"
        assert ErrorCategory.VALIDATION.value == "validation"

    def test_string_representation(self):
        """Test string representation matches expected format."""
        assert ErrorCategory.SECURITY.value == "security"
        assert ErrorCategory("security") == ErrorCategory.SECURITY

    def test_enum_iteration(self):
        """Test enum iteration covers all categories."""
        categories = list(ErrorCategory)
        assert len(categories) == 7


class TestStructuredError:
    """Tests for StructuredError dataclass."""

    def test_creation_with_required_fields(self):
        """Test creation with required fields only."""
        now = datetime.now()
        error = StructuredError(
            type=ErrorType.MANUAL,
            category=ErrorCategory.SECURITY,
            message="Test error",
            timestamp=now,
        )

        assert error.type == ErrorType.MANUAL
        assert error.category == ErrorCategory.SECURITY
        assert error.message == "Test error"
        assert error.recovery_hint is None
        assert error.context == {}

    def test_creation_with_all_fields(self):
        """Test creation with all fields specified."""
        now = datetime.now()
        error = StructuredError(
            type=ErrorType.RETRY,
            category=ErrorCategory.NETWORK,
            message="Connection failed",
            recovery_hint="Check network connection",
            timestamp=now,
            context={"url": "http://example.com"},
        )

        assert error.type == ErrorType.RETRY
        assert error.category == ErrorCategory.NETWORK
        assert error.message == "Connection failed"
        assert error.recovery_hint == "Check network connection"
        assert error.context == {"url": "http://example.com"}

    def test_default_values(self):
        """Test default values are applied correctly."""
        error = StructuredError(
            type=ErrorType.FATAL,
            category=ErrorCategory.CONFIG,
            message="Invalid config",
        )

        assert error.recovery_hint is None
        assert error.context == {}
        assert isinstance(error.timestamp, datetime)


class TestStructuredErrorHelpers:
    """Tests for StructuredError helper methods."""

    def test_is_retryable_returns_true_for_retry(self):
        """Test is_retryable returns True only for RETRY type."""
        error = StructuredError(
            type=ErrorType.RETRY,
            category=ErrorCategory.NETWORK,
            message="Test",
        )
        assert error.is_retryable() is True

    def test_is_retryable_returns_false_for_others(self):
        """Test is_retryable returns False for non-RETRY types."""
        for error_type in [ErrorType.MANUAL, ErrorType.FATAL, ErrorType.TIMEOUT]:
            error = StructuredError(
                type=error_type,
                category=ErrorCategory.NETWORK,
                message="Test",
            )
            assert error.is_retryable() is False, f"Should be False for {error_type}"

    def test_requires_human_returns_true_for_manual(self):
        """Test requires_human returns True only for MANUAL type."""
        error = StructuredError(
            type=ErrorType.MANUAL,
            category=ErrorCategory.SECURITY,
            message="Test",
        )
        assert error.requires_human() is True

    def test_requires_human_returns_false_for_others(self):
        """Test requires_human returns False for non-MANUAL types."""
        for error_type in [ErrorType.RETRY, ErrorType.FATAL, ErrorType.TIMEOUT]:
            error = StructuredError(
                type=error_type,
                category=ErrorCategory.NETWORK,
                message="Test",
            )
            assert error.requires_human() is False, f"Should be False for {error_type}"


class TestStructuredErrorSerialization:
    """Tests for StructuredError serialization methods."""

    def test_to_dict_serializes_all_fields(self):
        """Test to_dict produces JSON-serializable dict."""
        now = datetime(2024, 1, 15, 10, 30, 0)
        error = StructuredError(
            type=ErrorType.MANUAL,
            category=ErrorCategory.SECURITY,
            message="Command blocked",
            recovery_hint="Add to allowlist",
            timestamp=now,
            context={"command": "rm -rf /"},
        )

        result = error.to_dict()

        assert result["type"] == "manual"
        assert result["category"] == "security"
        assert result["message"] == "Command blocked"
        assert result["recovery_hint"] == "Add to allowlist"
        assert result["timestamp"] == "2024-01-15T10:30:00"
        assert result["context"] == {"command": "rm -rf /"}

    def test_from_dict_deserializes_all_fields(self):
        """Test from_dict correctly parses dictionary."""
        data = {
            "type": "retry",
            "category": "network",
            "message": "Connection failed",
            "recovery_hint": "Check connection",
            "timestamp": "2024-01-15T10:30:00",
            "context": {"url": "http://test.com"},
        }

        error = StructuredError.from_dict(data)

        assert error.type == ErrorType.RETRY
        assert error.category == ErrorCategory.NETWORK
        assert error.message == "Connection failed"
        assert error.recovery_hint == "Check connection"
        assert error.timestamp == datetime(2024, 1, 15, 10, 30, 0)
        assert error.context == {"url": "http://test.com"}

    def test_serialization_roundtrip(self):
        """Test that to_dict -> from_dict preserves data."""
        original = StructuredError(
            type=ErrorType.MANUAL,
            category=ErrorCategory.VALIDATION,
            message="Feature 5 failed",
            recovery_hint="Check implementation",
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            context={"feature_index": 5, "reason": "Button not found"},
        )

        serialized = original.to_dict()
        restored = StructuredError.from_dict(serialized)

        assert restored.type == original.type
        assert restored.category == original.category
        assert restored.message == original.message
        assert restored.recovery_hint == original.recovery_hint
        assert restored.timestamp == original.timestamp
        assert restored.context == original.context

    def test_from_dict_handles_missing_optional_fields(self):
        """Test from_dict handles missing optional fields gracefully."""
        data = {
            "type": "fatal",
            "category": "config",
            "message": "Invalid config",
        }

        error = StructuredError.from_dict(data)

        assert error.type == ErrorType.FATAL
        assert error.category == ErrorCategory.CONFIG
        assert error.message == "Invalid config"
        assert error.recovery_hint is None
        assert error.context == {}
        # timestamp should be set to now if missing
        assert isinstance(error.timestamp, datetime)


class TestToActionableErrorBridge:
    """Tests for to_actionable_error bridge method."""

    def test_message_mapping(self):
        """Test message mapping is correct."""
        error = StructuredError(
            type=ErrorType.MANUAL,
            category=ErrorCategory.SECURITY,
            message="Command blocked",
        )

        actionable = error.to_actionable_error()

        assert actionable.message == "Command blocked"

    def test_recovery_hint_becomes_context(self):
        """Test recovery_hint becomes ActionableError context."""
        error = StructuredError(
            type=ErrorType.MANUAL,
            category=ErrorCategory.SECURITY,
            message="Command blocked",
            recovery_hint="Add to allowlist in config",
        )

        actionable = error.to_actionable_error()

        assert actionable.context == "Add to allowlist in config"

    def test_output_is_actionable_error_instance(self):
        """Test output is valid ActionableError instance."""
        from claude_agent.errors import ActionableError

        error = StructuredError(
            type=ErrorType.MANUAL,
            category=ErrorCategory.SECURITY,
            message="Test",
        )

        actionable = error.to_actionable_error()

        assert isinstance(actionable, ActionableError)

    def test_help_command_based_on_category(self):
        """Test help_command is set based on category."""
        # SECURITY should have help command
        error = StructuredError(
            type=ErrorType.MANUAL,
            category=ErrorCategory.SECURITY,
            message="Blocked",
        )
        assert error.to_actionable_error().help_command == "claude-agent --help"

        # CONFIG should have init command
        error = StructuredError(
            type=ErrorType.MANUAL,
            category=ErrorCategory.CONFIG,
            message="Invalid",
        )
        assert error.to_actionable_error().help_command == "claude-agent init"

        # NETWORK should have no help command
        error = StructuredError(
            type=ErrorType.RETRY,
            category=ErrorCategory.NETWORK,
            message="Failed",
        )
        assert error.to_actionable_error().help_command is None


class TestErrorSecurityBlock:
    """Tests for error_security_block factory function."""

    def test_returns_correct_type_and_category(self):
        """Test returns StructuredError with MANUAL type and SECURITY category."""
        error = error_security_block("rm -rf /", "Command not in allowlist")

        assert error.type == ErrorType.MANUAL
        assert error.category == ErrorCategory.SECURITY

    def test_includes_command_in_context(self):
        """Test command is included in context dict."""
        error = error_security_block("rm -rf /", "Not allowed")

        assert error.context["command"] == "rm -rf /"
        assert error.context["reason"] == "Not allowed"

    def test_recovery_hint_includes_config_path(self):
        """Test recovery_hint contains config file reference."""
        error = error_security_block("docker", "Not in allowlist")

        assert ".claude-agent.yaml" in error.recovery_hint
        assert "extra_commands" in error.recovery_hint


class TestErrorValidationFailed:
    """Tests for error_validation_failed factory function."""

    def test_returns_correct_type_and_category(self):
        """Test returns StructuredError with MANUAL type and VALIDATION category."""
        error = error_validation_failed(5, "Button not found")

        assert error.type == ErrorType.MANUAL
        assert error.category == ErrorCategory.VALIDATION

    def test_includes_feature_index_in_context(self):
        """Test feature_index is included in context."""
        error = error_validation_failed(5, "Test failed")

        assert error.context["feature_index"] == 5
        assert error.context["reason"] == "Test failed"


class TestErrorFileNotFound:
    """Tests for error_file_not_found factory function."""

    def test_returns_correct_type_and_category(self):
        """Test returns StructuredError with MANUAL type and RESOURCE category."""
        error = error_file_not_found("/path/to/file.txt")

        assert error.type == ErrorType.MANUAL
        assert error.category == ErrorCategory.RESOURCE

    def test_includes_path_in_context(self):
        """Test path is included in context."""
        error = error_file_not_found("/path/to/file.txt")

        assert error.context["path"] == "/path/to/file.txt"


class TestErrorGitOperation:
    """Tests for error_git_operation factory function."""

    def test_returns_retry_type(self):
        """Test returns StructuredError with RETRY type."""
        error = error_git_operation("push", "Remote rejected")

        assert error.type == ErrorType.RETRY

    def test_returns_resource_category(self):
        """Test returns StructuredError with RESOURCE category."""
        error = error_git_operation("commit", "Lock file exists")

        assert error.category == ErrorCategory.RESOURCE

    def test_includes_operation_in_context(self):
        """Test operation is included in context."""
        error = error_git_operation("push", "Remote rejected")

        assert error.context["operation"] == "push"
        assert error.context["details"] == "Remote rejected"


class TestErrorTestFailure:
    """Tests for error_test_failure factory function."""

    def test_returns_logic_category(self):
        """Test returns StructuredError with LOGIC category."""
        error = error_test_failure("lint", "ESLint errors found")

        assert error.category == ErrorCategory.LOGIC

    def test_returns_manual_type(self):
        """Test returns StructuredError with MANUAL type."""
        error = error_test_failure("typecheck", "Type errors found")

        assert error.type == ErrorType.MANUAL

    def test_includes_test_type_in_context(self):
        """Test test_type is included in context."""
        error = error_test_failure("unit", "3 tests failed")

        assert error.context["test_type"] == "unit"
        assert error.context["details"] == "3 tests failed"


class TestErrorAgentTimeout:
    """Tests for error_agent_timeout factory function."""

    def test_returns_timeout_type(self):
        """Test returns StructuredError with TIMEOUT type."""
        error = error_agent_timeout("coding", 300.5)

        assert error.type == ErrorType.TIMEOUT

    def test_returns_resource_category(self):
        """Test returns StructuredError with RESOURCE category."""
        error = error_agent_timeout("validator", 120.0)

        assert error.category == ErrorCategory.RESOURCE

    def test_includes_agent_type_and_duration_in_context(self):
        """Test agent_type and duration are included in context."""
        error = error_agent_timeout("coding", 300.5)

        assert error.context["agent_type"] == "coding"
        assert error.context["duration_seconds"] == 300.5

    def test_recovery_hint_suggests_timeout_increase(self):
        """Test recovery_hint suggests increasing timeout."""
        error = error_agent_timeout("coding", 300.0)

        assert "timeout" in error.recovery_hint.lower()
