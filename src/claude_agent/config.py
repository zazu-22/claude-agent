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
class ValidatorConfig:
    """Validator agent configuration."""

    model: str = "claude-opus-4-5-20251101"
    enabled: bool = True
    max_rejections: int = 3  # Max validation failures before stopping
    max_turns: int = 75  # Lower than coding agent - forces quicker verdict


@dataclass
class SecurityConfigOptions:
    """Security configuration options."""

    extra_commands: list[str] = field(default_factory=list)


@dataclass
class WorkflowConfig:
    """Spec workflow configuration."""

    default: str = "full"  # "full" | "spec-only" | "code-only"
    auto_spec_enabled: bool = False
    skip_if_feature_list_exists: bool = True


@dataclass
class LoggingConfig:
    """Logging and observability configuration."""

    enabled: bool = True
    level: str = "info"  # debug, info, warning, error
    include_tool_results: bool = False  # Log full tool results (can be verbose)
    include_allowed_commands: bool = False  # Log security allows (verbose)
    max_summary_length: int = 500  # Truncate long fields
    # Rotation settings
    max_size_mb: int = 10  # Rotate when file exceeds this size
    max_files: int = 5  # Keep this many rotated files
    retention_days: int = 30  # Delete files older than this


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

    # Validator settings
    validator: ValidatorConfig = field(default_factory=ValidatorConfig)

    # Workflow settings
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)

    # Logging settings
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Metrics settings
    metrics_file: str = "drift-metrics.json"

    # Runtime flags (not persisted to config file)
    verbose: bool = False

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
    """Load configuration from YAML file.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Dictionary of configuration values.

    Raises:
        ConfigParseError: If the YAML file has syntax errors.
    """
    from claude_agent.errors import ConfigParseError

    try:
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return data
    except yaml.YAMLError as e:
        # Extract line number if available
        line_number = None
        error_msg = str(e)

        # yaml.YAMLError subclasses have mark attribute with line info
        if hasattr(e, 'problem_mark') and e.problem_mark is not None:
            line_number = e.problem_mark.line + 1  # 0-indexed to 1-indexed
            error_msg = e.problem if hasattr(e, 'problem') and e.problem else str(e)
        elif hasattr(e, 'context_mark') and e.context_mark is not None:
            line_number = e.context_mark.line + 1

        raise ConfigParseError(
            config_path=str(config_path),
            original_error=error_msg,
            line_number=line_number,
        ) from e


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
    cli_verbose: bool = False,
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
        cli_verbose: Enable verbose output

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

        # Validator settings
        if "validator" in file_config:
            validator_config = file_config["validator"]
            if "model" in validator_config:
                config.validator.model = validator_config["model"]
            if "enabled" in validator_config:
                config.validator.enabled = validator_config["enabled"]
            if "max_rejections" in validator_config:
                config.validator.max_rejections = validator_config["max_rejections"]
            if "max_turns" in validator_config:
                config.validator.max_turns = validator_config["max_turns"]

        # Workflow settings
        if "workflow" in file_config:
            workflow_config = file_config["workflow"]
            if "default" in workflow_config:
                config.workflow.default = workflow_config["default"]
            # Handle nested auto_spec section
            if "auto_spec" in workflow_config:
                auto_spec = workflow_config["auto_spec"]
                if "enabled" in auto_spec:
                    config.workflow.auto_spec_enabled = auto_spec["enabled"]
                if "skip_if_feature_list_exists" in auto_spec:
                    config.workflow.skip_if_feature_list_exists = auto_spec[
                        "skip_if_feature_list_exists"
                    ]

        # Logging settings
        if "logging" in file_config:
            logging_config = file_config["logging"]
            if "enabled" in logging_config:
                config.logging.enabled = logging_config["enabled"]
            if "level" in logging_config:
                config.logging.level = logging_config["level"]
            if "include_tool_results" in logging_config:
                config.logging.include_tool_results = logging_config["include_tool_results"]
            if "include_allowed_commands" in logging_config:
                config.logging.include_allowed_commands = logging_config["include_allowed_commands"]
            if "max_summary_length" in logging_config:
                config.logging.max_summary_length = logging_config["max_summary_length"]
            # Handle nested rotation section or flat keys
            if "rotation" in logging_config:
                rotation = logging_config["rotation"]
                if "max_size_mb" in rotation:
                    config.logging.max_size_mb = rotation["max_size_mb"]
                if "max_files" in rotation:
                    config.logging.max_files = rotation["max_files"]
                if "retention_days" in rotation:
                    config.logging.retention_days = rotation["retention_days"]
            else:
                # Also support flat keys for rotation settings
                if "max_size_mb" in logging_config:
                    config.logging.max_size_mb = logging_config["max_size_mb"]
                if "max_files" in logging_config:
                    config.logging.max_files = logging_config["max_files"]
                if "retention_days" in logging_config:
                    config.logging.retention_days = logging_config["retention_days"]

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

    if cli_verbose:
        config.verbose = cli_verbose

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

# Validator settings (runs after all features pass)
validator:
  model: claude-opus-4-5-20251101  # Recommended: use Opus for final validation
  enabled: true
  max_rejections: 3  # Stop after this many validation failures
  max_turns: 75  # Lower than coding agent to force quicker verdict

# Workflow settings
workflow:
  default: full  # "full" | "spec-only" | "code-only"
  auto_spec:
    enabled: false
    skip_if_feature_list_exists: true

# Logging settings
logging:
  enabled: true
  level: info  # debug, info, warning, error
  # include_tool_results: false  # Log full tool results (can be verbose)
  # include_allowed_commands: false  # Log security allows (verbose)
  # max_summary_length: 500  # Truncate long fields
  rotation:
    max_size_mb: 10  # Rotate when file exceeds this size
    max_files: 5  # Keep this many rotated files
    retention_days: 30  # Delete files older than this
"""
