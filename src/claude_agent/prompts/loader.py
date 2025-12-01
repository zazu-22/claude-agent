"""
Prompt Loading Utilities
========================

Load and render prompt templates with variable substitution.
"""

from pathlib import Path


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
    return render_template(
        template,
        {
            "spec_content": spec_content,
            "feature_count": str(feature_count),
            "init_command": init_command,
            "dev_command": dev_command,
        },
    )


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
    return render_template(
        template,
        {
            "init_command": init_command,
            "dev_command": dev_command,
        },
    )


def get_review_prompt(spec_content: str) -> str:
    """
    Load and render the spec review prompt.

    Args:
        spec_content: The project specification content

    Returns:
        Rendered prompt string
    """
    template = load_prompt("review")
    return render_template(
        template,
        {
            "spec_content": spec_content,
        },
    )


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
    return render_template(
        template,
        {
            "init_command": init_command,
            "dev_command": dev_command,
        },
    )


def write_spec_to_project(
    project_dir: Path,
    spec_content: str,
    source_path: Path | None = None,
) -> Path:
    """
    Write spec content to project directory for agent reference.

    External specs (provided via --spec) are copied to specs/app_spec.txt.
    If the source is already inside the specs/ directory, no copy is made.
    If specs/spec-validated.md already exists, a warning is emitted about
    potential conflict.

    Args:
        project_dir: Project directory path
        spec_content: Specification content to write
        source_path: Optional path to the source spec file (to detect if
                     it's already in specs/)

    Returns:
        Path to the written spec file
    """
    import sys

    specs_dir = project_dir / "specs"

    # Check if source is already inside specs/ directory
    if source_path is not None:
        try:
            source_path.resolve().relative_to(specs_dir.resolve())
            # Source is already in specs/ - no need to copy
            return source_path
        except ValueError:
            # Source is outside specs/ - will copy
            pass

    # Check if spec-validated.md already exists (potential conflict)
    spec_validated = specs_dir / "spec-validated.md"
    if spec_validated.exists():
        print(
            "Warning: specs/spec-validated.md already exists. "
            "The external spec will be written to specs/app_spec.txt but "
            "spec-validated.md will take priority for coding agents.",
            file=sys.stderr,
        )

    # Create specs/ directory if needed
    specs_dir.mkdir(parents=True, exist_ok=True)

    # Write to specs/app_spec.txt
    spec_path = specs_dir / "app_spec.txt"
    spec_path.write_text(spec_content)
    return spec_path


# =============================================================================
# Spec Workflow Prompt Loaders
# =============================================================================


def get_spec_create_prompt(goal: str, context: str = "") -> str:
    """
    Load and render the spec creation prompt.

    Args:
        goal: The user's goal or rough idea
        context: Optional additional context

    Returns:
        Rendered prompt string
    """
    template = load_prompt("spec_create")
    context_block = f"\n### ADDITIONAL CONTEXT\n\n{context}" if context else ""
    return render_template(
        template,
        {
            "goal": goal,
            "context": context_block,
        },
    )


def get_spec_validate_prompt(spec_content: str) -> str:
    """
    Load and render the spec validation prompt.

    Args:
        spec_content: The specification content to validate

    Returns:
        Rendered prompt string
    """
    template = load_prompt("spec_validate")
    return render_template(
        template,
        {
            "spec_content": spec_content,
        },
    )


def get_spec_decompose_prompt(spec_content: str, feature_count: int) -> str:
    """
    Load and render the spec decomposition prompt.

    Args:
        spec_content: The specification content to decompose
        feature_count: Target number of features to generate

    Returns:
        Rendered prompt string
    """
    template = load_prompt("spec_decompose")
    return render_template(
        template,
        {
            "spec_content": spec_content,
            "feature_count": str(feature_count),
        },
    )
