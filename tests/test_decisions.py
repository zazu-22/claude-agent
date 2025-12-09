"""
Test decision record protocol functionality.

Tests verify:
- Decision records serialize/deserialize correctly
- Append-only semantics are enforced
- Feature-relevant queries work correctly
- ID generation is sequential
"""

import pytest
import yaml
from pathlib import Path

from claude_agent.decisions import (
    DecisionRecord,
    DecisionLoadError,
    load_decisions,
    append_decision,
    get_next_decision_id,
    get_relevant_decisions,
    get_all_constraints,
)


class TestDecisionRecord:
    """Test DecisionRecord dataclass."""

    def test_create_minimal(self):
        """DecisionRecord can be created with minimal required fields."""
        record = DecisionRecord(
            id="DR-001",
            timestamp="2024-01-15T10:00:00Z",
            session=1,
            topic="Test topic",
            choice="Option A",
            alternatives_considered=["Option B"],
            rationale="Because A is better",
            constraints_created=["Must use A"],
        )
        assert record.id == "DR-001"
        assert record.affects_features == []  # Default empty

    def test_create_full(self):
        """DecisionRecord stores all fields including affects_features."""
        record = DecisionRecord(
            id="DR-002",
            timestamp="2024-01-15T10:00:00Z",
            session=2,
            topic="Another topic",
            choice="Choice",
            alternatives_considered=[],
            rationale="Reasons",
            constraints_created=[],
            affects_features=[1, 5, 10],
        )
        assert record.affects_features == [1, 5, 10]


class TestLoadDecisions:
    """Test loading decisions from file."""

    def test_load_nonexistent(self, tmp_path):
        """Returns empty list when file doesn't exist."""
        decisions = load_decisions(tmp_path)
        assert decisions == []

    def test_load_empty(self, tmp_path):
        """Returns empty list when file has no decisions."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "decisions.yaml").write_text("version: 1\ndecisions: []")

        decisions = load_decisions(tmp_path)
        assert decisions == []

    def test_load_existing(self, tmp_path):
        """Loads decisions correctly from YAML."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "decisions.yaml").write_text("""
version: 1
decisions:
  - id: DR-001
    topic: Test
    choice: A
    alternatives_considered:
      - B
    rationale: Testing
    constraints_created:
      - Use A
    affects_features: [1, 2]
""")

        decisions = load_decisions(tmp_path)
        assert len(decisions) == 1
        assert decisions[0].id == "DR-001"
        assert decisions[0].affects_features == [1, 2]

    def test_load_handles_missing_optional_fields(self, tmp_path):
        """Loads decisions with missing optional fields using None defaults."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "decisions.yaml").write_text("""
version: 1
decisions:
  - id: DR-001
    topic: Test
    choice: A
""")

        decisions = load_decisions(tmp_path)
        assert len(decisions) == 1
        assert decisions[0].id == "DR-001"
        # Optional fields default to None for consistency (Issue #39)
        assert decisions[0].timestamp is None
        assert decisions[0].session is None
        assert decisions[0].rationale is None
        # List fields still default to empty lists
        assert decisions[0].alternatives_considered == []
        assert decisions[0].constraints_created == []
        assert decisions[0].affects_features == []


class TestLoadDecisionsErrorHandling:
    """Test error handling for malformed decisions files."""

    def test_malformed_yaml_raises_error(self, tmp_path):
        """Raises DecisionLoadError for invalid YAML syntax."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "decisions.yaml").write_text("""
