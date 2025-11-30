"""
Interactive Wizard
==================

Interactive wizard for generating project specifications when none provided.
"""

from pathlib import Path
from typing import Optional

import questionary
from questionary import Style

from claude_agent.detection import detect_stack


# Custom style for questionary
WIZARD_STYLE = Style(
    [
        ("qmark", "fg:cyan bold"),
        ("question", "bold"),
        ("answer", "fg:cyan"),
        ("pointer", "fg:cyan bold"),
        ("highlighted", "fg:cyan bold"),
        ("selected", "fg:cyan"),
    ]
)


def analyze_existing_codebase(project_dir: Path) -> dict:
    """
    Analyze existing codebase to understand its structure.

    Returns dict with:
        - file_count: Number of files
        - detected_stack: Detected tech stack
        - has_tests: Whether test files exist
        - main_dirs: Main directories found
    """
    info = {
        "file_count": 0,
        "detected_stack": detect_stack(project_dir),
        "has_tests": False,
        "main_dirs": [],
        "has_readme": False,
        "has_config": False,
    }

    if not project_dir.exists():
        return info

    # Count files and check for patterns
    test_patterns = [
        "test_",
        "_test.py",
        ".test.js",
        ".spec.js",
        "tests/",
        "__tests__/",
    ]

    for item in project_dir.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            info["main_dirs"].append(item.name)
            if item.name in ("tests", "__tests__", "test"):
                info["has_tests"] = True
        elif item.is_file():
            info["file_count"] += 1
            if item.name.lower() in ("readme.md", "readme.txt", "readme"):
                info["has_readme"] = True
            if any(p in item.name.lower() for p in test_patterns):
                info["has_tests"] = True

    return info


def run_wizard(project_dir: Path) -> Optional[str]:
    """
    Run interactive wizard to generate a project specification.

    Args:
        project_dir: Path to the project directory

    Returns:
        Generated specification content, or None if cancelled
    """
    print("\n" + "=" * 60)
    print("  CLAUDE AGENT - Interactive Setup Wizard")
    print("=" * 60)
    print("\nNo spec file found. Let's figure out what you want to build!\n")

    # Analyze existing codebase
    analysis = analyze_existing_codebase(project_dir)

    if analysis["file_count"] > 0:
        print("Detected existing project:")
        print(f"  - Stack: {analysis['detected_stack']}")
        print(f"  - Files: {analysis['file_count']}")
        if analysis["main_dirs"]:
            print(f"  - Directories: {', '.join(analysis['main_dirs'][:5])}")
        print()

    # Ask what they want to do
    task_type = questionary.select(
        "What would you like to do?",
        choices=[
            questionary.Choice("Build something new from scratch", value="new"),
            questionary.Choice("Add new features to existing code", value="features"),
            questionary.Choice("Refactor/improve code quality", value="refactor"),
            questionary.Choice("Fix bugs", value="bugs"),
        ],
        style=WIZARD_STYLE,
    ).ask()

    if task_type is None:
        return None

    # Get description based on task type
    if task_type == "new":
        description = questionary.text(
            "Describe what you want to build:",
            multiline=True,
            style=WIZARD_STYLE,
        ).ask()
    elif task_type == "features":
        description = questionary.text(
            "Describe the features you want to add:",
            multiline=True,
            style=WIZARD_STYLE,
        ).ask()
    elif task_type == "refactor":
        description = questionary.text(
            "What aspects do you want to refactor or improve?",
            multiline=True,
            style=WIZARD_STYLE,
        ).ask()
    else:  # bugs
        description = questionary.text(
            "Describe the bugs or issues to fix:",
            multiline=True,
            style=WIZARD_STYLE,
        ).ask()

    if not description:
        return None

    # Ask about thoroughness
    thoroughness = questionary.select(
        "How thorough should the agent be? (affects runtime)",
        choices=[
            questionary.Choice("Quick (20 features) - ~30 min", value=20),
            questionary.Choice("Standard (50 features) - ~2 hours", value=50),
            questionary.Choice("Comprehensive (100 features) - ~4 hours", value=100),
            questionary.Choice("Exhaustive (200 features) - ~8+ hours", value=200),
        ],
        style=WIZARD_STYLE,
    ).ask()

    if thoroughness is None:
        return None

    # Generate spec based on inputs
    spec_content = generate_spec(
        task_type=task_type,
        description=description,
        feature_count=thoroughness,
        analysis=analysis,
    )

    # Show preview and confirm
    print("\n" + "-" * 60)
    print("Generated Specification Preview:")
    print("-" * 60)
    print(spec_content[:500] + "..." if len(spec_content) > 500 else spec_content)
    print("-" * 60)

    # Save spec file
    spec_path = project_dir / ".claude-agent-spec.md"
    spec_path.write_text(spec_content)
    print(f"\nSpec saved to: {spec_path}")

    # Confirm to proceed
    proceed = questionary.confirm(
        "Ready to start? (You can edit the spec file and re-run if needed)",
        default=True,
        style=WIZARD_STYLE,
    ).ask()

    if not proceed:
        print(f"\nSpec saved to: {spec_path}")
        print("Edit it and run claude-agent again when ready.")
        return None

    return spec_content


def generate_spec(
    task_type: str,
    description: str,
    feature_count: int,
    analysis: dict,
) -> str:
    """Generate a specification from wizard inputs."""

    if task_type == "new":
        title = "New Project Specification"
        intro = f"""
## Project Overview

Build the following application from scratch:

{description}

## Requirements

- Production-quality code
- Proper error handling
- Clean, maintainable architecture
- All features must be tested end-to-end
"""
    elif task_type == "features":
        title = "Feature Addition Specification"
        intro = f"""
## Overview

Add the following features to the existing codebase:

{description}

## Requirements

- Integrate seamlessly with existing code
- Maintain existing functionality
- Follow existing code patterns and conventions
- All new features must be tested end-to-end
"""
    elif task_type == "refactor":
        title = "Refactoring Specification"
        intro = f"""
## Overview

Refactor and improve the following aspects of the codebase:

{description}

## Requirements

- Maintain all existing functionality
- Improve code quality and maintainability
- Add tests for refactored code
- Document any API changes
"""
    else:  # bugs
        title = "Bug Fix Specification"
        intro = f"""
## Overview

Fix the following bugs and issues:

{description}

## Requirements

- Fix all described issues
- Add regression tests
- Ensure no new bugs are introduced
- Document root causes and fixes
"""

    # Add tech stack info if detected
    stack_section = ""
    if analysis["detected_stack"]:
        stack_section = f"""
## Technology Stack

Detected stack: {analysis["detected_stack"]}

Follow the conventions and patterns already established in this codebase.
"""

    # Add existing structure info
    structure_section = ""
    if analysis["main_dirs"]:
        structure_section = f"""
## Existing Structure

Main directories: {", ".join(analysis["main_dirs"][:10])}

Preserve the existing project structure and naming conventions.
"""

    return f"""# {title}

{intro}
{stack_section}
{structure_section}

## Testing

The agent will create {feature_count} detailed test cases in feature_list.json.
Each test case will be verified through the actual UI using browser automation.

## Notes

This specification was generated by the Claude Agent wizard.
Feel free to edit this file to add more details or requirements.
"""
