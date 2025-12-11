"""
Tests for XDG State Management Module
=====================================

Tests for the XDG-compliant state separation and workflow state management.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from claude_agent.state import (
    DIRS_TO_KEEP,
    FILES_TO_KEEP,
    FILES_TO_MIGRATE,
    MIGRATION_MARKER,
    VALID_PHASES,
    WorkflowState,
    clear_workflow_state,
    ensure_state_dirs,
    get_logs_dir,
    get_migration_status,
    get_project_hash,
    get_state_dir,
    get_workflow_dir,
    load_workflow_state,
    migrate_project_state,
    save_workflow_state,
)


class TestGetStateDir:
    """Tests for get_state_dir() function."""

    def test_returns_path_under_local_state_by_default(self):
        """Test returns path under ~/.local/state by default."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove XDG_STATE_HOME if present
            os.environ.pop("XDG_STATE_HOME", None)
            result = get_state_dir()

            # Should end with claude-agent
            assert result.name == "claude-agent"
            # Should be under .local/state (on Unix)
            assert ".local" in str(result) or "state" in str(result).lower()

    def test_respects_xdg_state_home_env_var(self):
        """Test respects XDG_STATE_HOME environment variable."""
        with patch.dict(os.environ, {"XDG_STATE_HOME": "/custom/state"}, clear=False):
            result = get_state_dir()

            assert result == Path("/custom/state/claude-agent")

    def test_path_ends_with_claude_agent(self):
        """Test path ends with /claude-agent/."""
        result = get_state_dir()
        assert result.name == "claude-agent"

    def test_returns_path_object(self):
        """Test returns a Path object."""
        result = get_state_dir()
        assert isinstance(result, Path)


class TestGetProjectHash:
    """Tests for get_project_hash() function."""

    def test_hash_is_exactly_12_characters(self):
        """Test hash is exactly 12 characters."""
        result = get_project_hash("/some/project/path")
        assert len(result) == 12

    def test_hash_is_stable(self):
        """Test same input produces same output."""
        path = "/my/project"
        result1 = get_project_hash(path)
        result2 = get_project_hash(path)
        assert result1 == result2

    def test_different_paths_produce_different_hashes(self):
        """Test different paths produce different hashes."""
        hash1 = get_project_hash("/path/one")
        hash2 = get_project_hash("/path/two")
        assert hash1 != hash2

    def test_hash_is_hexadecimal(self):
        """Test hash is valid hexadecimal."""
        result = get_project_hash("/some/path")
        # Should only contain hex characters
        assert all(c in "0123456789abcdef" for c in result)

    def test_accepts_path_object(self):
        """Test accepts Path objects."""
        result = get_project_hash(Path("/some/path"))
        assert len(result) == 12

    def test_uses_absolute_path(self):
        """Test uses absolute path for hashing."""
        # Relative and absolute paths to same location should hash the same
        # when resolved to the same absolute path
        abs_path = Path("/tmp/test_project").resolve()
        hash_from_string = get_project_hash(str(abs_path))
        hash_from_path = get_project_hash(abs_path)
        assert hash_from_string == hash_from_path


class TestGetWorkflowDir:
    """Tests for get_workflow_dir() function."""

    def test_returns_path_under_state_dir(self):
        """Test returns path under state directory."""
        result = get_workflow_dir("/my/project")
        state_dir = get_state_dir()

        assert str(result).startswith(str(state_dir))

    def test_includes_workflows_subdirectory(self):
        """Test includes workflows subdirectory."""
        result = get_workflow_dir("/my/project")
        assert "workflows" in result.parts

    def test_includes_project_hash(self):
        """Test includes project hash in path."""
        result = get_workflow_dir("/my/project")
        project_hash = get_project_hash("/my/project")

        assert project_hash in str(result)


