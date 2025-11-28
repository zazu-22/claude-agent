"""
Progress Tracking
=================

Utilities for tracking and displaying agent progress.
"""

import json
from pathlib import Path
from typing import Optional


def count_passing_tests(project_dir: Path) -> tuple[int, int]:
    """
    Count passing and total tests from feature_list.json.

    Returns:
        (passing_count, total_count) tuple
    """
    feature_list_path = project_dir / "feature_list.json"

    if not feature_list_path.exists():
        return 0, 0

    try:
        with open(feature_list_path) as f:
            features = json.load(f)

        total = len(features)
        passing = sum(1 for f in features if f.get("passes", False))
        return passing, total
    except (json.JSONDecodeError, IOError):
        return 0, 0


def get_session_state(project_dir: Path) -> str:
    """
    Determine current session state.

    Returns:
        One of: "fresh", "initialized", "in_progress", "complete"
    """
    feature_list_path = project_dir / "feature_list.json"

    if not feature_list_path.exists():
        return "fresh"

    passing, total = count_passing_tests(project_dir)

    if total == 0:
        return "initialized"
    elif passing == total:
        return "complete"
    else:
        return "in_progress"


def print_session_header(session_num: int, is_initializer: bool) -> None:
    """Print formatted session header."""
    print("\n" + "=" * 70)
    if is_initializer:
        print(f"  SESSION {session_num}: INITIALIZER AGENT")
        print("  Creating feature list and project structure...")
    else:
        print(f"  SESSION {session_num}: CODING AGENT")
        print("  Implementing features from feature_list.json...")
    print("=" * 70 + "\n")


def print_progress_summary(project_dir: Path) -> None:
    """Print current progress summary."""
    passing, total = count_passing_tests(project_dir)

    if total == 0:
        print("\nProgress: No features defined yet")
        return

    percentage = (passing / total) * 100
    bar_width = 40
    filled = int(bar_width * passing / total)
    bar = "█" * filled + "░" * (bar_width - filled)

    print(f"\nProgress: [{bar}] {passing}/{total} ({percentage:.1f}%)")


def print_startup_banner(
    project_dir: Path,
    stack: str,
    model: str,
    max_iterations: Optional[int],
) -> None:
    """Print startup banner with configuration summary."""
    print("\n" + "=" * 70)
    print("  CLAUDE AGENT")
    print("=" * 70)
    print(f"\nProject:    {project_dir.resolve()}")
    print(f"Stack:      {stack}")
    print(f"Model:      {model}")

    if max_iterations:
        print(f"Max iters:  {max_iterations}")
    else:
        print("Max iters:  Unlimited")

    state = get_session_state(project_dir)
    if state == "fresh":
        print("\nSession:    NEW PROJECT")
    elif state == "in_progress":
        passing, total = count_passing_tests(project_dir)
        print(f"\nSession:    RESUMING ({passing}/{total} features)")
    elif state == "complete":
        print("\nSession:    COMPLETE (all features passing)")

    print()