version: 1
decisions:
  - id: DR-001
    topic: [unclosed bracket
""")

        with pytest.raises(DecisionLoadError) as exc_info:
            load_decisions(tmp_path)
        assert "Failed to parse decisions.yaml" in str(exc_info.value)

    def test_non_dict_root_raises_error(self, tmp_path):
        """Raises DecisionLoadError when root is not a dict."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "decisions.yaml").write_text("- just a list\n- of items")

        with pytest.raises(DecisionLoadError) as exc_info:
            load_decisions(tmp_path)
        assert "expected dict, got list" in str(exc_info.value)

    def test_decisions_not_list_raises_error(self, tmp_path):
        """Raises DecisionLoadError when 'decisions' field is not a list."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "decisions.yaml").write_text("""
version: 1
decisions: "not a list"
""")

        with pytest.raises(DecisionLoadError) as exc_info:
            load_decisions(tmp_path)
        assert "expected list, got str" in str(exc_info.value)

    def test_decision_not_dict_raises_error(self, tmp_path):
        """Raises DecisionLoadError when a decision entry is not a dict."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "decisions.yaml").write_text("""
version: 1
decisions:
  - "just a string"
""")

        with pytest.raises(DecisionLoadError) as exc_info:
            load_decisions(tmp_path)
        assert "Invalid decision at index 0" in str(exc_info.value)
        assert "expected dict, got str" in str(exc_info.value)

    def test_missing_required_field_id_raises_error(self, tmp_path):
        """Raises DecisionLoadError when 'id' field is missing."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "decisions.yaml").write_text("""
version: 1
decisions:
  - topic: Test
    choice: A
""")

        with pytest.raises(DecisionLoadError) as exc_info:
            load_decisions(tmp_path)
        assert "missing required fields: id" in str(exc_info.value)

    def test_missing_required_field_topic_raises_error(self, tmp_path):
        """Raises DecisionLoadError when 'topic' field is missing."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "decisions.yaml").write_text("""
version: 1
decisions:
  - id: DR-001
    choice: A
""")

        with pytest.raises(DecisionLoadError) as exc_info:
            load_decisions(tmp_path)
        assert "missing required fields: topic" in str(exc_info.value)

    def test_missing_required_field_choice_raises_error(self, tmp_path):
        """Raises DecisionLoadError when 'choice' field is missing."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "decisions.yaml").write_text("""
version: 1
decisions:
  - id: DR-001
    topic: Test
""")

        with pytest.raises(DecisionLoadError) as exc_info:
            load_decisions(tmp_path)
        assert "missing required fields: choice" in str(exc_info.value)

    def test_missing_multiple_required_fields_raises_error(self, tmp_path):
        """Raises DecisionLoadError listing all missing required fields."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "decisions.yaml").write_text("""
version: 1
decisions:
  - rationale: Only optional field
""")

        with pytest.raises(DecisionLoadError) as exc_info:
            load_decisions(tmp_path)
        error_msg = str(exc_info.value)
        assert "id" in error_msg
        assert "topic" in error_msg
        assert "choice" in error_msg

    def test_error_at_second_decision_reports_correct_index(self, tmp_path):
        """Error message includes correct index for failed decision."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "decisions.yaml").write_text("""
version: 1
decisions:
  - id: DR-001
    topic: Valid
    choice: A
  - id: DR-002
    topic: Missing choice
""")

        with pytest.raises(DecisionLoadError) as exc_info:
            load_decisions(tmp_path)
        assert "Decision at index 1" in str(exc_info.value)


class TestAppendDecision:
    """Test appending decisions to file."""

    def test_append_creates_file(self, tmp_path):
        """Creates file if it doesn't exist."""
        record = DecisionRecord(
            id="DR-001",
            timestamp="2024-01-15T10:00:00Z",
            session=1,
            topic="Test",
            choice="A",
            alternatives_considered=[],
            rationale="Test",
            constraints_created=[],
        )

        append_decision(tmp_path, record)

        decisions = load_decisions(tmp_path)
        assert len(decisions) == 1
        assert decisions[0].id == "DR-001"

    def test_append_creates_directory(self, tmp_path):
        """Creates architecture directory if missing."""
        record = DecisionRecord(
            id="DR-001",
            timestamp="",
            session=1,
            topic="Test",
            choice="A",
            alternatives_considered=[],
            rationale="",
            constraints_created=[],
        )

        # Directory doesn't exist yet
        arch_dir = tmp_path / "architecture"
        assert not arch_dir.exists()

        append_decision(tmp_path, record)

        # Directory was created
        assert arch_dir.exists()
        assert (arch_dir / "decisions.yaml").exists()

    def test_append_preserves_existing(self, tmp_path):
        """Appending preserves existing decisions."""
        # Create first decision
        record1 = DecisionRecord(
            id="DR-001", timestamp="", session=1,
            topic="First", choice="A", alternatives_considered=[],
            rationale="", constraints_created=[],
        )
        append_decision(tmp_path, record1)

        # Append second
        record2 = DecisionRecord(
            id="DR-002", timestamp="", session=2,
            topic="Second", choice="B", alternatives_considered=[],
            rationale="", constraints_created=[],
        )
        append_decision(tmp_path, record2)

        decisions = load_decisions(tmp_path)
        assert len(decisions) == 2
        assert decisions[0].id == "DR-001"
        assert decisions[1].id == "DR-002"

    def test_append_preserves_existing_file_metadata(self, tmp_path):
        """Appending preserves version and locked_at from existing file."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "decisions.yaml").write_text("""
version: 1
locked_at: "2024-01-01T00:00:00Z"
decisions:
  - id: DR-001
    topic: Existing
    choice: A
""")

        record = DecisionRecord(
            id="DR-002", timestamp="", session=2,
            topic="New", choice="B", alternatives_considered=[],
            rationale="", constraints_created=[],
        )
        append_decision(tmp_path, record)

        # Read raw file to check metadata preserved
        with open(arch_dir / "decisions.yaml") as f:
            data = yaml.safe_load(f)

        assert data["version"] == 1
        assert data["locked_at"] == "2024-01-01T00:00:00Z"
        assert len(data["decisions"]) == 2


class TestGetNextDecisionId:
    """Test ID generation."""

    def test_first_id(self, tmp_path):
        """First ID is DR-001."""
        assert get_next_decision_id(tmp_path) == "DR-001"

    def test_increments(self, tmp_path):
        """IDs increment correctly."""
        record = DecisionRecord(
            id="DR-005", timestamp="", session=1,
            topic="", choice="", alternatives_considered=[],
            rationale="", constraints_created=[],
        )
        append_decision(tmp_path, record)

        assert get_next_decision_id(tmp_path) == "DR-006"

    def test_increments_from_last(self, tmp_path):
        """Gets next ID from last decision, not count."""
        # Add two decisions with non-sequential IDs
        record1 = DecisionRecord(
            id="DR-001", timestamp="", session=1,
            topic="", choice="", alternatives_considered=[],
            rationale="", constraints_created=[],
        )
        append_decision(tmp_path, record1)

        record2 = DecisionRecord(
            id="DR-010", timestamp="", session=2,
            topic="", choice="", alternatives_considered=[],
            rationale="", constraints_created=[],
        )
        append_decision(tmp_path, record2)

        # Should increment from last (DR-010), not count (DR-003)
        assert get_next_decision_id(tmp_path) == "DR-011"

    def test_handles_malformed_id(self, tmp_path):
        """Handles malformed IDs gracefully."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        # Write decision with malformed ID
        (arch_dir / "decisions.yaml").write_text("""
version: 1
decisions:
  - id: MALFORMED
    topic: Test
    choice: A
""")

        # Should fall back to count-based ID
        next_id = get_next_decision_id(tmp_path)
        assert next_id == "DR-002"


class TestGetRelevantDecisions:
    """Test feature-relevant decision queries."""

    def test_filters_by_feature(self, tmp_path):
        """Returns only decisions affecting the specified feature."""
        # Decision affecting features 1, 2
        append_decision(tmp_path, DecisionRecord(
            id="DR-001", timestamp="", session=1,
            topic="A", choice="", alternatives_considered=[],
            rationale="", constraints_created=[],
            affects_features=[1, 2],
        ))

        # Decision affecting features 3, 4
        append_decision(tmp_path, DecisionRecord(
            id="DR-002", timestamp="", session=1,
            topic="B", choice="", alternatives_considered=[],
            rationale="", constraints_created=[],
            affects_features=[3, 4],
        ))

        relevant = get_relevant_decisions(tmp_path, feature_index=2)
        assert len(relevant) == 1
        assert relevant[0].id == "DR-001"

    def test_returns_multiple_relevant(self, tmp_path):
        """Returns multiple decisions when feature is in multiple."""
        # Both decisions affect feature 5
        append_decision(tmp_path, DecisionRecord(
            id="DR-001", timestamp="", session=1,
            topic="A", choice="", alternatives_considered=[],
            rationale="", constraints_created=[],
            affects_features=[1, 5],
        ))

        append_decision(tmp_path, DecisionRecord(
            id="DR-002", timestamp="", session=1,
            topic="B", choice="", alternatives_considered=[],
            rationale="", constraints_created=[],
            affects_features=[5, 10],
        ))

        relevant = get_relevant_decisions(tmp_path, feature_index=5)
        assert len(relevant) == 2

    def test_empty_when_no_relevant(self, tmp_path):
        """Returns empty list when no decisions affect feature."""
        append_decision(tmp_path, DecisionRecord(
            id="DR-001", timestamp="", session=1,
            topic="A", choice="", alternatives_considered=[],
            rationale="", constraints_created=[],
            affects_features=[1, 2, 3],
        ))

        relevant = get_relevant_decisions(tmp_path, feature_index=99)
        assert relevant == []

    def test_empty_when_no_decisions(self, tmp_path):
        """Returns empty list when no decisions exist."""
        relevant = get_relevant_decisions(tmp_path, feature_index=1)
        assert relevant == []


class TestGetAllConstraints:
    """Test constraint aggregation."""

    def test_aggregates_constraints(self, tmp_path):
        """Returns all constraints from all decisions."""
        append_decision(tmp_path, DecisionRecord(
            id="DR-001", timestamp="", session=1,
            topic="", choice="", alternatives_considered=[],
            rationale="", constraints_created=["C1", "C2"],
        ))
        append_decision(tmp_path, DecisionRecord(
            id="DR-002", timestamp="", session=1,
            topic="", choice="", alternatives_considered=[],
            rationale="", constraints_created=["C3"],
        ))

        constraints = get_all_constraints(tmp_path)
        assert constraints == ["C1", "C2", "C3"]

    def test_empty_when_no_constraints(self, tmp_path):
        """Returns empty list when no constraints exist."""
        append_decision(tmp_path, DecisionRecord(
            id="DR-001", timestamp="", session=1,
            topic="", choice="", alternatives_considered=[],
            rationale="", constraints_created=[],
        ))

        constraints = get_all_constraints(tmp_path)
        assert constraints == []

    def test_empty_when_no_decisions(self, tmp_path):
        """Returns empty list when no decisions exist."""
        constraints = get_all_constraints(tmp_path)
        assert constraints == []