class TestGetLogsDir:
    """Tests for get_logs_dir() function."""

    def test_returns_path_under_state_dir(self):
        """Test returns path under state directory."""
        result = get_logs_dir()
        state_dir = get_state_dir()

        assert str(result).startswith(str(state_dir))

    def test_ends_with_logs(self):
        """Test path ends with logs."""
        result = get_logs_dir()
        assert result.name == "logs"


class TestEnsureStateDirs:
    """Tests for ensure_state_dirs() function."""

    def test_creates_state_dir(self, tmp_path):
        """Test creates state directory."""
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            ensure_state_dirs()

            assert (tmp_path / "state").exists()

    def test_creates_logs_dir(self, tmp_path):
        """Test creates logs directory."""
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            ensure_state_dirs()

            assert (tmp_path / "state" / "logs").exists()

    def test_creates_workflows_dir(self, tmp_path):
        """Test creates workflows directory."""
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            ensure_state_dirs()

            assert (tmp_path / "state" / "workflows").exists()

    def test_creates_project_workflow_dir_when_provided(self, tmp_path):
        """Test creates project-specific workflow dir when project_dir provided."""
        project_dir = tmp_path / "my_project"
        project_dir.mkdir()

        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            ensure_state_dirs(project_dir)

            # Should create a workflow dir with project hash
            workflows_dir = tmp_path / "state" / "workflows"
            assert workflows_dir.exists()
            # Should have at least one subdirectory
            subdirs = list(workflows_dir.iterdir())
            assert len(subdirs) == 1

    def test_handles_existing_directories(self, tmp_path):
        """Test handles existing directories gracefully."""
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        with patch("claude_agent.state.get_state_dir", return_value=state_dir):
            # Should not raise
            ensure_state_dirs()
            ensure_state_dirs()  # Call twice to test idempotency


class TestWorkflowState:
    """Tests for WorkflowState dataclass."""

    def test_creation_with_valid_phase(self):
        """Test creation with valid phase values."""
        for phase in VALID_PHASES:
            state = WorkflowState(
                id="test-id",
                project_dir="/test/project",
                phase=phase,
                started_at=datetime.now(),
                updated_at=datetime.now(),
            )
            assert state.phase == phase

    def test_raises_error_for_invalid_phase(self):
        """Test ValueError raised for invalid phase."""
        with pytest.raises(ValueError) as exc_info:
            WorkflowState(
                id="test-id",
                project_dir="/test/project",
                phase="invalid_phase",
                started_at=datetime.now(),
                updated_at=datetime.now(),
            )

        assert "Invalid phase" in str(exc_info.value)
        assert "invalid_phase" in str(exc_info.value)

    def test_default_values_applied(self):
        """Test default values are applied correctly."""
        state = WorkflowState(
            id="test-id",
            project_dir="/test/project",
            phase="coding",
            started_at=datetime.now(),
            updated_at=datetime.now(),
        )

        assert state.features_completed == 0
        assert state.features_total == 0
        assert state.current_feature_index is None
        assert state.iteration_count == 0
        assert state.last_error is None
        assert state.pause_reason is None
        assert state.recovery_steps == []

    def test_all_fields_can_be_set(self):
        """Test all fields can be set."""
        now = datetime.now()
        state = WorkflowState(
            id="test-id",
            project_dir="/test/project",
            phase="coding",
            started_at=now,
            updated_at=now,
            features_completed=5,
            features_total=50,
            current_feature_index=5,
            iteration_count=3,
            last_error={"type": "manual", "message": "Test error"},
            pause_reason="User requested",
            recovery_steps=["Step 1", "Step 2"],
        )

        assert state.features_completed == 5
        assert state.features_total == 50
        assert state.current_feature_index == 5
        assert state.iteration_count == 3
        assert state.last_error == {"type": "manual", "message": "Test error"}
        assert state.pause_reason == "User requested"
        assert state.recovery_steps == ["Step 1", "Step 2"]


