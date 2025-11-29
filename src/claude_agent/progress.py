"""
Progress Tracking
=================

Utilities for tracking and displaying agent progress.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# Spec workflow state file
SPEC_WORKFLOW_FILE = "spec-workflow.json"


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


def count_tests_by_type(project_dir: Path) -> dict:
    """
    Count tests by type (automated vs manual) and status.

    Returns:
        Dict with keys:
        - total: total number of tests
        - passing: tests with passes=true
        - automated_total: tests that can be automated
        - automated_passing: automated tests that pass
        - manual_total: tests requiring manual verification
        - manual_passing: manual tests marked as passing
    """
    feature_list_path = project_dir / "feature_list.json"

    result = {
        "total": 0,
        "passing": 0,
        "automated_total": 0,
        "automated_passing": 0,
        "manual_total": 0,
        "manual_passing": 0,
    }

    if not feature_list_path.exists():
        return result

    try:
        with open(feature_list_path) as f:
            features = json.load(f)

        for f in features:
            result["total"] += 1
            is_passing = f.get("passes", False)
            is_manual = f.get("requires_manual_testing", False)

            if is_passing:
                result["passing"] += 1

            if is_manual:
                result["manual_total"] += 1
                if is_passing:
                    result["manual_passing"] += 1
            else:
                result["automated_total"] += 1
                if is_passing:
                    result["automated_passing"] += 1

        return result
    except (json.JSONDecodeError, IOError):
        return result


def is_automated_work_complete(project_dir: Path) -> bool:
    """
    Check if all automated (non-manual) tests are passing.

    This triggers validation even if manual tests remain.
    """
    counts = count_tests_by_type(project_dir)
    return (
        counts["automated_total"] > 0
        and counts["automated_passing"] == counts["automated_total"]
    )


def get_session_state(project_dir: Path) -> str:
    """
    Determine current session state.

    Returns:
        One of: "fresh", "initialized", "in_progress", "pending_validation",
        "validating", "complete"
    """
    feature_list_path = project_dir / "feature_list.json"
    history_path = project_dir / "validation-history.json"

    if not feature_list_path.exists():
        return "fresh"

    passing, total = count_passing_tests(project_dir)
    counts = count_tests_by_type(project_dir)

    if total == 0:
        return "initialized"
    elif passing == total:
        # All tests pass - check if validation has approved
        if history_path.exists():
            try:
                with open(history_path) as f:
                    data = json.load(f)
                attempts = data.get("attempts", [])
                if attempts and attempts[-1].get("result") == "approved":
                    return "complete"
            except (json.JSONDecodeError, IOError):
                pass
        # All pass but not yet approved
        return "validating"
    elif is_automated_work_complete(project_dir):
        # All automated tests pass, only manual tests remain
        return "pending_validation"
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

    # Show manual test info if any exist
    counts = count_tests_by_type(project_dir)
    if counts["manual_total"] > 0:
        print(f"          (includes {counts['manual_total']} manual test(s) requiring user verification)")


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
    elif state == "validating":
        rejection_count = get_rejection_count(project_dir)
        print(f"\nSession:    VALIDATING (attempt {rejection_count + 1})")
    elif state == "complete":
        print("\nSession:    COMPLETE (all features passing)")

    print()


def load_validation_history(project_dir: Path) -> list[dict]:
    """
    Load validation history from validation-history.json.

    Returns:
        List of validation attempt records, or empty list if none.
    """
    history_path = project_dir / "validation-history.json"

    if not history_path.exists():
        return []

    try:
        with open(history_path) as f:
            data = json.load(f)
        return data.get("attempts", [])
    except (json.JSONDecodeError, IOError):
        return []


def save_validation_attempt(
    project_dir: Path,
    result: str,
    rejected_indices: list[int],
    summary: str,
) -> None:
    """
    Append a validation attempt to history file.

    Args:
        project_dir: Project directory path
        result: "approved" or "rejected"
        rejected_indices: List of test indices that were rejected
        summary: Summary text from validator
    """
    history_path = project_dir / "validation-history.json"

    # Load existing history
    if history_path.exists():
        try:
            with open(history_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            data = {"attempts": []}
    else:
        data = {"attempts": []}

    # Add new attempt
    attempt = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result": result,
        "rejected_indices": rejected_indices,
        "summary": summary,
    }
    data["attempts"].append(attempt)

    # Write back
    with open(history_path, "w") as f:
        json.dump(data, f, indent=2)


def get_rejection_count(project_dir: Path) -> int:
    """
    Count how many validation rejections have occurred.

    Returns:
        Number of rejected validation attempts.
    """
    history = load_validation_history(project_dir)
    return sum(1 for attempt in history if attempt.get("result") == "rejected")


def mark_tests_failed(
    project_dir: Path,
    test_indices: list[int],
    reasons: dict[int, str],
) -> tuple[int, list[str]]:
    """
    Mark specific tests as passes=false in feature_list.json.

    Args:
        project_dir: Project directory path
        test_indices: List of test indices to mark as failed
        reasons: Dict mapping test index to rejection reason

    Returns:
        (count_updated, list_of_errors)
    """
    feature_list_path = project_dir / "feature_list.json"
    temp_path = project_dir / "feature_list.json.tmp"

    errors = []
    updated = 0

    if not feature_list_path.exists():
        return 0, ["feature_list.json does not exist"]

    try:
        with open(feature_list_path) as f:
            features = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        return 0, [f"Failed to read feature_list.json: {e}"]

    # Validate indices
    max_index = len(features) - 1
    valid_indices = []
    for idx in test_indices:
        if idx < 0 or idx > max_index:
            errors.append(f"Invalid test index: {idx} (max: {max_index})")
        else:
            valid_indices.append(idx)

    # Apply updates to valid indices
    for idx in valid_indices:
        if features[idx].get("passes", False):
            features[idx]["passes"] = False
            updated += 1

    # Atomic write (temp file + rename)
    try:
        with open(temp_path, "w") as f:
            json.dump(features, f, indent=2)
        temp_path.rename(feature_list_path)
    except IOError as e:
        errors.append(f"Failed to write feature_list.json: {e}")
        if temp_path.exists():
            temp_path.unlink()

    return updated, errors


# =============================================================================
# Spec Workflow State Tracking
# =============================================================================


def get_spec_workflow_state(project_dir: Path) -> dict:
    """
    Load spec workflow state.

    Returns:
        Dict with keys:
        - phase: "none" | "created" | "validated" | "decomposed"
        - spec_file: Path to current spec file
        - history: List of step records
    """
    workflow_path = project_dir / SPEC_WORKFLOW_FILE

    if not workflow_path.exists():
        return {
            "phase": "none",
            "spec_file": None,
            "history": [],
        }

    try:
        with open(workflow_path) as f:
            data = json.load(f)
        # Ensure required keys exist
        data.setdefault("phase", "none")
        data.setdefault("spec_file", None)
        data.setdefault("history", [])
        return data
    except (json.JSONDecodeError, IOError):
        return {
            "phase": "none",
            "spec_file": None,
            "history": [],
        }


def save_spec_workflow_state(project_dir: Path, state: dict) -> None:
    """Save spec workflow state to file."""
    workflow_path = project_dir / SPEC_WORKFLOW_FILE

    # Add/update timestamps
    now = datetime.now(timezone.utc).isoformat()
    if "created_at" not in state:
        state["created_at"] = now
    state["updated_at"] = now

    with open(workflow_path, "w") as f:
        json.dump(state, f, indent=2)


def record_spec_step(project_dir: Path, step: str, result: dict) -> None:
    """
    Record completion of a spec workflow step.

    Args:
        step: "create" | "validate" | "decompose"
        result: Dict with status, output_file, etc.
    """
    state = get_spec_workflow_state(project_dir)

    # Update phase based on step
    phase_map = {
        "create": "created",
        "validate": "validated",
        "decompose": "decomposed",
    }
    state["phase"] = phase_map.get(step, state["phase"])

    # Update spec_file if provided
    if "output_file" in result:
        state["spec_file"] = result["output_file"]

    # Append to history
    history_entry = {
        "step": step,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **result,
    }
    state["history"].append(history_entry)

    save_spec_workflow_state(project_dir, state)


def get_spec_phase(project_dir: Path) -> str:
    """
    Get current spec workflow phase based on file presence.

    Returns:
        "none" | "created" | "validated" | "decomposed"
    """
    feature_list = project_dir / "feature_list.json"
    validated_spec = project_dir / "spec-validated.md"
    draft_spec = project_dir / "spec-draft.md"

    # Check in order of completion (most complete first)
    if feature_list.exists():
        return "decomposed"
    elif validated_spec.exists():
        return "validated"
    elif draft_spec.exists():
        return "created"
    else:
        return "none"
