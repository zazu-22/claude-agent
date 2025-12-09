"""
Tests for drift detection metrics tracking.
"""

import json
import pytest
from pathlib import Path

from click.testing import CliRunner

from claude_agent.cli import main
from claude_agent.metrics import (
    ARCH_DEVIATION_CRITICAL,
    ARCH_DEVIATION_WARNING,
    FLOAT_COMPARISON_EPSILON,
    INCOMPLETE_EVAL_WARNING,
    METRICS_FILENAME,
    MULTI_FEATURE_WARNING,
    REGRESSION_RATE_CRITICAL,
    REGRESSION_RATE_WARNING,
    REJECTION_RATE_CRITICAL,
    REJECTION_RATE_WARNING,
    SessionMetrics,
    ValidationMetrics,
    DriftMetrics,
    load_metrics,
    save_metrics,
    record_session_metrics,
    record_validation_metrics,
    calculate_drift_indicators,
    calculate_evaluation_completeness,
    validate_metrics_integrity,
    get_session_date_range,
    get_regression_rate_trend,
    get_velocity_values,
    get_architecture_deviation_count,
    calculate_health_status,
    get_dashboard_data,
    generate_sparkline,
)


class TestSessionMetrics:
    """Test SessionMetrics dataclass."""

    def test_creates_with_required_fields(self):
        """Verify SessionMetrics creates with required fields."""
        metrics = SessionMetrics(
            session_id=1,
            timestamp="2024-01-15T10:00:00Z",
            features_attempted=5,
            features_completed=3,
        )

        assert metrics.session_id == 1
        assert metrics.timestamp == "2024-01-15T10:00:00Z"
        assert metrics.features_attempted == 5
        assert metrics.features_completed == 3
        assert metrics.regressions_caught == 0
        assert metrics.assumptions_stated == 0
        assert metrics.assumptions_violated == 0
        assert metrics.architecture_deviations == 0
        assert metrics.evaluation_sections_present == []

    def test_creates_with_all_fields(self):
        """Verify SessionMetrics creates with all fields populated."""
        metrics = SessionMetrics(
            session_id=2,
            timestamp="2024-01-15T12:00:00Z",
            features_attempted=10,
            features_completed=8,
            regressions_caught=2,
            assumptions_stated=5,
            assumptions_violated=1,
            architecture_deviations=3,
            evaluation_sections_present=["assumptions", "architecture"],
        )

        assert metrics.regressions_caught == 2
        assert metrics.assumptions_stated == 5
        assert metrics.assumptions_violated == 1
        assert metrics.architecture_deviations == 3
        assert len(metrics.evaluation_sections_present) == 2


class TestValidationMetrics:
    """Test ValidationMetrics dataclass."""

    def test_creates_with_required_fields(self):
        """Verify ValidationMetrics creates with required fields."""
        metrics = ValidationMetrics(
            attempt=1,
            timestamp="2024-01-15T14:00:00Z",
            verdict="approved",
            features_tested=50,
            features_failed=0,
        )

        assert metrics.attempt == 1
        assert metrics.verdict == "approved"
        assert metrics.features_tested == 50
        assert metrics.features_failed == 0
        assert metrics.failure_reasons == []

    def test_creates_with_failure_reasons(self):
        """Verify ValidationMetrics creates with failure reasons."""
        reasons = ["Login button broken", "API timeout"]
        metrics = ValidationMetrics(
            attempt=2,
            timestamp="2024-01-15T16:00:00Z",
            verdict="rejected",
            features_tested=50,
            features_failed=2,
            failure_reasons=reasons,
        )

        assert metrics.verdict == "rejected"
        assert metrics.features_failed == 2
        assert len(metrics.failure_reasons) == 2
        assert "Login button broken" in metrics.failure_reasons


class TestDriftMetrics:
    """Test DriftMetrics dataclass."""

    def test_creates_empty(self):
        """Verify DriftMetrics creates empty by default."""
        metrics = DriftMetrics()

        assert metrics.sessions == []
        assert metrics.validation_attempts == []
        assert metrics.total_sessions == 0
        assert metrics.total_regressions_caught == 0
        assert metrics.average_features_per_session == 0.0
        assert metrics.rejection_count == 0


class TestLoadMetrics:
    """Test load_metrics function."""

    def test_load_metrics_empty(self, tmp_path):
        """Verify empty metrics returned for new project."""
        metrics = load_metrics(tmp_path)

        assert isinstance(metrics, DriftMetrics)
        assert len(metrics.sessions) == 0
        assert len(metrics.validation_attempts) == 0
        assert metrics.total_sessions == 0

    def test_loads_existing_metrics(self, tmp_path):
        """Verify loading existing metrics from file."""
        data = {
            "sessions": [
                {
                    "session_id": 1,
                    "timestamp": "2024-01-15T10:00:00Z",
                    "features_attempted": 5,
                    "features_completed": 3,
                    "regressions_caught": 1,
                    "assumptions_stated": 2,
                    "assumptions_violated": 0,
                    "architecture_deviations": 0,
                    "evaluation_sections_present": ["assumptions"],
                }
            ],
            "validation_attempts": [],
            "total_sessions": 1,
            "total_regressions_caught": 1,
            "average_features_per_session": 3.0,
            "rejection_count": 0,
        }

        metrics_path = tmp_path / METRICS_FILENAME
        with open(metrics_path, "w") as f:
            json.dump(data, f)

        metrics = load_metrics(tmp_path)

        assert len(metrics.sessions) == 1
        assert metrics.sessions[0].session_id == 1
        assert metrics.sessions[0].features_completed == 3
        assert metrics.total_sessions == 1
        assert metrics.total_regressions_caught == 1

    def test_handles_corrupted_json(self, tmp_path):
        """Verify graceful handling of corrupted JSON file."""
        metrics_path = tmp_path / METRICS_FILENAME
        metrics_path.write_text("{ invalid json }")

        metrics = load_metrics(tmp_path)

        assert isinstance(metrics, DriftMetrics)
        assert len(metrics.sessions) == 0

    def test_handles_missing_fields(self, tmp_path):
        """Verify graceful handling of missing fields in JSON."""
        data = {"sessions": []}

        metrics_path = tmp_path / METRICS_FILENAME
        with open(metrics_path, "w") as f:
            json.dump(data, f)

        metrics = load_metrics(tmp_path)

        assert isinstance(metrics, DriftMetrics)
        assert metrics.total_sessions == 0