class TestWorkflowStateSerialization:
    """Tests for WorkflowState serialization methods."""

    def test_to_dict_serializes_all_fields(self):
        """Test to_dict produces JSON-serializable dict."""
        now = datetime(2024, 1, 15, 10, 30, 0)
        state = WorkflowState(
            id="test-id",
            project_dir="/test/project",
            phase="coding",
            started_at=now,
            updated_at=now,
            features_completed=5,
            features_total=50,
            current_feature_index=5,
            iteration_count=3,
            last_error={"type": "manual"},
            pause_reason="Testing",
            recovery_steps=["Step 1"],
        )

        result = state.to_dict()

        assert result["id"] == "test-id"
        assert result["project_dir"] == "/test/project"
        assert result["phase"] == "coding"
        assert result["started_at"] == "2024-01-15T10:30:00"
        assert result["updated_at"] == "2024-01-15T10:30:00"
        assert result["features_completed"] == 5
        assert result["features_total"] == 50
        assert result["current_feature_index"] == 5
        assert result["iteration_count"] == 3
        assert result["last_error"] == {"type": "manual"}
        assert result["pause_reason"] == "Testing"
        assert result["recovery_steps"] == ["Step 1"]

    def test_to_dict_is_json_serializable(self):
        """Test to_dict output can be JSON serialized."""
        state = WorkflowState(
            id="test-id",
            project_dir="/test/project",
            phase="coding",
            started_at=datetime.now(),
            updated_at=datetime.now(),
        )

        result = state.to_dict()

        # Should not raise
        json_str = json.dumps(result)
        assert isinstance(json_str, str)

    def test_from_dict_deserializes_all_fields(self):
        """Test from_dict correctly parses dictionary."""
        data = {
            "id": "test-id",
            "project_dir": "/test/project",
            "phase": "validating",
            "started_at": "2024-01-15T10:30:00",
            "updated_at": "2024-01-15T11:30:00",
            "features_completed": 10,
            "features_total": 50,
            "current_feature_index": 10,
            "iteration_count": 5,
            "last_error": {"type": "retry"},
            "pause_reason": "Error",
            "recovery_steps": ["Fix bug"],
        }

        state = WorkflowState.from_dict(data)

        assert state.id == "test-id"
        assert state.project_dir == "/test/project"
        assert state.phase == "validating"
        assert state.started_at == datetime(2024, 1, 15, 10, 30, 0)
        assert state.updated_at == datetime(2024, 1, 15, 11, 30, 0)
        assert state.features_completed == 10
        assert state.features_total == 50
        assert state.current_feature_index == 10
        assert state.iteration_count == 5
        assert state.last_error == {"type": "retry"}
        assert state.pause_reason == "Error"
        assert state.recovery_steps == ["Fix bug"]

    def test_from_dict_handles_missing_optional_fields(self):
        """Test from_dict handles missing optional fields."""
        data = {
            "id": "test-id",
            "project_dir": "/test/project",
            "phase": "complete",
            "started_at": "2024-01-15T10:30:00",
            "updated_at": "2024-01-15T11:30:00",
        }

        state = WorkflowState.from_dict(data)

        assert state.features_completed == 0
        assert state.features_total == 0
        assert state.current_feature_index is None
        assert state.iteration_count == 0
        assert state.last_error is None
        assert state.pause_reason is None
        assert state.recovery_steps == []

    def test_serialization_roundtrip(self):
        """Test that to_dict -> from_dict preserves data."""
        now = datetime(2024, 1, 15, 10, 30, 0)
        original = WorkflowState(
            id="roundtrip-test",
            project_dir="/roundtrip/project",
            phase="paused",
            started_at=now,
            updated_at=now,
            features_completed=25,
            features_total=100,
            current_feature_index=25,
            iteration_count=10,
            last_error={"type": "manual", "category": "validation"},
            pause_reason="Feature failed",
            recovery_steps=["Review error", "Fix code"],
        )

        serialized = original.to_dict()
        restored = WorkflowState.from_dict(serialized)

        assert restored.id == original.id
        assert restored.project_dir == original.project_dir
        assert restored.phase == original.phase
        assert restored.started_at == original.started_at
        assert restored.updated_at == original.updated_at
        assert restored.features_completed == original.features_completed
        assert restored.features_total == original.features_total
        assert restored.current_feature_index == original.current_feature_index
        assert restored.iteration_count == original.iteration_count
        assert restored.last_error == original.last_error
        assert restored.pause_reason == original.pause_reason
        assert restored.recovery_steps == original.recovery_steps


