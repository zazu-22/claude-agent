"""
Tech Stack Detection
====================

Auto-detect project tech stack from marker files.
"""

from pathlib import Path


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


def detect_stack(project_dir: Path) -> str:
    """
    Detect tech stack from project marker files.

    Args:
        project_dir: Path to the project directory

    Returns:
        Detected stack name ("node", "python") or "node" as default
    """
    if not project_dir.exists():
        return "node"  # Default for new projects

    # Check each stack's markers
    for stack_name, stack_info in STACK_SIGNATURES.items():
        for marker in stack_info["markers"]:
            marker_path = project_dir / marker
            if marker_path.exists():
                return stack_name

    # Default to node if no markers found
    return "node"


def get_stack_commands(stack: str) -> set[str]:
    """Get allowed commands for a stack."""
    stack_info = STACK_SIGNATURES.get(stack, STACK_SIGNATURES["node"])
    return BASE_COMMANDS | set(stack_info["commands"])


def get_stack_pkill_targets(stack: str) -> set[str]:
    """Get allowed pkill targets for a stack."""
    stack_info = STACK_SIGNATURES.get(stack, STACK_SIGNATURES["node"])
    return set(stack_info["pkill_targets"])


def get_stack_init_command(stack: str) -> str:
    """Get default init command for a stack."""
    stack_info = STACK_SIGNATURES.get(stack, STACK_SIGNATURES["node"])
    return stack_info["init_command"]


def get_stack_dev_command(stack: str) -> str:
    """Get default dev command for a stack."""
    stack_info = STACK_SIGNATURES.get(stack, STACK_SIGNATURES["node"])
    return stack_info["dev_command"]


def get_available_stacks() -> list[str]:
    """Get list of available stack names."""
    return list(STACK_SIGNATURES.keys())
