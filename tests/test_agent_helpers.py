"""
Tests for agent.py helper functions.
=========================================

Tests for parse_evaluation_sections(), count_regressions(), and get_next_session_id().
"""

import pytest
from pathlib import Path

from claude_agent.agent import get_next_session_id
from claude_agent.metrics import count_regressions, parse_evaluation_sections


class TestParseEvaluationSections:
    """Tests for parse_evaluation_sections() function."""

    def test_all_sections_present(self):
        """Valid output with all 3 sections returns all identifiers."""
        output = """
        ### Step A - CONTEXT VERIFICATION
        - Feature list read: [Feature 5: Add login form]

        ### Step B - REGRESSION VERIFICATION
        - Feature [3]: PASS

        ### Step C - IMPLEMENTATION PLAN
        - Will add login form component
        """
        result = parse_evaluation_sections(output)
        assert set(result) == {"context", "regression", "plan"}

    def test_missing_sections(self):
        """Output with missing sections returns partial list."""
        # Only context present
        output = "### Step A - CONTEXT VERIFICATION\nFeature list checked"
        result = parse_evaluation_sections(output)
        assert result == ["context"]

    def test_only_regression_section(self):
        """Output with only regression section."""
        output = "### REGRESSION VERIFICATION\n- Feature [1]: PASS"
        result = parse_evaluation_sections(output)
        assert result == ["regression"]

    def test_only_plan_section(self):
        """Output with only plan section."""
        output = "### IMPLEMENTATION PLAN\nWill build feature X"
        result = parse_evaluation_sections(output)
        assert result == ["plan"]

    def test_empty_output(self):
        """Empty output returns empty list."""
        result = parse_evaluation_sections("")
        assert result == []

    def test_no_matching_sections(self):
        """Output without any matching sections returns empty list."""
        output = "Just some random text\nNo evaluation sections here"
        result = parse_evaluation_sections(output)
        assert result == []

    def test_partial_match_not_counted(self):
        """Partial matches should not be counted."""
        # "CONTEXT" alone should not match
        output = "CONTEXT is important\nVERIFICATION passed"
        result = parse_evaluation_sections(output)
        assert result == []

    def test_case_sensitivity(self):
        """Current implementation is case-sensitive."""
        # All uppercase - should match
        output = "CONTEXT VERIFICATION done"
        assert "context" in parse_evaluation_sections(output)

        # Mixed case - won't match (current behavior)
        output_lower = "Context Verification done"
        assert "context" not in parse_evaluation_sections(output_lower)


class TestCountRegressions:
    """Tests for count_regressions() function."""

    def test_multiple_fails(self):
        """Output with multiple FAILs in regression section."""
        output = """
        ### REGRESSION VERIFICATION
        - Feature [5]: FAIL
          Evidence: "Button broken"
        - Feature [7]: PASS
          Evidence: "Works correctly"
        - Feature [12]: FAIL
          Evidence: "Form submission fails"
        """
        assert count_regressions(output) == 2

    def test_only_passes(self):
        """Output with only PASSes returns 0."""
        output = """
        ### REGRESSION VERIFICATION
        - Feature [1]: PASS
        - Feature [2]: PASS
        - Feature [3]: PASS
        """
        assert count_regressions(output) == 0

    def test_no_regression_section(self):
        """No regression section returns 0."""
        output = """
        ### CONTEXT VERIFICATION
        Read the feature list.

        ### IMPLEMENTATION PLAN
        Will implement feature X.
        """
        assert count_regressions(output) == 0

    def test_case_insensitive_fail(self):
        """Matches 'FAIL', 'Fail', 'fail' case-insensitively."""
        output_upper = "### REGRESSION VERIFICATION\n- Feature [1]: FAIL"
        output_lower = "### REGRESSION VERIFICATION\n- Feature [1]: fail"
        output_mixed = "### REGRESSION VERIFICATION\n- Feature [1]: Fail"

        assert count_regressions(output_upper) == 1
        assert count_regressions(output_lower) == 1
        assert count_regressions(output_mixed) == 1

    def test_case_insensitive_section_header(self):
        """Section header matching is case-insensitive."""
        output = "### regression verification\n- Feature [1]: FAIL"
        assert count_regressions(output) == 1

    def test_fail_outside_section_not_counted(self):
        """FAIL outside regression section is not counted."""
        output = """
        ### CONTEXT VERIFICATION
        The previous session had a FAIL in testing.

        ### REGRESSION VERIFICATION
        - Feature [1]: PASS

        ### IMPLEMENTATION PLAN
        Will fix the FAIL from before.
        """
        # Only the regression section should be searched
        assert count_regressions(output) == 0

    def test_fail_requires_colon_prefix(self):
        """FAIL must be preceded by colon to count."""
        output = """
        ### REGRESSION VERIFICATION
        - Feature [1]: PASS
        The previous FAIL was fixed.
        - Feature [2]: FAIL
        """
        # Only ": FAIL" should count, not "previous FAIL"
        assert count_regressions(output) == 1

    def test_empty_regression_section(self):
        """Empty regression section returns 0."""
        output = """
        ### REGRESSION VERIFICATION

        ### IMPLEMENTATION PLAN
        """
        assert count_regressions(output) == 0

    def test_regression_section_at_end(self):
        """Regression section at end of output (no trailing section)."""
        output = """
        ### CONTEXT VERIFICATION
        Done.

        ### REGRESSION VERIFICATION
        - Feature [1]: FAIL
        - Feature [2]: FAIL
        """
        assert count_regressions(output) == 2


