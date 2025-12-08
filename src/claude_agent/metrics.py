"""
Drift Detection Metrics
=======================

Track metrics to measure and detect drift in long-running agent sessions.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


METRICS_FILENAME = "drift-metrics.json"

# Velocity trend detection thresholds
# 10% chosen to filter session-to-session noise while detecting meaningful changes.
# Empirical observation suggests normal variance is ~5-8% between sessions.
VELOCITY_TREND_THRESHOLD_PERCENT = 0.10

# Minimum absolute difference required to trigger trend detection.
# Prevents false "decreasing" trend when going from 1.5 to 1.4 features/session.
# Only trigger trend detection if the absolute difference is at least 0.5 features.
VELOCITY_MIN_ABSOLUTE_THRESHOLD = 0.5


@dataclass
class SessionMetrics:
    """Metrics for a single coding session."""

    session_id: int
    timestamp: str
    features_attempted: int
    features_completed: int
    regressions_caught: int = 0
    assumptions_stated: int = 0
    assumptions_violated: int = 0
    architecture_deviations: int = 0
    evaluation_sections_present: list[str] = field(default_factory=list)


@dataclass
class ValidationMetrics:
    """Metrics for a single validation attempt."""

    attempt: int
    timestamp: str
    verdict: str  # "approved" | "rejected"
    features_tested: int
    features_failed: int
    failure_reasons: list[str] = field(default_factory=list)


@dataclass
class DriftMetrics:
    """Aggregated drift metrics for a project."""

    sessions: list[SessionMetrics] = field(default_factory=list)
    validation_attempts: list[ValidationMetrics] = field(default_factory=list)
    total_sessions: int = 0
    total_regressions_caught: int = 0
    average_features_per_session: float = 0.0
    rejection_count: int = 0


def load_metrics(project_dir: Path) -> DriftMetrics:
    """
    Load drift metrics from project directory.

    Args:
        project_dir: Project directory path

    Returns:
        DriftMetrics object, or empty metrics if file doesn't exist
    """
    metrics_path = project_dir / METRICS_FILENAME

    if not metrics_path.exists():
        return DriftMetrics()

    try:
        with open(metrics_path) as f:
            data = json.load(f)

        # Reconstruct dataclasses from dict data
        sessions = [
            SessionMetrics(**session_data) for session_data in data.get("sessions", [])
        ]
        validation_attempts = [
            ValidationMetrics(**val_data)
            for val_data in data.get("validation_attempts", [])
        ]

        metrics = DriftMetrics(
            sessions=sessions,
            validation_attempts=validation_attempts,
            total_sessions=data.get("total_sessions", 0),
            total_regressions_caught=data.get("total_regressions_caught", 0),
            average_features_per_session=data.get("average_features_per_session", 0.0),
            rejection_count=data.get("rejection_count", 0),
        )

        # Validate integrity and log warnings for any inconsistencies
        integrity_errors = validate_metrics_integrity(metrics)
        if integrity_errors:
            for error in integrity_errors:
                logger.warning(f"Metrics integrity issue: {error}")

        return metrics
    except (json.JSONDecodeError, IOError, KeyError, TypeError):
        # Return empty metrics on any error
        return DriftMetrics()


def validate_metrics_integrity(metrics: DriftMetrics) -> list[str]:
    """
    Verify aggregate metrics match calculated values from sessions.

    Checks for consistency between stored aggregates and the actual
    session data. Inconsistencies may indicate file corruption or
    manual edits that introduced errors.

    Args:
        metrics: DriftMetrics object to validate

    Returns:
        List of integrity error descriptions (empty if valid)
    """
    errors = []

    # Validate total_sessions matches actual session count
    expected_sessions = len(metrics.sessions)
    if metrics.total_sessions != expected_sessions:
        errors.append(
            f"total_sessions mismatch: stored={metrics.total_sessions}, "
            f"calculated={expected_sessions}"
        )

    # Validate total_regressions_caught
    expected_regressions = sum(s.regressions_caught for s in metrics.sessions)
    if metrics.total_regressions_caught != expected_regressions:
        errors.append(
            f"total_regressions_caught mismatch: stored={metrics.total_regressions_caught}, "
            f"calculated={expected_regressions}"
        )

    # Validate average_features_per_session
    if expected_sessions > 0:
        expected_avg = (
            sum(s.features_completed for s in metrics.sessions) / expected_sessions
        )
        if abs(metrics.average_features_per_session - expected_avg) > 0.01:
            errors.append(
                f"average_features_per_session mismatch: "
                f"stored={metrics.average_features_per_session:.2f}, "
                f"calculated={expected_avg:.2f}"
            )

    # Validate rejection_count
    expected_rejections = sum(
        1 for v in metrics.validation_attempts if v.verdict == "rejected"
    )
    if metrics.rejection_count != expected_rejections:
        errors.append(
            f"rejection_count mismatch: stored={metrics.rejection_count}, "
            f"calculated={expected_rejections}"
        )

    return errors


def save_metrics(project_dir: Path, metrics: DriftMetrics) -> None:
    """
    Save drift metrics to project directory using atomic write.

    Args:
        project_dir: Project directory path
        metrics: DriftMetrics object to save
    """
    from claude_agent.progress import atomic_json_write

    metrics_path = project_dir / METRICS_FILENAME

    # Convert dataclasses to dict for JSON serialization
    data = {
        "sessions": [
            {
                "session_id": s.session_id,
                "timestamp": s.timestamp,
                "features_attempted": s.features_attempted,
                "features_completed": s.features_completed,
                "regressions_caught": s.regressions_caught,
                "assumptions_stated": s.assumptions_stated,
                "assumptions_violated": s.assumptions_violated,
                "architecture_deviations": s.architecture_deviations,
                "evaluation_sections_present": s.evaluation_sections_present,
            }
            for s in metrics.sessions
        ],
        "validation_attempts": [
            {
                "attempt": v.attempt,
                "timestamp": v.timestamp,
                "verdict": v.verdict,
                "features_tested": v.features_tested,
                "features_failed": v.features_failed,
                "failure_reasons": v.failure_reasons,
            }
            for v in metrics.validation_attempts
        ],
        "total_sessions": metrics.total_sessions,
        "total_regressions_caught": metrics.total_regressions_caught,
        "average_features_per_session": metrics.average_features_per_session,
        "rejection_count": metrics.rejection_count,
    }

    atomic_json_write(metrics_path, data)


def record_session_metrics(
    project_dir: Path,
    session_id: int,
    features_attempted: int,
    features_completed: int,
    regressions_caught: int = 0,
    assumptions_stated: int = 0,
    assumptions_violated: int = 0,
    architecture_deviations: int = 0,
    evaluation_sections_present: Optional[list[str]] = None,
) -> None:
    """
    Record metrics for a coding session.

    Args:
        project_dir: Project directory path
        session_id: Session number/ID
        features_attempted: Number of features attempted in this session
        features_completed: Number of features completed in this session
        regressions_caught: Number of regressions caught (default: 0)
        assumptions_stated: Number of assumptions stated (default: 0)
        assumptions_violated: Number of assumptions violated (default: 0)
        architecture_deviations: Number of architecture deviations (default: 0)
        evaluation_sections_present: List of evaluation section names present
    """
    if evaluation_sections_present is None:
        evaluation_sections_present = []

    # Load existing metrics
    metrics = load_metrics(project_dir)

    # Create new session metrics
    session_metrics = SessionMetrics(
        session_id=session_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        features_attempted=features_attempted,
        features_completed=features_completed,
        regressions_caught=regressions_caught,
        assumptions_stated=assumptions_stated,
        assumptions_violated=assumptions_violated,
        architecture_deviations=architecture_deviations,
        evaluation_sections_present=evaluation_sections_present,
    )

    # Add to sessions list
    metrics.sessions.append(session_metrics)

    # Update aggregate metrics
    metrics.total_sessions = len(metrics.sessions)
    metrics.total_regressions_caught = sum(
        s.regressions_caught for s in metrics.sessions
    )

    # Calculate average features per session
    total_features = sum(s.features_completed for s in metrics.sessions)
    if metrics.total_sessions > 0:
        metrics.average_features_per_session = total_features / metrics.total_sessions
    else:
        metrics.average_features_per_session = 0.0

    # Save updated metrics
    save_metrics(project_dir, metrics)


def record_validation_metrics(
    project_dir: Path,
    verdict: str,
    features_tested: int,
    features_failed: int,
    failure_reasons: Optional[list[str]] = None,
) -> None:
    """
    Record metrics for a validation attempt.

    Args:
        project_dir: Project directory path
        verdict: "approved" or "rejected"
        features_tested: Number of features tested
        features_failed: Number of features that failed
        failure_reasons: List of failure reason descriptions
    """
    if failure_reasons is None:
        failure_reasons = []

    # Load existing metrics
    metrics = load_metrics(project_dir)

    # Determine attempt number
    attempt = len(metrics.validation_attempts) + 1

    # Create new validation metrics
    validation_metrics = ValidationMetrics(
        attempt=attempt,
        timestamp=datetime.now(timezone.utc).isoformat(),
        verdict=verdict,
        features_tested=features_tested,
        features_failed=features_failed,
        failure_reasons=failure_reasons,
    )

    # Add to validation attempts list
    metrics.validation_attempts.append(validation_metrics)

    # Update rejection count
    metrics.rejection_count = sum(
        1 for v in metrics.validation_attempts if v.verdict == "rejected"
    )

    # Save updated metrics
    save_metrics(project_dir, metrics)


def calculate_drift_indicators(metrics: DriftMetrics) -> dict:
    """
    Calculate drift indicators from metrics.

    Args:
        metrics: DriftMetrics object

    Returns:
        Dict with keys:
        - regression_rate: Percentage of sessions with regressions (0-100)
        - velocity_trend: "increasing" | "stable" | "decreasing" | "insufficient_data"
        - rejection_rate: Percentage of validations rejected (0-100)
    """
    result = {
        "regression_rate": 0.0,
        "velocity_trend": "insufficient_data",
        "rejection_rate": 0.0,
    }

    # Calculate regression rate
    if metrics.total_sessions > 0:
        sessions_with_regressions = sum(
            1 for s in metrics.sessions if s.regressions_caught > 0
        )
        result["regression_rate"] = (
            sessions_with_regressions / metrics.total_sessions
        ) * 100

    # Calculate velocity trend (requires at least 6 sessions)
    if len(metrics.sessions) >= 6:
        # Split sessions into two halves
        mid = len(metrics.sessions) // 2
        first_half = metrics.sessions[:mid]
        second_half = metrics.sessions[mid:]

        # Calculate average features per session for each half
        first_avg = sum(s.features_completed for s in first_half) / len(first_half)
        second_avg = sum(s.features_completed for s in second_half) / len(second_half)

        # Determine trend using configured thresholds
        # Use max of percentage threshold and absolute minimum to avoid noise
        threshold = max(
            first_avg * VELOCITY_TREND_THRESHOLD_PERCENT,
            VELOCITY_MIN_ABSOLUTE_THRESHOLD,
        )
        if second_avg > first_avg + threshold:
            result["velocity_trend"] = "increasing"
        elif second_avg < first_avg - threshold:
            result["velocity_trend"] = "decreasing"
        else:
            result["velocity_trend"] = "stable"

    # Calculate rejection rate
    if len(metrics.validation_attempts) > 0:
        result["rejection_rate"] = (
            metrics.rejection_count / len(metrics.validation_attempts)
        ) * 100

    return result


# =============================================================================
# Output Parsing Functions
# =============================================================================


# Expected evaluation sections for the coding agent
EXPECTED_EVAL_SECTIONS = {"context", "regression", "plan"}


def parse_evaluation_sections(output: str) -> list[str]:
    """
    Parse agent output to identify which evaluation sections were present.

    Logs a warning if expected sections are missing from the output.

    Returns list of section identifiers: "context", "regression", "plan"
    """
    sections = []
    if "CONTEXT VERIFICATION" in output:
        sections.append("context")
    if "REGRESSION VERIFICATION" in output:
        sections.append("regression")
    if "IMPLEMENTATION PLAN" in output:
        sections.append("plan")

    # Warn about missing sections (indicates potential drift/skipped evaluation)
    missing = EXPECTED_EVAL_SECTIONS - set(sections)
    if missing:
        logger.warning(f"Evaluation sections missing from agent output: {sorted(missing)}")

    return sections


def count_regressions(output: str) -> int:
    """
    Count regressions detected in agent output from REGRESSION VERIFICATION section.

    Parses output like:
        ### Step B - REGRESSION VERIFICATION
        - Feature [12]: PASS
          Evidence: "Login form renders correctly"
        - Feature [5]: FAIL
          Evidence: "Button click no longer triggers submit"
    """
    section_pattern = re.compile(
        r"REGRESSION VERIFICATION.*?(?=###|IMPLEMENTATION PLAN|$)",
        re.DOTALL | re.IGNORECASE,
    )
    section_match = section_pattern.search(output)

    if not section_match:
        return 0

    section_content = section_match.group(0)
    fail_pattern = re.compile(r":\s*FAIL\b", re.IGNORECASE)
    fail_matches = fail_pattern.findall(section_content)

    return len(fail_matches)