class TestSaveMetrics:
    """Test save_metrics function."""

    def test_saves_metrics_to_file(self, tmp_path):
        """Verify metrics are saved to file correctly."""
        metrics = DriftMetrics(
            sessions=[
                SessionMetrics(
                    session_id=1,
                    timestamp="2024-01-15T10:00:00Z",
                    features_attempted=5,
                    features_completed=3,
                )
            ],
            total_sessions=1,
            average_features_per_session=3.0,
        )

        save_metrics(tmp_path, metrics)

        metrics_path = tmp_path / METRICS_FILENAME
        assert metrics_path.exists()

        with open(metrics_path) as f:
            data = json.load(f)

        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["session_id"] == 1
        assert data["total_sessions"] == 1

    def test_overwrites_existing_file(self, tmp_path):
        """Verify saving overwrites existing metrics file."""
        metrics1 = DriftMetrics(total_sessions=1)
        save_metrics(tmp_path, metrics1)

        metrics2 = DriftMetrics(total_sessions=2)
        save_metrics(tmp_path, metrics2)

        loaded = load_metrics(tmp_path)
        assert loaded.total_sessions == 2


class TestRecordSessionMetrics:
    """Test record_session_metrics function."""

    def test_record_session_metrics(self, tmp_path):
        """Verify session is recorded correctly."""
        record_session_metrics(
            tmp_path,
            session_id=1,
            features_attempted=5,
            features_completed=3,
            regressions_caught=1,
        )

        metrics = load_metrics(tmp_path)

        assert len(metrics.sessions) == 1
        assert metrics.sessions[0].session_id == 1
        assert metrics.sessions[0].features_attempted == 5
        assert metrics.sessions[0].features_completed == 3
        assert metrics.sessions[0].regressions_caught == 1
        assert metrics.total_sessions == 1
        assert metrics.total_regressions_caught == 1

    def test_records_multiple_sessions(self, tmp_path):
        """Verify multiple sessions are recorded and aggregated."""
        record_session_metrics(
            tmp_path, session_id=1, features_attempted=5, features_completed=3
        )
        record_session_metrics(
            tmp_path, session_id=2, features_attempted=10, features_completed=7
        )

        metrics = load_metrics(tmp_path)

        assert len(metrics.sessions) == 2
        assert metrics.total_sessions == 2
        assert metrics.average_features_per_session == 5.0  # (3 + 7) / 2

    def test_updates_aggregate_metrics(self, tmp_path):
        """Verify aggregate metrics are calculated correctly."""
        record_session_metrics(
            tmp_path,
            session_id=1,
            features_attempted=5,
            features_completed=3,
            regressions_caught=2,
        )
        record_session_metrics(
            tmp_path,
            session_id=2,
            features_attempted=10,
            features_completed=8,
            regressions_caught=1,
        )

        metrics = load_metrics(tmp_path)

        assert metrics.total_sessions == 2
        assert metrics.total_regressions_caught == 3
        assert metrics.average_features_per_session == 5.5  # (3 + 8) / 2

    def test_records_evaluation_sections(self, tmp_path):
        """Verify evaluation sections are recorded."""
        record_session_metrics(
            tmp_path,
            session_id=1,
            features_attempted=5,
            features_completed=3,
            evaluation_sections_present=["assumptions", "architecture", "regressions"],
        )

        metrics = load_metrics(tmp_path)

        assert len(metrics.sessions[0].evaluation_sections_present) == 3
        assert "assumptions" in metrics.sessions[0].evaluation_sections_present


class TestRecordValidationMetrics:
    """Test record_validation_metrics function."""

    def test_records_validation_attempt(self, tmp_path):
        """Verify validation attempt is recorded correctly."""
        record_validation_metrics(
            tmp_path,
            verdict="approved",
            features_tested=50,
            features_failed=0,
        )

        metrics = load_metrics(tmp_path)

        assert len(metrics.validation_attempts) == 1
        assert metrics.validation_attempts[0].attempt == 1
        assert metrics.validation_attempts[0].verdict == "approved"
        assert metrics.validation_attempts[0].features_tested == 50
        assert metrics.validation_attempts[0].features_failed == 0
        assert metrics.rejection_count == 0

    def test_records_rejection(self, tmp_path):
        """Verify rejection is counted correctly."""
        record_validation_metrics(
            tmp_path,
            verdict="rejected",
            features_tested=50,
            features_failed=3,
            failure_reasons=["Login broken", "API timeout", "CSS issue"],
        )

        metrics = load_metrics(tmp_path)

        assert len(metrics.validation_attempts) == 1
        assert metrics.validation_attempts[0].verdict == "rejected"
        assert metrics.validation_attempts[0].features_failed == 3
        assert len(metrics.validation_attempts[0].failure_reasons) == 3
        assert metrics.rejection_count == 1

    def test_records_multiple_validations(self, tmp_path):
        """Verify multiple validation attempts are tracked."""
        record_validation_metrics(
            tmp_path, verdict="rejected", features_tested=50, features_failed=2
        )
        record_validation_metrics(
            tmp_path, verdict="rejected", features_tested=50, features_failed=1
        )
        record_validation_metrics(
            tmp_path, verdict="approved", features_tested=50, features_failed=0
        )

        metrics = load_metrics(tmp_path)

        assert len(metrics.validation_attempts) == 3
        assert metrics.validation_attempts[0].attempt == 1
        assert metrics.validation_attempts[1].attempt == 2
        assert metrics.validation_attempts[2].attempt == 3
        assert metrics.rejection_count == 2


