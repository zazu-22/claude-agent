"""
Tests for Claude Code Hooks Module
==================================

Tests for hook generation, installation, and CLI commands.
"""

import json
import os
import stat
from pathlib import Path

import pytest
from click.testing import CliRunner

from claude_agent.hooks import (
    generate_hooks_config,
    generate_session_start_script,
    generate_session_stop_script,
    get_hooks_status,
    install_hooks,
    uninstall_hooks,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory."""
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    return project_dir


@pytest.fixture
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


# =============================================================================
# Test hooks.json Generation
# =============================================================================


class TestGenerateHooksConfig:
    """Tests for generate_hooks_config function."""

    def test_output_matches_expected_json_schema(self):
        """Test output matches expected JSON schema."""
        config = generate_hooks_config()

        assert "hooks" in config
        assert isinstance(config["hooks"], list)
        assert len(config["hooks"]) == 2

    def test_timeout_values_are_correct(self):
        """Test timeout values are correct."""
        config = generate_hooks_config()

        for hook in config["hooks"]:
            assert "timeout" in hook
            assert hook["timeout"] == 5000

    def test_custom_timeout_is_honored(self):
        """Test custom timeout is honored."""
        config = generate_hooks_config(timeout_ms=10000)

        for hook in config["hooks"]:
            assert hook["timeout"] == 10000

    def test_both_hooks_are_included(self):
        """Test both SessionStart and Stop hooks are included."""
        config = generate_hooks_config()

        events = [h["event"] for h in config["hooks"]]
        assert "SessionStart" in events
        assert "Stop" in events

    def test_script_paths_are_relative(self):
        """Test script paths are relative to project directory."""
        config = generate_hooks_config()

        for hook in config["hooks"]:
            assert "script" in hook
            assert hook["script"].startswith(".claude/hooks/")


# =============================================================================
# Test session-start.sh Script Content
# =============================================================================


class TestGenerateSessionStartScript:
    """Tests for generate_session_start_script function."""

    def test_script_is_posix_sh_compatible(self):
        """Test script uses POSIX sh shebang."""
        script = generate_session_start_script()

        # Check shebang is POSIX sh
        assert script.startswith("#!/bin/sh")

    def test_script_handles_missing_state_file(self):
        """Test script handles missing state file gracefully."""
        script = generate_session_start_script()

        # Script should check for file existence
        assert "if [ ! -f" in script or "if [ -f" in script

        # Script should output {} for missing file
        assert '{}' in script

    def test_output_format_matches_expected_json(self):
        """Test output format includes additionalContext key."""
        script = generate_session_start_script()

        # Script should produce JSON with additionalContext
        assert "additionalContext" in script

    def test_script_always_exits_zero(self):
        """Test script always exits with code 0."""
        script = generate_session_start_script()

        # Script should exit 0
        assert "exit 0" in script


# =============================================================================
# Test session-stop.sh Script Content
# =============================================================================


class TestGenerateSessionStopScript:
    """Tests for generate_session_stop_script function."""

    def test_script_is_posix_sh_compatible(self):
        """Test script uses POSIX sh shebang."""
        script = generate_session_stop_script()

        # Check shebang is POSIX sh
        assert script.startswith("#!/bin/sh")

    def test_script_handles_missing_state_file(self):
        """Test script handles missing state file gracefully."""
        script = generate_session_stop_script()

        # Script should check for file existence
        assert "if [ -f" in script

    def test_output_is_empty_json_object(self):
        """Test output is always empty JSON object."""
        script = generate_session_stop_script()

        # Script should output {}
        assert "printf '{}'" in script

    def test_script_always_exits_zero(self):
        """Test script always exits with code 0."""
        script = generate_session_stop_script()

        # Script should exit 0
        assert "exit 0" in script

    def test_logs_to_hooks_log(self):
        """Test script logs to hooks.log."""
        script = generate_session_stop_script()

        # Script should write to hooks.log
        assert "hooks.log" in script


# =============================================================================
# Test hooks install CLI Command
# =============================================================================


class TestHooksInstallCli:
    """Tests for hooks install CLI command."""

    def test_creates_claude_hooks_directory(self, tmp_project, runner):
        """Test creates .claude/hooks/ directory."""
        from claude_agent.cli import main

        result = runner.invoke(main, ["hooks", "install", str(tmp_project)])

        assert result.exit_code == 0
        assert (tmp_project / ".claude" / "hooks").exists()

    def test_writes_all_required_files(self, tmp_project, runner):
        """Test writes all required files."""
        from claude_agent.cli import main

        result = runner.invoke(main, ["hooks", "install", str(tmp_project)])

        assert result.exit_code == 0

        hooks_dir = tmp_project / ".claude" / "hooks"
        assert (hooks_dir / "hooks.json").exists()
        assert (hooks_dir / "session-start.sh").exists()
        assert (hooks_dir / "session-stop.sh").exists()

    def test_sets_correct_permissions(self, tmp_project, runner):
        """Test sets correct permissions on scripts."""
        from claude_agent.cli import main

        result = runner.invoke(main, ["hooks", "install", str(tmp_project)])

        assert result.exit_code == 0

        hooks_dir = tmp_project / ".claude" / "hooks"

        # Check scripts are executable
        start_script = hooks_dir / "session-start.sh"
        stop_script = hooks_dir / "session-stop.sh"

        assert os.access(start_script, os.X_OK)
        assert os.access(stop_script, os.X_OK)

    def test_handles_existing_installation(self, tmp_project, runner):
        """Test handles existing installation (overwrites)."""
        from claude_agent.cli import main

        # Install twice
        runner.invoke(main, ["hooks", "install", str(tmp_project)])
        result = runner.invoke(main, ["hooks", "install", str(tmp_project)])

        assert result.exit_code == 0
        assert "Hooks installed" in result.output

    def test_supports_current_directory_default(self, tmp_path, runner):
        """Test supports current directory as default."""
        from claude_agent.cli import main

        # Use isolated filesystem in tmp_path
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, ["hooks", "install"])

            assert result.exit_code == 0
            assert Path(".claude/hooks").exists()

    def test_outputs_success_message(self, tmp_project, runner):
        """Test outputs success message."""
        from claude_agent.cli import main

        result = runner.invoke(main, ["hooks", "install", str(tmp_project)])

        assert result.exit_code == 0
        assert "Hooks installed" in result.output or "✓" in result.output


# =============================================================================
# Test hooks uninstall CLI Command
# =============================================================================


class TestHooksUninstallCli:
    """Tests for hooks uninstall CLI command."""

    def test_removes_hooks_directory(self, tmp_project, runner):
        """Test removes hooks directory."""
        from claude_agent.cli import main

        # Install first
        runner.invoke(main, ["hooks", "install", str(tmp_project)])

        # Then uninstall
        result = runner.invoke(main, ["hooks", "uninstall", str(tmp_project)])

        assert result.exit_code == 0
        assert not (tmp_project / ".claude" / "hooks").exists()

    def test_handles_missing_directory_gracefully(self, tmp_project, runner):
        """Test handles missing directory gracefully."""
        from claude_agent.cli import main

        # Uninstall when never installed
        result = runner.invoke(main, ["hooks", "uninstall", str(tmp_project)])

        # Should succeed (idempotent)
        assert result.exit_code == 0
        assert "not installed" in result.output.lower() or "nothing to remove" in result.output.lower()

    def test_verifies_complete_removal(self, tmp_project, runner):
        """Test verifies complete removal."""
        from claude_agent.cli import main

        # Install
        runner.invoke(main, ["hooks", "install", str(tmp_project)])

        # Uninstall
        runner.invoke(main, ["hooks", "uninstall", str(tmp_project)])

        # Verify complete removal
        hooks_dir = tmp_project / ".claude" / "hooks"
        assert not hooks_dir.exists()


# =============================================================================
# Test hooks status CLI Command
# =============================================================================


class TestHooksStatusCli:
    """Tests for hooks status CLI command."""

    def test_shows_installed_status_when_hooks_exist(self, tmp_project, runner):
        """Test shows installed status when hooks exist."""
        from claude_agent.cli import main

        # Install first
        runner.invoke(main, ["hooks", "install", str(tmp_project)])

        # Check status
        result = runner.invoke(main, ["hooks", "status", str(tmp_project)])

        assert result.exit_code == 0
        assert "installed" in result.output.lower()

    def test_shows_not_installed_when_missing(self, tmp_project, runner):
        """Test shows not installed when missing."""
        from claude_agent.cli import main

        result = runner.invoke(main, ["hooks", "status", str(tmp_project)])

        assert result.exit_code == 0
        assert "not installed" in result.output.lower()

    def test_lists_all_hook_files(self, tmp_project, runner):
        """Test lists all hook files."""
        from claude_agent.cli import main

        # Install first
        runner.invoke(main, ["hooks", "install", str(tmp_project)])

        # Check status
        result = runner.invoke(main, ["hooks", "status", str(tmp_project)])

        assert result.exit_code == 0
        assert "hooks.json" in result.output
        assert "session-start.sh" in result.output
        assert "session-stop.sh" in result.output

    def test_json_output_format(self, tmp_project, runner):
        """Test JSON output format."""
        from claude_agent.cli import main

        # Install first
        runner.invoke(main, ["hooks", "install", str(tmp_project)])

        # Check status with JSON output
        result = runner.invoke(main, ["hooks", "status", str(tmp_project), "--json"])

        assert result.exit_code == 0

        # Should be valid JSON
        status = json.loads(result.output)
        assert "installed" in status
        assert "files" in status
        assert status["installed"] is True


# =============================================================================
# Test Integration: Hook Installation and Execution Flow
# =============================================================================


class TestHooksIntegration:
    """Integration tests for hook installation and execution flow."""

    def test_install_hooks_to_test_project(self, tmp_project):
        """Test installing hooks to a test project."""
        success, message = install_hooks(str(tmp_project))

        assert success
        assert (tmp_project / ".claude" / "hooks" / "hooks.json").exists()
        assert (tmp_project / ".claude" / "hooks" / "session-start.sh").exists()
        assert (tmp_project / ".claude" / "hooks" / "session-stop.sh").exists()

    def test_hooks_json_is_valid(self, tmp_project):
        """Test hooks.json is valid JSON matching schema."""
        install_hooks(str(tmp_project))

        hooks_json_path = tmp_project / ".claude" / "hooks" / "hooks.json"
        with open(hooks_json_path) as f:
            config = json.load(f)

        assert "hooks" in config
        assert len(config["hooks"]) == 2

        for hook in config["hooks"]:
            assert "event" in hook
            assert "script" in hook
            assert "timeout" in hook
            assert hook["event"] in ["SessionStart", "Stop"]

    def test_scripts_are_executable(self, tmp_project):
        """Test scripts have executable permission."""
        install_hooks(str(tmp_project))

        start_script = tmp_project / ".claude" / "hooks" / "session-start.sh"
        stop_script = tmp_project / ".claude" / "hooks" / "session-stop.sh"

        # Check executable permission
        assert os.access(start_script, os.X_OK)
        assert os.access(stop_script, os.X_OK)

        # Check specific mode (0o755)
        start_mode = start_script.stat().st_mode
        stop_mode = stop_script.stat().st_mode

        # Check owner execute bit
        assert start_mode & stat.S_IXUSR
        assert stop_mode & stat.S_IXUSR

    def test_uninstall_removes_all_files(self, tmp_project):
        """Test uninstall removes all files."""
        install_hooks(str(tmp_project))
        success, message = uninstall_hooks(str(tmp_project))

        assert success
        assert not (tmp_project / ".claude" / "hooks").exists()

    def test_status_reports_correctly(self, tmp_project):
        """Test status reports correctly for installed and uninstalled states."""
        # Not installed
        status = get_hooks_status(str(tmp_project))
        assert not status["installed"]
        assert len(status["files"]) == 0

        # Installed
        install_hooks(str(tmp_project))
        status = get_hooks_status(str(tmp_project))
        assert status["installed"]
        assert len(status["files"]) == 3

        # Uninstalled
        uninstall_hooks(str(tmp_project))
        status = get_hooks_status(str(tmp_project))
        assert not status["installed"]


# =============================================================================
# Test Edge Cases
# =============================================================================


class TestHooksEdgeCases:
    """Tests for edge cases and error handling."""

    def test_install_to_nonexistent_directory(self, tmp_path):
        """Test install to non-existent directory fails gracefully."""
        nonexistent = tmp_path / "does-not-exist"

        success, message = install_hooks(str(nonexistent))

        assert not success
        assert "not found" in message.lower() or "error" in message.lower()

    def test_uninstall_from_nonexistent_directory(self, tmp_path):
        """Test uninstall from non-existent directory fails gracefully."""
        nonexistent = tmp_path / "does-not-exist"

        success, message = uninstall_hooks(str(nonexistent))

        assert not success
        assert "not found" in message.lower()

    def test_status_for_nonexistent_directory(self, tmp_path):
        """Test status for non-existent directory reports errors."""
        nonexistent = tmp_path / "does-not-exist"

        status = get_hooks_status(str(nonexistent))

        assert not status["installed"]
        assert len(status["errors"]) > 0

    def test_install_with_relative_path(self, tmp_project, runner):
        """Test install with relative path works."""
        from claude_agent.cli import main

        # Use relative path from parent
        with runner.isolated_filesystem(temp_dir=tmp_project.parent):
            result = runner.invoke(main, ["hooks", "install", tmp_project.name])

            assert result.exit_code == 0

    def test_status_detects_missing_script_file(self, tmp_project):
        """Test status detects missing script file."""
        install_hooks(str(tmp_project))

        # Remove one script
        (tmp_project / ".claude" / "hooks" / "session-start.sh").unlink()

        status = get_hooks_status(str(tmp_project))

        assert status["installed"]  # Directory still exists
        assert len(status["errors"]) > 0
        assert any("session-start.sh" in e.lower() for e in status["errors"])

    def test_status_detects_non_executable_script(self, tmp_project):
        """Test status detects non-executable script."""
        install_hooks(str(tmp_project))

        # Remove execute permission
        start_script = tmp_project / ".claude" / "hooks" / "session-start.sh"
        os.chmod(start_script, stat.S_IRUSR | stat.S_IWUSR)  # rw- only

        status = get_hooks_status(str(tmp_project))

        assert status["installed"]
        assert any("not executable" in e.lower() for e in status["errors"])


# =============================================================================
# Test Hook Execution with Error Handling
# =============================================================================


class TestExecuteHookSafely:
    """Tests for execute_hook_safely function - Feature #126."""

    def test_returns_false_for_nonexistent_script(self, tmp_path):
        """Test returns failure for non-existent script."""
        from claude_agent.hooks import execute_hook_safely

        script_path = tmp_path / "does-not-exist.sh"
        success, output, error = execute_hook_safely(script_path)

        assert success is False
        assert output == "{}"
        assert error is not None
        assert "not found" in error.lower()

    def test_returns_false_for_non_executable_script(self, tmp_path):
        """Test returns failure for non-executable script."""
        from claude_agent.hooks import execute_hook_safely

        # Create script without execute permission
        script_path = tmp_path / "test-hook.sh"
        script_path.write_text('#!/bin/sh\necho "{}"')

        success, output, error = execute_hook_safely(script_path)

        assert success is False
        assert output == "{}"
        assert error is not None
        assert "not executable" in error.lower()

    def test_executes_valid_script_successfully(self, tmp_path):
        """Test successfully executes valid script."""
        from claude_agent.hooks import execute_hook_safely

        # Create valid executable script
        script_path = tmp_path / "test-hook.sh"
        script_path.write_text('#!/bin/sh\necho \'{"test": "value"}\'')
        os.chmod(script_path, stat.S_IRWXU)

        success, output, error = execute_hook_safely(script_path)

        assert success is True
        assert error is None
        assert json.loads(output) == {"test": "value"}

    def test_returns_empty_json_on_timeout(self, tmp_path):
        """Test returns empty JSON on timeout."""
        from claude_agent.hooks import execute_hook_safely

        # Create script that sleeps too long
        script_path = tmp_path / "slow-hook.sh"
        script_path.write_text('#!/bin/sh\nsleep 10\necho "{}"')
        os.chmod(script_path, stat.S_IRWXU)

        # Use very short timeout (100ms)
        success, output, error = execute_hook_safely(script_path, timeout_ms=100)

        assert success is False
        assert output == "{}"
        assert error is not None
        assert "timeout" in error.lower()

    def test_returns_empty_json_on_invalid_output(self, tmp_path):
        """Test returns empty JSON when script outputs invalid JSON."""
        from claude_agent.hooks import execute_hook_safely

        # Create script that outputs invalid JSON
        script_path = tmp_path / "bad-json-hook.sh"
        script_path.write_text('#!/bin/sh\necho "not valid json"')
        os.chmod(script_path, stat.S_IRWXU)

        success, output, error = execute_hook_safely(script_path)

        # Success because script executed, but output normalized to {}
        assert success is True
        assert output == "{}"
        assert error is None

    def test_handles_script_with_nonzero_exit(self, tmp_path):
        """Test handles script with non-zero exit code gracefully."""
        from claude_agent.hooks import execute_hook_safely

        # Create script that outputs JSON but exits with error
        script_path = tmp_path / "error-hook.sh"
        script_path.write_text('#!/bin/sh\necho "{}"\nexit 1')
        os.chmod(script_path, stat.S_IRWXU)

        success, output, error = execute_hook_safely(script_path)

        # Still returns success=True because we got valid output
        assert success is True
        assert output == "{}"
        assert error is None

    def test_uses_custom_working_directory(self, tmp_path):
        """Test uses custom working directory."""
        from claude_agent.hooks import execute_hook_safely

        # Create a script that prints the current directory
        script_path = tmp_path / "pwd-hook.sh"
        script_path.write_text('#!/bin/sh\necho "{\\"cwd\\": \\"$(pwd)\\"}"')
        os.chmod(script_path, stat.S_IRWXU)

        # Create a different working directory
        work_dir = tmp_path / "work"
        work_dir.mkdir()

        success, output, error = execute_hook_safely(script_path, cwd=work_dir)

        assert success is True
        data = json.loads(output)
        assert str(work_dir) in data["cwd"]

    def test_doesnt_crash_on_any_exception(self, tmp_path, monkeypatch):
        """Test never crashes on unexpected exceptions."""
        from claude_agent.hooks import execute_hook_safely

        # Create valid script
        script_path = tmp_path / "test-hook.sh"
        script_path.write_text('#!/bin/sh\necho "{}"')
        os.chmod(script_path, stat.S_IRWXU)

        # Mock subprocess.run to raise an unexpected exception
        def raise_error(*args, **kwargs):
            raise RuntimeError("Unexpected error!")

        import subprocess
        monkeypatch.setattr(subprocess, "run", raise_error)

        # Should not raise, should return gracefully
        success, output, error = execute_hook_safely(script_path)

        assert success is False
        assert output == "{}"
        assert error is not None
        assert "Unexpected error" in error


class TestExecuteSessionStartHook:
    """Tests for execute_session_start_hook convenience function."""

    def test_returns_empty_dict_when_not_installed(self, tmp_project):
        """Test returns empty dict when hooks not installed."""
        from claude_agent.hooks import execute_session_start_hook

        result = execute_session_start_hook(str(tmp_project))

        assert result == {}

    def test_returns_empty_dict_on_script_error(self, tmp_project):
        """Test returns empty dict on script error."""
        from claude_agent.hooks import execute_session_start_hook

        # Install hooks then break the script
        install_hooks(str(tmp_project))
        script_path = tmp_project / ".claude" / "hooks" / "session-start.sh"
        script_path.write_text("#!/bin/sh\nexit 1")

        result = execute_session_start_hook(str(tmp_project))

        # Should return empty dict, not crash
        assert isinstance(result, dict)


class TestExecuteSessionStopHook:
    """Tests for execute_session_stop_hook convenience function."""

    def test_returns_false_when_not_installed(self, tmp_project):
        """Test returns False when hooks not installed."""
        from claude_agent.hooks import execute_session_stop_hook

        result = execute_session_stop_hook(str(tmp_project))

        assert result is False

    def test_returns_true_on_successful_execution(self, tmp_project):
        """Test returns True on successful execution."""
        from claude_agent.hooks import execute_session_stop_hook

        install_hooks(str(tmp_project))

        result = execute_session_stop_hook(str(tmp_project))

        # May fail if python3 not available, but shouldn't crash
        assert isinstance(result, bool)


class TestHookExecutionError:
    """Tests for HookExecutionError exception class."""

    def test_exception_has_hook_name(self):
        """Test exception includes hook name."""
        from claude_agent.hooks import HookExecutionError

        error = HookExecutionError("test-hook.sh", "Something failed")

        assert error.hook_name == "test-hook.sh"
        assert "test-hook.sh" in str(error)

    def test_exception_has_message(self):
        """Test exception includes message."""
        from claude_agent.hooks import HookExecutionError

        error = HookExecutionError("test-hook.sh", "Something failed")

        assert error.message == "Something failed"
        assert "Something failed" in str(error)

    def test_exception_preserves_original_error(self):
        """Test exception preserves original error."""
        from claude_agent.hooks import HookExecutionError

        original = ValueError("Original error")
        error = HookExecutionError("test-hook.sh", "Wrapper message", original)

        assert error.original_error is original
