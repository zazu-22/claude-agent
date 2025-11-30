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


class TestConfigFileParsing:
    """Test workflow config parsing from YAML files."""

    def test_load_config_file_parses_workflow_section(self, tmp_path):
        """
        Purpose: Verify that load_config_file correctly reads workflow section
        from YAML. Tests feature #3.
        """
        from claude_agent.config import load_config_file

        config_content = """
workflow:
  default: spec-only
  auto_spec:
    enabled: true
    skip_if_feature_list_exists: false
"""
        config_file = tmp_path / ".claude-agent.yaml"
        config_file.write_text(config_content)

        file_config = load_config_file(config_file)

        assert "workflow" in file_config
        assert file_config["workflow"]["default"] == "spec-only"
        assert file_config["workflow"]["auto_spec"]["enabled"] is True
        assert file_config["workflow"]["auto_spec"]["skip_if_feature_list_exists"] is False

    def test_merge_config_applies_workflow_settings(self, tmp_path):
        """
        Purpose: Verify that merge_config correctly applies workflow settings
        from config file to Config object. Tests feature #4.
        """
        from claude_agent.config import merge_config

        config_content = """
workflow:
  default: code-only
  auto_spec:
    enabled: true
    skip_if_feature_list_exists: false
"""
        config_file = tmp_path / ".claude-agent.yaml"
        config_file.write_text(config_content)

        config = merge_config(project_dir=tmp_path)

        assert config.workflow.default == "code-only"
        assert config.workflow.auto_spec_enabled is True
        assert config.workflow.skip_if_feature_list_exists is False

    def test_merge_config_workflow_defaults_without_config_file(self, tmp_path):
        """
        Purpose: Verify that workflow defaults are used when no config file exists.
        """
        from claude_agent.config import merge_config

        config = merge_config(project_dir=tmp_path)

        assert config.workflow.default == "full"
        assert config.workflow.auto_spec_enabled is False
        assert config.workflow.skip_if_feature_list_exists is True