class TestCalculateDriftIndicators:
    """Test calculate_drift_indicators function."""

    def test_calculates_regression_rate(self):
        """Verify regression rate calculation is correct."""
        metrics = DriftMetrics(
            sessions=[
                SessionMetrics(
                    session_id=1,
                    timestamp="2024-01-15T10:00:00Z",
                    features_attempted=5,
                    features_completed=3,
                    regressions_caught=1,
                ),
                SessionMetrics(
                    session_id=2,
                    timestamp="2024-01-15T12:00:00Z",
                    features_attempted=5,
                    features_completed=4,
                    regressions_caught=0,
                ),
                SessionMetrics(
                    session_id=3,
                    timestamp="2024-01-15T14:00:00Z",
                    features_attempted=5,
                    features_completed=5,
                    regressions_caught=2,
                ),
                SessionMetrics(
                    session_id=4,
                    timestamp="2024-01-15T16:00:00Z",
                    features_attempted=5,
                    features_completed=3,
                    regressions_caught=0,
                ),
            ],
            total_sessions=4,
        )

        indicators = calculate_drift_indicators(metrics)

        # 2 out of 4 sessions had regressions = 50%
        assert indicators["regression_rate"] == 50.0

    def test_calculates_rejection_rate(self):
        """Verify rejection rate calculation is correct."""
        metrics = DriftMetrics(
            validation_attempts=[
                ValidationMetrics(
                    attempt=1,
                    timestamp="2024-01-15T10:00:00Z",
                    verdict="rejected",
                    features_tested=50,
                    features_failed=2,
                ),
                ValidationMetrics(
                    attempt=2,
                    timestamp="2024-01-15T12:00:00Z",
                    verdict="rejected",
                    features_tested=50,
                    features_failed=1,
                ),
                ValidationMetrics(
                    attempt=3,
                    timestamp="2024-01-15T14:00:00Z",
                    verdict="approved",
                    features_tested=50,
                    features_failed=0,
                ),
            ],
            rejection_count=2,
        )

        indicators = calculate_drift_indicators(metrics)

        # 2 out of 3 attempts rejected = 66.67%
        assert abs(indicators["rejection_rate"] - 66.67) < 0.01

    def test_velocity_trend_insufficient_data(self):
        """Verify velocity trend returns 'insufficient_data' with < 6 sessions."""
        metrics = DriftMetrics(
            sessions=[
                SessionMetrics(
                    session_id=i,
                    timestamp=f"2024-01-15T{10+i}:00:00Z",
                    features_attempted=5,
                    features_completed=3,
                )
                for i in range(5)
            ],
            total_sessions=5,
        )

        indicators = calculate_drift_indicators(metrics)

        assert indicators["velocity_trend"] == "insufficient_data"

    def test_velocity_trend_detection(self):
        """Test velocity trend detection with 6+ sessions."""
        # Increasing trend: first half avg=2, second half avg=8
        metrics = DriftMetrics(
            sessions=[
                SessionMetrics(
                    session_id=1,
                    timestamp="2024-01-15T10:00:00Z",
                    features_attempted=5,
                    features_completed=2,
                ),
                SessionMetrics(
                    session_id=2,
                    timestamp="2024-01-15T11:00:00Z",
                    features_attempted=5,
                    features_completed=2,
                ),
                SessionMetrics(
                    session_id=3,
                    timestamp="2024-01-15T12:00:00Z",
                    features_attempted=5,
                    features_completed=2,
                ),
                SessionMetrics(
                    session_id=4,
                    timestamp="2024-01-15T13:00:00Z",
                    features_attempted=10,
                    features_completed=8,
                ),
                SessionMetrics(
                    session_id=5,
                    timestamp="2024-01-15T14:00:00Z",
                    features_attempted=10,
                    features_completed=8,
                ),
                SessionMetrics(
                    session_id=6,
                    timestamp="2024-01-15T15:00:00Z",
                    features_attempted=10,
                    features_completed=8,
                ),
            ],
            total_sessions=6,
        )

        indicators = calculate_drift_indicators(metrics)

        assert indicators["velocity_trend"] == "increasing"

    def test_velocity_trend_decreasing(self):
        """Verify velocity trend detects decreasing velocity."""
        # Decreasing trend: first half avg=8, second half avg=2
        metrics = DriftMetrics(
            sessions=[
                SessionMetrics(
                    session_id=i,
                    timestamp=f"2024-01-15T{10+i}:00:00Z",
                    features_attempted=10,
                    features_completed=8 if i < 3 else 2,
                )
                for i in range(6)
            ],
            total_sessions=6,
        )

        indicators = calculate_drift_indicators(metrics)

        assert indicators["velocity_trend"] == "decreasing"

    def test_velocity_trend_stable(self):
        """Verify velocity trend detects stable velocity."""
        metrics = DriftMetrics(
            sessions=[
                SessionMetrics(
                    session_id=i,
                    timestamp=f"2024-01-15T{10+i}:00:00Z",
                    features_attempted=5,
                    features_completed=5,
                )
                for i in range(6)
            ],
            total_sessions=6,
        )

        indicators = calculate_drift_indicators(metrics)

        assert indicators["velocity_trend"] == "stable"

    def test_empty_metrics_returns_zeros(self):
        """Verify empty metrics returns zero indicators."""
        metrics = DriftMetrics()

        indicators = calculate_drift_indicators(metrics)

        assert indicators["regression_rate"] == 0.0
        assert indicators["velocity_trend"] == "insufficient_data"
        assert indicators["rejection_rate"] == 0.0


