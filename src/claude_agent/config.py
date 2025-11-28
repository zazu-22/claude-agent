"""
Configuration Loading
=====================

Load and merge configuration from CLI args, config files, and defaults.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


CONFIG_FILENAME = ".claude-agent.yaml"
CONFIG_FILENAME_ALT = ".claude-agent.yml"


@dataclass
class AgentConfig:
    """Agent-specific configuration."""

    model: str = "claude-opus-4-5-20251101"
    max_iterations: Optional[int] = None
    max_turns: int = 1000
    auto_continue_delay: int = 3


@dataclass
class SecurityConfigOptions:
    """Security configuration options."""

    extra_commands: list[str] = field(default_factory=list)


@dataclass
class Config:
    """Complete configuration for a claude-agent run."""

    # Project settings
    project_dir: Path = field(default_factory=lambda: Path.cwd())
    spec_file: Optional[Path] = None
    goal: Optional[str] = None
    features: int = 50
    stack: Optional[str] = None  # None = auto-detect
    review: bool = False  # Review spec before generating features

    # Agent settings
    agent: AgentConfig = field(default_factory=AgentConfig)

    # Security settings
    security: SecurityConfigOptions = field(default_factory=SecurityConfigOptions)

    @property
    def spec_content(self) -> Optional[str]:
        """Load spec content from file if specified."""
        if self.spec_file and self.spec_file.exists():
            return self.spec_file.read_text()
        return self.goal


def find_config_file(project_dir: Path) -> Optional[Path]:
    """
    Find config file in project directory.

    Checks for .claude-agent.yaml and .claude-agent.yml.
    """
    for filename in (CONFIG_FILENAME, CONFIG_FILENAME_ALT):
        config_path = project_dir / filename
        if config_path.exists():
            return config_path
    return None


def load_config_file(config_path: Path) -> dict[str, Any]:
    """Load configuration from YAML file."""
    with open(config_path) as f:
        data = yaml.safe_load(f) or {}
    return data


def merge_config(
    project_dir: Path,
    cli_spec: Optional[Path] = None,
    cli_goal: Optional[str] = None,
    cli_features: Optional[int] = None,
    cli_stack: Optional[str] = None,
    cli_model: Optional[str] = None,
    cli_max_iterations: Optional[int] = None,
    cli_config_path: Optional[Path] = None,
    cli_review: bool = False,
) -> Config:
    """
    Merge configuration from all sources.

    Priority (highest to lowest):
    1. CLI arguments
    2. Config file
    3. Defaults

    Args:
        project_dir: Project directory path
        cli_*: CLI argument values (None means not specified)
        cli_config_path: Explicit config file path

    Returns:
        Merged Config object
    """
    # Start with defaults
    config = Config(project_dir=project_dir)

    # Load config file if present
    config_path = cli_config_path or find_config_file(project_dir)
    if config_path and config_path.exists():
        file_config = load_config_file(config_path)

        # Apply file config
        if "spec_file" in file_config:
            spec_path = Path(file_config["spec_file"])
            if not spec_path.is_absolute():
                spec_path = project_dir / spec_path
            config.spec_file = spec_path

        if "goal" in file_config:
            config.goal = file_config["goal"]

        if "features" in file_config:
            config.features = file_config["features"]

        if "stack" in file_config:
            config.stack = file_config["stack"]

        # Agent settings
        if "agent" in file_config:
            agent_config = file_config["agent"]
            if "model" in agent_config:
                config.agent.model = agent_config["model"]
            if "max_iterations" in agent_config:
                config.agent.max_iterations = agent_config["max_iterations"]
            if "max_turns" in agent_config:
                config.agent.max_turns = agent_config["max_turns"]
            if "auto_continue_delay" in agent_config:
                config.agent.auto_continue_delay = agent_config["auto_continue_delay"]

        # Security settings
        if "security" in file_config:
            security_config = file_config["security"]
            if "extra_commands" in security_config:
                config.security.extra_commands = security_config["extra_commands"]

    # Apply CLI overrides (highest priority)
    if cli_spec is not None:
        config.spec_file = cli_spec

    if cli_goal is not None:
        config.goal = cli_goal

    if cli_features is not None:
        config.features = cli_features

    if cli_stack is not None:
        config.stack = cli_stack

    if cli_model is not None:
        config.agent.model = cli_model

    if cli_max_iterations is not None:
        config.agent.max_iterations = cli_max_iterations

    if cli_review:
        config.review = cli_review

    return config


def generate_config_template() -> str:
    """Generate a template config file content."""
    return """\
# Claude Agent Configuration
# https://github.com/anthropics/claude-agent

# Specification - provide either spec_file or goal
# spec_file: ./docs/SPEC.md
# goal: "Build a REST API with authentication"

# Number of features to generate (default: 50)
features: 50

# Tech stack - auto-detected if not specified
# Options: node, python
# stack: python

# Agent settings
agent:
  model: claude-opus-4-5-20251101
  # max_iterations: 10  # Limit iterations (default: unlimited)
  # auto_continue_delay: 3  # Seconds between sessions

# Security settings
security:
  extra_commands: []
  # Add additional allowed commands:
  # extra_commands:
  #   - docker
  #   - make
"""
