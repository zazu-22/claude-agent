"""
Decision Record Protocol
========================

Capture and query architectural decisions made during coding sessions.
Implements append-only decision log as specified in drift-mitigation-design.md.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

# Module-level constants for decisions file path
ARCH_DIR_NAME = "architecture"
DECISIONS_FILE = "decisions.yaml"


@dataclass
class DecisionRecord:
    """
    A single architectural decision record.

    Captures the full context of why a decision was made, enabling future
    sessions to understand constraints and avoid conflicting choices.

    Required fields:
        id: Format "DR-NNN" (e.g., "DR-001")
        topic: What was being decided
        choice: What was chosen

    Optional fields (None when not provided):
        timestamp: ISO format timestamp when decision was made
        session: Session number that made this decision
        rationale: Why this choice was made
        alternatives_considered: Other options evaluated
        constraints_created: What future sessions must honor
        affects_features: Feature indices affected by this decision
    """

    # Required fields
    id: str  # Format: "DR-NNN"
    topic: str  # What was being decided
    choice: str  # What was chosen

    # Optional fields with None defaults for consistency
    timestamp: Optional[str] = None  # ISO format
    session: Optional[int] = None  # Session number that made this decision
    rationale: Optional[str] = None  # Why this choice was made
    alternatives_considered: list[str] = field(default_factory=list)  # Other options evaluated
    constraints_created: list[str] = field(default_factory=list)  # What future sessions must honor
    affects_features: list[int] = field(default_factory=list)  # Feature indices


def get_decisions_path(project_dir: Path) -> Path:
    """Get path to decisions file."""
    return project_dir / ARCH_DIR_NAME / DECISIONS_FILE


class DecisionLoadError(Exception):
    """Error loading or parsing decision records."""

    pass


def load_decisions(project_dir: Path) -> list[DecisionRecord]:
    """
    Load all decision records from the decisions file.

    Args:
        project_dir: Project directory path

    Returns:
        List of DecisionRecord objects, empty list if file doesn't exist

    Raises:
        DecisionLoadError: If YAML is malformed or required fields are missing
    """
    decisions_path = get_decisions_path(project_dir)

    if not decisions_path.exists():
        return []

    try:
        with open(decisions_path) as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise DecisionLoadError(
            f"Failed to parse decisions.yaml: {e}"
        ) from e

    if not isinstance(data, dict):
        raise DecisionLoadError(
            f"Invalid decisions.yaml format: expected dict, got {type(data).__name__}"
        )

    decisions_list = data.get("decisions", [])
    if not isinstance(decisions_list, list):
        raise DecisionLoadError(
            f"Invalid 'decisions' field: expected list, got {type(decisions_list).__name__}"
        )

    records = []
    required_fields = ["id", "topic", "choice"]

    for i, d in enumerate(decisions_list):
        if not isinstance(d, dict):
            raise DecisionLoadError(
                f"Invalid decision at index {i}: expected dict, got {type(d).__name__}"
            )

        # Check required fields
        missing = [f for f in required_fields if f not in d]
        if missing:
            raise DecisionLoadError(
                f"Decision at index {i} missing required fields: {', '.join(missing)}"
            )

        records.append(DecisionRecord(
            id=d["id"],
            topic=d["topic"],
            choice=d["choice"],
            timestamp=d.get("timestamp"),  # None if not provided
            session=d.get("session"),  # None if not provided
            rationale=d.get("rationale"),  # None if not provided
            alternatives_considered=d.get("alternatives_considered", []),
            constraints_created=d.get("constraints_created", []),
            affects_features=d.get("affects_features", []),
        ))

    return records


def append_decision(project_dir: Path, record: DecisionRecord) -> None:
    """
    Append a new decision record to the decisions file.

    This is append-only - existing decisions are never modified.

    Args:
        project_dir: Project directory path
        record: DecisionRecord to append
    """
    decisions_path = get_decisions_path(project_dir)

    # Ensure architecture directory exists
    decisions_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing decisions
    if decisions_path.exists():
        with open(decisions_path) as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {"version": 1, "locked_at": datetime.now(timezone.utc).isoformat()}

    if "decisions" not in data:
        data["decisions"] = []

    # Append new decision
    data["decisions"].append({
        "id": record.id,
        "timestamp": record.timestamp,
        "session": record.session,
        "topic": record.topic,
        "choice": record.choice,
        "alternatives_considered": record.alternatives_considered,
        "rationale": record.rationale,
        "constraints_created": record.constraints_created,
        "affects_features": record.affects_features,
    })

    # Write back
    with open(decisions_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def get_next_decision_id(project_dir: Path) -> str:
    """
    Get the next available decision ID.

    Note: This function assumes single-agent execution. If concurrent agents
    are supported in the future, a lock file or atomic ID allocation mechanism
    would be needed to prevent duplicate IDs. Consider using UUIDs or timestamps
    for uniqueness if concurrency becomes a requirement.

    Args:
        project_dir: Project directory path

    Returns:
        String like "DR-001", "DR-002", etc.
    """
    decisions = load_decisions(project_dir)

    if not decisions:
        return "DR-001"

    # Extract numeric part from last ID
    last_id = decisions[-1].id
    try:
        num = int(last_id.split("-")[1])
        return f"DR-{num + 1:03d}"
    except (IndexError, ValueError):
        return f"DR-{len(decisions) + 1:03d}"


def get_relevant_decisions(
    project_dir: Path,
    feature_index: int,
) -> list[DecisionRecord]:
    """
    Get decisions relevant to a specific feature.

    Args:
        project_dir: Project directory path
        feature_index: Index of the feature in feature_list.json

    Returns:
        List of DecisionRecords that affect this feature
    """
    decisions = load_decisions(project_dir)
    return [d for d in decisions if feature_index in d.affects_features]


def get_all_constraints(project_dir: Path) -> list[str]:
    """
    Get all constraints created by all decisions.

    Returns:
        Flat list of all constraint strings
    """
    decisions = load_decisions(project_dir)
    constraints = []
    for d in decisions:
        constraints.extend(d.constraints_created)
    return constraints


def validate_feature_references(
    project_dir: Path,
    decision: DecisionRecord,
    feature_count: int,
) -> list[str]:
    """
    Validate that feature indices in a decision are within valid bounds.

    This is an optional validation that checks feature indices against the
    actual feature list size. Useful for catching errors when decisions
    reference non-existent features.

    Args:
        project_dir: Project directory path
        decision: The decision record to validate
        feature_count: Total number of features in feature_list.json

    Returns:
        List of error messages (empty if all references are valid)

    Example:
        >>> errors = validate_feature_references(project_dir, decision, 50)
        >>> if errors:
        ...     for err in errors:
        ...         print(f"Warning: {err}")
    """
    errors = []
    max_index = feature_count - 1

    for idx in decision.affects_features:
        if idx < 0:
            errors.append(
                f"Decision {decision.id} has negative feature index {idx}"
            )
        elif idx > max_index:
            errors.append(
                f"Decision {decision.id} references feature index {idx}, "
                f"but only {feature_count} features exist (max index: {max_index})"
            )

    return errors


def validate_all_feature_references(
    project_dir: Path,
    feature_count: int,
) -> list[str]:
    """
    Validate all decisions have valid feature references.

    Args:
        project_dir: Project directory path
        feature_count: Total number of features in feature_list.json

    Returns:
        List of error messages (empty if all references are valid)
    """
    decisions = load_decisions(project_dir)
    all_errors = []
    for decision in decisions:
        errors = validate_feature_references(project_dir, decision, feature_count)
        all_errors.extend(errors)
    return all_errors