class TestIntegration:
    """Integration tests for metrics workflow."""

    def test_full_session_workflow(self, tmp_path):
        """Test complete workflow: record sessions, validate, calculate."""
        # Record 3 sessions
        record_session_metrics(
            tmp_path,
            session_id=1,
            features_attempted=10,
            features_completed=8,
            regressions_caught=1,
        )
        record_session_metrics(
            tmp_path,
            session_id=2,
            features_attempted=15,
            features_completed=12,
            regressions_caught=0,
        )
        record_session_metrics(
            tmp_path,
            session_id=3,
            features_attempted=20,
            features_completed=18,
            regressions_caught=2,
        )

        # Record validation
        record_validation_metrics(
            tmp_path,
            verdict="rejected",
            features_tested=50,
            features_failed=3,
            failure_reasons=["Bug 1", "Bug 2", "Bug 3"],
        )

        # Load and calculate
        metrics = load_metrics(tmp_path)
        indicators = calculate_drift_indicators(metrics)

        # Verify aggregates
        assert metrics.total_sessions == 3
        assert metrics.total_regressions_caught == 3
        assert metrics.average_features_per_session == (8 + 12 + 18) / 3
        assert metrics.rejection_count == 1

        # Verify indicators
        # 2 sessions had regressions out of 3
        assert abs(indicators["regression_rate"] - (2 / 3) * 100) < 0.01
        # 1 of 1 rejected
        assert indicators["rejection_rate"] == 100.0

    def test_load_after_save_preserves_data(self, tmp_path):
        """Verify round-trip save/load preserves all data."""
        original = DriftMetrics(
            sessions=[
                SessionMetrics(
                    session_id=1,
                    timestamp="2024-01-15T10:00:00Z",
                    features_attempted=5,
                    features_completed=3,
                    regressions_caught=1,
                    assumptions_stated=2,
                    assumptions_violated=0,
                    architecture_deviations=1,
                    evaluation_sections_present=["assumptions", "architecture"],
                )
            ],
            validation_attempts=[
                ValidationMetrics(
                    attempt=1,
                    timestamp="2024-01-15T12:00:00Z",
                    verdict="approved",
                    features_tested=50,
                    features_failed=0,
                    failure_reasons=[],
                )
            ],
            total_sessions=1,
            total_regressions_caught=1,
            average_features_per_session=3.0,
            rejection_count=0,
        )

        save_metrics(tmp_path, original)
        loaded = load_metrics(tmp_path)

        # Verify all fields preserved
        assert loaded.total_sessions == original.total_sessions
        assert loaded.total_regressions_caught == original.total_regressions_caught
        assert (
            loaded.average_features_per_session
            == original.average_features_per_session
        )
        assert loaded.rejection_count == original.rejection_count

        assert len(loaded.sessions) == 1
        assert loaded.sessions[0].session_id == 1
        assert loaded.sessions[0].regressions_caught == 1
        assert len(loaded.sessions[0].evaluation_sections_present) == 2

        assert len(loaded.validation_attempts) == 1
        assert loaded.validation_attempts[0].verdict == "approved"


class TestValidateMetricsIntegrity:
    """Tests for validate_metrics_integrity() function."""

    def test_valid_metrics_returns_empty_list(self):
        """Valid consistent metrics should return no errors."""
        metrics = DriftMetrics(
            sessions=[
                SessionMetrics(
                    session_id=1,
                    timestamp="2024-01-15T10:00:00Z",
                    features_attempted=5,
                    features_completed=3,
                    regressions_caught=1,
                ),
                SessionMetrics(
                    session_id=2,
                    timestamp="2024-01-15T11:00:00Z",
                    features_attempted=5,
                    features_completed=5,
                    regressions_caught=0,
                ),
            ],
            validation_attempts=[
                ValidationMetrics(
                    attempt=1,
                    timestamp="2024-01-15T12:00:00Z",
                    verdict="rejected",
                    features_tested=10,
                    features_failed=2,
                )
            ],
            total_sessions=2,
            total_regressions_caught=1,
            average_features_per_session=4.0,  # (3+5)/2
            rejection_count=1,
        )
        errors = validate_metrics_integrity(metrics)
        assert errors == []

    def test_detects_total_sessions_mismatch(self):
        """Detects when total_sessions doesn't match session count."""
        metrics = DriftMetrics(
            sessions=[
                SessionMetrics(
                    session_id=1,
                    timestamp="2024-01-15T10:00:00Z",
                    features_attempted=5,
                    features_completed=3,
                )
            ],
            total_sessions=5,  # Wrong - should be 1
        )
        errors = validate_metrics_integrity(metrics)
        assert any("total_sessions mismatch" in e for e in errors)

    def test_detects_regressions_mismatch(self):
        """Detects when total_regressions_caught doesn't match sum."""
        metrics = DriftMetrics(
            sessions=[
                SessionMetrics(
                    session_id=1,
                    timestamp="2024-01-15T10:00:00Z",
                    features_attempted=5,
                    features_completed=3,
                    regressions_caught=2,
                ),
                SessionMetrics(
                    session_id=2,
                    timestamp="2024-01-15T11:00:00Z",
                    features_attempted=5,
                    features_completed=5,
                    regressions_caught=1,
                ),
            ],
            total_sessions=2,
            total_regressions_caught=10,  # Wrong - should be 3
        )
        errors = validate_metrics_integrity(metrics)
        assert any("total_regressions_caught mismatch" in e for e in errors)

    def test_detects_average_mismatch(self):
        """Detects when average_features_per_session is wrong."""
        metrics = DriftMetrics(
            sessions=[
                SessionMetrics(
                    session_id=1,
                    timestamp="2024-01-15T10:00:00Z",
                    features_attempted=5,
                    features_completed=4,
                ),
                SessionMetrics(
                    session_id=2,
                    timestamp="2024-01-15T11:00:00Z",
                    features_attempted=5,
                    features_completed=6,
                ),
            ],
            total_sessions=2,
            average_features_per_session=10.0,  # Wrong - should be 5.0
        )
        errors = validate_metrics_integrity(metrics)
        assert any("average_features_per_session mismatch" in e for e in errors)

    def test_detects_rejection_count_mismatch(self):
        """Detects when rejection_count doesn't match verdict counts."""
        metrics = DriftMetrics(
            validation_attempts=[
                ValidationMetrics(
                    attempt=1,
                    timestamp="2024-01-15T10:00:00Z",
                    verdict="rejected",
                    features_tested=10,
                    features_failed=2,
                ),
                ValidationMetrics(
                    attempt=2,
                    timestamp="2024-01-15T11:00:00Z",
                    verdict="approved",
                    features_tested=10,
                    features_failed=0,
                ),
            ],
            rejection_count=5,  # Wrong - should be 1
        )
        errors = validate_metrics_integrity(metrics)
        assert any("rejection_count mismatch" in e for e in errors)

    def test_empty_metrics_is_valid(self):
        """Empty metrics with zeroed aggregates is valid."""
        metrics = DriftMetrics()
        errors = validate_metrics_integrity(metrics)
        assert errors == []


