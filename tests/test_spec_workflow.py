"""
Tests for spec workflow functionality.

Purpose: Verify spec workflow state tracking, config handling, and CLI integration
work correctly. Each test validates specific behavior that could break if
implementation changes.
"""

import json
from pathlib import Path

import pytest


class TestSpecWorkflowState:
    """Test spec workflow state tracking functions."""

    def test_get_state_returns_empty_for_new_project(self, tmp_path):
        """
        Purpose: Verify that a new project with no workflow file returns
        default empty state, not an error.
        """
        # Import here to allow tests to run even if module not yet implemented
        from claude_agent.progress import get_spec_workflow_state

        state = get_spec_workflow_state(tmp_path)
        assert state["phase"] == "none"
        assert state["history"] == []

    def test_save_and_load_state_roundtrip(self, tmp_path):
        """
        Purpose: Verify state can be saved and loaded without data loss.
        This catches serialization bugs.
        """
        from claude_agent.progress import get_spec_workflow_state, save_spec_workflow_state

        state = {
            "phase": "created",
            "spec_file": "spec-draft.md",
            "history": [{"step": "create", "status": "complete"}],
        }
        save_spec_workflow_state(tmp_path, state)
        loaded = get_spec_workflow_state(tmp_path)
        assert loaded["phase"] == "created"
        assert loaded["history"][0]["step"] == "create"

    def test_record_step_appends_to_history(self, tmp_path):
        """
        Purpose: Verify recording steps accumulates history rather than
        replacing it. This is critical for workflow resumption.
        """
        from claude_agent.progress import get_spec_workflow_state, record_spec_step

        record_spec_step(tmp_path, "create", {"status": "complete"})
        record_spec_step(tmp_path, "validate", {"status": "complete"})

        state = get_spec_workflow_state(tmp_path)
        assert len(state["history"]) == 2
        assert state["history"][0]["step"] == "create"
        assert state["history"][1]["step"] == "validate"


class TestSpecPhaseDetection:
    """Test phase detection based on file presence."""

    def test_phase_none_when_no_files(self, tmp_path):
        """
        Purpose: Empty project should show 'none' phase.
        """
        from claude_agent.progress import get_spec_phase

        assert get_spec_phase(tmp_path) == "none"

    def test_phase_created_when_draft_exists(self, tmp_path):
        """
        Purpose: After spec create, phase should be 'created'.
        """
        from claude_agent.progress import get_spec_phase

        (tmp_path / "spec-draft.md").write_text("# Draft")
        assert get_spec_phase(tmp_path) == "created"

    def test_phase_validated_when_validated_exists(self, tmp_path):
        """
        Purpose: After validation passes, phase should be 'validated'.
        """
        from claude_agent.progress import get_spec_phase

        (tmp_path / "spec-draft.md").write_text("# Draft")
        (tmp_path / "spec-validated.md").write_text("# Validated")
        assert get_spec_phase(tmp_path) == "validated"

    def test_phase_decomposed_when_feature_list_exists(self, tmp_path):
        """
        Purpose: After decomposition, phase should be 'decomposed'.
        """
        from claude_agent.progress import get_spec_phase

        (tmp_path / "spec-draft.md").write_text("# Draft")
        (tmp_path / "spec-validated.md").write_text("# Validated")
        (tmp_path / "feature_list.json").write_text("[]")
        assert get_spec_phase(tmp_path) == "decomposed"


class TestWorkflowConfig:
    """Test WorkflowConfig dataclass."""

    def test_default_values(self):
        """
        Purpose: Verify defaults match documented behavior.
        """
        from claude_agent.config import WorkflowConfig

        config = WorkflowConfig()
        assert config.default == "full"
        assert config.auto_spec_enabled is False
        assert config.skip_if_feature_list_exists is True


class TestPromptLoading:
    """Test spec prompt loader functions."""

    def test_spec_create_prompt_includes_goal(self):
        """
        Purpose: Verify goal is properly substituted into prompt.
        """
        from claude_agent.prompts.loader import get_spec_create_prompt

        prompt = get_spec_create_prompt("Build a todo app")
        assert "Build a todo app" in prompt
        assert "SPEC CREATOR" in prompt

    def test_spec_validate_prompt_includes_content(self):
        """
        Purpose: Verify spec content is included in validation prompt.
        """
        from claude_agent.prompts.loader import get_spec_validate_prompt

        prompt = get_spec_validate_prompt("# My Spec\n\nDetails here")
        assert "My Spec" in prompt
        assert "SPEC VALIDATOR" in prompt

    def test_spec_decompose_prompt_includes_count(self):
        """
        Purpose: Verify feature count is properly templated.
        """
        from claude_agent.prompts.loader import get_spec_decompose_prompt

        prompt = get_spec_decompose_prompt("# Spec", 75)
        assert "75" in prompt
        assert "SPEC DECOMPOSER" in prompt
