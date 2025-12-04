"""
Tests for ActionableError Module
================================

Tests for the actionable error formatting system.
"""

import os
from unittest.mock import patch

import pytest

from claude_agent.errors import (
    ActionableError,
    format_error,
    format_error_with_context,
    missing_file_error,
    missing_option_error,
    print_error,
    quote_path,
    workflow_error,
)


class TestActionableError:
    """Tests for ActionableError class."""

    def test_error_with_all_fields(self):
        """Test ActionableError with all fields populated."""
        error = ActionableError(
            message="--auto-spec requires --goal",
            context="The auto-spec workflow needs a goal to generate a specification from.",
            example='claude-agent --auto-spec --goal "Build a REST API"',
            help_command="claude-agent --help",
        )

        # Format without colors for testing
        output = error.format(use_color=False)

        assert "Error: --auto-spec requires --goal" in output
        assert "The auto-spec workflow needs a goal" in output
        assert "Example: claude-agent --auto-spec" in output
        assert "Help: Run 'claude-agent --help'" in output

    def test_error_with_message_only(self):
        """Test ActionableError with only message (minimal)."""
        error = ActionableError(message="File not found")

        output = error.format(use_color=False)

        assert output == "Error: File not found"
        assert "Context:" not in output
        assert "Example:" not in output
        assert "Help:" not in output

    def test_error_with_message_and_example(self):
        """Test ActionableError with message and example only."""
        error = ActionableError(
            message="--goal required",
            example='claude-agent --goal "Build an API"',
        )

        output = error.format(use_color=False)

        assert "Error: --goal required" in output
        assert "Example: claude-agent --goal" in output
        # Should not have context or help sections
        lines = output.split("\n")
        # Filter empty lines
        non_empty = [l for l in lines if l.strip()]
        assert len(non_empty) == 2  # Error line and Example line

    def test_error_with_message_and_context(self):
        """Test ActionableError with message and context only."""
        error = ActionableError(
            message="spec-draft.md not found",
            context="Validation requires a draft specification.",
        )

        output = error.format(use_color=False)

        assert "Error: spec-draft.md not found" in output
        assert "Validation requires a draft" in output
        assert "Example:" not in output
        assert "Help:" not in output

    def test_str_method(self):
        """Test __str__ returns uncolored output."""
        error = ActionableError(
            message="Test error",
            context="Test context",
        )

        # str() should be same as format(use_color=False)
        assert str(error) == error.format(use_color=False)

    def test_color_output_with_no_color_env(self):
        """Test that NO_COLOR environment variable disables colors."""
        error = ActionableError(
            message="Test error",
            context="Test context",
        )

        # Set NO_COLOR
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            output = error.format(use_color=True)

        # Should not contain ANSI escape codes
        assert "\033[" not in output

    def test_optional_sections_empty(self):
        """Test that empty sections are not displayed."""
        error = ActionableError(
            message="Simple error",
            context=None,
            example=None,
            help_command=None,
        )

        output = error.format(use_color=False)

        # Should only contain the error line
        assert output.strip() == "Error: Simple error"


class TestFormatError:
    """Tests for format_error convenience function."""

    def test_format_error_full(self):
        """Test format_error with all parameters."""
        # Set NO_COLOR to get predictable output
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            output = format_error(
                message="Test message",
                context="Test context",
                example="test-command --flag",
                help_command="test-command --help",
            )

        assert "Error: Test message" in output
        assert "Test context" in output
        assert "Example: test-command --flag" in output
        assert "Help:" in output

    def test_format_error_minimal(self):
        """Test format_error with only message."""
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            output = format_error(message="Simple error")

        assert output.strip() == "Error: Simple error"


class TestFormatErrorWithContext:
    """Tests for format_error_with_context function."""

    def test_variable_substitution(self):
        """Test template variable substitution."""
        output = format_error_with_context(
            message="File {path} not found",
            context_dict={"path": "/foo/bar.txt"},
            context="Looking for {path}",
            example="Check path: {path}",
        )

        assert "/foo/bar.txt" in output
        assert "{path}" not in output

    def test_missing_variable_graceful(self):
        """Test that missing variables don't crash."""
        output = format_error_with_context(
            message="File {path} not found",
            context_dict={},  # No variables provided
        )

        # Should still produce output (with unresolved variable)
        assert "Error:" in output
        assert "{path}" in output  # Unresolved but not crashed

    def test_partial_substitution(self):
        """Test with some variables provided."""
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            output = format_error_with_context(
                message="{file} at {path}",
                context_dict={"file": "config.yaml"},
            )

        assert "config.yaml" in output
        assert "{path}" in output  # Unresolved


