"""
XDG State Management Module
===========================

XDG-compliant state separation for workflow management.

This module provides:
- XDG Base Directory functions for state storage paths
- WorkflowState dataclass for session persistence
- CRUD operations for workflow state with atomic writes

Design Philosophy
-----------------
Operational state (workflow progress, validation history, logs) is stored in
XDG-compliant directories (~/.local/state/claude-agent/) to avoid polluting
project directories.

Project-bound artifacts (feature_list.json, architecture/, app_spec.txt)
remain in the project directory.

State Isolation
---------------
Each project has an isolated workflow directory identified by a 12-character
SHA256 hash of its absolute path. This ensures:
- Stable identification across runs
- No collisions between project directories
- Human-readable (partial hash) directory names

Concurrency Note
----------------
Only one claude-agent process should run per project directory at a time.
Concurrent access to state files is not supported. Atomic writes prevent
corruption on crash.

Usage Example
-------------
    from claude_agent.state import (
        get_state_dir,
        get_workflow_dir,
        WorkflowState,
        load_workflow_state,
        save_workflow_state,
    )

    # Get paths
    state_dir = get_state_dir()  # ~/.local/state/claude-agent/
    workflow_dir = get_workflow_dir("/path/to/project")

    # Create workflow state
    state = WorkflowState(
        id="abc123",
        project_dir="/path/to/project",
        phase="coding",
        started_at=datetime.now(),
        updated_at=datetime.now(),
        features_completed=5,
        features_total=50,
    )

    # Persist state
    save_workflow_state(state)  # Atomic write

    # Load state
    loaded = load_workflow_state("/path/to/project")
    if loaded:
        print(f"Phase: {loaded.phase}")
"""

import hashlib
import json
import os
import platform
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# =============================================================================
# Constants
# =============================================================================

# Valid phase values for WorkflowState
VALID_PHASES = frozenset({"initializing", "coding", "validating", "complete", "paused"})


# =============================================================================
# XDG Path Functions
# =============================================================================

def get_state_dir() -> Path:
    """Get XDG-compliant state directory path.

    Returns ~/.local/state/claude-agent/ on Unix systems.
    Respects XDG_STATE_HOME environment variable if set.
    Falls back to %LOCALAPPDATA%/claude-agent/ on Windows.

    Returns:
        Path to the state directory (may not exist yet)
    """
    if platform.system() == "Windows":
        # Windows fallback: use LOCALAPPDATA
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        return Path(base) / "claude-agent"

    # Unix systems: respect XDG_STATE_HOME or use default
    xdg_state_home = os.environ.get("XDG_STATE_HOME")
    if xdg_state_home:
        base = Path(xdg_state_home)
    else:
        base = Path.home() / ".local" / "state"

    return base / "claude-agent"


def get_project_hash(project_dir: Path | str) -> str:
    """Compute 12-character hash for project identification.

    Creates a stable, unique identifier for a project based on its
    absolute path. The hash is used to isolate workflow state between
    different projects.

    Args:
        project_dir: Path to the project directory

    Returns:
        12-character hexadecimal hash of the absolute path
    """
    # Convert to absolute path string
    abs_path = str(Path(project_dir).resolve())

    # Compute SHA256 hash
    hash_bytes = hashlib.sha256(abs_path.encode("utf-8")).hexdigest()

    # Return first 12 characters
    return hash_bytes[:12]


def get_workflow_dir(project_dir: Path | str) -> Path:
    """Get workflow state directory for a specific project.

    Returns {state_dir}/workflows/{project_hash}/ path.

    Args:
        project_dir: Path to the project directory

    Returns:
        Path to the project's workflow directory
    """
    state_dir = get_state_dir()
    project_hash = get_project_hash(project_dir)
    return state_dir / "workflows" / project_hash


def get_logs_dir() -> Path:
    """Get XDG-compliant logs directory path.

    Returns {state_dir}/logs/ path.

    Returns:
        Path to the logs directory
    """
    return get_state_dir() / "logs"


def ensure_state_dirs(project_dir: Optional[Path | str] = None) -> None:
    """Create state directories with secure permissions.

    Creates:
    - Base state directory (~/.local/state/claude-agent/)
    - Logs directory ({state_dir}/logs/)
    - Workflow directory for project if provided ({state_dir}/workflows/{hash}/)

    All directories are created with 0o700 permissions (user-only access).

    Args:
        project_dir: Optional project directory for workflow dir creation
    """
    # Create base state directory
    state_dir = get_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    # Set permissions on Unix (Windows ignores this)
    if platform.system() != "Windows":
        os.chmod(state_dir, 0o700)

    # Create logs directory
    logs_dir = get_logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)
    if platform.system() != "Windows":
        os.chmod(logs_dir, 0o700)

    # Create workflows base directory
    workflows_dir = state_dir / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)
    if platform.system() != "Windows":
        os.chmod(workflows_dir, 0o700)

    # Create project-specific workflow directory if provided
    if project_dir:
        workflow_dir = get_workflow_dir(project_dir)
        workflow_dir.mkdir(parents=True, exist_ok=True)
        if platform.system() != "Windows":
            os.chmod(workflow_dir, 0o700)


