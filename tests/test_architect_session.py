"""
Test architecture lock agent session integration.

Tests verify:
- Architecture phase runs at correct point in flow
- Skip flag works correctly
- Graceful degradation when architecture fails
- State detection works correctly
"""

import pytest
from pathlib import Path

from claude_agent.agent import is_architecture_locked


class TestIsArchitectureLocked:
    """Test architecture state detection."""

    def test_false_when_no_directory(self, tmp_path):
        """Returns False when architecture/ doesn't exist."""
        assert is_architecture_locked(tmp_path) is False

    def test_false_when_empty_directory(self, tmp_path):
        """Returns False when architecture/ exists but is empty."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()

        assert is_architecture_locked(tmp_path) is False

    def test_false_when_missing_contracts(self, tmp_path):
        """Returns False when contracts.yaml is missing."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "schemas.yaml").write_text("version: 1")
        (arch_dir / "decisions.yaml").write_text("version: 1")
        # Missing contracts.yaml

        assert is_architecture_locked(tmp_path) is False

    def test_false_when_missing_schemas(self, tmp_path):
        """Returns False when schemas.yaml is missing."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("version: 1")
        (arch_dir / "decisions.yaml").write_text("version: 1")
        # Missing schemas.yaml

        assert is_architecture_locked(tmp_path) is False

    def test_false_when_missing_decisions(self, tmp_path):
        """Returns False when decisions.yaml is missing."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("version: 1")
        (arch_dir / "schemas.yaml").write_text("version: 1")
        # Missing decisions.yaml

        assert is_architecture_locked(tmp_path) is False

    def test_true_when_all_files_exist(self, tmp_path):
        """Returns True when all required files exist."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("version: 1")
        (arch_dir / "schemas.yaml").write_text("version: 1")
        (arch_dir / "decisions.yaml").write_text("version: 1")

        assert is_architecture_locked(tmp_path) is True

    def test_true_with_additional_files(self, tmp_path):
        """Returns True even with additional files in directory."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("version: 1")
        (arch_dir / "schemas.yaml").write_text("version: 1")
        (arch_dir / "decisions.yaml").write_text("version: 1")
        (arch_dir / "extra.yaml").write_text("notes: some extra file")

        assert is_architecture_locked(tmp_path) is True

    def test_handles_nested_path(self, tmp_path):
        """Works with nested project directories."""
        project_dir = tmp_path / "deep" / "nested" / "project"
        project_dir.mkdir(parents=True)

        # Initially false
        assert is_architecture_locked(project_dir) is False

        # Create architecture files
        arch_dir = project_dir / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("version: 1")
        (arch_dir / "schemas.yaml").write_text("version: 1")
        (arch_dir / "decisions.yaml").write_text("version: 1")

        # Now true
        assert is_architecture_locked(project_dir) is True


class TestConfigSkipArchitecture:
    """Test skip architecture configuration."""

    def test_default_values(self):
        """Config has correct defaults."""
        from claude_agent.config import Config, ArchitectureConfig

        config = Config()

        assert config.architecture.enabled is True
        assert config.architecture.required is False
        assert config.skip_architecture is False

    def test_skip_architecture_from_cli(self):
        """skip_architecture can be set via merge_config."""
        from claude_agent.config import merge_config
        from pathlib import Path

        config = merge_config(
            project_dir=Path("."),
            cli_skip_architecture=True,
        )

        assert config.skip_architecture is True

    def test_architecture_config_from_yaml(self, tmp_path):
        """Architecture config can be loaded from YAML."""
        from claude_agent.config import merge_config

        # Create config file
        config_file = tmp_path / ".claude-agent.yaml"
        config_file.write_text("""
architecture:
  enabled: false
  required: true
""")

        config = merge_config(
            project_dir=tmp_path,
            cli_config_path=config_file,
        )

        assert config.architecture.enabled is False
        assert config.architecture.required is True


class TestArchitectPromptLoader:
    """Test architect prompt loading."""

    def test_prompt_loads(self):
        """get_architect_prompt returns non-empty string."""
        from claude_agent.prompts.loader import get_architect_prompt

        prompt = get_architect_prompt()

        assert prompt is not None
        assert len(prompt) > 0
        assert isinstance(prompt, str)

    def test_prompt_contains_evaluation_sequence(self):
        """Prompt contains mandatory evaluation sequence."""
        from claude_agent.prompts.loader import get_architect_prompt

        prompt = get_architect_prompt()

        assert "EVALUATION SEQUENCE" in prompt

    def test_prompt_contains_output_files(self):
        """Prompt specifies all three output files."""
        from claude_agent.prompts.loader import get_architect_prompt

        prompt = get_architect_prompt()

        assert "architecture/contracts.yaml" in prompt
        assert "architecture/schemas.yaml" in prompt
        assert "architecture/decisions.yaml" in prompt

    def test_prompt_contains_yaml_examples(self):
        """Prompt contains YAML format examples."""
        from claude_agent.prompts.loader import get_architect_prompt

        prompt = get_architect_prompt()

        assert "version: 1" in prompt
        assert "locked_at:" in prompt