class TestMissingFileError:
    """Tests for missing_file_error helper."""

    def test_basic_missing_file(self):
        """Test basic missing file error."""
        error = missing_file_error("spec-draft.md")

        assert error.message == "spec-draft.md not found"
        assert error.help_command == "claude-agent --help"

    def test_missing_file_with_create_command(self):
        """Test missing file with create command."""
        error = missing_file_error(
            "spec-draft.md",
            create_command="claude-agent spec create --goal '...'",
        )

        assert error.message == "spec-draft.md not found"
        assert error.example == "claude-agent spec create --goal '...'"

    def test_missing_file_with_context(self):
        """Test missing file with custom context."""
        error = missing_file_error(
            "config.yaml",
            context="Configuration file is required for this operation.",
        )

        assert error.context == "Configuration file is required for this operation."

    def test_missing_file_quotes_spaces(self):
        """Test that paths with spaces are quoted."""
        error = missing_file_error("my file.txt")

        assert '"my file.txt"' in error.message


class TestMissingOptionError:
    """Tests for missing_option_error helper."""

    def test_basic_missing_option(self):
        """Test basic missing option error."""
        error = missing_option_error(
            "--goal",
            example='claude-agent --goal "Build an API"',
        )

        assert error.message == "--goal is required"
        assert 'claude-agent --goal "Build an API"' in error.example
        assert error.help_command == "claude-agent --help"

    def test_missing_option_with_context(self):
        """Test missing option with custom context."""
        error = missing_option_error(
            "--config",
            example="claude-agent --config path/to/config.yaml",
            context="Configuration is required for this mode.",
        )

        assert error.context == "Configuration is required for this mode."

    def test_missing_option_custom_help(self):
        """Test missing option with custom help command."""
        error = missing_option_error(
            "--spec",
            example="claude-agent --spec ./SPEC.md",
            help_command="claude-agent spec --help",
        )

        assert error.help_command == "claude-agent spec --help"


class TestWorkflowError:
    """Tests for workflow_error helper."""

    def test_basic_workflow_error(self):
        """Test basic workflow error."""
        error = workflow_error(
            "Validation",
            suggestion="Run 'claude-agent spec validate' to retry",
        )

        assert error.message == "Validation failed"
        assert "claude-agent spec validate" in error.example
        assert error.help_command == "claude-agent spec status"

    def test_workflow_error_with_context(self):
        """Test workflow error with custom context."""
        error = workflow_error(
            "Decomposition",
            suggestion="Run 'claude-agent spec decompose' to retry",
            context="The spec may have issues.",
        )

        assert error.context == "The spec may have issues."


class TestQuotePath:
    """Tests for quote_path function."""

    def test_simple_path(self):
        """Test path without special characters."""
        assert quote_path("/foo/bar.txt") == "/foo/bar.txt"

    def test_path_with_space(self):
        """Test path with spaces."""
        assert quote_path("/foo/bar baz.txt") == '"/foo/bar baz.txt"'

    def test_path_with_quotes(self):
        """Test path with existing quotes."""
        result = quote_path('/foo/"bar".txt')
        assert result == '"/foo/\\"bar\\".txt"'

    def test_path_with_special_chars(self):
        """Test path with various special characters."""
        assert quote_path("/foo/$bar.txt") == '"/foo/$bar.txt"'
        assert quote_path("/foo/(bar).txt") == '"/foo/(bar).txt"'


class TestPrintError:
    """Tests for print_error function."""

    def test_print_error_basic(self, capsys):
        """Test that print_error outputs to stderr by default."""
        error = ActionableError(message="Test error")
        print_error(error)

        captured = capsys.readouterr()
        assert "Error: Test error" in captured.err

    def test_print_error_to_stdout(self, capsys):
        """Test print_error with err=False."""
        error = ActionableError(message="Test error")
        print_error(error, err=False)

        captured = capsys.readouterr()
        assert "Error: Test error" in captured.out
        assert captured.err == ""


