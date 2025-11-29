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

    def test_spec_create_from_file_reads_goal(self, runner, tmp_path):
        """
        Purpose: Verify spec create --from-file reads goal from file.
        Tests feature #35 (CLI: spec create accepts goal from --from-file).

        Note: We can't run the full session without mocking Claude, so we
        verify the file is read by checking it doesn't show the "no goal" error.
        Since the agent session would fail without Claude, we accept that.
        """
        goal_file = tmp_path / "goal.txt"
        goal_file.write_text("Build a task management application")

        # The command will fail because there's no Claude connection,
        # but it should NOT fail with "goal required" error
        result = runner.invoke(main, [
            "spec", "create",
            "--from-file", str(goal_file),
            "-p", str(tmp_path)
        ])

        # Should NOT show "goal or from-file required" error
        assert "--goal or --from-file required" not in result.output

    def test_spec_validate_defaults_to_draft(self, runner, tmp_path):
        """
        Purpose: Verify spec validate uses spec-draft.md by default.
        Tests feature #39 (CLI: spec validate defaults to spec-draft.md).

        Note: Without mocking Claude, we can only verify it finds and tries
        to use the draft file (not that it shows file not found error).
        """
        # Create a spec-draft.md
        (tmp_path / "spec-draft.md").write_text("# Test Spec\n\nSome content")

        # The command will fail because there's no Claude connection,
        # but it should NOT fail with "spec-draft.md not found" error
        result = runner.invoke(main, [
            "spec", "validate",
            "-p", str(tmp_path)
        ])

        # Should NOT show "not found" error since spec-draft.md exists
        assert "not found" not in result.output.lower()

    def test_spec_status_shows_file_existence(self, runner, tmp_path):
        """
        Purpose: Verify spec status shows which files exist.
        Tests feature at line 731.
        """
        # Create only spec-draft.md
        (tmp_path / "spec-draft.md").write_text("# Draft")

        result = runner.invoke(main, ["spec", "status", "-p", str(tmp_path)])
        assert result.exit_code == 0

        # Should show spec-draft.md is present
        assert "spec-draft.md" in result.output
        assert "present" in result.output.lower()

        # Should show spec-validated.md is missing
        assert "spec-validated.md" in result.output
        assert "missing" in result.output.lower()

    def test_spec_status_shows_workflow_history(self, runner, tmp_path):
        """
        Purpose: Verify spec status shows workflow history when available.
        Tests feature at line 743.
        """
        import json

        # Create spec-workflow.json with history
        workflow_state = {
            "phase": "created",
            "history": [
                {"step": "create", "timestamp": "2025-01-15T10:00:00Z", "status": "complete"}
            ]
        }
        (tmp_path / "spec-workflow.json").write_text(json.dumps(workflow_state))

        result = runner.invoke(main, ["spec", "status", "-p", str(tmp_path)])
        assert result.exit_code == 0

        # Should show history section
        assert "History:" in result.output or "history" in result.output.lower()
        assert "create" in result.output.lower()

    def test_auto_spec_requires_goal(self, runner, tmp_path):
        """
        Purpose: Verify --auto-spec flag requires --goal.
        Tests feature at line 777.
        """
        result = runner.invoke(main, ["--auto-spec", "-p", str(tmp_path)])
        assert result.exit_code != 0
        assert "goal" in result.output.lower()


class TestAutoSpecMainCommand:
    """Test --auto-spec flag on main command."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_auto_spec_runs_workflow_before_coding_agent(self, runner, tmp_path):
        """
        Purpose: Verify --auto-spec runs spec workflow then coding agent.
        Tests feature: CLI: --auto-spec runs spec workflow before coding agent
        """
        from unittest.mock import patch, AsyncMock

        workflow_called = []
        agent_called = []

        async def mock_workflow(config, goal):
            workflow_called.append(goal)
            # Create the expected files so the coding agent can proceed
            (config.project_dir / "feature_list.json").write_text("[]")
            return True

        async def mock_agent(config):
            agent_called.append(True)

        # Patch run_spec_workflow where it's defined (agent module - imported locally)
        # Patch run_autonomous_agent at cli module level (imported at top of cli.py)
        with patch("claude_agent.agent.run_spec_workflow", side_effect=mock_workflow):
            with patch("claude_agent.cli.run_autonomous_agent", side_effect=mock_agent):
                result = runner.invoke(main, [
                    "--auto-spec",
                    "-g", "Build a test app",
                    "-p", str(tmp_path)
                ])

        # Workflow should have been called
        assert len(workflow_called) == 1
        assert "Build a test app" in workflow_called[0]

        # Coding agent should have been called after workflow
        assert len(agent_called) == 1

    def test_auto_spec_exits_if_workflow_fails(self, runner, tmp_path):
        """
        Purpose: Verify --auto-spec exits early if spec workflow fails.
        Tests feature: CLI: --auto-spec exits if spec workflow fails
        """
        from unittest.mock import patch, AsyncMock

        agent_called = []

        async def mock_workflow(config, goal):
            return False  # Workflow fails

        async def mock_agent(config):
            agent_called.append(True)

        # Patch run_spec_workflow where it's defined (agent module - imported locally)
        # Patch run_autonomous_agent at cli module level (imported at top of cli.py)
        with patch("claude_agent.agent.run_spec_workflow", side_effect=mock_workflow):
            with patch("claude_agent.cli.run_autonomous_agent", side_effect=mock_agent):
                result = runner.invoke(main, [
                    "--auto-spec",
                    "-g", "Build a test app",
                    "-p", str(tmp_path)
                ])

        # Should exit with non-zero code
        assert result.exit_code != 0

        # Coding agent should NOT have been called
        assert len(agent_called) == 0

        # Should show error message
        assert "failed" in result.output.lower()


class TestSpecAutoExitCodes:
    """Test spec auto command exit codes with mocked agent sessions."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_spec_auto_exits_with_code_0_on_success(self, runner, tmp_path):
        """
        Purpose: Verify spec auto returns exit code 0 when workflow succeeds.
        Tests feature: CLI: spec auto exits with code 0 on success
        """
        from unittest.mock import patch, AsyncMock

        # Mock run_spec_workflow where it's imported from (agent module)
        with patch("claude_agent.agent.run_spec_workflow", new_callable=AsyncMock) as mock_workflow:
            mock_workflow.return_value = True

            result = runner.invoke(main, [
                "spec", "auto",
                "-g", "Build a todo app",
                "-p", str(tmp_path)
            ])

            assert result.exit_code == 0
            mock_workflow.assert_called_once()

    def test_spec_auto_exits_with_code_1_on_failure(self, runner, tmp_path):
        """
        Purpose: Verify spec auto returns exit code 1 when workflow fails.
        Tests feature: CLI: spec auto exits with code 1 on failure
        """
        from unittest.mock import patch, AsyncMock

        # Mock run_spec_workflow where it's imported from (agent module)
        with patch("claude_agent.agent.run_spec_workflow", new_callable=AsyncMock) as mock_workflow:
            mock_workflow.return_value = False

            result = runner.invoke(main, [
                "spec", "auto",
                "-g", "Build a todo app",
                "-p", str(tmp_path)
            ])

            assert result.exit_code == 1
            mock_workflow.assert_called_once()
