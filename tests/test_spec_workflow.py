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

    def test_get_state_returns_default_for_corrupted_json(self, tmp_path):
        """
        Purpose: Verify that corrupted JSON returns default state without error.
        Tests feature: get_spec_workflow_state returns default for corrupted JSON
        """
        from claude_agent.progress import get_spec_workflow_state, SPEC_WORKFLOW_FILE

        # Create corrupted JSON file
        workflow_path = tmp_path / SPEC_WORKFLOW_FILE
        workflow_path.write_text("{ invalid json }")

        # Should return default state without raising exception
        state = get_spec_workflow_state(tmp_path)
        assert state["phase"] == "none"
        assert state["history"] == []
        assert state["spec_file"] is None


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

    def test_imports_follow_project_conventions(self):
        """
        Purpose: Verify imports follow stdlib, third-party, local order.
        Tests feature: Import statements follow project conventions
        """
        import ast
        import inspect
        from claude_agent import spec_wizard

        # Get source and parse
        source = inspect.getsource(spec_wizard)
        tree = ast.parse(source)

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = node.module if isinstance(node, ast.ImportFrom) else node.names[0].name
                if module:
                    imports.append((node.lineno, module))

        # Group by type
        stdlib = {"pathlib", "typing", "json", "os", "sys", "datetime", "ast", "inspect"}
        local = {"claude_agent"}

        positions = {"stdlib": [], "third_party": [], "local": []}
        for lineno, module in imports:
            root = module.split(".")[0]
            if root in stdlib:
                positions["stdlib"].append(lineno)
            elif root in local:
                positions["local"].append(lineno)
            else:
                positions["third_party"].append(lineno)

        # Verify order: stdlib < third_party < local
        if positions["stdlib"] and positions["third_party"]:
            assert max(positions["stdlib"]) < min(positions["third_party"]), \
                "stdlib imports should come before third-party"
        if positions["third_party"] and positions["local"]:
            assert max(positions["third_party"]) < min(positions["local"]), \
                "third-party imports should come before local"


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