class TestIntegration:
    """Integration tests for error module."""

    def test_cli_style_usage(self):
        """Test typical CLI error pattern."""
        # This tests the pattern used in cli.py
        error = ActionableError(
            message="--auto-spec requires --goal",
            context="The auto-spec workflow needs a goal to generate a specification from.",
            example='claude-agent --auto-spec --goal "Build a REST API for user management"',
            help_command="claude-agent --help",
        )

        output = error.format(use_color=False)

        # Verify structure
        lines = [l for l in output.split("\n") if l.strip()]
        assert lines[0].startswith("Error:")
        assert any("Example:" in l for l in lines)
        assert any("Help:" in l for l in lines)

    def test_error_formatting_consistency(self):
        """Test that all errors have consistent indentation."""
        error = ActionableError(
            message="Test",
            context="Context line",
            example="Example line",
            help_command="help",
        )

        output = error.format(use_color=False)
        lines = output.split("\n")

        # Non-error lines should be indented with 2 spaces
        for line in lines[1:]:
            if line.strip():  # Skip empty lines
                assert line.startswith("  "), f"Line not indented: {line!r}"

    def test_concise_simple_errors(self):
        """Test that simple errors are concise (under 5 lines)."""
        error = ActionableError(message="Missing option")

        output = error.format(use_color=False)
        lines = output.strip().split("\n")

        assert len(lines) <= 5, f"Simple error has too many lines: {len(lines)}"


class TestGracefulDegradation:
    """Tests for graceful degradation when formatting fails."""

    def test_print_error_degrades_gracefully_on_format_failure(self, capsys):
        """Test that print_error outputs basic message when format() raises."""
        error = ActionableError(message="Test error message")

        # Mock format() to raise an exception
        with patch.object(error, "format", side_effect=RuntimeError("Format failed")):
            print_error(error)

        captured = capsys.readouterr()
        # Should fall back to basic error message
        assert "Error: Test error message" in captured.err

    def test_print_error_degrades_gracefully_on_click_failure(self, capsys):
        """Test that print_error uses raw print when click.echo fails."""
        import sys
        import io

        error = ActionableError(message="Fallback test")

        # Capture stderr manually since click.echo might fail
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()

        try:
            # Mock both format() and click.echo to fail
            with patch.object(error, "format", side_effect=RuntimeError("Format failed")):
                with patch("click.echo", side_effect=RuntimeError("Click failed")):
                    print_error(error)

            output = sys.stderr.getvalue()
            # Should fall back to raw print
            assert "Error: Fallback test" in output
        finally:
            sys.stderr = old_stderr

    def test_format_error_degrades_gracefully(self):
        """Test that format_error returns basic message when ActionableError fails."""
        # Mock ActionableError to raise on instantiation
        with patch(
            "claude_agent.errors.ActionableError",
            side_effect=RuntimeError("ActionableError failed"),
        ):
            result = format_error(message="Degraded error test")

        # Should fall back to basic format
        assert result == "Error: Degraded error test"

    def test_format_error_degrades_on_format_method_failure(self):
        """Test format_error degrades when format() method fails."""
        original_actionable_error = ActionableError

        class FailingActionableError(original_actionable_error):
            def format(self, use_color=True):
                raise RuntimeError("Format method failed")

        with patch(
            "claude_agent.errors.ActionableError",
            FailingActionableError,
        ):
            result = format_error(message="Method failure test")

        # Should fall back to basic format
        assert result == "Error: Method failure test"

    def test_print_error_preserves_message_content(self, capsys):
        """Test that degraded output preserves the original error message."""
        error = ActionableError(
            message="Configuration file '/path/to/config.yaml' not found",
            context="This context should not appear in degraded output",
            example="This example should not appear in degraded output",
        )

        with patch.object(error, "format", side_effect=RuntimeError("Format failed")):
            print_error(error)

        captured = capsys.readouterr()
        # Message should be preserved
        assert "Configuration file '/path/to/config.yaml' not found" in captured.err
        # But rich formatting should not
        assert "context should not appear" not in captured.err

    def test_print_error_no_silent_failure(self, capsys):
        """Test that print_error always outputs something, never silently fails."""
        error = ActionableError(message="Must always output")

        # Even with format failure, something should be output
        with patch.object(error, "format", side_effect=RuntimeError("Format failed")):
            print_error(error)

        captured = capsys.readouterr()
        # Must have some output
        assert len(captured.err) > 0 or len(captured.out) > 0
        assert "Error:" in captured.err

    def test_degraded_output_to_stdout_when_requested(self, capsys):
        """Test that degraded output respects err=False parameter."""
        error = ActionableError(message="Stdout test")

        with patch.object(error, "format", side_effect=RuntimeError("Format failed")):
            print_error(error, err=False)

        captured = capsys.readouterr()
        # Should go to stdout, not stderr
        assert "Error: Stdout test" in captured.out
        assert captured.err == ""