class TestLoadWorkflowState:
    """Tests for load_workflow_state() function."""

    def test_returns_none_for_nonexistent_file(self, tmp_path):
        """Test returns None for non-existent file."""
        with patch("claude_agent.state.get_workflow_dir", return_value=tmp_path):
            result = load_workflow_state("/nonexistent/project")

            assert result is None

    def test_returns_workflow_state_after_save(self, tmp_path):
        """Test returns correct WorkflowState after save."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        workflow_dir = tmp_path / "workflow"
        workflow_dir.mkdir()

        with patch("claude_agent.state.get_workflow_dir", return_value=workflow_dir):
            # Create and save state
            state = WorkflowState(
                id="test-id",
                project_dir=str(project_dir),
                phase="coding",
                started_at=datetime(2024, 1, 15, 10, 0, 0),
                updated_at=datetime(2024, 1, 15, 10, 0, 0),
                features_completed=5,
                features_total=50,
            )

            # Write state file directly for this test
            state_file = workflow_dir / "workflow-state.json"
            with open(state_file, "w") as f:
                json.dump(state.to_dict(), f)

            # Load and verify
            loaded = load_workflow_state(project_dir)

            assert loaded is not None
            assert loaded.id == "test-id"
            assert loaded.phase == "coding"
            assert loaded.features_completed == 5

    def test_returns_none_on_json_parse_error(self, tmp_path):
        """Test returns None on JSON parse errors."""
        workflow_dir = tmp_path / "workflow"
        workflow_dir.mkdir()
        state_file = workflow_dir / "workflow-state.json"

        # Write invalid JSON
        with open(state_file, "w") as f:
            f.write("not valid json {{{")

        with patch("claude_agent.state.get_workflow_dir", return_value=workflow_dir):
            result = load_workflow_state("/some/project")

            assert result is None


class TestSaveWorkflowState:
    """Tests for save_workflow_state() function."""

    def test_creates_state_file(self, tmp_path):
        """Test creates state file with correct content."""
        workflow_dir = tmp_path / "workflow"
        workflow_dir.mkdir()

        with patch("claude_agent.state.get_workflow_dir", return_value=workflow_dir):
            with patch("claude_agent.state.ensure_state_dirs"):
                state = WorkflowState(
                    id="test-id",
                    project_dir=str(tmp_path),
                    phase="coding",
                    started_at=datetime(2024, 1, 15, 10, 0, 0),
                    updated_at=datetime(2024, 1, 15, 10, 0, 0),
                )

                save_workflow_state(state)

                state_file = workflow_dir / "workflow-state.json"
                assert state_file.exists()

                with open(state_file) as f:
                    data = json.load(f)

                assert data["id"] == "test-id"
                assert data["phase"] == "coding"

    def test_updates_updated_at_timestamp(self, tmp_path):
        """Test updates updated_at timestamp on save."""
        workflow_dir = tmp_path / "workflow"
        workflow_dir.mkdir()

        with patch("claude_agent.state.get_workflow_dir", return_value=workflow_dir):
            with patch("claude_agent.state.ensure_state_dirs"):
                old_time = datetime(2024, 1, 1, 0, 0, 0)
                state = WorkflowState(
                    id="test-id",
                    project_dir=str(tmp_path),
                    phase="coding",
                    started_at=old_time,
                    updated_at=old_time,
                )

                save_workflow_state(state)

                # updated_at should be changed
                assert state.updated_at != old_time
                assert state.updated_at > old_time


class TestClearWorkflowState:
    """Tests for clear_workflow_state() function."""

    def test_returns_true_when_file_exists(self, tmp_path):
        """Test returns True when file exists and is deleted."""
        workflow_dir = tmp_path / "workflow"
        workflow_dir.mkdir()
        state_file = workflow_dir / "workflow-state.json"
        state_file.write_text("{}")

        with patch("claude_agent.state.get_workflow_dir", return_value=workflow_dir):
            result = clear_workflow_state("/some/project")

            assert result is True
            assert not state_file.exists()

    def test_returns_true_when_file_does_not_exist(self, tmp_path):
        """Test returns True when file doesn't exist (idempotent)."""
        workflow_dir = tmp_path / "workflow"
        workflow_dir.mkdir()

        with patch("claude_agent.state.get_workflow_dir", return_value=workflow_dir):
            result = clear_workflow_state("/some/project")

            assert result is True

    def test_file_is_actually_removed(self, tmp_path):
        """Verify file is actually removed from filesystem."""
        workflow_dir = tmp_path / "workflow"
        workflow_dir.mkdir()
        state_file = workflow_dir / "workflow-state.json"
        state_file.write_text('{"id": "test"}')

        assert state_file.exists()

        with patch("claude_agent.state.get_workflow_dir", return_value=workflow_dir):
            clear_workflow_state("/some/project")

        assert not state_file.exists()


