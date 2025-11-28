"""
Prompt Loading Utilities
========================

Load and render prompt templates with variable substitution.
"""

import re
from pathlib import Path
from typing import Optional


PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompt_path = PROMPTS_DIR / f"{name}.md"
    return prompt_path.read_text()


def render_template(template: str, variables: dict[str, str]) -> str:
    """
    Render a template with variable substitution.

    Uses {{variable_name}} syntax for placeholders.
    """
    result = template
    for key, value in variables.items():
        placeholder = "{{" + key + "}}"
        result = result.replace(placeholder, str(value))
    return result


def get_initializer_prompt(
    spec_content: str,
    feature_count: int = 50,
    init_command: str = "npm install",
    dev_command: str = "npm run dev",
) -> str:
    """
    Load and render the initializer prompt.

    Args:
        spec_content: The project specification content
        feature_count: Number of features to generate
        init_command: Command to install dependencies
        dev_command: Command to start development server

    Returns:
        Rendered prompt string
    """
    template = load_prompt("initializer")
    return render_template(template, {
        "spec_content": spec_content,
        "feature_count": str(feature_count),
        "init_command": init_command,
        "dev_command": dev_command,
    })


def get_coding_prompt(
    init_command: str = "npm install",
    dev_command: str = "npm run dev",
) -> str:
    """
    Load and render the coding agent prompt.

    Args:
        init_command: Command to install dependencies
        dev_command: Command to start development server

    Returns:
        Rendered prompt string
    """
    template = load_prompt("coding")
    return render_template(template, {
        "init_command": init_command,
        "dev_command": dev_command,
    })


def get_review_prompt(spec_content: str) -> str:
    """
    Load and render the spec review prompt.

    Args:
        spec_content: The project specification content

    Returns:
        Rendered prompt string
    """
    template = load_prompt("review")
    return render_template(template, {
        "spec_content": spec_content,
    })


def get_validator_prompt(
    init_command: str = "npm install",
    dev_command: str = "npm run dev",
) -> str:
    """
    Load and render the validator agent prompt.

    Args:
        init_command: Command to install dependencies
        dev_command: Command to start development server

    Returns:
        Rendered prompt string
    """
    template = load_prompt("validator")
    return render_template(template, {
        "init_command": init_command,
        "dev_command": dev_command,
    })


def write_spec_to_project(project_dir: Path, spec_content: str) -> Path:
    """
    Write spec content to project directory for agent reference.

    Args:
        project_dir: Project directory path
        spec_content: Specification content to write

    Returns:
        Path to the written spec file
    """
    spec_path = project_dir / "app_spec.txt"
    spec_path.write_text(spec_content)
    return spec_path