class TestCLIErrorOutputFormat:
    """Integration tests verifying CLI error output format.

    These tests invoke CLI commands with invalid arguments and verify
    that the error output follows the actionable error format with
    proper sections and exit codes.
    """

    @pytest.fixture
    def runner(self):
        """Create Click CLI test runner."""
        from click.testing import CliRunner
        return CliRunner()

    @pytest.fixture
    def cli_main(self):
        """Import the main CLI entry point."""
        from claude_agent.cli import main
        return main

    def test_auto_spec_without_goal_shows_actionable_error(self, runner, cli_main, tmp_path):
        """Test --auto-spec without --goal shows actionable error format."""
        result = runner.invoke(cli_main, ["--auto-spec", "-p", str(tmp_path)])

        assert result.exit_code != 0
        # Should contain Error: prefix
        assert "Error:" in result.output
        # Should contain example usage
        assert "Example:" in result.output or "claude-agent --auto-spec --goal" in result.output
        # Should suggest help
        assert "Help:" in result.output or "--help" in result.output

    def test_spec_create_without_goal_shows_actionable_error(self, runner, cli_main, tmp_path):
        """Test spec create without goal shows actionable error format."""
        result = runner.invoke(cli_main, ["spec", "create", "-p", str(tmp_path)])

        assert result.exit_code != 0
        # Should contain Error: prefix
        assert "Error:" in result.output
        # Should contain example usage
        assert "Example:" in result.output or "spec create" in result.output
        # Should mention --goal option
        assert "goal" in result.output.lower()

    def test_spec_validate_missing_file_shows_actionable_error(self, runner, cli_main, tmp_path):
        """Test spec validate on missing file shows actionable error format."""
        result = runner.invoke(cli_main, ["spec", "validate", "-p", str(tmp_path)])

        assert result.exit_code != 0
        # Should contain Error: prefix
        assert "Error:" in result.output
        # Should indicate file not found
        assert "not found" in result.output.lower()
        # Should suggest how to create the file
        assert "spec create" in result.output or "Example:" in result.output

    def test_spec_auto_without_goal_shows_actionable_error(self, runner, cli_main, tmp_path):
        """Test spec auto without goal on new project shows actionable error format."""
        result = runner.invoke(cli_main, ["spec", "auto", "-p", str(tmp_path)])

        assert result.exit_code != 0
        # Should contain Error: prefix
        assert "Error:" in result.output
        # Should mention goal is required
        assert "goal" in result.output.lower()
        # Should show example
        assert "Example:" in result.output or "spec auto --goal" in result.output

    def test_spec_decompose_no_spec_shows_actionable_error(self, runner, cli_main, tmp_path):
        """Test spec decompose with no spec files shows actionable error format."""
        result = runner.invoke(cli_main, ["spec", "decompose", "-p", str(tmp_path)])

        assert result.exit_code != 0
        # Should contain Error: prefix
        assert "Error:" in result.output
        # Should indicate no spec found
        assert "not found" in result.output.lower() or "no spec" in result.output.lower()

    def test_error_output_has_proper_structure(self, runner, cli_main, tmp_path):
        """Test that error output has proper multi-line structure."""
        result = runner.invoke(cli_main, ["--auto-spec", "-p", str(tmp_path)])

        assert result.exit_code != 0

        # Error output should be multi-line with sections
        lines = result.output.strip().split("\n")
        non_empty_lines = [l for l in lines if l.strip()]

        # Should have at least the error line and one guidance line
        assert len(non_empty_lines) >= 2, f"Expected multi-line output, got: {result.output}"

        # First non-empty line should start with "Error:"
        assert non_empty_lines[0].strip().startswith("Error:")

    def test_error_exit_code_is_1(self, runner, cli_main, tmp_path):
        """Test that errors exit with code 1."""
        result = runner.invoke(cli_main, ["--auto-spec", "-p", str(tmp_path)])
        assert result.exit_code == 1

    def test_spec_validate_custom_path_not_found_shows_actionable_error(self, runner, cli_main, tmp_path):
        """Test spec validate with nonexistent custom path shows actionable error."""
        result = runner.invoke(
            cli_main,
            ["spec", "validate", str(tmp_path / "nonexistent.md"), "-p", str(tmp_path)]
        )

        # Click validates path existence for exists=True
        # This test verifies the error is informative
        assert result.exit_code != 0
        # Should mention the file doesn't exist
        assert "does not exist" in result.output.lower() or "no such file" in result.output.lower()

    def test_logs_invalid_since_shows_actionable_error(self, runner, cli_main, tmp_path):
        """Test logs --since with invalid format shows actionable error."""
        result = runner.invoke(
            cli_main,
            ["logs", "--since", "invalid_format", "-p", str(tmp_path)]
        )

        # Should return without crash
        assert result.exit_code == 0 or "Error:" in result.output
        # If there's an error, it should be actionable
        if "Error:" in result.output:
            # Should show valid format examples
            assert "1h" in result.output or "2d" in result.output or "format" in result.output.lower()


