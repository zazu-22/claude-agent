"""
Decision Record Protocol
========================

Capture and query architectural decisions made during coding sessions.
Implements append-only decision log as specified in drift-mitigation-design.md.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml


@dataclass
class DecisionRecord:
    """
    A single architectural decision record.

    Captures the full context of why a decision was made, enabling future
    sessions to understand constraints and avoid conflicting choices.
    """

    id: str  # Format: "DR-NNN"
    timestamp: str  # ISO format
    session: int  # Session number that made this decision
    topic: str  # What was being decided
    choice: str  # What was chosen
    alternatives_considered: list[str]  # Other options evaluated
    rationale: str  # Why this choice was made
    constraints_created: list[str]  # What future sessions must honor
    affects_features: list[int] = field(default_factory=list)  # Feature indices


def get_decisions_path(project_dir: Path) -> Path:
    """Get path to decisions file."""
    return project_dir / "architecture" / "decisions.yaml"


def load_decisions(project_dir: Path) -> list[DecisionRecord]:
    """
    Load all decision records from the decisions file.

    Args:
        project_dir: Project directory path

    Returns:
        List of DecisionRecord objects, empty list if file doesn't exist
    """
    decisions_path = get_decisions_path(project_dir)

    if not decisions_path.exists():
        return []

    with open(decisions_path) as f:
        data = yaml.safe_load(f) or {}

    records = []
    for d in data.get("decisions", []):
        records.append(DecisionRecord(
            id=d["id"],
            timestamp=d.get("timestamp", ""),
            session=d.get("session", 0),
            topic=d["topic"],
            choice=d["choice"],
            alternatives_considered=d.get("alternatives_considered", []),
            rationale=d.get("rationale", ""),
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
