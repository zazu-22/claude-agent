"""
Tests for drift detection metrics tracking.
"""

import json
import pytest
from pathlib import Path

from claude_agent.metrics import (
    FLOAT_COMPARISON_EPSILON,
    METRICS_FILENAME,
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