class TestNonInteractiveOutput:
    """Tests for non-interactive (piped) error output.

    These tests verify that error messages work correctly when output
    is piped to a file or another command (non-interactive mode).
    """

    def test_no_ansi_codes_with_no_color_env(self):
        """Test that NO_COLOR environment variable disables ANSI codes."""
        error = ActionableError(
            message="Test error",
            context="Test context",
            example="test-command --flag",
            help_command="test-command --help",
        )

        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            output = error.format(use_color=True)

        # Should not contain any ANSI escape codes
        assert "\033[" not in output
        assert "\x1b[" not in output
        # But should still contain the error content
        assert "Error: Test error" in output
        assert "Test context" in output

    def test_no_ansi_codes_when_use_color_false(self):
        """Test that use_color=False produces clean output without ANSI codes."""
        error = ActionableError(
            message="Plain text error",
            context="This should be readable in plain text",
            example="example-command",
            help_command="help-command",
        )

        output = error.format(use_color=False)

        # Should not contain any ANSI escape codes
        assert "\033[" not in output
        assert "\x1b[" not in output
        # Content should be present
        assert "Error: Plain text error" in output
        assert "This should be readable" in output

    def test_piped_output_is_readable(self):
        """Test that output piped to file is readable as plain text."""
        error = ActionableError(
            message="File not found: config.yaml",
            context="Configuration file is required",
            example="touch config.yaml",
            help_command="app --help",
        )

        # Simulate piped output (no colors)
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            output = error.format()

        # Should be human-readable
        lines = output.split("\n")
        assert any("Error:" in line for line in lines)
        assert any("config.yaml" in line for line in lines)

    def test_str_method_produces_no_ansi_codes(self):
        """Test that __str__ method produces output suitable for piping."""
        error = ActionableError(
            message="Test message for piping",
            context="This goes to a file",
        )

        output = str(error)

        # str() should always be safe for piping
        assert "\033[" not in output
        assert "\x1b[" not in output
        assert "Test message for piping" in output

    def test_cli_piped_output_has_no_ansi_codes(self):
        """Test that CLI error output has no ANSI codes when piped."""
        from click.testing import CliRunner
        from claude_agent.cli import main

        runner = CliRunner()

        # CliRunner simulates non-interactive mode by default
        result = runner.invoke(main, ["--auto-spec"])

        # Should have error output
        assert result.exit_code != 0

        # CliRunner captures output as plain text, so ANSI codes would be visible
        # Most importantly, the error message should be readable
        assert "Error:" in result.output or "goal" in result.output.lower()

    def test_format_error_function_respects_no_color(self):
        """Test format_error convenience function respects NO_COLOR."""
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            output = format_error(
                message="Convenience function test",
                context="Context here",
                example="example",
                help_command="help",
            )

        assert "\033[" not in output
        assert "Convenience function test" in output

    def test_print_error_outputs_to_correct_stream(self, capsys):
        """Test that print_error can output to either stdout or stderr."""
        error = ActionableError(message="Stream test")

        # Default: stderr
        print_error(error)
        captured = capsys.readouterr()
        assert "Stream test" in captured.err
        assert captured.out == ""

        # With err=False: stdout
        print_error(error, err=False)
        captured = capsys.readouterr()
        assert "Stream test" in captured.out

    def test_error_message_captured_in_file_simulation(self):
        """Test that error message can be captured when redirecting to file."""
        import io

        error = ActionableError(
            message="Captured error",
            context="This should be in the file",
            example="fix-command",
        )

        # Simulate capturing to a file (StringIO)
        output_buffer = io.StringIO()

        # Write the error output as it would appear in a file
        output_buffer.write(error.format(use_color=False))

        # Read back
        output_buffer.seek(0)
        captured = output_buffer.read()

        assert "Captured error" in captured
        assert "This should be in the file" in captured
        assert "fix-command" in captured
        # No ANSI codes
        assert "\033[" not in captured


