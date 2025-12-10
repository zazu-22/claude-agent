"""
Tests for the doctor module
===========================

Unit tests for health check functionality.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from claude_agent.cli import main
from claude_agent.doctor import (
    CheckResult,
    CheckStatus,
    DoctorReport,
    FixResult,
    check_claude_cli,
    check_config,
    check_git,
    check_project_dir,
    check_puppeteer,
    check_stack_tools,
    format_report,
    format_report_json,
    run_doctor_checks,
)


# =============================================================================
# CheckStatus Enum Tests
# =============================================================================


class TestCheckStatus:
    """Test CheckStatus enum values."""

    def test_pass_value(self):
        """Test PASS status has correct value."""
        assert CheckStatus.PASS.value == "pass"

    def test_fail_value(self):
        """Test FAIL status has correct value."""
        assert CheckStatus.FAIL.value == "fail"

    def test_warn_value(self):
        """Test WARN status has correct value."""
        assert CheckStatus.WARN.value == "warn"

    def test_skip_value(self):
        """Test SKIP status has correct value."""
        assert CheckStatus.SKIP.value == "skip"


# =============================================================================
# CheckResult Dataclass Tests
# =============================================================================


class TestCheckResult:
    """Test CheckResult dataclass."""

    def test_required_fields_only(self):
        """Test creating CheckResult with only required fields."""
        result = CheckResult(
            name="Test Check",
            category="tools",
            status=CheckStatus.PASS,
            message="Test passed",
        )
        assert result.name == "Test Check"
        assert result.category == "tools"
        assert result.status == CheckStatus.PASS
        assert result.message == "Test passed"
        assert result.fix_command is None
        assert result.version is None
        assert result.details is None

    def test_all_fields(self):
        """Test creating CheckResult with all fields."""
        result = CheckResult(
            name="Test Check",
            category="tools",
            status=CheckStatus.FAIL,
            message="Test failed",
            fix_command="fix-command",
            version="1.2.3",
            details="Detailed info",
        )
        assert result.fix_command == "fix-command"
        assert result.version == "1.2.3"
        assert result.details == "Detailed info"


# =============================================================================
# DoctorReport Dataclass Tests
# =============================================================================


class TestDoctorReport:
    """Test DoctorReport dataclass and computed properties."""

    def test_error_count(self):
        """Test error_count property."""
        report = DoctorReport(
            checks=[
                CheckResult("A", "cat", CheckStatus.PASS, "ok"),
                CheckResult("B", "cat", CheckStatus.FAIL, "bad"),
                CheckResult("C", "cat", CheckStatus.FAIL, "bad"),
                CheckResult("D", "cat", CheckStatus.WARN, "warn"),
            ]
        )
        assert report.error_count == 2

    def test_warning_count(self):
        """Test warning_count property."""
        report = DoctorReport(
            checks=[
                CheckResult("A", "cat", CheckStatus.PASS, "ok"),
                CheckResult("B", "cat", CheckStatus.WARN, "warn1"),
                CheckResult("C", "cat", CheckStatus.WARN, "warn2"),
                CheckResult("D", "cat", CheckStatus.SKIP, "skip"),
            ]
        )
        assert report.warning_count == 2

    def test_pass_count(self):
        """Test pass_count property."""
        report = DoctorReport(
            checks=[
                CheckResult("A", "cat", CheckStatus.PASS, "ok"),
                CheckResult("B", "cat", CheckStatus.PASS, "ok"),
                CheckResult("C", "cat", CheckStatus.FAIL, "bad"),
            ]
        )
        assert report.pass_count == 2

    def test_is_healthy_true(self):
        """Test is_healthy returns True when no errors."""
        report = DoctorReport(
            checks=[
                CheckResult("A", "cat", CheckStatus.PASS, "ok"),
                CheckResult("B", "cat", CheckStatus.WARN, "warn"),
            ]
        )
        assert report.is_healthy is True

    def test_is_healthy_false(self):
        """Test is_healthy returns False when errors present."""
        report = DoctorReport(
            checks=[
                CheckResult("A", "cat", CheckStatus.PASS, "ok"),
                CheckResult("B", "cat", CheckStatus.FAIL, "bad"),
            ]
        )
        assert report.is_healthy is False


# =============================================================================
# Individual Check Function Tests
# =============================================================================


class TestCheckClaudeCli:
    """Test check_claude_cli function."""

    @patch("claude_agent.doctor.shutil.which")
    @patch("claude_agent.doctor.subprocess.run")
    def test_success(self, mock_run, mock_which):
        """Test successful Claude CLI check."""
        mock_which.return_value = "/usr/local/bin/claude"
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="1.2.3 (Claude Code)",
            stderr="",
        )

        result = check_claude_cli()

        assert result.status == CheckStatus.PASS
        assert result.version == "1.2.3"
        assert "installed" in result.message.lower()

    @patch("claude_agent.doctor.shutil.which")
    def test_not_found(self, mock_which):
        """Test Claude CLI not in PATH."""
        mock_which.return_value = None

        result = check_claude_cli()

        assert result.status == CheckStatus.FAIL
        assert "not installed" in result.message.lower()
        assert result.fix_command is not None
        assert "claude.ai/code" in result.fix_command

    @patch("claude_agent.doctor.shutil.which")
    @patch("claude_agent.doctor.subprocess.run")
    def test_timeout(self, mock_run, mock_which):
        """Test Claude CLI timeout."""
        mock_which.return_value = "/usr/local/bin/claude"
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["claude"], timeout=3)

        result = check_claude_cli()

        assert result.status == CheckStatus.FAIL
        assert "timeout" in result.message.lower()


class TestCheckGit:
    """Test check_git function."""

    @patch("claude_agent.doctor.shutil.which")
    @patch("claude_agent.doctor.subprocess.run")
    def test_success(self, mock_run, mock_which):
        """Test successful git check."""
        mock_which.return_value = "/usr/bin/git"
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="git version 2.39.0",
            stderr="",
        )

        result = check_git()

        assert result.status == CheckStatus.PASS
        assert result.version == "2.39.0"

    @patch("claude_agent.doctor.shutil.which")
    def test_not_found(self, mock_which):
        """Test git not in PATH."""
        mock_which.return_value = None

        result = check_git()

        assert result.status == CheckStatus.FAIL
        assert "not installed" in result.message.lower()


class TestCheckStackTools:
    """Test check_stack_tools function."""

    @patch("claude_agent.doctor.shutil.which")
    @patch("claude_agent.doctor.subprocess.run")
    def test_node_stack_success(self, mock_run, mock_which):
        """Test successful Node.js stack check."""
        mock_which.return_value = "/usr/local/bin/node"
        mock_run.return_value = MagicMock(returncode=0, stdout="v20.10.0", stderr="")

        results = check_stack_tools("node")

        assert len(results) >= 2
        node_result = next(r for r in results if r.name == "Node.js")
        assert node_result.status == CheckStatus.PASS

    @patch("claude_agent.doctor.shutil.which")
    @patch("claude_agent.doctor.subprocess.run")
    def test_python_stack_success(self, mock_run, mock_which):
        """Test successful Python stack check."""
        mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}" if cmd in ("python3", "uv") else None
        mock_run.return_value = MagicMock(returncode=0, stdout="Python 3.12.0", stderr="")

        results = check_stack_tools("python")

        assert len(results) >= 2
        python_result = next(r for r in results if r.name == "Python")
        assert python_result.status == CheckStatus.PASS


class TestCheckPuppeteer:
    """Test check_puppeteer function."""

    @patch("claude_agent.doctor.subprocess.run")
    def test_success(self, mock_run):
        """Test puppeteer-mcp-server found."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="puppeteer-mcp-server@1.0.0",
            stderr="",
        )

        result = check_puppeteer(npm_available=True)

        assert result.status == CheckStatus.PASS

    @patch("claude_agent.doctor.subprocess.run")
    def test_not_found(self, mock_run):
        """Test puppeteer-mcp-server not found."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="",
        )

        result = check_puppeteer(npm_available=True)

        assert result.status == CheckStatus.FAIL
        assert result.fix_command == "npm install -g puppeteer-mcp-server"

    def test_skip_when_npm_unavailable(self):
        """Test check is skipped when npm is not available."""
        result = check_puppeteer(npm_available=False)

        assert result.status == CheckStatus.SKIP
        assert "requires npm" in result.message.lower()


class TestCheckProjectDir:
    """Test check_project_dir function."""

    def test_existing_writable_dir(self, tmp_path):
        """Test with existing writable directory."""
        result = check_project_dir(tmp_path)

        assert result.status == CheckStatus.PASS
        assert "writable" in result.message.lower()

    def test_non_existent_dir(self, tmp_path):
        """Test with non-existent directory."""
        non_existent = tmp_path / "does_not_exist"

        result = check_project_dir(non_existent)

        assert result.status == CheckStatus.FAIL
        assert "does not exist" in result.message.lower()
        assert "mkdir" in result.fix_command


class TestCheckConfig:
    """Test check_config function."""

    def test_valid_config(self, tmp_path):
        """Test with valid config file."""
        config_file = tmp_path / ".claude-agent.yaml"
        config_file.write_text("features: 50\nstack: python\n")

        results = check_config(tmp_path)

        assert len(results) == 1
        assert results[0].status == CheckStatus.PASS

    def test_invalid_yaml(self, tmp_path):
        """Test with invalid YAML syntax."""
        config_file = tmp_path / ".claude-agent.yaml"
        config_file.write_text("features: [unclosed bracket\n")

        results = check_config(tmp_path)

        assert len(results) == 1
        assert results[0].status == CheckStatus.FAIL
        assert "syntax error" in results[0].message.lower()

    def test_unknown_keys_warning(self, tmp_path):
        """Test warning for unknown configuration keys."""
        config_file = tmp_path / ".claude-agent.yaml"
        config_file.write_text("features: 50\nunknown_key: value\n")

        results = check_config(tmp_path)

        # Should have a warning for unknown key
        warn_results = [r for r in results if r.status == CheckStatus.WARN]
        assert len(warn_results) == 1
        assert "unknown_key" in warn_results[0].message

    def test_no_config_file(self, tmp_path):
        """Test when no config file exists."""
        results = check_config(tmp_path)

        assert len(results) == 1
        assert results[0].status == CheckStatus.PASS
        assert "not found" in results[0].message.lower()


# =============================================================================
# Orchestration Tests
# =============================================================================


class TestRunDoctorChecks:
    """Test run_doctor_checks orchestration."""

    @patch("claude_agent.doctor.check_claude_cli")
    @patch("claude_agent.doctor.check_git")
    @patch("claude_agent.doctor.check_stack_tools")
    @patch("claude_agent.doctor.check_puppeteer")
    @patch("claude_agent.doctor.check_project_dir")
    @patch("claude_agent.doctor.check_config")
    def test_aggregates_all_checks(
        self,
        mock_config,
        mock_project,
        mock_puppeteer,
        mock_stack,
        mock_git,
        mock_claude,
        tmp_path,
    ):
        """Test that run_doctor_checks aggregates all check results."""
        mock_claude.return_value = CheckResult("Claude", "auth", CheckStatus.PASS, "ok")
        mock_git.return_value = CheckResult("Git", "tools", CheckStatus.PASS, "ok")
        mock_stack.return_value = [CheckResult("Python", "tools", CheckStatus.PASS, "ok")]
        mock_puppeteer.return_value = CheckResult("Puppeteer", "tools", CheckStatus.PASS, "ok")
        mock_project.return_value = CheckResult("Project", "project", CheckStatus.PASS, "ok")
        mock_config.return_value = [CheckResult("Config", "project", CheckStatus.PASS, "ok")]

        report = run_doctor_checks(tmp_path, stack="python")

        assert len(report.checks) == 6
        assert report.project_dir == str(tmp_path)
        assert report.stack == "python"


# =============================================================================
# Output Formatting Tests
# =============================================================================


class TestFormatReportJson:
    """Test JSON output formatting."""

    def test_valid_json_structure(self):
        """Test that JSON output has expected structure."""
        report = DoctorReport(
            checks=[
                CheckResult("Test", "tools", CheckStatus.PASS, "ok", version="1.0"),
            ],
            project_dir="/test/path",
            stack="python",
        )

        output = format_report_json(report)

        assert output["project_dir"] == "/test/path"
        assert output["stack"] == "python"
        assert output["is_healthy"] is True
        assert output["summary"]["errors"] == 0
        assert output["summary"]["passed"] == 1
        assert len(output["checks"]) == 1
        assert output["checks"][0]["status"] == "pass"

    def test_omits_none_values(self):
        """Test that None values are omitted from check results."""
        report = DoctorReport(
            checks=[
                CheckResult("Test", "tools", CheckStatus.PASS, "ok"),
            ]
        )

        output = format_report_json(report)

        # version and fix_command should not be present
        assert "version" not in output["checks"][0]
        assert "fix_command" not in output["checks"][0]


# =============================================================================
# CLI Integration Tests
# =============================================================================


class TestDoctorCommand:
    """Test doctor CLI command."""

    def test_command_recognized(self):
        """Test that doctor command is recognized."""
        runner = CliRunner()
        result = runner.invoke(main, ["doctor", "--help"])

        assert result.exit_code == 0
        assert "Check environment health" in result.output

    def test_json_output_is_valid(self):
        """Test that --json flag produces valid JSON."""
        runner = CliRunner()
        # Use isolated filesystem to avoid real config
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["doctor", "--json"])

            # Should be parseable JSON regardless of exit code
            try:
                data = json.loads(result.output)
                assert "is_healthy" in data
                assert "checks" in data
            except json.JSONDecodeError:
                pytest.fail(f"Output was not valid JSON: {result.output}")

    def test_exit_code_healthy(self):
        """Test exit code 0 when all checks pass."""
        # This test will depend on the actual environment
        # We test the behavior, not mock everything
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".claude-agent.yaml").write_text("features: 50\n")
            result = runner.invoke(main, ["doctor", "--json"])
            data = json.loads(result.output)

            # If all checks pass, exit code should be 0
            if data["is_healthy"]:
                assert result.exit_code == 0
            else:
                assert result.exit_code == 1


# =============================================================================
# Fix Attempt Tests
# =============================================================================


class TestAttemptFixes:
    """Test attempt_fixes function."""

    def test_creates_missing_directory(self, tmp_path):
        """Test that attempt_fixes creates missing project directory."""
        from claude_agent.doctor import attempt_fixes, DoctorReport, CheckResult, CheckStatus

        # Create a report with a failed project directory check
        non_existent = tmp_path / "new_project"
        report = DoctorReport(
            checks=[
                CheckResult(
                    name="Project Directory",
                    category="project",
                    status=CheckStatus.FAIL,
                    message=f"Directory does not exist: {non_existent}",
                    fix_command=f"mkdir -p {non_existent}",
                )
            ],
            project_dir=str(non_existent),
        )

        # Attempt fixes
        results = attempt_fixes(report, non_existent)

        # Verify directory was created
        assert non_existent.exists()
        assert non_existent.is_dir()

        # Verify fix result
        dir_fix = next(r for r in results if r.name == "Project Directory")
        assert dir_fix.success is True
        assert dir_fix.fix_type == "fixed"
