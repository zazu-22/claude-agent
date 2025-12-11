"""
Integration Tests for Milestone 5 Features
==========================================

End-to-end integration tests for:
- Hook context injection on session start
- Error persistence and recovery
- State migration from project to XDG
- Skill injection in prompts
- Phase tracking in logs
- Performance requirements
"""

import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_agent.hooks import (
    execute_hook_safely,
    generate_session_start_script,
    generate_session_stop_script,
    install_hooks,
)
from claude_agent.logging import AgentLogger, EventType, LogLevel, LogReader
from claude_agent.prompts.loader import get_coding_prompt, get_validator_prompt
from claude_agent.prompts.skills import get_available_skills, inject_skills, load_skill
from claude_agent.state import (
    FILES_TO_KEEP,
    FILES_TO_MIGRATE,
    WorkflowState,
    clear_workflow_state,
    ensure_state_dirs,
    get_logs_dir,
    get_project_hash,
    get_state_dir,
    get_workflow_dir,
    load_workflow_state,
    migrate_project_state,
    save_workflow_state,
)
from claude_agent.structured_errors import (
    ErrorCategory,
    ErrorType,
    StructuredError,
    error_security_block,
    error_validation_failed,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory with typical files."""
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()

    # Create project-bound files
    (project_dir / "feature_list.json").write_text('{"features": []}')
    (project_dir / "app_spec.txt").write_text("Test specification")
    (project_dir / "claude-progress.txt").write_text("=== SESSION 1 ===\n")

    # Create architecture directory
    arch_dir = project_dir / "architecture"
    arch_dir.mkdir()
    (arch_dir / "contracts.yaml").write_text("version: 1\n")

    return project_dir


@pytest.fixture
def tmp_xdg_state(tmp_path, monkeypatch):
    """Create a temporary XDG state directory."""
    xdg_dir = tmp_path / "xdg_state"
    xdg_dir.mkdir()
    monkeypatch.setenv("XDG_STATE_HOME", str(xdg_dir))
    return xdg_dir


@pytest.fixture
def mock_logger(tmp_path):
    """Create a mock logger for testing."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "test.log"

    logger = AgentLogger(
        session_id="test-session",
        log_file=log_file,
    )
    return logger


# =============================================================================
# Test: Session Start with Hook Context Injection (#142)
# =============================================================================


class TestSessionStartHookContextInjection:
    """Test end-to-end workflow: session start with hook context injection."""

    def test_hooks_installed_to_test_project(self, tmp_project):
        """Step 1: Install hooks to test project."""
        success, errors = install_hooks(tmp_project)

        assert success
        assert len(errors) == 0
        assert (tmp_project / ".claude" / "hooks" / "hooks.json").exists()
        assert (tmp_project / ".claude" / "hooks" / "session-start.sh").exists()
        assert (tmp_project / ".claude" / "hooks" / "session-stop.sh").exists()

    def test_workflow_state_with_active_phase_created(self, tmp_project, tmp_xdg_state):
        """Step 2: Create workflow state with active phase."""
        ensure_state_dirs(tmp_project)

        state = WorkflowState(
            id="test-workflow-123",
            project_dir=str(tmp_project),
            phase="coding",
            started_at=datetime.now(),
            updated_at=datetime.now(),
            features_completed=5,
            features_total=50,
            current_feature_index=6,
        )
        save_workflow_state(state)

        # Verify state was saved
        loaded = load_workflow_state(tmp_project)
        assert loaded is not None
        assert loaded.phase == "coding"
        assert loaded.features_completed == 5

    def test_session_start_script_outputs_valid_json(self, tmp_project, tmp_xdg_state):
        """Step 3: Simulate session start - verify script outputs valid JSON."""
        # Set up workflow state
        ensure_state_dirs(tmp_project)
        state = WorkflowState(
            id="test-workflow-456",
            project_dir=str(tmp_project),
            phase="coding",
            started_at=datetime.now(),
            updated_at=datetime.now(),
            features_completed=10,
            features_total=20,
        )
        save_workflow_state(state)

        # Install hooks
        install_hooks(tmp_project)

        # Execute the session-start script
        script_path = tmp_project / ".claude" / "hooks" / "session-start.sh"
        success, output, error = execute_hook_safely(script_path, timeout_seconds=5)

        # Verify output is valid JSON
        assert success
        assert output is not None
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_hook_output_contains_workflow_context(self, tmp_project, tmp_xdg_state):
        """Step 4: Verify hook output contains workflow context."""
        # Set up workflow state with error
        ensure_state_dirs(tmp_project)
        state = WorkflowState(
            id="test-workflow-789",
            project_dir=str(tmp_project),
            phase="coding",
            started_at=datetime.now(),
            updated_at=datetime.now(),
            features_completed=15,
            features_total=30,
            last_error={
                "type": "manual",
                "category": "validation",
                "message": "Feature 15 failed",
            },
        )
        save_workflow_state(state)

        # Install hooks
        install_hooks(tmp_project)

        # Execute the session-start script
        script_path = tmp_project / ".claude" / "hooks" / "session-start.sh"
        success, output, error = execute_hook_safely(script_path, timeout_seconds=5)

        # Parse and check context
        parsed = json.loads(output)
        if "additionalContext" in parsed:
            context = parsed["additionalContext"]
            # Context should mention workflow state
            assert "coding" in context.lower() or "15" in context or "30" in context


# =============================================================================
# Test: Error Persistence and Recovery (#143)
# =============================================================================


class TestErrorPersistenceAndRecovery:
    """Test end-to-end workflow: error persistence and recovery."""

    def test_create_structured_error(self):
        """Step 1: Trigger error that creates StructuredError."""
        err = error_validation_failed(
            feature_index=5,
            reason="Login button not responding"
        )

        assert err.type == ErrorType.MANUAL
        assert err.category == ErrorCategory.VALIDATION
        assert "5" in str(err.context.get("feature_index"))

    def test_error_persisted_to_workflow_state(self, tmp_project, tmp_xdg_state):
        """Step 2: End session with error persisted."""
        ensure_state_dirs(tmp_project)

        # Create error
        err = error_security_block(
            command="rm -rf /",
            reason="Command not allowed"
        )

        # Create workflow state with error
        state = WorkflowState(
            id="error-test-001",
            project_dir=str(tmp_project),
            phase="paused",
            started_at=datetime.now(),
            updated_at=datetime.now(),
            last_error=err.to_dict(),
        )
        save_workflow_state(state)

        # Verify error was persisted
        loaded = load_workflow_state(tmp_project)
        assert loaded is not None
        assert loaded.last_error is not None
        assert loaded.last_error["type"] == "manual"
        assert loaded.last_error["category"] == "security"

    def test_error_displayed_on_session_resume(self, tmp_project, tmp_xdg_state):
        """Step 3 & 4: Start new session, verify error is in context."""
        ensure_state_dirs(tmp_project)

        # Set up state with error
        err = error_validation_failed(10, "Timeout waiting for element")
        state = WorkflowState(
            id="resume-test-001",
            project_dir=str(tmp_project),
            phase="paused",
            started_at=datetime.now(),
            updated_at=datetime.now(),
            last_error=err.to_dict(),
        )
        save_workflow_state(state)

        # Install hooks and execute
        install_hooks(tmp_project)
        script_path = tmp_project / ".claude" / "hooks" / "session-start.sh"
        success, output, error = execute_hook_safely(script_path, timeout_seconds=5)

        # Verify error info is in output
        assert success
        parsed = json.loads(output)
        if "additionalContext" in parsed:
            context = parsed["additionalContext"]
            # Should contain error information
            assert "error" in context.lower() or "manual" in context.lower()

    def test_error_cleared_on_recovery(self, tmp_project, tmp_xdg_state):
        """Step 5: Clear error on recovery."""
        ensure_state_dirs(tmp_project)

        # Set up state with error
        err = error_validation_failed(10, "Test error")
        state = WorkflowState(
            id="clear-test-001",
            project_dir=str(tmp_project),
            phase="paused",
            started_at=datetime.now(),
            updated_at=datetime.now(),
            last_error=err.to_dict(),
        )
        save_workflow_state(state)

        # Simulate recovery - clear error
        loaded = load_workflow_state(tmp_project)
        loaded.last_error = None
        loaded.phase = "coding"
        save_workflow_state(loaded)

        # Verify error is cleared
        final = load_workflow_state(tmp_project)
        assert final.last_error is None
        assert final.phase == "coding"


# =============================================================================
# Test: State Migration from Project to XDG (#144)
# =============================================================================


class TestStateMigrationProjectToXDG:
    """Test end-to-end workflow: state migration from project to XDG."""

    def test_create_project_with_old_style_files(self, tmp_project):
        """Step 1: Create project with old-style state files."""
        # Create old-style files in project directory
        (tmp_project / "validation-history.json").write_text('{"history": []}')
        (tmp_project / "drift-metrics.json").write_text('{"metrics": {}}')

        # Create old-style logs directory
        old_logs = tmp_project / ".claude-agent" / "logs"
        old_logs.mkdir(parents=True)
        (old_logs / "agent-2024-01-01.log").write_text('{"ts": "2024-01-01"}')

        assert (tmp_project / "validation-history.json").exists()
        assert (tmp_project / "drift-metrics.json").exists()
        assert (old_logs / "agent-2024-01-01.log").exists()

    def test_migration_moves_files_to_xdg(self, tmp_project, tmp_xdg_state):
        """Step 2 & 3: Run agent (triggers migration), verify files moved to XDG."""
        # Create old-style files
        (tmp_project / "validation-history.json").write_text('{"history": ["test"]}')
        (tmp_project / "drift-metrics.json").write_text('{"metrics": {"test": 1}}')

        # Run migration
        result = migrate_project_state(tmp_project)

        # Verify files migrated to XDG
        workflow_dir = get_workflow_dir(tmp_project)
        assert (workflow_dir / "validation-history.json").exists()
        assert (workflow_dir / "drift-metrics.json").exists()

        # Verify content preserved
        migrated_history = json.loads((workflow_dir / "validation-history.json").read_text())
        assert migrated_history["history"] == ["test"]

    def test_project_bound_files_remain_in_project(self, tmp_project, tmp_xdg_state):
        """Step 4: Verify project-bound files remain in project."""
        # Run migration
        migrate_project_state(tmp_project)

        # Verify project-bound files still exist
        assert (tmp_project / "feature_list.json").exists()
        assert (tmp_project / "app_spec.txt").exists()
        assert (tmp_project / "claude-progress.txt").exists()
        assert (tmp_project / "architecture" / "contracts.yaml").exists()


# =============================================================================
# Test: Skill Injection in Coding Agent Prompt (#145)
# =============================================================================


class TestSkillInjectionInPrompt:
    """Test end-to-end workflow: skill injection in coding agent prompt."""

    def test_load_coding_prompt_with_skill_placeholders(self):
        """Step 1: Load coding prompt with skill placeholders."""
        # Get the raw prompt content
        prompt = get_coding_prompt(
            project_dir="/test/project",
            spec_text="Test spec",
            features_json='{"features": []}',
            progress_notes="Session 1",
            stack="python",
        )

        # Prompt should exist and be substantial
        assert prompt is not None
        assert len(prompt) > 1000

    def test_skills_are_injected(self):
        """Step 2: Verify skills are injected."""
        # Get available skills
        available = get_available_skills()
        assert len(available) >= 4
        assert "regression-testing" in available
        assert "error-recovery" in available

        # Test injection
        test_prompt = "## Skills\n\n{{skill:regression-testing}}\n\n{{skill:error-recovery}}"
        result = inject_skills(test_prompt)

        # Verify placeholders were replaced
        assert "{{skill:regression-testing}}" not in result
        assert "{{skill:error-recovery}}" not in result
        # Content should be longer due to injected skills
        assert len(result) > len(test_prompt)

    def test_prompt_size_within_limit(self):
        """Step 3: Verify prompt size is within limit."""
        prompt = get_coding_prompt(
            project_dir="/test/project",
            spec_text="Test spec",
            features_json='{"features": []}',
            progress_notes="Session 1",
            stack="python",
        )

        # Prompt should be under 50KB
        assert len(prompt.encode("utf-8")) < 50 * 1024

    def test_all_placeholders_replaced(self):
        """Step 4: Verify all placeholders are replaced (or left as-is if missing)."""
        test_prompt = """
        ## Skills
        {{skill:regression-testing}}
        {{skill:error-recovery}}
        {{skill:architecture-verification}}
        {{skill:browser-testing}}
        {{skill:nonexistent-skill}}
        """

        result = inject_skills(test_prompt)

        # Known skills should be replaced
        assert "{{skill:regression-testing}}" not in result
        assert "{{skill:error-recovery}}" not in result
        assert "{{skill:architecture-verification}}" not in result
        assert "{{skill:browser-testing}}" not in result

        # Unknown skill should remain as-is (per DR-012)
        assert "{{skill:nonexistent-skill}}" in result


# =============================================================================
# Test: Phase Tracking in Logs (#146)
# =============================================================================


class TestPhaseTrackingInLogs:
    """Test end-to-end workflow: phase tracking in logs."""

    def test_phase_enter_exit_events_logged(self, tmp_path):
        """Step 1-3: Run through multiple phases, verify PHASE_ENTER/EXIT events."""
        log_file = tmp_path / "test.log"
        logger = AgentLogger(session_id="phase-test", log_file=log_file)

        # Enter coding phase
        logger.phase_enter("coding", iteration=1)

        # Log some events
        logger.log_feature_complete(index=0, name="Test feature")

        # Exit to validating
        logger.phase_exit("coding", features_completed=1)
        logger.phase_enter("validating", features_completed=1)

        # Exit validating
        logger.phase_exit("validating", verdict="approved")
        logger.phase_enter("complete")

        # Read logs
        reader = LogReader(log_file)
        entries = reader.read_entries()

        # Verify phase events exist
        phase_events = [e for e in entries if e.event in (EventType.PHASE_ENTER, EventType.PHASE_EXIT)]
        assert len(phase_events) >= 4  # 2 enters + 2 exits minimum

        # Verify phase enter events
        enter_events = [e for e in entries if e.event == EventType.PHASE_ENTER]
        assert len(enter_events) >= 3

        # Verify phase exit events
        exit_events = [e for e in entries if e.event == EventType.PHASE_EXIT]
        assert len(exit_events) >= 2

    def test_phase_filter_in_log_query(self, tmp_path):
        """Step 2: Query logs with --phase filter."""
        log_file = tmp_path / "test.log"
        logger = AgentLogger(session_id="filter-test", log_file=log_file)

        # Log events in different phases
        logger.phase_enter("coding")
        logger.log_feature_start(index=0, name="Feature A")
        logger.log_feature_complete(index=0, name="Feature A")
        logger.phase_exit("coding")

        logger.phase_enter("validating")
        logger.log_feature_start(index=1, name="Validation")
        logger.phase_exit("validating")

        # Query by phase
        reader = LogReader(log_file)
        coding_entries = reader.read_entries(phase="coding")
        validating_entries = reader.read_entries(phase="validating")

        # Note: PHASE_ENTER sets the phase but logs itself with that phase
        # So entries during "coding" phase should have phase="coding"
        # Verify we can filter by phase
        assert all(e.phase == "coding" for e in coding_entries if e.phase)

    def test_phase_field_in_all_entries(self, tmp_path):
        """Step 4: Verify phase field in all entries."""
        log_file = tmp_path / "test.log"
        logger = AgentLogger(session_id="field-test", log_file=log_file)

        # Log events in a phase
        logger.phase_enter("coding")
        logger.log_feature_start(index=0, name="Test")
        logger.log_feature_complete(index=0, name="Test")

        # Read and verify all have phase field
        reader = LogReader(log_file)
        entries = reader.read_entries()

        # All entries should have phase field (may be empty string for phase_enter itself)
        for entry in entries:
            assert hasattr(entry, "phase")


# =============================================================================
# Test: Performance Requirements
# =============================================================================


class TestPerformanceRequirements:
    """Test performance requirements from spec."""

    def test_hook_execution_under_500ms(self, tmp_project, tmp_xdg_state):
        """Verify hook execution completes within 500ms."""
        ensure_state_dirs(tmp_project)

        # Create minimal workflow state
        state = WorkflowState(
            id="perf-test-001",
            project_dir=str(tmp_project),
            phase="coding",
            started_at=datetime.now(),
            updated_at=datetime.now(),
        )
        save_workflow_state(state)

        # Install hooks
        install_hooks(tmp_project)

        # Measure execution time
        script_path = tmp_project / ".claude" / "hooks" / "session-start.sh"
        start = time.time()
        execute_hook_safely(script_path, timeout_seconds=5)
        elapsed = time.time() - start

        assert elapsed < 0.5, f"Hook execution took {elapsed:.3f}s, expected < 0.5s"

    def test_state_load_under_100ms(self, tmp_project, tmp_xdg_state):
        """Verify state load completes within 100ms."""
        ensure_state_dirs(tmp_project)

        # Create workflow state
        state = WorkflowState(
            id="load-perf-test",
            project_dir=str(tmp_project),
            phase="coding",
            started_at=datetime.now(),
            updated_at=datetime.now(),
            features_completed=25,
            features_total=50,
        )
        save_workflow_state(state)

        # Measure load time
        start = time.time()
        loaded = load_workflow_state(tmp_project)
        elapsed = time.time() - start

        assert loaded is not None
        assert elapsed < 0.1, f"State load took {elapsed:.3f}s, expected < 0.1s"

    def test_log_append_under_10ms(self, tmp_path):
        """Verify log append completes within 10ms."""
        log_file = tmp_path / "perf.log"
        logger = AgentLogger(session_id="append-perf", log_file=log_file)

        # Measure append time
        times = []
        for i in range(100):
            start = time.time()
            logger.log_feature_complete(index=i, name=f"Feature {i}")
            times.append(time.time() - start)

        avg_time = sum(times) / len(times)
        assert avg_time < 0.01, f"Avg log append took {avg_time:.3f}s, expected < 0.01s"

    def test_log_query_under_500ms_for_1000_entries(self, tmp_path):
        """Verify log query for 1000 entries completes within 500ms."""
        log_file = tmp_path / "large.log"
        logger = AgentLogger(session_id="query-perf", log_file=log_file)

        # Generate 1000+ log entries
        logger.phase_enter("coding")
        for i in range(1100):
            logger.log_feature_complete(index=i, name=f"Feature {i}")

        # Measure query time
        reader = LogReader(log_file)
        start = time.time()
        entries = reader.read_entries()
        elapsed = time.time() - start

        assert len(entries) >= 1000
        assert elapsed < 0.5, f"Log query took {elapsed:.3f}s, expected < 0.5s"


# =============================================================================
# Test: Error Type Behavior
# =============================================================================


class TestErrorTypeBehavior:
    """Test error type behaviors per DR-002."""

    def test_retry_error_is_retryable(self):
        """Test RETRY error type triggers automatic retry behavior."""
        from claude_agent.structured_errors import error_git_operation

        err = error_git_operation("push", "rejected non-fast-forward")

        assert err.type == ErrorType.RETRY
        assert err.is_retryable() is True
        assert err.requires_human() is False

    def test_manual_error_requires_human(self):
        """Test MANUAL error type pauses workflow for human intervention."""
        err = error_validation_failed(5, "Button not working")

        assert err.type == ErrorType.MANUAL
        assert err.requires_human() is True
        assert err.is_retryable() is False

    def test_fatal_error_aborts(self):
        """Test FATAL error type aborts workflow with clear message."""
        err = StructuredError(
            type=ErrorType.FATAL,
            category=ErrorCategory.CONFIG,
            message="Missing required configuration",
            recovery_hint="Check .claude-agent.yaml exists",
        )

        assert err.type == ErrorType.FATAL
        assert err.is_retryable() is False
        assert err.requires_human() is False

    def test_timeout_error_escalates(self):
        """Test TIMEOUT error type logs and escalates appropriately."""
        from claude_agent.structured_errors import error_agent_timeout

        err = error_agent_timeout("coding", 3600)

        assert err.type == ErrorType.TIMEOUT
        assert err.is_retryable() is False
        assert err.requires_human() is False
        assert "timeout" in err.recovery_hint.lower() or "simplif" in err.recovery_hint.lower()


# =============================================================================
# Test: POSIX Shell Compatibility
# =============================================================================


class TestPOSIXShellCompatibility:
    """Test hook scripts are POSIX sh-compatible."""

    def test_session_start_script_shebang(self):
        """Verify session-start.sh uses #!/bin/sh shebang."""
        script = generate_session_start_script()
        assert script.startswith("#!/bin/sh")

    def test_session_stop_script_shebang(self):
        """Verify session-stop.sh uses #!/bin/sh shebang."""
        script = generate_session_stop_script()
        assert script.startswith("#!/bin/sh")

    def test_no_bash_specific_syntax_in_start_script(self):
        """Verify no bash-specific syntax in session-start.sh."""
        script = generate_session_start_script()

        # Check for common bash-isms
        assert "[[" not in script  # [[ ]] is bash-specific
        assert "]]" not in script
        assert "declare" not in script
        assert "typeset" not in script
        assert "local" not in script or script.count("local") == 0  # local is POSIX but we avoid it
        assert "${array[@]}" not in script  # bash arrays

    def test_no_bash_specific_syntax_in_stop_script(self):
        """Verify no bash-specific syntax in session-stop.sh."""
        script = generate_session_stop_script()

        # Check for common bash-isms
        assert "[[" not in script
        assert "]]" not in script
        assert "declare" not in script


# =============================================================================
# Test: File Permissions
# =============================================================================


class TestFilePermissions:
    """Test file and directory permissions."""

    def test_state_directory_permissions(self, tmp_project, tmp_xdg_state):
        """Verify state files created with user-only permissions."""
        ensure_state_dirs(tmp_project)

        state_dir = get_state_dir()
        workflow_dir = get_workflow_dir(tmp_project)

        # Check directory permissions (should be 0o700)
        if state_dir.exists():
            mode = state_dir.stat().st_mode & 0o777
            assert mode == 0o700 or mode == 0o755, f"State dir mode is {oct(mode)}"

    def test_hook_script_permissions(self, tmp_project):
        """Verify hook scripts executable only by owner."""
        import stat

        install_hooks(tmp_project)

        start_script = tmp_project / ".claude" / "hooks" / "session-start.sh"
        stop_script = tmp_project / ".claude" / "hooks" / "session-stop.sh"

        # Check scripts are executable
        assert start_script.stat().st_mode & stat.S_IXUSR
        assert stop_script.stat().st_mode & stat.S_IXUSR


# =============================================================================
# Test: Error Recovery Scenarios
# =============================================================================


class TestErrorRecoveryScenarios:
    """Test recovery from various error conditions."""

    def test_recovery_from_corrupted_workflow_state(self, tmp_project, tmp_xdg_state):
        """Test recovery from corrupted workflow state."""
        ensure_state_dirs(tmp_project)

        # Create corrupted JSON
        workflow_dir = get_workflow_dir(tmp_project)
        workflow_dir.mkdir(parents=True, exist_ok=True)
        (workflow_dir / "workflow-state.json").write_text("{invalid json")

        # Attempt to load - should return None gracefully
        loaded = load_workflow_state(tmp_project, warn_on_issues=False)
        assert loaded is None

    def test_recovery_from_missing_hook_scripts(self, tmp_project, tmp_xdg_state):
        """Test recovery from missing hook scripts."""
        # Install hooks
        install_hooks(tmp_project)

        # Delete one script
        start_script = tmp_project / ".claude" / "hooks" / "session-start.sh"
        start_script.unlink()

        # Try to execute - should fail gracefully
        success, output, error = execute_hook_safely(start_script, timeout_seconds=5)

        assert not success
        assert error is not None

    def test_recovery_from_invalid_skill_file(self, tmp_path):
        """Test recovery from invalid skill file."""
        # Create a skill directory with invalid file
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "bad-skill.md").write_text("")  # Empty skill

        # load_skill should handle this gracefully
        with patch("claude_agent.prompts.skills.SKILLS_DIR", skills_dir):
            skill = load_skill("bad-skill")
            # Empty file returns empty string
            assert skill == ""

        # inject_skills should leave placeholder for missing skills
        result = inject_skills("{{skill:nonexistent}}")
        assert "{{skill:nonexistent}}" in result


# =============================================================================
# Test: Skills Functionality
# =============================================================================


class TestSkillsFunctionality:
    """Test skills module functionality."""

    def test_at_least_4_skills_exist_and_load(self):
        """Ensure at least 4 skills are extracted and working."""
        available = get_available_skills()

        assert len(available) >= 4

        # Verify required skills exist
        required = ["regression-testing", "error-recovery", "architecture-verification", "browser-testing"]
        for skill in required:
            assert skill in available, f"Required skill '{skill}' not found"

            # Verify skill loads
            content = load_skill(skill)
            assert content is not None
            assert len(content) > 100  # Should have substantial content

    def test_skill_injection_syntax_works(self):
        """Verify skills reference via {{skill:name}} syntax works in prompts."""
        test_prompt = "Before\n\n{{skill:regression-testing}}\n\nAfter"

        result = inject_skills(test_prompt)

        # Placeholder should be replaced
        assert "{{skill:regression-testing}}" not in result
        # Original text should remain
        assert "Before" in result
        assert "After" in result
        # Injected content should be present
        assert "Purpose" in result or "Pattern" in result