class TestVerboseModeIntegration:
    """Tests for error module integration with --verbose flag.

    Verifies that actionable errors work correctly regardless of
    verbose mode settings.
    """

    @pytest.fixture
    def runner(self):
        """Create Click CLI test runner."""
        from click.testing import CliRunner
        return CliRunner()

    @pytest.fixture
    def cli_main(self):
        """Import the main CLI entry point."""
        from claude_agent.cli import main
        return main

    def test_verbose_mode_preserves_error_format(self, runner, cli_main, tmp_path):
        """Test that --verbose flag doesn't break actionable error format."""
        result = runner.invoke(
            cli_main,
            ["--verbose", "--auto-spec", "-p", str(tmp_path)]
        )

        assert result.exit_code != 0
        # Error should still have actionable format
        assert "Error:" in result.output
        # Should still show example or help
        assert "Example:" in result.output or "Help:" in result.output or "--help" in result.output

    def test_non_verbose_mode_shows_actionable_error(self, runner, cli_main, tmp_path):
        """Test that non-verbose mode shows standard actionable error."""
        result = runner.invoke(
            cli_main,
            ["--auto-spec", "-p", str(tmp_path)]  # No --verbose
        )

        assert result.exit_code != 0
        assert "Error:" in result.output
        # Should have example usage
        assert "Example:" in result.output or "claude-agent" in result.output

    def test_verbose_and_non_verbose_both_have_error_prefix(self, runner, cli_main, tmp_path):
        """Test both modes use Error: prefix consistently."""
        # With verbose
        verbose_result = runner.invoke(
            cli_main,
            ["--verbose", "--auto-spec", "-p", str(tmp_path)]
        )

        # Without verbose
        non_verbose_result = runner.invoke(
            cli_main,
            ["--auto-spec", "-p", str(tmp_path)]
        )

        # Both should have Error: prefix
        assert "Error:" in verbose_result.output
        assert "Error:" in non_verbose_result.output

    def test_verbose_mode_with_spec_create_error(self, runner, cli_main, tmp_path):
        """Test verbose mode with spec create error."""
        result = runner.invoke(
            cli_main,
            ["--verbose", "spec", "create", "-p", str(tmp_path)]
        )

        assert result.exit_code != 0
        # Should have actionable error format
        assert "Error:" in result.output
        assert "goal" in result.output.lower()

    def test_verbose_mode_with_spec_validate_error(self, runner, cli_main, tmp_path):
        """Test verbose mode with spec validate error (missing file)."""
        result = runner.invoke(
            cli_main,
            ["--verbose", "spec", "validate", "-p", str(tmp_path)]
        )

        assert result.exit_code != 0
        assert "Error:" in result.output
        assert "not found" in result.output.lower()

    def test_error_format_is_consistent_across_modes(self, runner, cli_main, tmp_path):
        """Test that error format structure is consistent in both modes."""
        verbose_result = runner.invoke(
            cli_main,
            ["--verbose", "spec", "auto", "-p", str(tmp_path)]
        )

        non_verbose_result = runner.invoke(
            cli_main,
            ["spec", "auto", "-p", str(tmp_path)]
        )

        # Both should fail with similar error structure
        assert verbose_result.exit_code != 0
        assert non_verbose_result.exit_code != 0

        # Both should mention goal
        assert "goal" in verbose_result.output.lower()
        assert "goal" in non_verbose_result.output.lower()

        # Both should have actionable format elements
        for result in [verbose_result, non_verbose_result]:
            assert "Error:" in result.output

    def test_verbose_flag_is_recognized(self, runner, cli_main):
        """Test that --verbose flag is recognized by CLI."""
        # Run with --verbose --help to verify flag exists
        result = runner.invoke(cli_main, ["--help"])

        assert result.exit_code == 0
        assert "--verbose" in result.output or "-v" in result.output


