"""
CLI integration tests for spec workflow.

Purpose: Verify CLI commands work correctly end-to-end, including
argument parsing, error handling, and state file creation.
"""

import pytest
from click.testing import CliRunner

from claude_agent.cli import main


class TestSpecCLI:
    """Test spec subcommand CLI integration."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_spec_status_on_empty_project(self, runner, tmp_path):
        """
        Purpose: Verify status command works on empty project without error.
        """
        result = runner.invoke(main, ["spec", "status", "-p", str(tmp_path)])
        assert result.exit_code == 0
        assert "Phase: none" in result.output

    def test_spec_create_requires_goal(self, runner, tmp_path):
        """
        Purpose: Verify create command fails with clear error when no goal.
        """
        result = runner.invoke(main, ["spec", "create", "-p", str(tmp_path)])
        assert result.exit_code != 0
        assert "goal" in result.output.lower() or "required" in result.output.lower()

    def test_spec_validate_fails_without_spec(self, runner, tmp_path):
        """
        Purpose: Verify validate command fails clearly when no spec exists.
        """
        result = runner.invoke(main, ["spec", "validate", "-p", str(tmp_path)])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_spec_decompose_warns_on_draft(self, runner, tmp_path):
        """
        Purpose: Verify decompose warns when using unvalidated draft.
        """
        (tmp_path / "spec-draft.md").write_text("# Draft spec")
        result = runner.invoke(main, ["spec", "decompose", "-p", str(tmp_path)])
        # Should either warn about using draft or fail asking for validation
        assert "warning" in result.output.lower() or "validate" in result.output.lower()

    def test_spec_auto_requires_goal(self, runner, tmp_path):
        """
        Purpose: Verify spec auto fails with clear error when no goal.
        """
        result = runner.invoke(main, ["spec", "auto", "-p", str(tmp_path)])
        assert result.exit_code != 0
        # Click shows "Missing option" for required options
        assert "goal" in result.output.lower() or "required" in result.output.lower()

    def test_spec_help_shows_subcommands(self, runner):
        """
        Purpose: Verify spec --help shows all subcommands.
        """
        result = runner.invoke(main, ["spec", "--help"])
        assert result.exit_code == 0
        assert "create" in result.output
        assert "validate" in result.output
        assert "decompose" in result.output
        assert "auto" in result.output
        assert "status" in result.output
