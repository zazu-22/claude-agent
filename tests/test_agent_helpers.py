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
        """Valid output with all 3 sections returns all identifiers and is_complete=True."""
        output = """
        ### Step A - CONTEXT VERIFICATION
        - Feature list read: [Feature 5: Add login form]

        ### Step B - REGRESSION VERIFICATION
        - Feature [3]: PASS

        ### Step C - IMPLEMENTATION PLAN
        - Will add login form component
        """
        sections, is_complete = parse_evaluation_sections(output)
        assert set(sections) == {"context", "regression", "plan"}
        assert is_complete is True

    def test_missing_sections(self):
        """Output with missing sections returns partial list and is_complete=False."""
        # Only context present
        output = "### Step A - CONTEXT VERIFICATION\nFeature list checked"
        sections, is_complete = parse_evaluation_sections(output)
        assert sections == ["context"]
        assert is_complete is False

    def test_only_regression_section(self):
        """Output with only regression section."""
        output = "### REGRESSION VERIFICATION\n- Feature [1]: PASS"
        sections, is_complete = parse_evaluation_sections(output)
        assert sections == ["regression"]
        assert is_complete is False

    def test_only_plan_section(self):
        """Output with only plan section."""
        output = "### IMPLEMENTATION PLAN\nWill build feature X"
        sections, is_complete = parse_evaluation_sections(output)
        assert sections == ["plan"]
        assert is_complete is False

    def test_empty_output(self):
        """Empty output returns empty list and is_complete=False."""
        sections, is_complete = parse_evaluation_sections("")
        assert sections == []
        assert is_complete is False

    def test_no_matching_sections(self):
        """Output without any matching sections returns empty list."""
        output = "Just some random text\nNo evaluation sections here"
        sections, is_complete = parse_evaluation_sections(output)
        assert sections == []
        assert is_complete is False

    def test_partial_match_not_counted(self):
        """Partial matches should not be counted."""
        # "CONTEXT" alone should not match
        output = "CONTEXT is important\nVERIFICATION passed"
        sections, is_complete = parse_evaluation_sections(output)
        assert sections == []
        assert is_complete is False

    def test_case_sensitivity(self):
        """Matching is case-insensitive but requires markdown header format."""
        # All uppercase with header - should match
        output = "### CONTEXT VERIFICATION done"
        sections, _ = parse_evaluation_sections(output)
        assert "context" in sections

        # Mixed case with header - should also match (case-insensitive)
        output_mixed = "### Context Verification done"
        sections_mixed, _ = parse_evaluation_sections(output_mixed)
        assert "context" in sections_mixed

        # Without markdown header prefix - should NOT match (prevents false positives)
        output_no_header = "CONTEXT VERIFICATION done"
        sections_no_header, _ = parse_evaluation_sections(output_no_header)
        assert "context" not in sections_no_header

    def test_numbered_steps(self):
        """Supports numbered steps like 'Step 1 -' in addition to lettered 'Step A -'."""
        output_numbered = "### Step 1 - CONTEXT VERIFICATION\nChecking context"
        sections, _ = parse_evaluation_sections(output_numbered)
        assert "context" in sections

        output_double_digit = "### Step 12 - REGRESSION VERIFICATION\nChecking"
        sections2, _ = parse_evaluation_sections(output_double_digit)
        assert "regression" in sections2

    def test_dash_variants(self):
        """Supports ASCII hyphen, en-dash, and em-dash."""
        # ASCII hyphen (-)
        output_hyphen = "### Step A - CONTEXT VERIFICATION"
        sections1, _ = parse_evaluation_sections(output_hyphen)
        assert "context" in sections1

        # En-dash (–)
        output_endash = "### Step B – REGRESSION VERIFICATION"
        sections2, _ = parse_evaluation_sections(output_endash)
        assert "regression" in sections2

        # Em-dash (—)
        output_emdash = "### Step C — IMPLEMENTATION PLAN"
        sections3, _ = parse_evaluation_sections(output_emdash)
        assert "plan" in sections3

    def test_minimal_spacing(self):
        """Handles headers with minimal or no spacing around dashes."""
        output_no_space = "###Step A-CONTEXT VERIFICATION"
        sections, _ = parse_evaluation_sections(output_no_space)
        assert "context" in sections

        output_tight = "### Step B-REGRESSION VERIFICATION"
        sections2, _ = parse_evaluation_sections(output_tight)
        assert "regression" in sections2

    def test_leading_whitespace(self):
        """Handles indented headers with leading whitespace."""
        output_indented = "    ### CONTEXT VERIFICATION\nChecking context"
        sections, _ = parse_evaluation_sections(output_indented)
        assert "context" in sections

        output_tabbed = "\t### REGRESSION VERIFICATION"
        sections2, _ = parse_evaluation_sections(output_tabbed)
        assert "regression" in sections2

    def test_double_hash_headers(self):
        """Supports both ## and ### header levels."""
        output_h2 = "## CONTEXT VERIFICATION"
        sections1, _ = parse_evaluation_sections(output_h2)
        assert "context" in sections1

        output_h3 = "### CONTEXT VERIFICATION"
        sections2, _ = parse_evaluation_sections(output_h3)
        assert "context" in sections2

        # Single # should not match
        output_h1 = "# CONTEXT VERIFICATION"
        sections3, _ = parse_evaluation_sections(output_h1)
        assert "context" not in sections3


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
        count, found = count_regressions(output)
        assert count == 2
        assert found is True

    def test_only_passes(self):
        """Output with only PASSes returns 0 with section found."""
        output = """
        ### REGRESSION VERIFICATION
        - Feature [1]: PASS
        - Feature [2]: PASS
        - Feature [3]: PASS
        """
        count, found = count_regressions(output)
        assert count == 0
        assert found is True

    def test_no_regression_section(self):
        """No regression section returns 0 with section not found."""
        output = """
        ### CONTEXT VERIFICATION
        Read the feature list.

        ### IMPLEMENTATION PLAN
        Will implement feature X.
        """
        count, found = count_regressions(output)
        assert count == 0
        assert found is False

    def test_case_insensitive_fail(self):
        """Matches 'FAIL', 'Fail', 'fail' case-insensitively."""
        output_upper = "### REGRESSION VERIFICATION\n- Feature [1]: FAIL"
        output_lower = "### REGRESSION VERIFICATION\n- Feature [1]: fail"
        output_mixed = "### REGRESSION VERIFICATION\n- Feature [1]: Fail"

        count1, found1 = count_regressions(output_upper)
        count2, found2 = count_regressions(output_lower)
        count3, found3 = count_regressions(output_mixed)

        assert count1 == 1 and found1 is True
        assert count2 == 1 and found2 is True
        assert count3 == 1 and found3 is True

    def test_case_insensitive_section_header(self):
        """Section header matching is case-insensitive."""
        output = "### regression verification\n- Feature [1]: FAIL"
        count, found = count_regressions(output)
        assert count == 1
        assert found is True

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
        count, found = count_regressions(output)
        assert count == 0
        assert found is True

    def test_fail_requires_colon_prefix(self):
        """FAIL must be preceded by colon to count."""
        output = """
        ### REGRESSION VERIFICATION
        - Feature [1]: PASS
        The previous FAIL was fixed.
        - Feature [2]: FAIL
        """
        # Only ": FAIL" should count, not "previous FAIL"
        count, found = count_regressions(output)
        assert count == 1
        assert found is True

    def test_empty_regression_section(self):
        """Empty regression section returns 0 with section found."""
        output = """
        ### REGRESSION VERIFICATION

        ### IMPLEMENTATION PLAN
        """
        count, found = count_regressions(output)
        assert count == 0
        assert found is True

    def test_regression_section_at_end(self):
        """Regression section at end of output (no trailing section)."""
        output = """
        ### CONTEXT VERIFICATION
        Done.

        ### REGRESSION VERIFICATION
        - Feature [1]: FAIL
        - Feature [2]: FAIL
        """
        count, found = count_regressions(output)
        assert count == 2
        assert found is True


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