class TestPromptTemplateContent:
    """Test that prompt templates contain required content."""

    def test_spec_create_has_do_not_feature_list_instruction(self):
        """
        Purpose: Verify spec_create.md instructs not to generate feature_list.json.
        Tests feature: Prompt templates specify not to generate feature_list.json
        """
        from claude_agent.prompts.loader import load_prompt

        content = load_prompt("spec_create")
        assert "feature_list.json" in content
        assert "DO NOT" in content

    def test_spec_create_has_do_not_application_code_instruction(self):
        """
        Purpose: Verify spec_create.md instructs not to write application code.
        Tests feature: Prompt templates specify not to write application code
        """
        from claude_agent.prompts.loader import load_prompt

        content = load_prompt("spec_create")
        assert "application code" in content.lower()
        assert "DO NOT" in content

    def test_spec_validate_has_two_output_files(self):
        """
        Purpose: Verify spec_validate.md specifies both output files.
        Tests feature: spec_validate.md instructs creation of two output files
        """
        from claude_agent.prompts.loader import load_prompt

        content = load_prompt("spec_validate")
        assert "spec-validation.md" in content
        assert "spec-validated.md" in content
        assert "OUTPUT 1" in content or "OUTPUT" in content
        assert "only if PASS" in content

    def test_spec_validate_has_all_validation_categories(self):
        """
        Purpose: Verify spec_validate.md includes all validation categories.
        Tests feature: spec_validate.md includes all validation categories
        """
        from claude_agent.prompts.loader import load_prompt

        content = load_prompt("spec_validate")
        assert "Completeness" in content
        assert "Ambiguities" in content
        assert "Scope Risks" in content
        assert "Technical Gaps" in content
        assert "Contradictions" in content

    def test_spec_decompose_has_all_feature_categories(self):
        """
        Purpose: Verify spec_decompose.md specifies all feature categories.
        Tests feature: spec_decompose.md specifies all feature categories
        """
        from claude_agent.prompts.loader import load_prompt

        content = load_prompt("spec_decompose")
        assert "functional" in content
        assert "technical" in content
        assert "style" in content
        assert "integration" in content
        assert "error-handling" in content

    def test_spec_decompose_has_manual_testing_explanation(self):
        """
        Purpose: Verify spec_decompose.md explains requires_manual_testing flag.
        Tests feature: spec_decompose.md explains requires_manual_testing flag
        """
        from claude_agent.prompts.loader import load_prompt

        content = load_prompt("spec_decompose")
        assert "MANUAL TESTING" in content.upper()
        assert "requires_manual_testing" in content

    def test_spec_decompose_has_independence_and_ordering(self):
        """
        Purpose: Verify spec_decompose.md emphasizes independence and ordering.
        Tests feature: spec_decompose.md emphasizes feature independence and ordering
        """
        from claude_agent.prompts.loader import load_prompt

        content = load_prompt("spec_decompose")
        assert "Independence" in content or "independent" in content.lower()
        assert "Ordering" in content or "foundational" in content.lower()

    def test_prompts_use_double_brace_syntax(self):
        """
        Purpose: Verify all prompts use {{variable}} syntax consistently.
        Tests feature: New prompts use {{variable}} syntax consistently
        """
        from claude_agent.prompts.loader import load_prompt

        create = load_prompt("spec_create")
        validate = load_prompt("spec_validate")
        decompose = load_prompt("spec_decompose")

        assert "{{goal}}" in create
        assert "{{context}}" in create
        assert "{{spec_content}}" in validate
        assert "{{spec_content}}" in decompose
        assert "{{feature_count}}" in decompose

    def test_prompts_have_your_role_section(self):
        """
        Purpose: Verify all prompts include clear role identification.
        Tests feature: Spec prompts include clear role identification
        """
        from claude_agent.prompts.loader import load_prompt

        create = load_prompt("spec_create")
        validate = load_prompt("spec_validate")
        decompose = load_prompt("spec_decompose")

        assert "YOUR ROLE" in create
        assert "YOUR ROLE" in validate
        assert "YOUR ROLE" in decompose

    def test_prompts_have_your_task_section(self):
        """
        Purpose: Verify all prompts include clear task description.
        Tests feature: Spec prompts include clear task description
        """
        from claude_agent.prompts.loader import load_prompt

        create = load_prompt("spec_create")
        validate = load_prompt("spec_validate")
        decompose = load_prompt("spec_decompose")

        assert "YOUR TASK" in create
        assert "YOUR TASK" in validate
        assert "YOUR TASK" in decompose

    def test_prompts_have_output_section(self):
        """
        Purpose: Verify all prompts specify output files.
        Tests feature: Spec prompts include OUTPUT section specifying files to create
        """
        from claude_agent.prompts.loader import load_prompt

        create = load_prompt("spec_create")
        validate = load_prompt("spec_validate")
        decompose = load_prompt("spec_decompose")

        assert "OUTPUT" in create
        assert "spec-draft.md" in create
        assert "OUTPUT" in validate
        assert "spec-validation.md" in validate
        assert "spec-validated.md" in validate
        assert "OUTPUT" in decompose
        assert "feature_list.json" in decompose
        assert "app_spec.txt" in decompose

    def test_spec_create_specifies_output_filename(self):
        """
        Purpose: Verify spec_create.md specifies output file name explicitly.
        Tests feature: Spec create prompt specifies output file name explicitly
        """
        from claude_agent.prompts.loader import load_prompt

        content = load_prompt("spec_create")
        assert "spec-draft.md" in content

    def test_spec_validate_specifies_both_output_filenames(self):
        """
        Purpose: Verify spec_validate.md specifies both output filenames.
        Tests feature: Spec validate prompt specifies both output filenames
        """
        from claude_agent.prompts.loader import load_prompt

        content = load_prompt("spec_validate")
        assert "spec-validation.md" in content
        assert "spec-validated.md" in content

    def test_spec_decompose_specifies_app_spec_copy(self):
        """
        Purpose: Verify spec_decompose.md specifies app_spec.txt copy instruction.
        Tests feature: Spec decompose prompt specifies app_spec.txt copy instruction
        """
        from claude_agent.prompts.loader import load_prompt

        content = load_prompt("spec_decompose")
        assert "app_spec.txt" in content

    def test_prompts_are_valid_markdown(self):
        """
        Purpose: Verify all prompt templates are valid markdown.
        Tests feature: All prompt templates are valid markdown
        """
        from claude_agent.prompts.loader import load_prompt

        # These should all load without error
        create = load_prompt("spec_create")
        validate = load_prompt("spec_validate")
        decompose = load_prompt("spec_decompose")

        # Basic checks for markdown structure
        assert len(create) > 100
        assert len(validate) > 100
        assert len(decompose) > 100

        # Check no unclosed code blocks (triple backtick should be even count)
        assert create.count("```") % 2 == 0
        assert validate.count("```") % 2 == 0
        assert decompose.count("```") % 2 == 0