class TestCalculateEvaluationCompleteness:
    """Test calculate_evaluation_completeness function."""

    def test_all_sections_returns_1(self):
        """All expected sections present returns 1.0."""
        sections = ["context", "regression", "plan"]
        assert calculate_evaluation_completeness(sections) == 1.0

    def test_two_of_three_returns_two_thirds(self):
        """Two of three sections returns 2/3."""
        sections = ["context", "regression"]
        score = calculate_evaluation_completeness(sections)
        assert abs(score - 2 / 3) < FLOAT_COMPARISON_EPSILON

    def test_one_of_three_returns_one_third(self):
        """One of three sections returns 1/3."""
        sections = ["plan"]
        score = calculate_evaluation_completeness(sections)
        assert abs(score - 1 / 3) < FLOAT_COMPARISON_EPSILON

    def test_empty_list_returns_0(self):
        """Empty list returns 0.0."""
        sections = []
        assert calculate_evaluation_completeness(sections) == 0.0

    def test_ignores_unknown_sections(self):
        """Unknown section names are ignored."""
        sections = ["context", "unknown", "regression", "extra"]
        score = calculate_evaluation_completeness(sections)
        assert abs(score - 2 / 3) < FLOAT_COMPARISON_EPSILON


class TestNewMetricsFields:
    """Test new metrics fields: features_regressed, evaluation_completeness_score, is_multi_feature."""

    def test_session_metrics_includes_new_fields(self):
        """SessionMetrics includes all new fields with defaults."""
        metrics = SessionMetrics(
            session_id=1,
            timestamp="2024-01-15T10:00:00Z",
            features_attempted=1,
            features_completed=1,
        )
        assert metrics.features_regressed == 0
        assert metrics.evaluation_completeness_score == 1.0
        assert metrics.is_multi_feature is False

    def test_session_metrics_accepts_new_fields(self):
        """SessionMetrics accepts new field values."""
        metrics = SessionMetrics(
            session_id=1,
            timestamp="2024-01-15T10:00:00Z",
            features_attempted=1,
            features_completed=-2,
            features_regressed=2,
            evaluation_completeness_score=0.67,
            is_multi_feature=True,
        )
        assert metrics.features_regressed == 2
        assert metrics.evaluation_completeness_score == 0.67
        assert metrics.is_multi_feature is True

    def test_drift_metrics_includes_new_aggregates(self):
        """DriftMetrics includes new aggregate fields."""
        metrics = DriftMetrics()
        assert metrics.multi_feature_session_count == 0
        assert metrics.incomplete_evaluation_count == 0

    def test_record_session_metrics_tracks_new_fields(self, tmp_path):
        """record_session_metrics accepts and stores new fields."""
        record_session_metrics(
            project_dir=tmp_path,
            session_id=1,
            features_attempted=1,
            features_completed=3,
            features_regressed=0,
            evaluation_completeness_score=0.67,
            is_multi_feature=True,
        )

        metrics = load_metrics(tmp_path)
        session = metrics.sessions[0]
        assert session.evaluation_completeness_score == 0.67
        assert session.is_multi_feature is True
        assert metrics.multi_feature_session_count == 1
        assert metrics.incomplete_evaluation_count == 1

    def test_record_session_metrics_aggregates_counts(self, tmp_path):
        """record_session_metrics correctly aggregates new field counts."""
        # First session: multi-feature, incomplete evaluation
        record_session_metrics(
            project_dir=tmp_path,
            session_id=1,
            features_attempted=1,
            features_completed=2,
            evaluation_completeness_score=0.5,
            is_multi_feature=True,
        )
        # Second session: single-feature, complete evaluation
        record_session_metrics(
            project_dir=tmp_path,
            session_id=2,
            features_attempted=1,
            features_completed=1,
            evaluation_completeness_score=1.0,
            is_multi_feature=False,
        )
        # Third session: single-feature, incomplete evaluation
        record_session_metrics(
            project_dir=tmp_path,
            session_id=3,
            features_attempted=1,
            features_completed=0,
            evaluation_completeness_score=0.33,
            is_multi_feature=False,
        )

        metrics = load_metrics(tmp_path)
        assert metrics.multi_feature_session_count == 1
        assert metrics.incomplete_evaluation_count == 2

    def test_load_metrics_backward_compatibility(self, tmp_path):
        """load_metrics provides defaults for files without new fields."""
        # Create a metrics file without new fields (simulating old format)
        old_format = {
            "sessions": [
                {
                    "session_id": 1,
                    "timestamp": "2024-01-15T10:00:00Z",
                    "features_attempted": 1,
                    "features_completed": 1,
                    "regressions_caught": 0,
                    "assumptions_stated": 0,
                    "assumptions_violated": 0,
                    "architecture_deviations": 0,
                    "evaluation_sections_present": [],
                    # Note: no features_regressed, evaluation_completeness_score, is_multi_feature
                }
            ],
            "validation_attempts": [],
            "total_sessions": 1,
            "total_regressions_caught": 0,
            "average_features_per_session": 1.0,
            "rejection_count": 0,
            # Note: no multi_feature_session_count, incomplete_evaluation_count
        }
        metrics_path = tmp_path / METRICS_FILENAME
        with open(metrics_path, "w") as f:
            json.dump(old_format, f)

        metrics = load_metrics(tmp_path)
        session = metrics.sessions[0]

        # Check defaults applied to session
        assert session.features_regressed == 0
        assert session.evaluation_completeness_score == 1.0
        assert session.is_multi_feature is False

        # Check defaults applied to aggregates
        assert metrics.multi_feature_session_count == 0
        assert metrics.incomplete_evaluation_count == 0

    def test_record_session_metrics_validates_completeness_score(self, tmp_path):
        """record_session_metrics raises ValueError for invalid completeness score."""
        with pytest.raises(ValueError, match="evaluation_completeness_score must be 0.0-1.0"):
            record_session_metrics(
                project_dir=tmp_path,
                session_id=1,
                features_attempted=1,
                features_completed=1,
                evaluation_completeness_score=1.5,  # Invalid: > 1.0
            )

        with pytest.raises(ValueError, match="evaluation_completeness_score must be 0.0-1.0"):
            record_session_metrics(
                project_dir=tmp_path,
                session_id=1,
                features_attempted=1,
                features_completed=1,
                evaluation_completeness_score=-0.1,  # Invalid: < 0.0
            )