class TestValidPhases:
    """Tests for VALID_PHASES constant."""

    def test_contains_all_expected_phases(self):
        """Test VALID_PHASES contains all expected values."""
        expected = {"initializing", "coding", "validating", "complete", "paused"}
        assert VALID_PHASES == expected

    def test_is_frozen_set(self):
        """Test VALID_PHASES is immutable."""
        assert isinstance(VALID_PHASES, frozenset)


class TestLastErrorIntegration:
    """Tests for last_error field integration with StructuredError."""

    def test_last_error_accepts_structured_error_dict(self):
        """Test last_error field accepts dict from StructuredError.to_dict()."""
        from claude_agent.structured_errors import error_validation_failed

        error = error_validation_failed(5, "Button not found")
        error_dict = error.to_dict()

        state = WorkflowState(
            id="test-id",
            project_dir="/test/project",
            phase="paused",
            started_at=datetime.now(),
            updated_at=datetime.now(),
            last_error=error_dict,
        )

        assert state.last_error == error_dict
        assert state.last_error["type"] == "manual"
        assert state.last_error["category"] == "validation"

    def test_last_error_serialization_roundtrip(self):
        """Test last_error survives serialization roundtrip."""
        from claude_agent.structured_errors import error_security_block

        error = error_security_block("rm -rf /", "Not allowed")
        error_dict = error.to_dict()

        state = WorkflowState(
            id="test-id",
            project_dir="/test/project",
            phase="paused",
            started_at=datetime(2024, 1, 15, 10, 0, 0),
            updated_at=datetime(2024, 1, 15, 10, 0, 0),
            last_error=error_dict,
        )

        serialized = state.to_dict()
        restored = WorkflowState.from_dict(serialized)

        assert restored.last_error == error_dict
        assert restored.last_error["context"]["command"] == "rm -rf /"

    def test_structured_error_can_be_reconstructed(self):
        """Test StructuredError can be reconstructed from last_error."""
        from claude_agent.structured_errors import StructuredError, error_file_not_found

        error = error_file_not_found("/missing/file.txt")
        error_dict = error.to_dict()

        state = WorkflowState(
            id="test-id",
            project_dir="/test/project",
            phase="paused",
            started_at=datetime(2024, 1, 15, 10, 0, 0),
            updated_at=datetime(2024, 1, 15, 10, 0, 0),
            last_error=error_dict,
        )

        # Reconstruct StructuredError from last_error
        if state.last_error:
            reconstructed = StructuredError.from_dict(state.last_error)
            assert reconstructed.message == error.message
            assert reconstructed.recovery_hint == error.recovery_hint
            assert reconstructed.context["path"] == "/missing/file.txt"