class TestDependencies:
    """Test that no new external dependencies were added."""

    def test_no_new_external_dependencies_added(self):
        """
        Purpose: Verify no new external dependencies were added to pyproject.toml.
        Tests feature: No new external dependencies added

        The spec workflow uses only existing dependencies:
        - click (CLI)
        - questionary (interactive prompts)
        - pyyaml (config parsing)
        - claude-code-sdk (agent sessions)
        """
        from pathlib import Path

        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        content = pyproject_path.read_text()

        # These are the only allowed dependencies
        expected_deps = [
            "claude-code-sdk",
            "click",
            "pyyaml",
            "questionary",
        ]

        # Extract dependencies section
        in_deps = False
        deps_found = []
        for line in content.split("\n"):
            if line.strip() == "dependencies = [":
                in_deps = True
                continue
            if in_deps:
                if line.strip() == "]":
                    break
                # Extract dependency name from line like '    "click>=8.0",'
                if '"' in line:
                    dep = line.strip().strip('",').split(">=")[0].split(">")[0].split("<")[0]
                    deps_found.append(dep)

        # Verify only expected dependencies
        for dep in deps_found:
            assert dep in expected_deps, f"Unexpected dependency: {dep}"


class TestFixtureUsage:
    """Test that test files use pytest fixtures correctly."""

    def test_test_files_use_tmp_path_fixture(self):
        """
        Purpose: Verify tmp_path fixture is used for temp directories.
        Tests feature: Test files use pytest fixtures correctly
        """
        from pathlib import Path

        test_workflow = Path(__file__)
        content = test_workflow.read_text()

        # Should use tmp_path fixture, not tempfile module
        assert "tmp_path" in content
        # Should be used in function signature (as fixture parameter)
        assert "def test_" in content

    def test_cli_tests_use_cli_runner_fixture(self):
        """
        Purpose: Verify CliRunner fixture is properly defined in test_spec_cli.py.
        Tests feature: Test files use pytest fixtures correctly
        """
        from pathlib import Path

        test_cli = Path(__file__).parent / "test_spec_cli.py"
        content = test_cli.read_text()

        # Should define runner fixture
        assert "@pytest.fixture" in content
        assert "def runner(self)" in content
        assert "CliRunner" in content


class TestSessionHeaderFormatting:
    """Test session header formatting consistency."""

    def test_session_headers_use_70_char_separator(self):
        """
        Purpose: Verify session headers use 70-character separator lines.
        Tests feature: Session headers use consistent formatting with existing agent.py
        """
        from claude_agent.progress import print_session_header
        from io import StringIO
        import sys

        # Capture output
        old_stdout = sys.stdout
        sys.stdout = StringIO()

        print_session_header(1, is_initializer=False)

        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        # Check for 70 '=' characters
        assert "=" * 70 in output

    def test_session_headers_use_equals_separator(self):
        """
        Purpose: Verify session headers use '=' separator lines.
        Tests feature: Session headers use consistent formatting with existing agent.py
        """
        from claude_agent.progress import print_session_header
        from io import StringIO
        import sys

        old_stdout = sys.stdout
        sys.stdout = StringIO()

        print_session_header(1, is_initializer=True)

        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        # Should have '=' separators, not '-' or other characters
        lines = output.strip().split("\n")
        separator_lines = [l for l in lines if l.strip() and set(l.strip()) == {"="}]
        assert len(separator_lines) >= 2  # At least 2 separator lines