# =============================================================================
# Dashboard Helper Function Tests
# =============================================================================


class TestGetSessionDateRange:
    """Tests for get_session_date_range function."""

    def test_returns_none_for_empty_metrics(self):
        """Empty metrics returns None."""
        metrics = DriftMetrics()
        assert get_session_date_range(metrics) is None

    def test_returns_date_range(self):
        """Returns correct date range from sessions."""
        metrics = DriftMetrics(
            sessions=[
                SessionMetrics(
                    session_id=1,
                    timestamp="2024-01-10T10:00:00Z",
                    features_attempted=5,
                    features_completed=3,
                ),
                SessionMetrics(
                    session_id=2,
                    timestamp="2024-01-15T12:00:00Z",
                    features_attempted=5,
                    features_completed=4,
                ),
                SessionMetrics(
                    session_id=3,
                    timestamp="2024-01-20T14:00:00Z",
                    features_attempted=5,
                    features_completed=5,
                ),
            ]
        )
        date_range = get_session_date_range(metrics)
        assert date_range == ("2024-01-10", "2024-01-20")

    def test_same_date_for_single_session(self):
        """Single session returns same date for start and end."""
        metrics = DriftMetrics(
            sessions=[
                SessionMetrics(
                    session_id=1,
                    timestamp="2024-01-15T10:00:00Z",
                    features_attempted=5,
                    features_completed=3,
                ),
            ]
        )
        date_range = get_session_date_range(metrics)
        assert date_range == ("2024-01-15", "2024-01-15")


class TestGetRegressionRateTrend:
    """Tests for get_regression_rate_trend function."""

    def test_returns_empty_for_no_sessions(self):
        """Empty metrics returns empty list."""
        metrics = DriftMetrics()
        assert get_regression_rate_trend(metrics) == []

    def test_returns_regression_indicators(self):
        """Returns 1.0 for sessions with regressions, 0.0 otherwise."""
        metrics = DriftMetrics(
            sessions=[
                SessionMetrics(
                    session_id=1,
                    timestamp="2024-01-10T10:00:00Z",
                    features_attempted=5,
                    features_completed=3,
                    regressions_caught=2,
                ),
                SessionMetrics(
                    session_id=2,
                    timestamp="2024-01-11T10:00:00Z",
                    features_attempted=5,
                    features_completed=4,
                    regressions_caught=0,
                ),
                SessionMetrics(
                    session_id=3,
                    timestamp="2024-01-12T10:00:00Z",
                    features_attempted=5,
                    features_completed=5,
                    regressions_caught=1,
                ),
            ]
        )
        trend = get_regression_rate_trend(metrics)
        assert trend == [1.0, 0.0, 1.0]

    def test_respects_last_n_parameter(self):
        """Only returns last N sessions."""
        metrics = DriftMetrics(
            sessions=[
                SessionMetrics(
                    session_id=i,
                    timestamp=f"2024-01-{10+i}T10:00:00Z",
                    features_attempted=5,
                    features_completed=3,
                    regressions_caught=1 if i % 2 == 0 else 0,
                )
                for i in range(10)
            ]
        )
        trend = get_regression_rate_trend(metrics, last_n=3)
        assert len(trend) == 3