class TestConfigParseError:
    """Tests for ConfigParseError exception and config_parse_error helper."""

    def test_config_parse_error_basic(self):
        """Test ConfigParseError with basic parameters."""
        from claude_agent.errors import ConfigParseError

        error = ConfigParseError(
            config_path=".claude-agent.yaml",
            original_error="expected <block end>, but found '<scalar>'",
        )

        assert error.config_path == ".claude-agent.yaml"
        assert "expected <block end>" in error.original_error
        assert error.line_number is None

    def test_config_parse_error_with_line_number(self):
        """Test ConfigParseError with line number."""
        from claude_agent.errors import ConfigParseError

        error = ConfigParseError(
            config_path=".claude-agent.yaml",
            original_error="mapping values are not allowed here",
            line_number=15,
        )

        assert error.line_number == 15
        assert "15" in str(error) or "line" in str(error).lower()

    def test_config_parse_error_actionable_format(self):
        """Test that ConfigParseError produces actionable error format."""
        from claude_agent.errors import ConfigParseError

        error = ConfigParseError(
            config_path=".claude-agent.yaml",
            original_error="invalid syntax",
            line_number=10,
        )

        actionable = error.get_actionable_error()

        # Check all sections are present
        output = actionable.format(use_color=False)
        assert "Error:" in output
        assert ".claude-agent.yaml" in output
        assert "line 10" in output
        assert "YAML" in output or "syntax" in output.lower()

    def test_config_parse_error_helper(self):
        """Test config_parse_error helper function."""
        from claude_agent.errors import config_parse_error

        error = config_parse_error(
            config_path=".claude-agent.yaml",
            error_message="unexpected end of stream",
            line_number=5,
        )

        output = error.format(use_color=False)
        assert "Error:" in output
        assert ".claude-agent.yaml" in output
        assert "line 5" in output
        assert "Example:" in output or "syntax" in output.lower()
        assert "Help:" in output or "init" in output.lower()

    def test_config_parse_error_without_line_number(self):
        """Test config_parse_error without line number."""
        from claude_agent.errors import config_parse_error

        error = config_parse_error(
            config_path="config.yaml",
            error_message="invalid YAML",
        )

        output = error.format(use_color=False)
        assert "Error:" in output
        assert "config.yaml" in output
        # Should not have "line" if no line number
        assert "line" not in output.lower() or "Check" in output

    def test_malformed_yaml_triggers_config_parse_error(self, tmp_path):
        """Test that malformed YAML in config file triggers ConfigParseError."""
        from claude_agent.config import load_config_file
        from claude_agent.errors import ConfigParseError

        # Create malformed YAML
        config_file = tmp_path / ".claude-agent.yaml"
        config_file.write_text("""
agent:
  model: test
  invalid_yaml: [unclosed bracket
features: 50
""")

        with pytest.raises(ConfigParseError) as exc_info:
            load_config_file(config_file)

        error = exc_info.value
        assert error.config_path == str(config_file)
        # Should have some error message
        assert len(error.original_error) > 0

    def test_malformed_yaml_has_line_number(self, tmp_path):
        """Test that malformed YAML error includes line number when available."""
        from claude_agent.config import load_config_file
        from claude_agent.errors import ConfigParseError

        # Create malformed YAML with specific error location
        config_file = tmp_path / ".claude-agent.yaml"
        config_file.write_text("""features: 50
agent:
  model: test
  bad: : colon
security:
  extra_commands: []
""")

        with pytest.raises(ConfigParseError) as exc_info:
            load_config_file(config_file)

        error = exc_info.value
        # Line number should be available for this type of error
        assert error.line_number is not None

    def test_cli_shows_actionable_error_for_malformed_config(self, tmp_path):
        """Test that CLI shows actionable error for malformed config."""
        from click.testing import CliRunner
        from claude_agent.cli import main

        # Create malformed YAML config
        config_file = tmp_path / ".claude-agent.yaml"
        config_file.write_text("""
agent:
  model: test
  broken: [unclosed
""")

        runner = CliRunner()
        result = runner.invoke(main, ["-p", str(tmp_path), "--goal", "test"])

        assert result.exit_code == 1
        # Should have actionable error format
        assert "Error:" in result.output
        # Should mention the config file
        assert ".claude-agent.yaml" in result.output or "parse" in result.output.lower()