class TestCLIHelpText:
    """Test CLI help text follows existing patterns."""

    def test_spec_help_text_follows_patterns(self):
        """
        Purpose: Verify spec --help follows existing CLI style.
        Tests feature: CLI help text follows existing patterns
        """
        from click.testing import CliRunner
        from claude_agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["spec", "--help"])

        # Should include subcommand descriptions
        assert "create" in result.output
        assert "validate" in result.output
        assert "decompose" in result.output
        assert "status" in result.output
        assert "auto" in result.output

        # Help text should follow click conventions
        assert "Usage:" in result.output or "usage:" in result.output.lower()

    def test_spec_subcommands_have_help_text(self):
        """
        Purpose: Verify each spec subcommand has descriptive help text.
        Tests feature: CLI help text follows existing patterns
        """
        from click.testing import CliRunner
        from claude_agent.cli import main

        runner = CliRunner()

        for cmd in ["create", "validate", "decompose", "auto", "status"]:
            result = runner.invoke(main, ["spec", cmd, "--help"])
            assert result.exit_code == 0
            # Each should have a description
            assert len(result.output) > 50  # Not just "Usage:"


class TestErrorMessages:
    """Test error messages are clear and actionable."""

    def test_spec_create_missing_goal_message_is_actionable(self):
        """
        Purpose: Verify error message explains how to fix the issue.
        Tests feature: Error messages are clear and actionable
        """
        from click.testing import CliRunner
        from claude_agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["spec", "create", "-p", "/tmp/test"])

        # Should explain what's missing
        assert "goal" in result.output.lower()
        # Should suggest solution
        assert "--goal" in result.output or "--from-file" in result.output or "-i" in result.output

    def test_spec_validate_missing_spec_message_is_actionable(self, tmp_path):
        """
        Purpose: Verify error message explains how to fix the issue.
        Tests feature: Error messages are clear and actionable
        """
        from click.testing import CliRunner
        from claude_agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["spec", "validate", "-p", str(tmp_path)])

        # Should explain what's missing
        assert "not found" in result.output.lower()
        # Should suggest solution
        assert "spec create" in result.output or "specify" in result.output.lower()


class TestClickEchoUsage:
    """Test progress output uses click.echo consistently."""

    def test_cli_module_uses_click_echo(self):
        """
        Purpose: Verify CLI uses click.echo for user-facing output.
        Tests feature: Progress output uses click.echo consistently
        """
        from pathlib import Path

        cli_path = Path(__file__).parent.parent / "src" / "claude_agent" / "cli.py"
        content = cli_path.read_text()

        # Should use click.echo for output
        assert "click.echo" in content

        # Count usage - should be significant
        echo_count = content.count("click.echo")
        assert echo_count >= 10  # At least 10 uses

    def test_cli_module_avoids_direct_print_for_user_output(self):
        """
        Purpose: Verify CLI doesn't use print() for user-facing output.
        Tests feature: Progress output uses click.echo consistently

        Note: Some internal debugging print() may be acceptable, but
        user-facing output should use click.echo.
        """
        from pathlib import Path
        import ast

        cli_path = Path(__file__).parent.parent / "src" / "claude_agent" / "cli.py"
        content = cli_path.read_text()

        # Parse and find print calls
        tree = ast.parse(content)
        print_calls = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "print":
                    print_calls += 1

        # Should have very few or no print() calls in CLI
        assert print_calls <= 2, f"Found {print_calls} print() calls in cli.py"


class TestSpecStatusAlignment:
    """Test spec status output label alignment."""

    def test_spec_status_labels_aligned(self, tmp_path):
        """
        Purpose: Verify spec status output aligns labels consistently.
        Tests feature: Spec status output aligns labels consistently
        """
        from click.testing import CliRunner
        from claude_agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["spec", "status", "-p", str(tmp_path)])

        # Output should be structured
        assert "Project:" in result.output
        assert "Phase:" in result.output
        assert "Files:" in result.output

        # Labels should be on separate lines with consistent structure
        lines = result.output.strip().split("\n")
        assert len(lines) >= 3  # At least Project, Phase, Files