class TestGetVelocityValues:
    """Tests for get_velocity_values function."""

    def test_returns_empty_for_no_sessions(self):
        """Empty metrics returns empty list."""
        metrics = DriftMetrics()
        assert get_velocity_values(metrics) == []

    def test_returns_feature_counts(self):
        """Returns features_completed values."""
        metrics = DriftMetrics(
            sessions=[
                SessionMetrics(
                    session_id=1,
                    timestamp="2024-01-10T10:00:00Z",
                    features_attempted=5,
                    features_completed=3,
                ),
                SessionMetrics(
                    session_id=2,
                    timestamp="2024-01-11T10:00:00Z",
                    features_attempted=10,
                    features_completed=8,
                ),
            ]
        )
        values = get_velocity_values(metrics)
        assert values == [3.0, 8.0]


class TestGetArchitectureDeviationCount:
    """Tests for get_architecture_deviation_count function."""

    def test_returns_zero_for_empty_metrics(self):
        """Empty metrics returns 0."""
        metrics = DriftMetrics()
        assert get_architecture_deviation_count(metrics) == 0

    def test_sums_deviations_across_sessions(self):
        """Returns sum of architecture_deviations."""
        metrics = DriftMetrics(
            sessions=[
                SessionMetrics(
                    session_id=1,
                    timestamp="2024-01-10T10:00:00Z",
                    features_attempted=5,
                    features_completed=3,
                    architecture_deviations=2,
                ),
                SessionMetrics(
                    session_id=2,
                    timestamp="2024-01-11T10:00:00Z",
                    features_attempted=5,
                    features_completed=4,
                    architecture_deviations=3,
                ),
            ]
        )
        count = get_architecture_deviation_count(metrics)
        assert count == 5


class TestCalculateHealthStatus:
    """Tests for calculate_health_status function."""

    def test_healthy_when_all_good(self):
        """Returns 'healthy' when all indicators are good."""
        indicators = {
            "regression_rate": 10.0,
            "velocity_trend": "stable",
            "rejection_rate": 20.0,
            "multi_feature_rate": 10.0,
            "incomplete_evaluation_rate": 10.0,
        }
        assert calculate_health_status(indicators) == "healthy"

    def test_critical_on_high_regression_rate(self):
        """Returns 'critical' when regression_rate > 50%."""
        indicators = {
            "regression_rate": 60.0,
            "velocity_trend": "stable",
            "rejection_rate": 20.0,
            "multi_feature_rate": 10.0,
            "incomplete_evaluation_rate": 10.0,
        }
        assert calculate_health_status(indicators) == "critical"

    def test_critical_on_high_rejection_rate(self):
        """Returns 'critical' when rejection_rate > 60%."""
        indicators = {
            "regression_rate": 10.0,
            "velocity_trend": "stable",
            "rejection_rate": 70.0,
            "multi_feature_rate": 10.0,
            "incomplete_evaluation_rate": 10.0,
        }
        assert calculate_health_status(indicators) == "critical"

    def test_critical_on_decreasing_velocity(self):
        """Returns 'critical' when velocity_trend is 'decreasing'."""
        indicators = {
            "regression_rate": 10.0,
            "velocity_trend": "decreasing",
            "rejection_rate": 20.0,
            "multi_feature_rate": 10.0,
            "incomplete_evaluation_rate": 10.0,
        }
        assert calculate_health_status(indicators) == "critical"

    def test_warning_on_moderate_regression_rate(self):
        """Returns 'warning' when regression_rate > 25%."""
        indicators = {
            "regression_rate": 30.0,
            "velocity_trend": "stable",
            "rejection_rate": 20.0,
            "multi_feature_rate": 10.0,
            "incomplete_evaluation_rate": 10.0,
        }
        assert calculate_health_status(indicators) == "warning"

    def test_warning_on_moderate_rejection_rate(self):
        """Returns 'warning' when rejection_rate > 30%."""
        indicators = {
            "regression_rate": 10.0,
            "velocity_trend": "stable",
            "rejection_rate": 40.0,
            "multi_feature_rate": 10.0,
            "incomplete_evaluation_rate": 10.0,
        }
        assert calculate_health_status(indicators) == "warning"

    def test_warning_on_high_incomplete_eval_rate(self):
        """Returns 'warning' when incomplete_evaluation_rate > 25%."""
        indicators = {
            "regression_rate": 10.0,
            "velocity_trend": "stable",
            "rejection_rate": 20.0,
            "multi_feature_rate": 10.0,
            "incomplete_evaluation_rate": 30.0,
        }
        assert calculate_health_status(indicators) == "warning"

    def test_warning_on_high_multi_feature_rate(self):
        """Returns 'warning' when multi_feature_rate > 50%."""
        indicators = {
            "regression_rate": 10.0,
            "velocity_trend": "stable",
            "rejection_rate": 20.0,
            "multi_feature_rate": 60.0,
            "incomplete_evaluation_rate": 10.0,
        }
        assert calculate_health_status(indicators) == "warning"


class TestGenerateSparkline:
    """Tests for generate_sparkline function."""

    def test_returns_empty_for_empty_list(self):
        """Empty values returns empty string."""
        assert generate_sparkline([]) == ""

    def test_generates_sparkline_for_increasing_values(self):
        """Increasing values produce ascending sparkline."""
        sparkline = generate_sparkline([1, 2, 3, 4, 5])
        assert len(sparkline) == 5
        # First char should be lowest, last should be highest
        assert sparkline[0] == " " or sparkline[0] == "▁"
        assert sparkline[-1] == "█"

    def test_constant_values_produce_same_blocks(self):
        """Constant values produce same block characters."""
        sparkline = generate_sparkline([5, 5, 5, 5])
        assert len(sparkline) == 4
        # All should be the same character
        assert len(set(sparkline)) == 1

    def test_respects_width_parameter(self):
        """Sparkline respects width limit."""
        sparkline = generate_sparkline([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], width=5)
        # Should show last 5 values
        assert len(sparkline) == 5