# =============================================================================
# WorkflowState Dataclass
# =============================================================================

@dataclass
class WorkflowState:
    """Persistent workflow state for session handoff.

    Tracks the current state of a claude-agent workflow including:
    - Phase of execution (initializing, coding, validating, complete, paused)
    - Feature progress (completed/total)
    - Last error for recovery context
    - Recovery steps for guidance

    Attributes:
        id: Unique workflow identifier
        project_dir: Absolute path to the project directory
        phase: Current workflow phase (validated on creation)
        started_at: When the workflow started
        updated_at: When state was last updated (auto-updated on save)
        features_completed: Number of features completed
        features_total: Total number of features
        current_feature_index: Index of feature being worked on
        iteration_count: Number of coding iterations
        last_error: Serialized StructuredError from last error
        pause_reason: Why the workflow was paused
        recovery_steps: Steps to recover from current state
    """
    id: str
    project_dir: str
    phase: str
    started_at: datetime
    updated_at: datetime
    features_completed: int = 0
    features_total: int = 0
    current_feature_index: Optional[int] = None
    iteration_count: int = 0
    last_error: Optional[dict] = None
    pause_reason: Optional[str] = None
    recovery_steps: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate phase on creation."""
        if self.phase not in VALID_PHASES:
            valid_list = ", ".join(sorted(VALID_PHASES))
            raise ValueError(
                f"Invalid phase '{self.phase}'. Must be one of: {valid_list}"
            )

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dictionary.

        Datetime fields are converted to ISO format strings.

        Returns:
            JSON-serializable dictionary representation
        """
        return {
            "id": self.id,
            "project_dir": self.project_dir,
            "phase": self.phase,
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "features_completed": self.features_completed,
            "features_total": self.features_total,
            "current_feature_index": self.current_feature_index,
            "iteration_count": self.iteration_count,
            "last_error": self.last_error,
            "pause_reason": self.pause_reason,
            "recovery_steps": self.recovery_steps,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowState":
        """Deserialize from dictionary.

        Handles datetime parsing and missing optional fields.

        Args:
            data: Dictionary from to_dict() or JSON parsing

        Returns:
            WorkflowState instance

        Raises:
            ValueError: If required fields are missing or invalid
            KeyError: If required fields are missing
        """
        # Parse datetime fields
        started_at = datetime.fromisoformat(data["started_at"])
        updated_at = datetime.fromisoformat(data["updated_at"])

        return cls(
            id=data["id"],
            project_dir=data["project_dir"],
            phase=data["phase"],
            started_at=started_at,
            updated_at=updated_at,
            features_completed=data.get("features_completed", 0),
            features_total=data.get("features_total", 0),
            current_feature_index=data.get("current_feature_index"),
            iteration_count=data.get("iteration_count", 0),
            last_error=data.get("last_error"),
            pause_reason=data.get("pause_reason"),
            recovery_steps=data.get("recovery_steps", []),
        )


# =============================================================================
# State Persistence Functions
# =============================================================================

def load_workflow_state(project_dir: Path | str) -> Optional[WorkflowState]:
    """Load workflow state for a project.

    Args:
        project_dir: Path to the project directory

    Returns:
        WorkflowState if file exists and is valid, None otherwise.
        Returns None on file not found or JSON parse errors.
    """
    workflow_dir = get_workflow_dir(project_dir)
    state_file = workflow_dir / "workflow-state.json"

    if not state_file.exists():
        return None

    try:
        with open(state_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return WorkflowState.from_dict(data)
    except (json.JSONDecodeError, KeyError, ValueError):
        # Return None on parse errors - let caller decide how to handle
        return None


def save_workflow_state(state: WorkflowState) -> None:
    """Save workflow state with atomic write.

    Uses temp file + rename pattern to prevent corruption on crash.
    Automatically updates the updated_at timestamp.

    Args:
        state: WorkflowState to save

    Note:
        Creates the workflow directory if it doesn't exist.
    """
    # Ensure directory exists
    ensure_state_dirs(state.project_dir)

    # Update timestamp
    state.updated_at = datetime.now()

    # Get target path
    workflow_dir = get_workflow_dir(state.project_dir)
    state_file = workflow_dir / "workflow-state.json"

    # Serialize state
    data = state.to_dict()
    json_content = json.dumps(data, indent=2)

    # Atomic write: write to temp file then rename
    # Use same directory for temp file to ensure same filesystem
    fd, temp_path = tempfile.mkstemp(
        suffix=".json",
        prefix="workflow-state-",
        dir=workflow_dir
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json_content)
        # Atomic rename (on same filesystem)
        os.replace(temp_path, state_file)
    except Exception:
        # Clean up temp file on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def clear_workflow_state(project_dir: Path | str) -> bool:
    """Delete workflow state file for a project.

    Idempotent: returns True whether file existed or not.

    Args:
        project_dir: Path to the project directory

    Returns:
        True if operation succeeded (file deleted or didn't exist)
    """
    workflow_dir = get_workflow_dir(project_dir)
    state_file = workflow_dir / "workflow-state.json"

    try:
        if state_file.exists():
            state_file.unlink()
        return True
    except OSError:
        # Permission error or other issue
        return False
