"""
Tests for Agent State Integration (Feature #121)
================================================

Tests for the integration of state module with agent.py, verifying that
workflow state is created, updated, and persisted correctly during agent runs.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from claude_agent.agent import (
    _create_workflow_state,
    _update_workflow_state,
)
from claude_agent.state import (
    WorkflowState,
    load_workflow_state,
    save_workflow_state,
    get_workflow_dir,
)


class TestCreateWorkflowState:
    """Tests for _create_workflow_state helper function."""

    def test_creates_workflow_state_with_defaults(self, tmp_path):
        """Test creates WorkflowState with default values."""
        state = _create_workflow_state(tmp_path)

        assert isinstance(state, WorkflowState)
        assert state.project_dir == str(tmp_path.resolve())
        assert state.phase == "initializing"
        assert state.features_completed == 0
        assert state.features_total == 0
        assert len(state.id) == 8  # Short UUID

    def test_creates_workflow_state_with_custom_values(self, tmp_path):
        """Test creates WorkflowState with custom values."""
        state = _create_workflow_state(
            project_dir=tmp_path,
            phase="coding",
            features_completed=5,
            features_total=50,
        )

        assert state.phase == "coding"
        assert state.features_completed == 5
        assert state.features_total == 50

    def test_creates_unique_ids(self, tmp_path):
        """Test each call creates unique workflow ID."""
        state1 = _create_workflow_state(tmp_path)
        state2 = _create_workflow_state(tmp_path)

        assert state1.id != state2.id

    def test_sets_timestamps(self, tmp_path):
        """Test sets started_at and updated_at timestamps."""
        state = _create_workflow_state(tmp_path)

        assert isinstance(state.started_at, datetime)
        assert isinstance(state.updated_at, datetime)
        # Timestamps should be close to now
        now = datetime.now()
        assert abs((now - state.started_at).total_seconds()) < 2

    def test_initializing_phase_is_valid(self, tmp_path):
        """Test 'initializing' is a valid phase."""
        state = _create_workflow_state(tmp_path, phase="initializing")
        assert state.phase == "initializing"

    def test_coding_phase_is_valid(self, tmp_path):
        """Test 'coding' is a valid phase."""
        state = _create_workflow_state(tmp_path, phase="coding")
        assert state.phase == "coding"


class TestUpdateWorkflowState:
    """Tests for _update_workflow_state helper function."""

    def test_updates_phase(self, tmp_path):
        """Test updates phase field."""
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            state = _create_workflow_state(tmp_path)
            _update_workflow_state(state, phase="coding")
            assert state.phase == "coding"

    def test_updates_features_completed(self, tmp_path):
        """Test updates features_completed field."""
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            state = _create_workflow_state(tmp_path)
            _update_workflow_state(state, features_completed=10)
            assert state.features_completed == 10

    def test_updates_features_total(self, tmp_path):
        """Test updates features_total field."""
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            state = _create_workflow_state(tmp_path)
            _update_workflow_state(state, features_total=50)
            assert state.features_total == 50

    def test_updates_current_feature_index(self, tmp_path):
        """Test updates current_feature_index field."""
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            state = _create_workflow_state(tmp_path)
            _update_workflow_state(state, current_feature_index=5)
            assert state.current_feature_index == 5

    def test_updates_iteration_count(self, tmp_path):
        """Test updates iteration_count field."""
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            state = _create_workflow_state(tmp_path)
            _update_workflow_state(state, iteration_count=3)
            assert state.iteration_count == 3

    def test_updates_last_error(self, tmp_path):
        """Test updates last_error field."""
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            state = _create_workflow_state(tmp_path)
            error = {"message": "Test error", "recovery_hint": "Try again"}
            _update_workflow_state(state, last_error=error)
            assert state.last_error == error

    def test_clears_error(self, tmp_path):
        """Test clear_error=True clears last_error field."""
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            state = _create_workflow_state(tmp_path)
            state.last_error = {"message": "Previous error"}
            _update_workflow_state(state, clear_error=True)
            assert state.last_error is None

    def test_persists_state_to_disk(self, tmp_path):
        """Test saves state to disk after update."""
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            state = _create_workflow_state(tmp_path)
            save_workflow_state(state)  # Initial save
            _update_workflow_state(state, phase="coding", features_completed=5)

            # Load from disk and verify
            loaded = load_workflow_state(tmp_path)
            assert loaded is not None
            assert loaded.phase == "coding"
            assert loaded.features_completed == 5

    def test_handles_none_state(self):
        """Test gracefully handles None state."""
        # Should not raise
        _update_workflow_state(None, phase="coding")

    def test_logs_state_changes_when_logger_provided(self, tmp_path):
        """Test logs state changes when logger provided."""
        mock_logger = MagicMock()
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            state = _create_workflow_state(tmp_path)
            _update_workflow_state(state, phase="coding", logger=mock_logger)

        mock_logger.debug.assert_called()

    def test_logs_warning_on_save_failure(self, tmp_path):
        """Test logs warning when save fails."""
        mock_logger = MagicMock()
        state = _create_workflow_state(tmp_path)
        # Make save fail by pointing to non-existent directory
        state.project_dir = "/nonexistent/path/that/does/not/exist"

        with patch("claude_agent.agent.save_workflow_state", side_effect=OSError("Permission denied")):
            _update_workflow_state(state, phase="coding", logger=mock_logger)

        mock_logger.warning.assert_called()

    def test_multiple_updates_accumulate(self, tmp_path):
        """Test multiple updates accumulate correctly."""
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            state = _create_workflow_state(tmp_path)
            _update_workflow_state(state, phase="coding")
            _update_workflow_state(state, features_completed=5)
            _update_workflow_state(state, features_total=50)
            _update_workflow_state(state, iteration_count=2)

            assert state.phase == "coding"
            assert state.features_completed == 5
            assert state.features_total == 50
            assert state.iteration_count == 2


class TestWorkflowStatePhaseTransitions:
    """Tests for phase transitions in workflow state."""

    def test_initializing_to_coding(self, tmp_path):
        """Test transition from initializing to coding phase."""
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            state = _create_workflow_state(tmp_path, phase="initializing")
            _update_workflow_state(state, phase="coding")
            assert state.phase == "coding"

    def test_coding_to_validating(self, tmp_path):
        """Test transition from coding to validating phase."""
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            state = _create_workflow_state(tmp_path, phase="coding")
            _update_workflow_state(state, phase="validating")
            assert state.phase == "validating"

    def test_validating_to_complete(self, tmp_path):
        """Test transition from validating to complete phase."""
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            state = _create_workflow_state(tmp_path, phase="validating")
            _update_workflow_state(state, phase="complete")
            assert state.phase == "complete"

    def test_coding_to_paused(self, tmp_path):
        """Test transition from coding to paused phase."""
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            state = _create_workflow_state(tmp_path, phase="coding")
            _update_workflow_state(
                state,
                phase="paused",
                pause_reason="Max iterations reached",
            )
            assert state.phase == "paused"


class TestWorkflowStateRecovery:
    """Tests for workflow state recovery scenarios."""

    def test_resume_from_saved_state(self, tmp_path):
        """Test resuming workflow from saved state."""
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            # Create and save initial state
            state1 = _create_workflow_state(
                tmp_path,
                phase="coding",
                features_completed=10,
                features_total=50,
            )
            save_workflow_state(state1)

            # Load and verify
            loaded = load_workflow_state(tmp_path)
            assert loaded is not None
            assert loaded.phase == "coding"
            assert loaded.features_completed == 10
            assert loaded.features_total == 50

    def test_resume_with_previous_error(self, tmp_path):
        """Test resuming workflow with previous error context."""
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            # Create state with error
            state = _create_workflow_state(tmp_path, phase="coding")
            state.last_error = {
                "message": "Network timeout",
                "recovery_hint": "Check connection",
            }
            save_workflow_state(state)

            # Load and verify error is preserved
            loaded = load_workflow_state(tmp_path)
            assert loaded is not None
            assert loaded.last_error is not None
            assert loaded.last_error["message"] == "Network timeout"

    def test_clear_error_on_successful_session(self, tmp_path):
        """Test error is cleared on successful session start."""
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            # Create state with error
            state = _create_workflow_state(tmp_path, phase="coding")
            state.last_error = {"message": "Previous error"}
            save_workflow_state(state)

            # Update with clear_error=True (as agent does on session start)
            _update_workflow_state(state, clear_error=True)

            # Verify error is cleared
            loaded = load_workflow_state(tmp_path)
            assert loaded is not None
            assert loaded.last_error is None


class TestWorkflowStateIntegrationWithAgent:
    """Integration tests for workflow state in agent context."""

    def test_state_dir_created_on_agent_start(self, tmp_path):
        """Test state directories are created on agent start."""
        from claude_agent.state import ensure_state_dirs, get_workflow_dir

        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            ensure_state_dirs(tmp_path / "project")

            workflow_dir = get_workflow_dir(tmp_path / "project")
            assert workflow_dir.exists()

    def test_migration_called_on_first_run(self, tmp_path):
        """Test migration is called on first run."""
        from claude_agent.state import migrate_project_state, ensure_state_dirs

        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Create old-style validation history
        (project_dir / "validation-history.json").write_text('{"old": true}')

        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            ensure_state_dirs(project_dir)
            success, messages = migrate_project_state(project_dir)

            assert success is True
            assert any("Migrated" in msg for msg in messages)

    def test_iteration_count_increments(self, tmp_path):
        """Test iteration count increments across updates."""
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            state = _create_workflow_state(tmp_path)
            assert state.iteration_count == 0

            _update_workflow_state(state, iteration_count=1)
            assert state.iteration_count == 1

            _update_workflow_state(state, iteration_count=2)
            assert state.iteration_count == 2

    def test_progress_tracking_accuracy(self, tmp_path):
        """Test progress tracking matches feature counts."""
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            state = _create_workflow_state(
                tmp_path,
                features_completed=0,
                features_total=50,
            )
            save_workflow_state(state)

            # Simulate progress
            _update_workflow_state(state, features_completed=10)
            loaded = load_workflow_state(tmp_path)
            assert loaded.features_completed == 10
            assert loaded.features_total == 50

            # More progress
            _update_workflow_state(state, features_completed=25)
            loaded = load_workflow_state(tmp_path)
            assert loaded.features_completed == 25