class TestStateMigration:
    """Tests for state migration functions."""

    def test_migrate_moves_files_correctly(self, tmp_path):
        """Test migration moves files correctly."""
        from claude_agent.state import (
            FILES_TO_MIGRATE,
            migrate_project_state,
        )

        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Create test files to migrate
        for filename in FILES_TO_MIGRATE:
            (project_dir / filename).write_text(f'{{"file": "{filename}"}}')

        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            success, messages = migrate_project_state(project_dir)

        assert success is True
        assert any("Migration completed successfully" in msg for msg in messages)

        # Check files were copied to XDG
        from claude_agent.state import get_workflow_dir
        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            workflow_dir = get_workflow_dir(project_dir)

        for filename in FILES_TO_MIGRATE:
            assert (workflow_dir / filename).exists()
            # Verify content preserved
            content = (workflow_dir / filename).read_text()
            assert f'"file": "{filename}"' in content

    def test_migration_is_idempotent(self, tmp_path):
        """Test migration is idempotent (safe to run twice)."""
        from claude_agent.state import migrate_project_state

        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Create test file
        (project_dir / "validation-history.json").write_text('{"test": true}')

        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            # Run migration twice
            success1, messages1 = migrate_project_state(project_dir)
            success2, messages2 = migrate_project_state(project_dir)

        assert success1 is True
        assert success2 is True
        # Second run should report already migrated
        assert any("already completed" in msg for msg in messages2)

    def test_migration_preserves_file_contents(self, tmp_path):
        """Test migration preserves file contents."""
        from claude_agent.state import migrate_project_state, get_workflow_dir

        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Create file with specific content
        test_content = '{"key": "value", "nested": {"inner": 123}}'
        (project_dir / "validation-history.json").write_text(test_content)

        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            migrate_project_state(project_dir)
            workflow_dir = get_workflow_dir(project_dir)

        # Verify content is identical
        migrated_content = (workflow_dir / "validation-history.json").read_text()
        assert migrated_content == test_content

    def test_migration_handles_missing_files_gracefully(self, tmp_path):
        """Test migration handles missing files gracefully."""
        from claude_agent.state import migrate_project_state

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        # Don't create any files

        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            success, messages = migrate_project_state(project_dir)

        assert success is True
        # Should report skipped files
        assert any("Skipped" in msg for msg in messages)

    def test_migration_preserves_original_files(self, tmp_path):
        """Test original files are preserved after migration."""
        from claude_agent.state import migrate_project_state

        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Create test file
        test_file = project_dir / "validation-history.json"
        test_file.write_text('{"original": true}')

        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            migrate_project_state(project_dir)

        # Original should still exist (preserved until verified)
        assert test_file.exists()
        assert '{"original": true}' == test_file.read_text()

    def test_migrate_logs_directory(self, tmp_path):
        """Test logs directory migration."""
        from claude_agent.state import migrate_project_state, get_logs_dir

        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Create old logs directory
        old_logs = project_dir / ".claude-agent" / "logs"
        old_logs.mkdir(parents=True)
        (old_logs / "session-001.log").write_text("Log content 1")
        (old_logs / "session-002.log").write_text("Log content 2")

        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            success, messages = migrate_project_state(project_dir)
            logs_dir = get_logs_dir()

        assert success is True
        # Check logs were migrated
        assert (logs_dir / "session-001.log").exists()
        assert (logs_dir / "session-002.log").exists()
        assert (logs_dir / "session-001.log").read_text() == "Log content 1"

    def test_get_migration_status(self, tmp_path):
        """Test get_migration_status function."""
        from claude_agent.state import migrate_project_state, get_migration_status

        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Create test file
        (project_dir / "validation-history.json").write_text('{}')

        with patch("claude_agent.state.get_state_dir", return_value=tmp_path / "state"):
            # Before migration
            status_before = get_migration_status(project_dir)
            assert status_before["migrated"] is False
            assert "validation-history.json" in status_before["files_in_project"]

            # After migration
            migrate_project_state(project_dir)
            status_after = get_migration_status(project_dir)
            assert status_after["migrated"] is True
            assert "validation-history.json" in status_after["files_in_xdg"]

    def test_files_to_keep_list(self):
        """Test FILES_TO_KEEP contains expected files."""
        from claude_agent.state import FILES_TO_KEEP

        assert "feature_list.json" in FILES_TO_KEEP
        assert "app_spec.txt" in FILES_TO_KEEP
        assert "claude-progress.txt" in FILES_TO_KEEP

    def test_dirs_to_keep_list(self):
        """Test DIRS_TO_KEEP contains expected directories."""
        from claude_agent.state import DIRS_TO_KEEP

        assert "architecture" in DIRS_TO_KEEP


