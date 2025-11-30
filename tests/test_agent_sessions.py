"""
Tests for agent session runners (spec workflow).

Purpose: Verify that spec workflow session runners correctly:
- Call the Claude client
- Create expected output files
- Record steps in spec-workflow.json
- Handle success and failure cases

These tests mock the Claude client to test the orchestration logic
without making actual API calls.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class MockClient:
    """Mock Claude SDK client for testing."""

    def __init__(self, should_succeed=True, create_files=None):
        """
        Args:
            should_succeed: If True, session completes normally
            create_files: Dict of {filename: content} to create during session
        """
        self.should_succeed = should_succeed
        self.create_files = create_files or {}
        self.project_dir = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def query(self, message):
        pass

    async def receive_response(self):
        """Simulate receiving response from Claude."""
        # Create any files that the agent would create
        if self.project_dir and self.create_files:
            for filename, content in self.create_files.items():
                (self.project_dir / filename).write_text(content)

        # Yield a simple text response
        mock_msg = MagicMock()
        mock_msg.__class__.__name__ = "AssistantMessage"
        mock_block = MagicMock()
        mock_block.__class__.__name__ = "TextBlock"
        mock_block.text = "Session completed."
        mock_msg.content = [mock_block]
        yield mock_msg

        # Yield end message
        end_msg = MagicMock()
        end_msg.__class__.__name__ = "ResultMessage"
        end_msg.num_turns = 5
        end_msg.is_error = not self.should_succeed
        end_msg.subtype = "done" if self.should_succeed else "error"
        end_msg.result = "Done"
        yield end_msg


@pytest.fixture
def mock_create_client():
    """Fixture that patches create_client and returns the mock factory."""
    with patch("claude_agent.agent.create_client") as mock:
        yield mock


@pytest.fixture
def mock_config(tmp_path):
    """Create a mock Config object for testing."""
    from claude_agent.config import Config, AgentConfig, SecurityConfigOptions, ValidatorConfig, WorkflowConfig

    return Config(
        project_dir=tmp_path,
        spec_file=None,
        goal=None,
        features=50,
        stack=None,
        review=False,
        agent=AgentConfig(
            model="claude-sonnet-4-20250514",
            max_turns=100,
            max_iterations=10,
            auto_continue_delay=1,
        ),
        security=SecurityConfigOptions(extra_commands=[]),
        validator=ValidatorConfig(
            model="claude-sonnet-4-20250514",
            enabled=True,
            max_rejections=3,
            max_turns=75,
        ),
        workflow=WorkflowConfig(),
    )


class TestRunSpecCreateSession:
    """Test run_spec_create_session function."""

    @pytest.mark.asyncio
    async def test_records_step_on_success(self, tmp_path, mock_create_client, mock_config):
        """
        Purpose: Verify create session records step in spec-workflow.json.
        Tests feature: run_spec_create_session records step in spec-workflow.json
        """
        from claude_agent.agent import run_spec_create_session
        from claude_agent.progress import get_spec_workflow_state

        # Set up mock client that creates spec-draft.md
        mock_client = MockClient(
            should_succeed=True,
            create_files={"spec-draft.md": "# Generated Spec\n\nContent here"}
        )
        mock_client.project_dir = tmp_path
        mock_create_client.return_value = mock_client

        # Run session
        status, spec_path = await run_spec_create_session(
            mock_config, "Build a todo app"
        )

        # Verify step was recorded
        state = get_spec_workflow_state(tmp_path)
        assert len(state["history"]) >= 1
        create_step = next((h for h in state["history"] if h["step"] == "create"), None)
        assert create_step is not None
        assert create_step["status"] == "complete"

    @pytest.mark.asyncio
    async def test_returns_complete_on_success(self, tmp_path, mock_create_client, mock_config):
        """
        Purpose: Verify create session returns correct status on success.
        """
        from claude_agent.agent import run_spec_create_session

        mock_client = MockClient(
            should_succeed=True,
            create_files={"spec-draft.md": "# Generated Spec"}
        )
        mock_client.project_dir = tmp_path
        mock_create_client.return_value = mock_client

        status, spec_path = await run_spec_create_session(
            mock_config, "Build a todo app"
        )

        assert status == "complete"
        assert spec_path == tmp_path / "spec-draft.md"
        assert spec_path.exists()

    @pytest.mark.asyncio
    async def test_returns_error_when_file_not_created(self, tmp_path, mock_create_client, mock_config):
        """
        Purpose: Verify create session returns error when spec-draft.md not created.
        """
        from claude_agent.agent import run_spec_create_session

        # Mock client that doesn't create the file
        mock_client = MockClient(should_succeed=True, create_files={})
        mock_client.project_dir = tmp_path
        mock_create_client.return_value = mock_client

        status, spec_path = await run_spec_create_session(
            mock_config, "Build a todo app"
        )

        assert status == "error"
        assert not spec_path.exists()


class TestRunSpecValidateSession:
    """Test run_spec_validate_session function."""

    @pytest.mark.asyncio
    async def test_records_step_with_passed_true(self, tmp_path, mock_create_client, mock_config):
        """
        Purpose: Verify validate session records passed=true when validated.md created.
        Tests feature: run_spec_validate_session records step with passed=true
        """
        from claude_agent.agent import run_spec_validate_session
        from claude_agent.progress import get_spec_workflow_state

        # Create input spec file
        spec_path = tmp_path / "spec-draft.md"
        spec_path.write_text("# Test Spec\n\nContent here")

        # Mock client that creates validated spec
        mock_client = MockClient(
            should_succeed=True,
            create_files={
                "spec-validated.md": "# Validated Spec",
                "spec-validation.md": "## Validation Report\n\nPASS"
            }
        )
        mock_client.project_dir = tmp_path
        mock_create_client.return_value = mock_client

        status, passed = await run_spec_validate_session(mock_config, spec_path)

        assert passed is True

        # Verify step recorded
        state = get_spec_workflow_state(tmp_path)
        validate_step = next((h for h in state["history"] if h["step"] == "validate"), None)
        assert validate_step is not None
        assert validate_step["passed"] is True

    @pytest.mark.asyncio
    async def test_records_step_with_passed_false(self, tmp_path, mock_create_client, mock_config):
        """
        Purpose: Verify validate session records passed=false when validation fails.
        Tests feature: run_spec_validate_session records step with passed=false
        """
        from claude_agent.agent import run_spec_validate_session
        from claude_agent.progress import get_spec_workflow_state

        # Create input spec file
        spec_path = tmp_path / "spec-draft.md"
        spec_path.write_text("# Test Spec\n\nIncomplete content")

        # Mock client that creates validation report but NOT validated spec
        mock_client = MockClient(
            should_succeed=True,
            create_files={
                "spec-validation.md": "## Validation Report\n\nFAIL - blocking issues"
            }
        )
        mock_client.project_dir = tmp_path
        mock_create_client.return_value = mock_client

        status, passed = await run_spec_validate_session(mock_config, spec_path)

        assert passed is False

        # Verify step recorded
        state = get_spec_workflow_state(tmp_path)
        validate_step = next((h for h in state["history"] if h["step"] == "validate"), None)
        assert validate_step is not None
        assert validate_step["passed"] is False


class TestRunSpecDecomposeSession:
    """Test run_spec_decompose_session function."""

    @pytest.mark.asyncio
    async def test_records_step_with_feature_count(self, tmp_path, mock_create_client, mock_config):
        """
        Purpose: Verify decompose session records step with feature_count.
        Tests feature: run_spec_decompose_session records step and feature_count
        """
        from claude_agent.agent import run_spec_decompose_session
        from claude_agent.progress import get_spec_workflow_state

        # Create validated spec
        spec_path = tmp_path / "spec-validated.md"
        spec_path.write_text("# Validated Spec\n\nDetailed content")

        # Mock client that creates feature list
        feature_list = [
            {"category": "functional", "description": "Test 1", "steps": [], "passes": False}
        ]
        mock_client = MockClient(
            should_succeed=True,
            create_files={
                "feature_list.json": json.dumps(feature_list, indent=2),
                "app_spec.txt": "# Spec copy"
            }
        )
        mock_client.project_dir = tmp_path
        mock_create_client.return_value = mock_client

        status, feature_path = await run_spec_decompose_session(
            mock_config, spec_path, feature_count=60
        )

        assert feature_path.exists()

        # Verify step recorded with feature_count
        state = get_spec_workflow_state(tmp_path)
        decompose_step = next((h for h in state["history"] if h["step"] == "decompose"), None)
        assert decompose_step is not None
        assert decompose_step["feature_count"] == 60

    @pytest.mark.asyncio
    async def test_returns_error_when_no_feature_list(self, tmp_path, mock_create_client, mock_config):
        """
        Purpose: Verify decompose session handles missing feature_list.json.
        """
        from claude_agent.agent import run_spec_decompose_session

        spec_path = tmp_path / "spec-validated.md"
        spec_path.write_text("# Spec")

        # Mock client that doesn't create feature list
        mock_client = MockClient(should_succeed=True, create_files={})
        mock_client.project_dir = tmp_path
        mock_create_client.return_value = mock_client

        status, feature_path = await run_spec_decompose_session(
            mock_config, spec_path, feature_count=50
        )

        assert not feature_path.exists()


class TestRunSpecWorkflow:
    """Test run_spec_workflow function (auto mode)."""

    @pytest.mark.asyncio
    async def test_returns_false_on_create_failure(self, tmp_path, mock_create_client, mock_config):
        """
        Purpose: Verify workflow returns False if spec creation fails.
        Tests feature: run_spec_workflow returns False if spec creation fails
        """
        from claude_agent.agent import run_spec_workflow

        # Mock client that doesn't create spec-draft.md
        mock_client = MockClient(should_succeed=True, create_files={})
        mock_client.project_dir = tmp_path
        mock_create_client.return_value = mock_client

        result = await run_spec_workflow(mock_config, "Build a todo app")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_validation_failure(self, tmp_path, mock_create_client, mock_config):
        """
        Purpose: Verify workflow returns False if validation fails.
        Tests feature: run_spec_workflow returns False after validation failure
        """
        from claude_agent.agent import run_spec_workflow

        # Track which session we're in to return different files
        call_count = [0]

        def make_mock_client(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: create session - succeeds
                client = MockClient(
                    should_succeed=True,
                    create_files={"spec-draft.md": "# Spec"}
                )
            else:
                # Second call: validate session - fails (no validated.md)
                client = MockClient(
                    should_succeed=True,
                    create_files={"spec-validation.md": "## Report\nFAIL"}
                )
            client.project_dir = tmp_path
            return client

        mock_create_client.side_effect = make_mock_client

        result = await run_spec_workflow(mock_config, "Build a todo app")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_when_all_succeed(self, tmp_path, mock_create_client, mock_config):
        """
        Purpose: Verify workflow returns True when all steps succeed.
        Tests feature: run_spec_workflow returns True when all steps succeed
        """
        from claude_agent.agent import run_spec_workflow

        call_count = [0]

        def make_mock_client(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Create session
                client = MockClient(
                    should_succeed=True,
                    create_files={"spec-draft.md": "# Draft Spec"}
                )
            elif call_count[0] == 2:
                # Validate session
                client = MockClient(
                    should_succeed=True,
                    create_files={
                        "spec-validated.md": "# Validated Spec",
                        "spec-validation.md": "## Report\nPASS"
                    }
                )
            else:
                # Decompose session
                features = [{"category": "functional", "description": "Test", "steps": [], "passes": False}]
                client = MockClient(
                    should_succeed=True,
                    create_files={
                        "feature_list.json": json.dumps(features),
                        "app_spec.txt": "# Spec"
                    }
                )
            client.project_dir = tmp_path
            return client

        mock_create_client.side_effect = make_mock_client

        result = await run_spec_workflow(mock_config, "Build a todo app")

        assert result is True

        # Verify all files exist
        assert (tmp_path / "spec-draft.md").exists()
        assert (tmp_path / "spec-validated.md").exists()
        assert (tmp_path / "feature_list.json").exists()

    @pytest.mark.asyncio
    async def test_prints_workflow_banner(self, tmp_path, mock_create_client, mock_config, capsys):
        """
        Purpose: Verify workflow prints banner at start.
        Tests feature: run_spec_workflow prints progress banner at start
        """
        from claude_agent.agent import run_spec_workflow

        # Mock client that fails immediately (we just want to check banner)
        mock_client = MockClient(should_succeed=True, create_files={})
        mock_client.project_dir = tmp_path
        mock_create_client.return_value = mock_client

        await run_spec_workflow(mock_config, "Build a todo app")

        captured = capsys.readouterr()
        assert "SPEC WORKFLOW - AUTO MODE" in captured.out
        assert "Build a todo app" in captured.out
