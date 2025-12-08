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
from typing import Optional, TypedDict

logger = logging.getLogger(__name__)


METRICS_FILENAME = "drift-metrics.json"

# Velocity trend detection thresholds
# Initial estimate: 10% chosen to filter session-to-session noise while detecting
# meaningful changes. TODO: Tune these thresholds after collecting production data
# from multiple projects to establish actual variance baselines.
VELOCITY_TREND_THRESHOLD_PERCENT = 0.10

# Minimum absolute difference required to trigger trend detection.
# Initial estimate: Prevents false "decreasing" trend when going from 1.5 to 1.4
# features/session. TODO: Validate this threshold with real session data.
VELOCITY_MIN_ABSOLUTE_THRESHOLD = 0.5

# Tolerance for floating point comparisons in integrity validation.
# Value of 0.01 chosen to accommodate rounding errors from division operations
# (e.g., average_features_per_session = sum/count) while being strict enough to
# catch meaningful discrepancies. Typical floating point errors are ~1e-15,
# so 0.01 provides a wide margin for accumulated errors.
FLOAT_COMPARISON_EPSILON = 0.01


@dataclass
class SessionMetrics:
    """
    Metrics for a single coding session.

    Note on regression-related fields:
    - features_regressed: Count of features that went from passing to failing
      during this session. Calculated as abs(features_completed) when negative.
      This measures actual test status changes in feature_list.json.
    - regressions_caught: Count of regressions detected by the agent's
      REGRESSION VERIFICATION step. This measures the agent's ability to
      catch regressions before they propagate.
    """

    session_id: int
    timestamp: str
    features_attempted: int
    features_completed: int  # Net change (can be negative for regressions)
    features_regressed: int = 0  # Count of features that went from passing to failing
    regressions_caught: int = 0  # Count detected in REGRESSION VERIFICATION step
    assumptions_stated: int = 0
    assumptions_violated: int = 0
    architecture_deviations: int = 0
    evaluation_sections_present: list[str] = field(default_factory=list)
    evaluation_completeness_score: float = 1.0  # 0.0-1.0, 1.0 = all sections present
    is_multi_feature: bool = False  # True if session worked on multiple features


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
    multi_feature_session_count: int = 0  # Sessions with is_multi_feature=True
    incomplete_evaluation_count: int = 0  # Sessions with completeness_score < 1.0


class DriftIndicators(TypedDict):
    """Type definition for drift indicators returned by calculate_drift_indicators."""

    regression_rate: float  # Percentage of sessions with regressions (0-100)
    velocity_trend: str  # "increasing" | "stable" | "decreasing" | "insufficient_data"
    rejection_rate: float  # Percentage of validations rejected (0-100)


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
        # Add backwards compatibility for new fields with defaults
        sessions = []
        for session_data in data.get("sessions", []):
            # Defaults for fields added after initial release
            if "features_regressed" not in session_data:
                session_data["features_regressed"] = 0
            if "evaluation_completeness_score" not in session_data:
                session_data["evaluation_completeness_score"] = 1.0
            if "is_multi_feature" not in session_data:
                session_data["is_multi_feature"] = False
            sessions.append(SessionMetrics(**session_data))
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
            multi_feature_session_count=data.get("multi_feature_session_count", 0),
            incomplete_evaluation_count=data.get("incomplete_evaluation_count", 0),
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
        if abs(metrics.average_features_per_session - expected_avg) > FLOAT_COMPARISON_EPSILON:
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
                "features_regressed": s.features_regressed,
                "regressions_caught": s.regressions_caught,
                "assumptions_stated": s.assumptions_stated,
                "assumptions_violated": s.assumptions_violated,
                "architecture_deviations": s.architecture_deviations,
                "evaluation_sections_present": s.evaluation_sections_present,
                "evaluation_completeness_score": s.evaluation_completeness_score,
                "is_multi_feature": s.is_multi_feature,
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
        "multi_feature_session_count": metrics.multi_feature_session_count,
        "incomplete_evaluation_count": metrics.incomplete_evaluation_count,
    }

    atomic_json_write(metrics_path, data)