class TestConcurrentAccessDetection:
    """Tests for concurrent access detection (Feature #129)."""

    def test_is_state_stale_returns_false_for_complete_phase(self):
        """Test is_state_stale returns False for complete phase."""
        from claude_agent.state import is_state_stale

        state = WorkflowState(
            id="test-id",
            project_dir="/test/project",
            phase="complete",
            started_at=datetime(2020, 1, 1, 0, 0, 0),  # Old date
            updated_at=datetime(2020, 1, 1, 0, 0, 0),  # Old date
        )

        assert is_state_stale(state) is False

    def test_is_state_stale_returns_false_for_paused_phase(self):
        """Test is_state_stale returns False for paused phase."""
        from claude_agent.state import is_state_stale

        state = WorkflowState(
            id="test-id",
            project_dir="/test/project",
            phase="paused",
            started_at=datetime(2020, 1, 1, 0, 0, 0),  # Old date
            updated_at=datetime(2020, 1, 1, 0, 0, 0),  # Old date
        )

        assert is_state_stale(state) is False

    def test_is_state_stale_returns_true_for_old_coding_phase(self):
        """Test is_state_stale returns True for old state in coding phase."""
        from claude_agent.state import is_state_stale

        state = WorkflowState(
            id="test-id",
            project_dir="/test/project",
            phase="coding",
            started_at=datetime(2020, 1, 1, 0, 0, 0),  # Very old
            updated_at=datetime(2020, 1, 1, 0, 0, 0),  # Very old
        )

        assert is_state_stale(state) is True

    def test_is_state_stale_returns_true_for_dead_pid(self, tmp_path):
        """Test is_state_stale returns True when owning process is dead."""
        from claude_agent.state import is_state_stale

        # Use a PID that is definitely not running (very high number)
        state = WorkflowState(
            id="test-id",
            project_dir=str(tmp_path),
            phase="coding",
            started_at=datetime.now(),
            updated_at=datetime.now(),
            owning_pid=99999999,  # This PID should not exist
            hostname=None,  # Will match current host
        )

        assert is_state_stale(state) is True

    def test_check_concurrent_access_returns_none_for_same_process(self):
        """Test check_concurrent_access returns None when same process."""
        import os
        from claude_agent.state import check_concurrent_access, _get_current_hostname

        state = WorkflowState(
            id="test-id",
            project_dir="/test/project",
            phase="coding",
            started_at=datetime.now(),
            updated_at=datetime.now(),
            owning_pid=os.getpid(),
            hostname=_get_current_hostname(),
        )

        assert check_concurrent_access(state) is None

    def test_check_concurrent_access_returns_warning_for_running_process(self, monkeypatch):
        """Test check_concurrent_access returns warning for other running process."""
        from claude_agent.state import check_concurrent_access, _get_current_hostname

        # Mock _is_process_running to return True
        monkeypatch.setattr("claude_agent.state._is_process_running", lambda pid: True)

        state = WorkflowState(
            id="test-id",
            project_dir="/test/project",
            phase="coding",
            started_at=datetime.now(),
            updated_at=datetime.now(),
            owning_pid=12345,  # Different PID
            hostname=_get_current_hostname(),
        )

        warning = check_concurrent_access(state)
        assert warning is not None
        assert "concurrent access" in warning.lower()

    def test_check_concurrent_access_returns_warning_for_different_host(self):
        """Test check_concurrent_access returns warning for different hostname."""
        from claude_agent.state import check_concurrent_access

        state = WorkflowState(
            id="test-id",
            project_dir="/test/project",
            phase="coding",
            started_at=datetime.now(),
            updated_at=datetime.now(),
            owning_pid=12345,
            hostname="other-machine.local",
        )

        warning = check_concurrent_access(state)
        assert warning is not None
        assert "other-machine.local" in warning

    def test_save_workflow_state_sets_owning_pid_and_hostname(self, tmp_path):
        """Test save_workflow_state sets owning_pid and hostname."""
        import os
        from claude_agent.state import _get_current_hostname

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        workflow_dir = tmp_path / "workflow"
        workflow_dir.mkdir()

        state = WorkflowState(
            id="test-id",
            project_dir=str(project_dir),
            phase="coding",
            started_at=datetime.now(),
            updated_at=datetime.now(),
        )

        # Initially no owning_pid
        assert state.owning_pid is None
        assert state.hostname is None

        with patch("claude_agent.state.get_workflow_dir", return_value=workflow_dir):
            with patch("claude_agent.state.ensure_state_dirs"):
                save_workflow_state(state)

        # After save, should have owning_pid and hostname
        assert state.owning_pid == os.getpid()
        assert state.hostname == _get_current_hostname()

    def test_workflow_state_includes_pid_in_serialization(self):
        """Test WorkflowState serializes owning_pid and hostname."""
        import os

        state = WorkflowState(
            id="test-id",
            project_dir="/test/project",
            phase="coding",
            started_at=datetime.now(),
            updated_at=datetime.now(),
            owning_pid=os.getpid(),
            hostname="test-host",
        )

        serialized = state.to_dict()

        assert "owning_pid" in serialized
        assert serialized["owning_pid"] == os.getpid()
        assert "hostname" in serialized
        assert serialized["hostname"] == "test-host"

    def test_workflow_state_from_dict_handles_missing_pid(self):
        """Test WorkflowState.from_dict handles missing owning_pid (backward compat)."""
        data = {
            "id": "test-id",
            "project_dir": "/test/project",
            "phase": "coding",
            "started_at": "2024-01-15T10:00:00",
            "updated_at": "2024-01-15T10:00:00",
            # No owning_pid or hostname
        }

        state = WorkflowState.from_dict(data)

        assert state.owning_pid is None
        assert state.hostname is None

    def test_atomic_write_still_works_with_pid_tracking(self, tmp_path):
        """Test save_workflow_state still uses atomic writes with PID tracking."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        workflow_dir = tmp_path / "workflow"
        workflow_dir.mkdir()

        state = WorkflowState(
            id="test-id",
            project_dir=str(project_dir),
            phase="coding",
            started_at=datetime.now(),
            updated_at=datetime.now(),
        )

        with patch("claude_agent.state.get_workflow_dir", return_value=workflow_dir):
            with patch("claude_agent.state.ensure_state_dirs"):
                save_workflow_state(state)

        # Verify file was created
        state_file = workflow_dir / "workflow-state.json"
        assert state_file.exists()

        # Verify content is valid JSON with PID
        content = json.loads(state_file.read_text())
        assert "owning_pid" in content
        assert "hostname" in content