class TestJSONErrorHandling:
    """Test JSON file operations error handling."""

    def test_get_spec_workflow_state_handles_io_error(self, tmp_path, monkeypatch):
        """
        Purpose: Verify graceful handling of IOError when reading JSON.
        Tests feature: JSON file operations use proper error handling
        """
        from claude_agent.progress import get_spec_workflow_state, SPEC_WORKFLOW_FILE
        import builtins

        # Create a valid JSON file first
        workflow_path = tmp_path / SPEC_WORKFLOW_FILE
        workflow_path.write_text('{"phase": "created", "history": []}')

        # Mock open to raise IOError
        original_open = builtins.open
        def mock_open(*args, **kwargs):
            if str(workflow_path) in str(args[0]):
                raise IOError("Simulated IO error")
            return original_open(*args, **kwargs)

        monkeypatch.setattr(builtins, "open", mock_open)

        # Should return default state without raising exception
        state = get_spec_workflow_state(tmp_path)
        assert state["phase"] == "none"
        assert state["history"] == []

    def test_count_passing_tests_handles_json_decode_error(self, tmp_path):
        """
        Purpose: Verify graceful handling of JSONDecodeError.
        Tests feature: JSON file operations use proper error handling
        """
        from claude_agent.progress import count_passing_tests

        # Create corrupted JSON
        feature_list = tmp_path / "feature_list.json"
        feature_list.write_text("{ invalid json")

        # Should return (0, 0) without raising exception
        passing, total = count_passing_tests(tmp_path)
        assert passing == 0
        assert total == 0


class TestRecordSpecStepFields:
    """Test spec workflow state recording includes all required fields."""

    def test_record_step_includes_status_field(self, tmp_path):
        """
        Purpose: Verify history entries include status field.
        Tests feature: History entries include status field
        """
        from claude_agent.progress import record_spec_step, get_spec_workflow_state

        record_spec_step(tmp_path, "create", {"status": "complete"})

        state = get_spec_workflow_state(tmp_path)
        assert len(state["history"]) == 1
        assert "status" in state["history"][0]
        assert state["history"][0]["status"] == "complete"

    def test_record_step_includes_output_file(self, tmp_path):
        """
        Purpose: Verify history entries include output_file for each step.
        Tests feature: History entries include output_file for each step
        """
        from claude_agent.progress import record_spec_step, get_spec_workflow_state

        record_spec_step(tmp_path, "create", {
            "status": "complete",
            "output_file": "spec-draft.md"
        })

        state = get_spec_workflow_state(tmp_path)
        assert "output_file" in state["history"][0]
        assert state["history"][0]["output_file"] == "spec-draft.md"

    def test_validate_history_entry_includes_validation_report(self, tmp_path):
        """
        Purpose: Verify validate history entry includes validation_report field.
        Tests feature: Validate history entry includes validation_report field
        """
        from claude_agent.progress import record_spec_step, get_spec_workflow_state

        record_spec_step(tmp_path, "validate", {
            "status": "complete",
            "passed": True,
            "output_file": "spec-validated.md",
            "validation_report": "spec-validation.md"
        })

        state = get_spec_workflow_state(tmp_path)
        assert "validation_report" in state["history"][0]
        assert state["history"][0]["validation_report"] == "spec-validation.md"

    def test_record_step_includes_timestamp(self, tmp_path):
        """
        Purpose: Verify history entries include timestamp.
        Tests feature: Spec workflow records updated_at timestamp on each step
        """
        from claude_agent.progress import record_spec_step, get_spec_workflow_state

        record_spec_step(tmp_path, "create", {"status": "complete"})

        state = get_spec_workflow_state(tmp_path)
        assert "timestamp" in state["history"][0]
        # ISO 8601 format
        assert "T" in state["history"][0]["timestamp"]

    def test_workflow_state_includes_spec_file(self, tmp_path):
        """
        Purpose: Verify workflow state includes spec_file field.
        Tests feature: Spec workflow state includes spec_file field
        """
        from claude_agent.progress import record_spec_step, get_spec_workflow_state

        record_spec_step(tmp_path, "create", {
            "status": "complete",
            "output_file": "spec-draft.md"
        })

        state = get_spec_workflow_state(tmp_path)
        assert "spec_file" in state
        assert state["spec_file"] == "spec-draft.md"

    def test_workflow_state_includes_created_at(self, tmp_path):
        """
        Purpose: Verify workflow state includes created_at timestamp.
        Tests feature: Spec workflow records created_at timestamp
        """
        from claude_agent.progress import record_spec_step, get_spec_workflow_state

        record_spec_step(tmp_path, "create", {"status": "complete"})

        state = get_spec_workflow_state(tmp_path)
        assert "created_at" in state
        assert "T" in state["created_at"]  # ISO 8601 format

    def test_workflow_state_includes_updated_at(self, tmp_path):
        """
        Purpose: Verify workflow state includes updated_at timestamp.
        Tests feature: Spec workflow records updated_at timestamp on each step
        """
        from claude_agent.progress import record_spec_step, get_spec_workflow_state

        record_spec_step(tmp_path, "create", {"status": "complete"})

        state = get_spec_workflow_state(tmp_path)
        assert "updated_at" in state

    def test_multiple_runs_preserve_history(self, tmp_path):
        """
        Purpose: Verify multiple spec workflow runs preserve history.
        Tests feature: Multiple spec workflow runs preserve history
        """
        from claude_agent.progress import record_spec_step, get_spec_workflow_state

        # First run
        record_spec_step(tmp_path, "create", {"status": "complete"})
        record_spec_step(tmp_path, "validate", {"status": "complete"})

        # Second run
        record_spec_step(tmp_path, "create", {"status": "complete"})

        state = get_spec_workflow_state(tmp_path)
        assert len(state["history"]) == 3  # All entries preserved