class TestGetDashboardData:
    """Tests for get_dashboard_data function."""

    def test_returns_empty_dashboard_for_new_project(self, tmp_path):
        """New project returns dashboard with zero values."""
        dashboard = get_dashboard_data(tmp_path)

        assert dashboard["session_count"] == 0
        assert dashboard["date_range"] is None
        assert dashboard["regression_rate_trend"] == []
        assert dashboard["velocity_trend"] == "insufficient_data"
        assert dashboard["velocity_values"] == []
        assert dashboard["rejection_rate"] == 0.0
        assert dashboard["architecture_deviation_count"] == 0
        assert dashboard["health_status"] == "healthy"

    def test_returns_populated_dashboard(self, tmp_path):
        """Project with sessions returns populated dashboard."""
        # Record some sessions
        record_session_metrics(
            tmp_path,
            session_id=1,
            features_attempted=5,
            features_completed=3,
            regressions_caught=1,
            architecture_deviations=2,
        )
        record_session_metrics(
            tmp_path,
            session_id=2,
            features_attempted=5,
            features_completed=4,
            regressions_caught=0,
            architecture_deviations=1,
        )

        dashboard = get_dashboard_data(tmp_path)

        assert dashboard["session_count"] == 2
        assert dashboard["date_range"] is not None
        assert len(dashboard["regression_rate_trend"]) == 2
        assert len(dashboard["velocity_values"]) == 2
        assert dashboard["architecture_deviation_count"] == 3
        assert "indicators" in dashboard


# =============================================================================
# CLI Integration Tests for Drift Command
# =============================================================================


class TestDriftCLI:
    """CLI integration tests for the drift command."""

    @pytest.fixture
    def runner(self):
        """Create a CLI test runner."""
        return CliRunner()

    def test_drift_help_shows_description(self, runner):
        """Verify drift --help shows command description."""
        result = runner.invoke(main, ["drift", "--help"])
        assert result.exit_code == 0
        assert "dashboard" in result.output.lower()
        assert "--json" in result.output

    def test_drift_on_empty_project(self, runner, tmp_path):
        """Verify drift command works on empty project with no metrics."""
        result = runner.invoke(main, ["drift", str(tmp_path)])
        assert result.exit_code == 0
        assert "No sessions recorded" in result.output
        assert "HEALTHY" in result.output

    def test_drift_json_output_on_empty_project(self, runner, tmp_path):
        """Verify --json outputs valid JSON with empty metrics."""
        result = runner.invoke(main, ["drift", "--json", str(tmp_path)])
        assert result.exit_code == 0

        # Should be valid JSON
        output = json.loads(result.output)
        assert output["session_count"] == 0
        assert output["health_status"] == "healthy"
        assert output["date_range"] is None

    def test_drift_shows_sessions(self, runner, tmp_path):
        """Verify drift shows session data when metrics exist."""
        # Create some metrics
        record_session_metrics(
            tmp_path,
            session_id=1,
            features_attempted=5,
            features_completed=3,
        )

        result = runner.invoke(main, ["drift", str(tmp_path)])
        assert result.exit_code == 0
        assert "Session 1" in result.output
        assert "HEALTHY" in result.output

    def test_drift_json_output_with_data(self, runner, tmp_path):
        """Verify --json outputs correct data with metrics."""
        record_session_metrics(
            tmp_path,
            session_id=1,
            features_attempted=5,
            features_completed=3,
            regressions_caught=1,
            architecture_deviations=2,
        )
        record_session_metrics(
            tmp_path,
            session_id=2,
            features_attempted=5,
            features_completed=4,
        )

        result = runner.invoke(main, ["drift", "--json", str(tmp_path)])
        assert result.exit_code == 0

        output = json.loads(result.output)
        assert output["session_count"] == 2
        assert output["date_range"] is not None
        assert len(output["regression_rate_trend"]) == 2
        assert output["architecture_deviation_count"] == 2
        assert "indicators" in output


class TestThresholdConstants:
    """Tests to verify threshold constants are properly exported and used."""

    def test_critical_thresholds_are_exported(self):
        """Verify critical threshold constants are accessible."""
        assert REGRESSION_RATE_CRITICAL == 50
        assert REJECTION_RATE_CRITICAL == 60

    def test_warning_thresholds_are_exported(self):
        """Verify warning threshold constants are accessible."""
        assert REGRESSION_RATE_WARNING == 25
        assert REJECTION_RATE_WARNING == 30
        assert INCOMPLETE_EVAL_WARNING == 25
        assert MULTI_FEATURE_WARNING == 50

    def test_arch_deviation_thresholds_are_exported(self):
        """Verify architecture deviation thresholds are accessible."""
        assert ARCH_DEVIATION_CRITICAL == 10
        assert ARCH_DEVIATION_WARNING == 5

    def test_health_status_uses_constants(self):
        """Verify calculate_health_status respects threshold constants."""
        # Just at critical threshold should be warning (not critical)
        indicators = {
            "regression_rate": REGRESSION_RATE_CRITICAL,
            "velocity_trend": "stable",
            "rejection_rate": 0.0,
            "multi_feature_rate": 0.0,
            "incomplete_evaluation_rate": 0.0,
        }
        # Exactly at threshold is warning (using > not >=)
        assert calculate_health_status(indicators) == "warning"

        # Above critical should be critical
        indicators["regression_rate"] = REGRESSION_RATE_CRITICAL + 1
        assert calculate_health_status(indicators) == "critical"