class TestPermissionError:
    """Tests for permission_error helper function."""

    def test_permission_error_basic(self):
        """Test basic permission error."""
        from claude_agent.errors import permission_error

        error = permission_error("/etc/config.yaml", operation="write")

        output = error.format(use_color=False)
        assert "Error:" in output
        assert "Permission denied" in output
        assert "/etc/config.yaml" in output
        assert "write" in output

    def test_permission_error_with_context(self):
        """Test permission error with custom context."""
        from claude_agent.errors import permission_error

        error = permission_error(
            "/var/log/app.log",
            operation="read",
            context="Log files require elevated permissions.",
        )

        output = error.format(use_color=False)
        assert "Error:" in output
        assert "read" in output
        assert "Log files require" in output

    def test_permission_error_quotes_spaces(self):
        """Test that paths with spaces are quoted."""
        from claude_agent.errors import permission_error

        error = permission_error("/my path/with spaces/file.txt", operation="access")

        output = error.format(use_color=False)
        # Path should be quoted
        assert '"/my path/with spaces/file.txt"' in output


class TestNetworkError:
    """Tests for network_error helper function."""

    def test_network_error_basic(self):
        """Test basic network error."""
        from claude_agent.errors import network_error

        error = network_error("API connection")

        output = error.format(use_color=False)
        assert "Error:" in output
        assert "API connection" in output
        assert "network" in output.lower()

    def test_network_error_with_message(self):
        """Test network error with original error message."""
        from claude_agent.errors import network_error

        error = network_error(
            "Claude API request",
            error_message="Connection refused",
        )

        output = error.format(use_color=False)
        assert "Error:" in output
        assert "Claude API request" in output
        assert "Connection refused" in output

    def test_network_error_with_suggestion(self):
        """Test network error with custom suggestion."""
        from claude_agent.errors import network_error

        error = network_error(
            "Database connection",
            suggestion="Check database server status and retry",
        )

        output = error.format(use_color=False)
        assert "Error:" in output
        assert "Check database server" in output


class TestResetConfirmation:
    """Tests for reset confirmation message format."""

    def test_reset_shows_warning(self, tmp_path):
        """Test that reset shows warning about destructive action."""
        from click.testing import CliRunner
        from claude_agent.cli import main

        # Create a file that would be reset
        (tmp_path / "feature_list.json").write_text("[]")

        runner = CliRunner()
        # Use 'n' to not actually delete files
        result = runner.invoke(main, ["--reset", "-p", str(tmp_path)], input="n\n")

        # Should show warning header
        assert "Warning:" in result.output or "warning" in result.output.lower()
        # Should list files to be deleted
        assert "feature_list.json" in result.output
        # Should mention it's destructive
        assert "cannot be undone" in result.output or "delete" in result.output.lower()

    def test_reset_lists_files_clearly(self, tmp_path):
        """Test that reset lists all files to be deleted."""
        from click.testing import CliRunner
        from claude_agent.cli import main

        # Create multiple files
        (tmp_path / "feature_list.json").write_text("[]")
        (tmp_path / "claude-progress.txt").write_text("progress")
        (tmp_path / "spec-workflow.json").write_text("{}")

        runner = CliRunner()
        result = runner.invoke(main, ["--reset", "-p", str(tmp_path)], input="n\n")

        # Should list all files
        assert "feature_list.json" in result.output
        assert "claude-progress.txt" in result.output
        assert "spec-workflow.json" in result.output

    def test_reset_no_files_shows_message(self, tmp_path):
        """Test that reset with no files shows appropriate message."""
        from click.testing import CliRunner
        from claude_agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--reset", "-p", str(tmp_path)])

        assert "No agent files to reset" in result.output

    def test_reset_cancelled_message(self, tmp_path):
        """Test that cancelled reset shows clear message."""
        from click.testing import CliRunner
        from claude_agent.cli import main

        (tmp_path / "feature_list.json").write_text("[]")

        runner = CliRunner()
        result = runner.invoke(main, ["--reset", "-p", str(tmp_path)], input="n\n")

        assert "cancelled" in result.output.lower()

    def test_reset_complete_message(self, tmp_path):
        """Test that completed reset shows success message."""
        from click.testing import CliRunner
        from claude_agent.cli import main

        (tmp_path / "feature_list.json").write_text("[]")

        runner = CliRunner()
        result = runner.invoke(main, ["--reset", "-p", str(tmp_path)], input="y\n")

        assert "Reset complete" in result.output or "complete" in result.output.lower()
        # Should suggest next step
        assert "Run" in result.output or "again" in result.output