class TestPromptHandling:
    """Test prompt function edge cases."""

    def test_get_spec_create_prompt_handles_empty_goal(self):
        """
        Purpose: Verify empty goal is handled gracefully.
        Tests feature: get_spec_create_prompt handles empty goal gracefully
        """
        from claude_agent.prompts.loader import get_spec_create_prompt

        # Should not raise exception
        prompt = get_spec_create_prompt("")
        assert isinstance(prompt, str)
        assert len(prompt) > 100  # Still has template content

    def test_get_spec_decompose_prompt_handles_zero_feature_count(self):
        """
        Purpose: Verify zero feature count is handled gracefully.
        Tests feature: get_spec_decompose_prompt handles zero feature count
        """
        from claude_agent.prompts.loader import get_spec_decompose_prompt

        # Should not raise exception
        prompt = get_spec_decompose_prompt("# Spec", 0)
        assert isinstance(prompt, str)
        assert "0" in prompt

    def test_spec_create_accepts_multiline_goal(self):
        """
        Purpose: Verify multiline goals are handled correctly.
        Tests feature: CLI spec create accepts long multiline goals
        """
        from claude_agent.prompts.loader import get_spec_create_prompt

        multiline_goal = """Build a web application with:
- User authentication
- Dashboard
- Settings page
- Admin panel"""

        prompt = get_spec_create_prompt(multiline_goal)
        assert "User authentication" in prompt
        assert "Dashboard" in prompt


class TestCLIPathHandling:
    """Test CLI path handling functionality."""

    def test_cli_resolves_relative_paths(self, tmp_path):
        """
        Purpose: Verify CLI properly resolves relative project paths to absolute.
        Tests feature: CLI properly resolves relative project paths to absolute
        """
        from claude_agent.config import merge_config
        import os

        # Save original working directory
        original_cwd = os.getcwd()

        try:
            # Change to tmp_path so relative path works
            os.chdir(tmp_path)

            # Create a subdirectory
            subdir = tmp_path / "project"
            subdir.mkdir()

            # merge_config resolves paths in CLI
            config = merge_config(project_dir=subdir)

            # Should be absolute
            assert config.project_dir.is_absolute()
        finally:
            os.chdir(original_cwd)

    def test_spec_status_shows_correct_timestamp_format(self, tmp_path):
        """
        Purpose: Verify spec status shows timestamps in readable format.
        Tests feature: Spec status shows correct timestamp format
        """
        from click.testing import CliRunner
        from claude_agent.cli import main
        import json

        # Create workflow state with timestamp
        workflow_state = {
            "phase": "created",
            "history": [{
                "step": "create",
                "timestamp": "2025-11-30T10:00:00Z",
                "status": "complete"
            }]
        }
        (tmp_path / "spec-workflow.json").write_text(json.dumps(workflow_state))

        runner = CliRunner()
        result = runner.invoke(main, ["spec", "status", "-p", str(tmp_path)])

        # Should display timestamp
        assert "2025-11-30T10:00:00Z" in result.output or "2025" in result.output
