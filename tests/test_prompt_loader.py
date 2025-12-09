"""
Test prompt loading and template rendering functionality.

Tests verify:
- get_architecture_context correctly loads and formats decisions
- render_coding_prompt substitutes all template variables
- Architecture context is only included when architecture/ exists
"""

import pytest
from pathlib import Path

from claude_agent.prompts.loader import (
    get_architecture_context,
    render_coding_prompt,
    get_last_passed_feature,
)


class TestGetArchitectureContext:
    """Test architecture context generation for coding agent."""

    def test_returns_none_when_no_directory(self, tmp_path):
        """Returns None when architecture/ directory doesn't exist."""
        result = get_architecture_context(tmp_path)
        assert result is None

    def test_returns_none_when_no_decisions(self, tmp_path):
        """Returns None when decisions.yaml has no decisions."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "decisions.yaml").write_text("version: 1\ndecisions: []")

        result = get_architecture_context(tmp_path)
        assert result is None

    def test_returns_none_on_malformed_yaml(self, tmp_path):
        """Returns None gracefully when decisions.yaml is malformed."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "decisions.yaml").write_text("version: 1\ndecisions: [unclosed")

        result = get_architecture_context(tmp_path)
        assert result is None

    def test_formats_single_decision(self, tmp_path):
        """Formats a single decision correctly."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "decisions.yaml").write_text("""
version: 1
decisions:
  - id: DR-001
    topic: Authentication strategy
    choice: JWT with refresh tokens
    rationale: Spec requires stateless API
    constraints_created:
      - All authenticated endpoints must validate JWT
      - Token refresh endpoint must exist
    affects_features: [3, 5, 12]
""")

        result = get_architecture_context(tmp_path)

        assert result is not None
        assert "ARCHITECTURE DECISIONS (LOCKED)" in result
        assert "DR-001: Authentication strategy" in result
        assert "JWT with refresh tokens" in result
        assert "Spec requires stateless API" in result
        assert "All authenticated endpoints must validate JWT" in result
        assert "Token refresh endpoint must exist" in result
        assert "[3, 5, 12]" in result

    def test_formats_multiple_decisions(self, tmp_path):
        """Formats multiple decisions correctly."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "decisions.yaml").write_text("""
version: 1
decisions:
  - id: DR-001
    topic: Auth strategy
    choice: JWT
  - id: DR-002
    topic: Database
    choice: PostgreSQL
    rationale: ACID compliance needed
    constraints_created:
      - Use pg driver
""")

        result = get_architecture_context(tmp_path)

        assert result is not None
        assert "DR-001: Auth strategy" in result
        assert "DR-002: Database" in result
        assert "PostgreSQL" in result
        assert "Use pg driver" in result

    def test_handles_missing_optional_fields(self, tmp_path):
        """Formats decisions with only required fields."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "decisions.yaml").write_text("""
version: 1
decisions:
  - id: DR-001
    topic: Minimal decision
    choice: Option A
""")

        result = get_architecture_context(tmp_path)

        assert result is not None
        assert "DR-001: Minimal decision" in result
        assert "Option A" in result
        # Optional fields should not appear as empty
        assert "Rationale:" not in result
        assert "Constraints:" not in result
        assert "Affects Features:" not in result


class TestRenderCodingPrompt:
    """Test coding prompt rendering with template variables."""

    def test_substitutes_last_passed_feature(self, tmp_path):
        """Substitutes {{last_passed_feature}} placeholder."""
        # Create feature list with passing features
        import json
        feature_list = [
            {"description": "Feature 1", "passes": True},
            {"description": "Feature 2", "passes": True},
            {"description": "Feature 3", "passes": False},
        ]
        (tmp_path / "feature_list.json").write_text(json.dumps(feature_list))

        template = "Test {{last_passed_feature}} for regressions."
        result = render_coding_prompt(template, tmp_path)

        assert "Feature #1: Feature 2" in result
        assert "{{last_passed_feature}}" not in result

    def test_substitutes_architecture_context_when_present(self, tmp_path):
        """Substitutes {{architecture_context}} when architecture exists."""
        # Create architecture with decisions
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "decisions.yaml").write_text("""
version: 1
decisions:
  - id: DR-001
    topic: Test decision
    choice: Option A
""")

        template = "Before:\n{{architecture_context}}\nAfter"
        result = render_coding_prompt(template, tmp_path)

        assert "ARCHITECTURE DECISIONS (LOCKED)" in result
        assert "DR-001: Test decision" in result
        assert "{{architecture_context}}" not in result

    def test_removes_architecture_placeholder_when_missing(self, tmp_path):
        """Removes {{architecture_context}} placeholder when no architecture exists."""
        template = "Before:\n{{architecture_context}}\nAfter"
        result = render_coding_prompt(template, tmp_path)

        assert "{{architecture_context}}" not in result
        assert "Before:\n\nAfter" in result

    def test_handles_both_placeholders(self, tmp_path):
        """Handles both template placeholders correctly."""
        # Create feature list
        import json
        feature_list = [{"description": "Test feature", "passes": True}]
        (tmp_path / "feature_list.json").write_text(json.dumps(feature_list))

        # Create architecture
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "decisions.yaml").write_text("""
version: 1
decisions:
  - id: DR-001
    topic: Test
    choice: A
""")

        template = "Feature: {{last_passed_feature}}\n\n{{architecture_context}}"
        result = render_coding_prompt(template, tmp_path)

        assert "Feature #0: Test feature" in result
        assert "DR-001: Test" in result


class TestGetLastPassedFeature:
    """Test last passed feature detection."""

    def test_no_feature_list(self, tmp_path):
        """Returns fallback when no feature list exists."""
        result = get_last_passed_feature(tmp_path)
        assert result == "the most recently completed feature"

    def test_no_passing_features(self, tmp_path):
        """Returns fallback when no features are passing."""
        import json
        feature_list = [
            {"description": "Feature 1", "passes": False},
            {"description": "Feature 2", "passes": False},
        ]
        (tmp_path / "feature_list.json").write_text(json.dumps(feature_list))

        result = get_last_passed_feature(tmp_path)
        assert result == "the most recently completed feature"

    def test_returns_last_passing(self, tmp_path):
        """Returns the last (highest index) passing feature."""
        import json
        feature_list = [
            {"description": "First feature", "passes": True},
            {"description": "Second feature", "passes": True},
            {"description": "Third feature", "passes": False},
            {"description": "Fourth feature", "passes": True},
        ]
        (tmp_path / "feature_list.json").write_text(json.dumps(feature_list))

        result = get_last_passed_feature(tmp_path)
        assert result == "Feature #3: Fourth feature"

    def test_truncates_long_description(self, tmp_path):
        """Truncates descriptions longer than 50 characters."""
        import json
        long_description = "A" * 100
        feature_list = [{"description": long_description, "passes": True}]
        (tmp_path / "feature_list.json").write_text(json.dumps(feature_list))

        result = get_last_passed_feature(tmp_path)
        assert len(result) < 70  # "Feature #0: " + 50 chars
        assert result.startswith("Feature #0: ")

    def test_handles_malformed_json(self, tmp_path):
        """Returns fallback when feature list is malformed."""
        (tmp_path / "feature_list.json").write_text("not valid json")

        result = get_last_passed_feature(tmp_path)
        assert result == "the most recently completed feature"
