"""
Skills Module
=============

Modular, injectable knowledge modules for agent prompts.

This module provides skill loading and injection capabilities, allowing
reusable knowledge patterns to be extracted from prompts and loaded
dynamically at runtime.

Skills are markdown files stored in this directory that can be injected
into prompts using the {{skill:name}} placeholder syntax.

Key Functions:
- load_skill(skill_name): Load a skill's content by name
- get_available_skills(): List all available skill names
- inject_skills(prompt, skill_names): Replace placeholders with skill content

Architecture Decision References:
- DR-012: Placeholder format is exactly {{skill:name}}
- DR-013: Soft limit of 50KB per assembled prompt with warning
- DR-014: Four required skills: regression-testing, error-recovery,
          architecture-verification, browser-testing
"""

import logging
import re
from pathlib import Path
from typing import Optional

# Module-level constants
SKILLS_DIR = Path(__file__).parent
SKILL_PLACEHOLDER_PATTERN = re.compile(r"\{\{skill:([a-zA-Z0-9_-]+)\}\}")
MAX_PROMPT_SIZE_BYTES = 50 * 1024  # 50KB soft limit (DR-013)

# Logger for this module
logger = logging.getLogger(__name__)


def load_skill(skill_name: str) -> Optional[str]:
    """
    Load a skill's markdown content by name.

    Args:
        skill_name: Name of the skill (without .md extension)

    Returns:
        The skill's markdown content, or None if not found

    Example:
        >>> content = load_skill("regression-testing")
        >>> if content:
        ...     print("Skill loaded successfully")
    """
    skill_path = SKILLS_DIR / f"{skill_name}.md"

    try:
        if not skill_path.exists():
            logger.debug(f"Skill not found: {skill_name} (looked in {skill_path})")
            return None

        content = skill_path.read_text(encoding="utf-8")
        logger.debug(f"Loaded skill: {skill_name} ({len(content)} bytes)")
        return content

    except OSError as e:
        logger.warning(f"Error reading skill '{skill_name}': {e}")
        return None


def get_available_skills() -> list[str]:
    """
    List all available skill names.

    Returns:
        Sorted list of skill names (without .md extension).
        Returns empty list if no skills found or directory doesn't exist.

    Example:
        >>> skills = get_available_skills()
        >>> print(skills)
        ['architecture-verification', 'browser-testing', 'error-recovery', 'regression-testing']
    """
    try:
        if not SKILLS_DIR.exists():
            return []

        skills = []
        for path in SKILLS_DIR.glob("*.md"):
            # Exclude files starting with underscore (internal/draft)
            if not path.name.startswith("_"):
                skills.append(path.stem)

        return sorted(skills)

    except OSError as e:
        logger.warning(f"Error listing skills: {e}")
        return []


def inject_skills(prompt: str, skill_names: Optional[list[str]] = None) -> str:
    """
    Replace {{skill:name}} placeholders with skill content.

    This function finds all skill placeholders in the prompt and replaces
    them with the corresponding skill content. If a skill is not found,
    the placeholder is left as-is (per DR-012).

    Args:
        prompt: The prompt template containing {{skill:name}} placeholders
        skill_names: Optional list of skill names to inject. If None,
                    all placeholders in the prompt are processed.

    Returns:
        The prompt with placeholders replaced by skill content.
        Missing skills leave their placeholders unchanged.

    Note:
        A warning is logged if the assembled prompt exceeds 50KB (DR-013).

    Example:
        >>> prompt = "Instructions: {{skill:regression-testing}}"
        >>> result = inject_skills(prompt)
        >>> "{{skill:regression-testing}}" not in result  # replaced if skill exists
    """
    if not prompt:
        return prompt

    def replace_skill(match: re.Match) -> str:
        """Replace a single skill placeholder."""
        skill_name = match.group(1)

        # If skill_names is specified, only inject those skills
        if skill_names is not None and skill_name not in skill_names:
            return match.group(0)  # Leave placeholder as-is

        content = load_skill(skill_name)
        if content is None:
            logger.warning(f"Skill placeholder left unchanged: {{{{skill:{skill_name}}}}}")
            return match.group(0)  # Leave placeholder as-is per DR-012

        return content

    # Replace all skill placeholders
    result = SKILL_PLACEHOLDER_PATTERN.sub(replace_skill, prompt)

    # Check prompt size and warn if exceeded (DR-013)
    result_size = len(result.encode("utf-8"))
    if result_size > MAX_PROMPT_SIZE_BYTES:
        logger.warning(
            f"Assembled prompt exceeds 50KB soft limit: {result_size} bytes "
            f"({result_size / 1024:.1f} KB). Consider reducing skill content."
        )

    return result


def validate_skill_structure(skill_name: str) -> tuple[bool, list[str]]:
    """
    Validate that a skill file has the required structure.

    Per DR-014, each skill MUST have these sections:
    - Purpose
    - When to Use
    - Pattern

    Args:
        skill_name: Name of the skill to validate

    Returns:
        Tuple of (is_valid, list of error messages).
        If valid, error list is empty.

    Example:
        >>> valid, errors = validate_skill_structure("regression-testing")
        >>> if not valid:
        ...     print("Errors:", errors)
    """
    content = load_skill(skill_name)
    if content is None:
        return False, [f"Skill '{skill_name}' not found"]

    errors = []
    required_sections = ["Purpose", "When to Use", "Pattern"]

    for section in required_sections:
        # Look for section as markdown heading (## Section or # Section)
        pattern = rf"^#{{1,2}}\s+{re.escape(section)}"
        if not re.search(pattern, content, re.MULTILINE | re.IGNORECASE):
            errors.append(f"Missing required section: '{section}'")

    return len(errors) == 0, errors


def get_skill_size(skill_name: str) -> Optional[int]:
    """
    Get the size of a skill file in bytes.

    Useful for checking individual skill sizes against the ~5KB guideline.

    Args:
        skill_name: Name of the skill

    Returns:
        Size in bytes, or None if skill not found
    """
    content = load_skill(skill_name)
    if content is None:
        return None
    return len(content.encode("utf-8"))


# Module exports
__all__ = [
    "load_skill",
    "get_available_skills",
    "inject_skills",
    "validate_skill_structure",
    "get_skill_size",
    "SKILLS_DIR",
    "MAX_PROMPT_SIZE_BYTES",
]