def record_session_metrics(
    project_dir: Path,
    session_id: int,
    features_attempted: int,
    features_completed: int,
    features_regressed: int = 0,
    regressions_caught: int = 0,
    assumptions_stated: int = 0,
    assumptions_violated: int = 0,
    architecture_deviations: int = 0,
    evaluation_sections_present: Optional[list[str]] = None,
    evaluation_completeness_score: float = 1.0,
    is_multi_feature: bool = False,
) -> None:
    """
    Record metrics for a coding session.

    Args:
        project_dir: Project directory path
        session_id: Session number/ID
        features_attempted: Number of features attempted in this session
        features_completed: Net features completed (can be negative for regressions)
        features_regressed: Number of features that regressed (>= 0)
        regressions_caught: Number of regressions caught (default: 0)
        assumptions_stated: Number of assumptions stated (default: 0)
        assumptions_violated: Number of assumptions violated (default: 0)
        architecture_deviations: Number of architecture deviations (default: 0)
        evaluation_sections_present: List of evaluation section names present
        evaluation_completeness_score: Score from 0.0-1.0 (default: 1.0)
        is_multi_feature: True if session worked on multiple features

    Raises:
        ValueError: If evaluation_completeness_score is outside 0.0-1.0 range
    """
    if evaluation_sections_present is None:
        evaluation_sections_present = []

    # Validate evaluation_completeness_score range
    if not (0.0 <= evaluation_completeness_score <= 1.0):
        raise ValueError(
            f"evaluation_completeness_score must be 0.0-1.0, got {evaluation_completeness_score}"
        )

    # Load existing metrics
    metrics = load_metrics(project_dir)

    # Create new session metrics
    session_metrics = SessionMetrics(
        session_id=session_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        features_attempted=features_attempted,
        features_completed=features_completed,
        features_regressed=features_regressed,
        regressions_caught=regressions_caught,
        assumptions_stated=assumptions_stated,
        assumptions_violated=assumptions_violated,
        architecture_deviations=architecture_deviations,
        evaluation_sections_present=evaluation_sections_present,
        evaluation_completeness_score=evaluation_completeness_score,
        is_multi_feature=is_multi_feature,
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

    # Update drift indicator aggregates
    metrics.multi_feature_session_count = sum(
        1 for s in metrics.sessions if s.is_multi_feature
    )
    metrics.incomplete_evaluation_count = sum(
        1 for s in metrics.sessions if s.evaluation_completeness_score < 1.0
    )

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


def calculate_drift_indicators(metrics: DriftMetrics) -> DriftIndicators:
    """
    Calculate drift indicators from metrics.

    Args:
        metrics: DriftMetrics object

    Returns:
        DriftIndicators with keys:
        - regression_rate: Percentage of sessions with regressions (0-100)
        - velocity_trend: "increasing" | "stable" | "decreasing" | "insufficient_data"
        - rejection_rate: Percentage of validations rejected (0-100)
    """
    result: DriftIndicators = {
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

# Regex patterns for evaluation section headers
# These require the header format: "### Step X - SECTION_NAME" or "## SECTION_NAME"
# to avoid false matches on echoed text or comments about sections
# Allow optional leading whitespace for indented output
CONTEXT_SECTION_PATTERN = re.compile(
    r"^\s*#{2,3}\s*(?:Step\s*[A-Z]?\s*[-–—]?\s*)?CONTEXT\s+VERIFICATION",
    re.MULTILINE | re.IGNORECASE,
)
REGRESSION_SECTION_PATTERN = re.compile(
    r"^\s*#{2,3}\s*(?:Step\s*[A-Z]?\s*[-–—]?\s*)?REGRESSION\s+VERIFICATION",
    re.MULTILINE | re.IGNORECASE,
)
PLAN_SECTION_PATTERN = re.compile(
    r"^\s*#{2,3}\s*(?:Step\s*[A-Z]?\s*[-–—]?\s*)?IMPLEMENTATION\s+PLAN",
    re.MULTILINE | re.IGNORECASE,
)


def parse_evaluation_sections(output: str) -> tuple[list[str], bool]:
    """
    Parse agent output to identify which evaluation sections were present.

    Uses regex patterns to match structured headers (e.g., "### Step A - CONTEXT
    VERIFICATION") rather than simple substring matching. This prevents false
    positives from echoed headers or comments about sections.

    Logs a warning if expected sections are missing from the output.

    Returns:
        Tuple of (sections, is_complete):
        - sections: list of section identifiers found ("context", "regression", "plan")
        - is_complete: True if all expected sections are present
    """
    sections = []

    if CONTEXT_SECTION_PATTERN.search(output):
        sections.append("context")
    if REGRESSION_SECTION_PATTERN.search(output):
        sections.append("regression")
    if PLAN_SECTION_PATTERN.search(output):
        sections.append("plan")

    # Check for missing sections (indicates potential drift/skipped evaluation)
    missing = EXPECTED_EVAL_SECTIONS - set(sections)
    is_complete = len(missing) == 0

    if missing:
        logger.warning(f"Evaluation sections missing from agent output: {sorted(missing)}")

    return sections, is_complete


def calculate_evaluation_completeness(sections: list[str]) -> float:
    """
    Calculate evaluation completeness score based on sections present.

    Args:
        sections: List of section identifiers found

    Returns:
        Score from 0.0 to 1.0 (1.0 = all expected sections present)
    """
    if not EXPECTED_EVAL_SECTIONS:
        return 1.0
    return len(set(sections) & EXPECTED_EVAL_SECTIONS) / len(EXPECTED_EVAL_SECTIONS)


def count_regressions(output: str) -> int:
    """
    Count regressions detected in agent output from REGRESSION VERIFICATION section.

    Parses output like:
        ### Step B - REGRESSION VERIFICATION
        - Feature [12]: PASS
          Evidence: "Login form renders correctly"
        - Feature [5]: FAIL
          Evidence: "Button click no longer triggers submit"

    Uses specific patterns to avoid false matches:
    - Requires the section header to be a markdown heading
    - Matches "Feature [N]: FAIL" or "Feature #N: FAIL" patterns specifically
    - Stops at the next section header (###) or IMPLEMENTATION PLAN
    """
    # Look for the REGRESSION VERIFICATION section starting with a markdown header
    # Allow optional leading whitespace for indented output
    # Use \Z for end of string ($ in multiline mode matches end of each line)
    section_pattern = re.compile(
        r"^\s*#{2,3}\s*(?:Step\s*[A-Z]?\s*[-–—]?\s*)?REGRESSION\s+VERIFICATION"
        r"(.*?)(?=^\s*#{2,3}\s|IMPLEMENTATION\s+PLAN|\Z)",
        re.DOTALL | re.MULTILINE | re.IGNORECASE,
    )
    section_match = section_pattern.search(output)

    if not section_match:
        logger.debug("REGRESSION VERIFICATION section not found in agent output")
        return 0

    section_content = section_match.group(1)

    # Match specific feature failure patterns:
    # - "Feature [12]: FAIL" or "Feature #12: FAIL"
    # - "-" at start of line indicates a list item
    # This avoids matching unrelated "FAIL" text in evidence or comments
    fail_pattern = re.compile(
        r"^\s*[-*]\s*Feature\s*[#\[]?\d+[\]:]?\s*:\s*FAIL\b",
        re.MULTILINE | re.IGNORECASE,
    )
    fail_matches = fail_pattern.findall(section_content)

    return len(fail_matches)
