"""
Spec Workflow Interactive Mode
==============================

Interactive helpers for the -i flag on spec subcommands.
"""

from pathlib import Path
from typing import Optional

import questionary
from questionary import Choice

from claude_agent.wizard import WIZARD_STYLE


def interactive_spec_create(project_dir: Path) -> tuple[Optional[str], str]:
    """
    Interactive spec creation with questionary.

    Args:
        project_dir: Project directory path

    Returns:
        (goal, context) tuple, or (None, "") if cancelled
    """
    print("\n" + "=" * 60)
    print("  SPEC CREATION - Interactive Mode")
    print("=" * 60 + "\n")

    goal = questionary.text(
        "What would you like to build?",
        multiline=True,
        instruction="(Press Escape then Enter to submit)",
        style=WIZARD_STYLE,
    ).ask()

    if not goal:
        return None, ""

    add_context = questionary.confirm(
        "Do you have additional context to provide?",
        default=False,
        style=WIZARD_STYLE,
    ).ask()

    context = ""
    if add_context:
        context = questionary.text(
            "Additional context (requirements, constraints, preferences):",
            multiline=True,
            style=WIZARD_STYLE,
        ).ask() or ""

    return goal, context


def interactive_spec_review(spec_path: Path) -> str:
    """
    Review generated spec interactively.

    Args:
        spec_path: Path to the spec file

    Returns:
        Action: "continue" | "view" | "edit" | "regenerate"
    """
    choice = questionary.select(
        "Spec created. What would you like to do?",
        choices=[
            Choice("Continue to validation", value="continue"),
            Choice("View spec", value="view"),
            Choice("Edit in default editor", value="edit"),
            Choice("Regenerate spec", value="regenerate"),
        ],
        style=WIZARD_STYLE,
    ).ask()

    return choice or "continue"


def interactive_validation_review(
    validation_path: Path,
    passed: bool,
) -> str:
    """
    Review validation results interactively.

    Args:
        validation_path: Path to validation report
        passed: Whether validation passed

    Returns:
        Action: "continue" | "view" | "fix" | "override"
    """
    if passed:
        choices = [
            Choice("Continue to decomposition", value="continue"),
            Choice("View validation report", value="view"),
            Choice("Edit validated spec", value="edit"),
        ]
    else:
        choices = [
            Choice("View blocking issues", value="view"),
            Choice("Fix issues manually", value="fix"),
            Choice("Override and continue anyway", value="override"),
        ]

    choice = questionary.select(
        "Validation complete. What would you like to do?",
        choices=choices,
        style=WIZARD_STYLE,
    ).ask()

    return choice or ("continue" if passed else "view")
