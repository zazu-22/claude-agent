"""
Tech Stack Detection
====================

Auto-detect project tech stack from marker files.
Searches current directory and parent directories up to git root.
"""

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Stack signatures for detection
STACK_SIGNATURES = {
    "node": {
        "markers": [
            "package.json",
            "tsconfig.json",
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
        ],
        "commands": ["npm", "npx", "node", "yarn", "pnpm"],
        "pkill_targets": ["node", "npm", "npx", "vite", "next", "webpack"],
        "init_command": "npm install",
        "dev_command": "npm run dev",
    },
    "python": {
        "markers": [
            "pyproject.toml",
            "setup.py",
            "requirements.txt",
            "Pipfile",
            "poetry.lock",
            "uv.lock",
        ],
        "commands": [
            "python",
            "python3",
            "pip",
            "pip3",
            "uv",
            "poetry",
            "pytest",
            "ruff",
            "mypy",
        ],
        "pkill_targets": ["python", "python3", "uvicorn", "gunicorn", "flask"],
        "init_command": "pip install -r requirements.txt",
        "dev_command": "python main.py",
    },
}

# Base commands allowed for all stacks
BASE_COMMANDS = {
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "grep",
    "cp",
    "mkdir",
    "chmod",
    "pwd",
    "git",
    "ps",
    "lsof",
    "sleep",
    "pkill",
    "init.sh",
}


@dataclass
class StackDetectionResult:
    """Result of stack detection with metadata."""

    stack: str
    detected_at: Optional[Path]  # Directory where marker was found, None if defaulted
    marker_found: Optional[str]  # Which marker file triggered detection
    is_explicit: bool  # True if from config, False if auto-detected
    is_default: bool  # True if no markers found and using fallback

    @property
    def warning_message(self) -> Optional[str]:
        """Return warning message if detection was ambiguous."""
        if self.is_default:
            return (
                f"No stack markers found. Defaulting to '{self.stack}'. "
                "Set 'stack:' explicitly in .claude-agent.yaml to avoid this warning."
            )
        return None


def find_git_root(start_dir: Path) -> Optional[Path]:
    """
    Find the git repository root starting from a directory.

    Args:
        start_dir: Directory to start searching from

    Returns:
        Path to git root, or None if not in a git repo
    """
    current = start_dir.resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return None


def find_project_root(start_dir: Path) -> Path:
    """
    Find the project root by looking for stack markers or git root.

    Searches from start_dir up to git root (or filesystem root).
    Returns the directory containing the first marker found,
    or git root if no markers found, or start_dir as last resort.

    Args:
        start_dir: Directory to start searching from

    Returns:
        Best guess at project root directory
    """
    start_dir = start_dir.resolve()
    git_root = find_git_root(start_dir)
    stop_at = git_root.parent if git_root else start_dir.parent

    current = start_dir
    while current != stop_at and current != current.parent:
        # Check for any stack marker
        for stack_info in STACK_SIGNATURES.values():
            for marker in stack_info["markers"]:
                if (current / marker).exists():
                    return current
        current = current.parent

    # No markers found - return git root if available, otherwise start_dir
    return git_root if git_root else start_dir


def detect_stack_in_directory(directory: Path) -> Optional[tuple[str, str]]:
    """
    Check a single directory for stack markers.

    Args:
        directory: Directory to check

    Returns:
        Tuple of (stack_name, marker_file) if found, None otherwise
    """
    for stack_name, stack_info in STACK_SIGNATURES.items():
        for marker in stack_info["markers"]:
            if (directory / marker).exists():
                return (stack_name, marker)
    return None


def detect_stack(
    project_dir: Path,
    search_parents: bool = True,
    default_stack: str = "python",
) -> StackDetectionResult:
    """
    Detect tech stack from project marker files.

    Searches the project directory and optionally parent directories
    up to the git root for stack marker files.

    Args:
        project_dir: Path to the project directory
        search_parents: If True, search parent directories up to git root
        default_stack: Stack to use if no markers found (default: python)

    Returns:
        StackDetectionResult with detection details
    """
    project_dir = project_dir.resolve()

    if not project_dir.exists():
        return StackDetectionResult(
            stack=default_stack,
            detected_at=None,
            marker_found=None,
            is_explicit=False,
            is_default=True,
        )

    # First check the project directory itself
    result = detect_stack_in_directory(project_dir)
    if result:
        return StackDetectionResult(
            stack=result[0],
            detected_at=project_dir,
            marker_found=result[1],
            is_explicit=False,
            is_default=False,
        )

    # Search parent directories if enabled
    if search_parents:
        git_root = find_git_root(project_dir)
        stop_at = git_root.parent if git_root else project_dir

        current = project_dir.parent
        while current != stop_at and current != current.parent:
            result = detect_stack_in_directory(current)
            if result:
                return StackDetectionResult(
                    stack=result[0],
                    detected_at=current,
                    marker_found=result[1],
                    is_explicit=False,
                    is_default=False,
                )
            current = current.parent

    # No markers found - return default with warning flag
    return StackDetectionResult(
        stack=default_stack,
        detected_at=None,
        marker_found=None,
        is_explicit=False,
        is_default=True,
    )


def detect_stack_simple(project_dir: Path) -> str:
    """
    Simple stack detection returning just the stack name.

    This is a convenience wrapper for backward compatibility.
    Emits a warning if no markers found and defaulting.

    Args:
        project_dir: Path to the project directory

    Returns:
        Detected stack name
    """
    result = detect_stack(project_dir)
    if result.warning_message:
        warnings.warn(result.warning_message, UserWarning, stacklevel=2)
    return result.stack


def get_stack_commands(stack: str) -> set[str]:
    """Get allowed commands for a stack."""
    stack_info = STACK_SIGNATURES.get(stack, STACK_SIGNATURES["python"])
    return BASE_COMMANDS | set(stack_info["commands"])


def get_stack_pkill_targets(stack: str) -> set[str]:
    """Get allowed pkill targets for a stack."""
    stack_info = STACK_SIGNATURES.get(stack, STACK_SIGNATURES["python"])
    return set(stack_info["pkill_targets"])


def get_stack_init_command(stack: str) -> str:
    """Get default init command for a stack."""
    stack_info = STACK_SIGNATURES.get(stack, STACK_SIGNATURES["python"])
    return stack_info["init_command"]


def get_stack_dev_command(stack: str) -> str:
    """Get default dev command for a stack."""
    stack_info = STACK_SIGNATURES.get(stack, STACK_SIGNATURES["python"])
    return stack_info["dev_command"]


def get_available_stacks() -> list[str]:
    """Get list of available stack names."""
    return list(STACK_SIGNATURES.keys())