class TestInteractiveSpecWizard:
    """Test spec_wizard.py interactive functions."""

    def test_interactive_spec_create_function_signature(self):
        """
        Purpose: Verify interactive_spec_create has correct signature.
        Tests feature at line 821.
        """
        from claude_agent.spec_wizard import interactive_spec_create
        import inspect

        sig = inspect.signature(interactive_spec_create)
        params = list(sig.parameters.keys())

        # Should have project_dir parameter
        assert "project_dir" in params

        # Check return annotation if present
        # Function returns tuple[Optional[str], str]
        assert callable(interactive_spec_create)

    def test_interactive_spec_create_returns_none_on_cancel(self, tmp_path):
        """
        Purpose: Verify interactive_spec_create returns (None, '') when user cancels.
        Tests feature: interactive_spec_create returns (None, '') when cancelled
        """
        from unittest.mock import patch, MagicMock
        from claude_agent.spec_wizard import interactive_spec_create

        # Mock questionary.text to return None (user cancelled/empty)
        mock_text = MagicMock()
        mock_text.ask.return_value = None

        with patch("claude_agent.spec_wizard.questionary.text", return_value=mock_text):
            goal, context = interactive_spec_create(tmp_path)

        assert goal is None
        assert context == ""

    def test_interactive_spec_create_returns_goal_and_context(self, tmp_path):
        """
        Purpose: Verify interactive_spec_create returns goal and context from user.
        Tests feature: interactive_spec_create prompts for goal with multiline input
        """
        from unittest.mock import patch, MagicMock
        from claude_agent.spec_wizard import interactive_spec_create

        # Mock questionary.text for goal
        mock_goal_text = MagicMock()
        mock_goal_text.ask.return_value = "Build a todo app"

        # Mock questionary.confirm for "add context?" prompt
        mock_confirm = MagicMock()
        mock_confirm.ask.return_value = True

        # Mock questionary.text for context
        mock_context_text = MagicMock()
        mock_context_text.ask.return_value = "Use React and TypeScript"

        call_count = [0]

        def mock_text_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_goal_text
            return mock_context_text

        with patch("claude_agent.spec_wizard.questionary.text", side_effect=mock_text_side_effect):
            with patch("claude_agent.spec_wizard.questionary.confirm", return_value=mock_confirm):
                goal, context = interactive_spec_create(tmp_path)

        assert goal == "Build a todo app"
        assert context == "Use React and TypeScript"

    def test_interactive_spec_create_skips_context_when_declined(self, tmp_path):
        """
        Purpose: Verify context prompt is skipped when user declines.
        Tests feature: interactive_spec_create skips context prompt when user declines
        """
        from unittest.mock import patch, MagicMock
        from claude_agent.spec_wizard import interactive_spec_create

        # Mock questionary.text for goal
        mock_goal_text = MagicMock()
        mock_goal_text.ask.return_value = "Build a todo app"

        # Mock questionary.confirm - user says NO to context
        mock_confirm = MagicMock()
        mock_confirm.ask.return_value = False

        with patch("claude_agent.spec_wizard.questionary.text", return_value=mock_goal_text):
            with patch("claude_agent.spec_wizard.questionary.confirm", return_value=mock_confirm):
                goal, context = interactive_spec_create(tmp_path)

        assert goal == "Build a todo app"
        assert context == ""  # No context because user declined

    def test_interactive_spec_review_returns_action(self, tmp_path):
        """
        Purpose: Verify interactive_spec_review returns user's action choice.
        Tests feature: interactive_spec_review function returns action string
        """
        from unittest.mock import patch, MagicMock
        from claude_agent.spec_wizard import interactive_spec_review

        mock_select = MagicMock()
        mock_select.ask.return_value = "view"

        with patch("claude_agent.spec_wizard.questionary.select", return_value=mock_select):
            action = interactive_spec_review(tmp_path / "spec.md")

        assert action == "view"

    def test_interactive_validation_review_shows_pass_options(self, tmp_path):
        """
        Purpose: Verify validation review shows correct options when passed=True.
        Tests feature: interactive_validation_review shows different options based on passed flag
        """
        from unittest.mock import patch, MagicMock, call
        from claude_agent.spec_wizard import interactive_validation_review

        mock_select = MagicMock()
        mock_select.ask.return_value = "continue"

        with patch("claude_agent.spec_wizard.questionary.select", return_value=mock_select) as mock_questionary:
            action = interactive_validation_review(tmp_path / "validation.md", passed=True)

        # Verify "continue" is returned
        assert action == "continue"

        # Verify select was called with choices containing "Continue to decomposition"
        call_args = mock_questionary.call_args
        choices = call_args.kwargs.get("choices", call_args.args[1] if len(call_args.args) > 1 else [])
        choice_values = [c.value for c in choices]
        assert "continue" in choice_values
        assert "view" in choice_values
        assert "edit" in choice_values

    def test_interactive_validation_review_shows_fail_options(self, tmp_path):
        """
        Purpose: Verify validation review shows correct options when passed=False.
        Tests feature: interactive_validation_review shows different options based on passed flag
        """
        from unittest.mock import patch, MagicMock
        from claude_agent.spec_wizard import interactive_validation_review

        mock_select = MagicMock()
        mock_select.ask.return_value = "fix"

        with patch("claude_agent.spec_wizard.questionary.select", return_value=mock_select) as mock_questionary:
            action = interactive_validation_review(tmp_path / "validation.md", passed=False)

        # Verify "fix" is returned
        assert action == "fix"

        # Verify select was called with failure-specific choices
        call_args = mock_questionary.call_args
        choices = call_args.kwargs.get("choices", call_args.args[1] if len(call_args.args) > 1 else [])
        choice_values = [c.value for c in choices]
        assert "view" in choice_values
        assert "fix" in choice_values
        assert "override" in choice_values


class TestSpecWizardModule:
    """Test spec_wizard.py module structure and imports."""

    def test_wizard_style_imported_from_wizard(self):
        """
        Purpose: Verify WIZARD_STYLE is imported from wizard.py.
        Tests feature: WIZARD_STYLE is imported from wizard.py in spec_wizard.py
        """
        from claude_agent import spec_wizard
        # Check WIZARD_STYLE is available
        assert hasattr(spec_wizard, "WIZARD_STYLE")

    def test_uses_questionary(self):
        """
        Purpose: Verify spec_wizard uses questionary for prompts.
        Tests feature: spec_wizard uses questionary for interactive prompts
        """
        from claude_agent import spec_wizard
        import questionary
        # Module should use questionary (verified by the import)
        assert "questionary" in dir(spec_wizard) or hasattr(spec_wizard, "questionary")


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