class TestGetNextSessionId:
    """Tests for get_next_session_id() function."""

    def test_no_progress_file(self, tmp_path):
        """No progress file returns 1."""
        result = get_next_session_id(tmp_path)
        assert result == 1

    def test_empty_progress_file(self, tmp_path):
        """Empty progress file returns 1."""
        progress_file = tmp_path / "claude-progress.txt"
        progress_file.write_text("")
        result = get_next_session_id(tmp_path)
        assert result == 1

    def test_with_existing_sessions(self, tmp_path):
        """Existing sessions returns max + 1."""
        progress_file = tmp_path / "claude-progress.txt"
        # Write structured progress notes
        progress_file.write_text("""
=== SESSION 1: 2024-01-15T10:00:00Z ===
Status: 5/20 features passing (25%)

## Context Verification
- Feature list state: [quoted]

## Handoff Notes
Current state: In progress

=========================================

=== SESSION 2: 2024-01-15T11:00:00Z ===
Status: 8/20 features passing (40%)

## Context Verification
- Feature list state: [quoted]

## Handoff Notes
Current state: Continuing

=========================================
""")
        result = get_next_session_id(tmp_path)
        assert result == 3

    def test_malformed_file_returns_1(self, tmp_path):
        """Malformed file returns 1 (graceful degradation)."""
        progress_file = tmp_path / "claude-progress.txt"
        progress_file.write_text("This is not structured progress notes")
        result = get_next_session_id(tmp_path)
        assert result == 1

    def test_session_id_gaps(self, tmp_path):
        """Gaps in session IDs still returns max + 1."""
        progress_file = tmp_path / "claude-progress.txt"
        # Sessions 1, 3, 5 (gaps at 2, 4)
        progress_file.write_text("""
=== SESSION 1: 2024-01-15T10:00:00Z ===
Status: 1/10 features passing (10%)

## Context Verification
- Feature list: checked

## Handoff Notes
Current state: Started

=========================================

=== SESSION 3: 2024-01-15T11:00:00Z ===
Status: 3/10 features passing (30%)

## Context Verification
- Feature list: checked

## Handoff Notes
Current state: Continuing

=========================================

=== SESSION 5: 2024-01-15T12:00:00Z ===
Status: 5/10 features passing (50%)

## Context Verification
- Feature list: checked

## Handoff Notes
Current state: Half done

=========================================
""")
        result = get_next_session_id(tmp_path)
        assert result == 6  # max(1, 3, 5) + 1 = 6

    def test_validation_sessions_not_counted(self, tmp_path):
        """Validation sessions use separate numbering and don't affect session IDs."""
        progress_file = tmp_path / "claude-progress.txt"
        # Validation sessions have format "=== VALIDATION SESSION: timestamp ===" (no number)
        # They use -1 internally and don't count toward coding session IDs
        progress_file.write_text("""
=== SESSION 2: 2024-01-15T10:00:00Z ===
Status: 5/10 features passing (50%)

## Context Verification
- Feature list: checked

## Handoff Notes
Current state: Done

=========================================

=== VALIDATION SESSION: 2024-01-15T11:00:00Z ===
Verdict: REJECTED

## Features Tested
- Feature 1: FAIL - Button missing

## Handoff Notes
Current state: Needs fixes

=========================================
""")
        result = get_next_session_id(tmp_path)
        # Validation sessions don't increment coding session count
        # max coding session is 2, so next should be 3
        assert result == 3
