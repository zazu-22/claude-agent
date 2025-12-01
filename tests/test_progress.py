"""
Tests for progress tracking utilities.
"""

import pytest
from pathlib import Path

from claude_agent.progress import (
    ValidationVerdict,
    parse_validation_verdict,
    find_spec_draft,
    find_spec_validated,
    find_spec_validation_report,
    find_spec_for_coding,
)


class TestParseValidationVerdict:
    """Test parse_validation_verdict function."""

    def test_parses_machine_readable_pass(self, tmp_path):
        """Verify parsing of machine-readable PASS verdict."""
        validation_content = """<!-- VALIDATION_RESULT
verdict: PASS
blocking: 0
warnings: 2
suggestions: 5
-->

# Validation Report

**Verdict: PASS**

Spec looks good!
"""
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        (specs_dir / "spec-validation.md").write_text(validation_content)

        verdict = parse_validation_verdict(tmp_path)

        assert verdict.passed is True
        assert verdict.verdict == "PASS"
        assert verdict.blocking == 0
        assert verdict.warnings == 2
        assert verdict.suggestions == 5
        assert verdict.error is None

    def test_parses_machine_readable_fail(self, tmp_path):
        """Verify parsing of machine-readable FAIL verdict."""
        validation_content = """<!-- VALIDATION_RESULT
verdict: FAIL
blocking: 3
warnings: 1
suggestions: 0
-->

# Validation Report

**Verdict: FAIL**

Critical issues found.
"""
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        (specs_dir / "spec-validation.md").write_text(validation_content)

        verdict = parse_validation_verdict(tmp_path)

        assert verdict.passed is False
        assert verdict.verdict == "FAIL"
        assert verdict.blocking == 3
        assert verdict.warnings == 1
        assert verdict.suggestions == 0
        assert verdict.error is None

    def test_fallback_to_legacy_format(self, tmp_path):
        """Verify fallback parsing for older format without VALIDATION_RESULT block."""
        # Old format without machine-readable block
        validation_content = """# Validation Report

**Verdict: PASS**

| Severity | Count |
|----------|-------|
| BLOCKING | 0     |
| WARNING  | 2     |
| SUGGESTION | 3   |
"""
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        (specs_dir / "spec-validation.md").write_text(validation_content)

        verdict = parse_validation_verdict(tmp_path)

        assert verdict.passed is True
        assert verdict.verdict == "PASS"
        assert verdict.blocking == 0

    def test_handles_missing_validation_file(self, tmp_path):
        """Verify error handling when validation file doesn't exist."""
        verdict = parse_validation_verdict(tmp_path)

        assert verdict.passed is False
        assert verdict.verdict == "UNKNOWN"
        assert verdict.error == "spec-validation.md not found"

    def test_case_insensitive_verdict_parsing(self, tmp_path):
        """Verify verdict parsing is case-insensitive."""
        validation_content = """<!-- VALIDATION_RESULT
verdict: pass
blocking: 0
warnings: 0
suggestions: 0
-->
"""
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        (specs_dir / "spec-validation.md").write_text(validation_content)

        verdict = parse_validation_verdict(tmp_path)

        assert verdict.verdict == "PASS"  # Normalized to uppercase
        assert verdict.passed is True

    def test_infers_verdict_from_blocking_count(self, tmp_path):
        """Verify fallback to inferring verdict from blocking count."""
        # No explicit verdict, but has blocking count in table
        validation_content = """# Validation Report

| Severity | Count |
|----------|-------|
| BLOCKING | 0     |
| WARNING  | 1     |
"""
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        (specs_dir / "spec-validation.md").write_text(validation_content)

        verdict = parse_validation_verdict(tmp_path)

        assert verdict.passed is True
        assert verdict.verdict == "PASS"
        assert verdict.blocking == 0
        # Error indicates it was inferred
        assert verdict.error is not None
        assert "Inferred" in verdict.error

    def test_infers_fail_from_blocking_count(self, tmp_path):
        """Verify inferring FAIL verdict when blocking count > 0."""
        validation_content = """# Validation Report

| Severity | Count |
|----------|-------|
| BLOCKING | 2     |
| WARNING  | 1     |
"""
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        (specs_dir / "spec-validation.md").write_text(validation_content)

        verdict = parse_validation_verdict(tmp_path)

        assert verdict.passed is False
        assert verdict.verdict == "FAIL"
        assert verdict.blocking == 2

    def test_finds_file_in_subdirectory(self, tmp_path):
        """Verify finding validation file in specs/ subdirectory."""
        validation_content = """<!-- VALIDATION_RESULT
verdict: PASS
blocking: 0
warnings: 0
suggestions: 0
-->
"""
        # Create in nested subdirectory
        subdir = tmp_path / "specs" / "feature-name"
        subdir.mkdir(parents=True)
        (subdir / "spec-validation.md").write_text(validation_content)

        verdict = parse_validation_verdict(tmp_path)

        assert verdict.passed is True
        assert verdict.verdict == "PASS"

    def test_prefers_specs_over_root(self, tmp_path):
        """Verify specs/ location is preferred over project root."""
        root_content = """<!-- VALIDATION_RESULT
verdict: FAIL
blocking: 1
warnings: 0
suggestions: 0
-->
"""
        specs_content = """<!-- VALIDATION_RESULT
verdict: PASS
blocking: 0
warnings: 0
suggestions: 0
-->
"""
        # Create in both locations
        (tmp_path / "spec-validation.md").write_text(root_content)
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        (specs_dir / "spec-validation.md").write_text(specs_content)

        verdict = parse_validation_verdict(tmp_path)

        # Should prefer specs/ location with PASS
        assert verdict.passed is True
        assert verdict.verdict == "PASS"


class TestValidationVerdictImmutability:
    """Test that ValidationVerdict is immutable."""

    def test_cannot_modify_verdict(self):
        """Verify ValidationVerdict fields cannot be modified."""
        verdict = ValidationVerdict(
            passed=True,
            verdict="PASS",
            blocking=0,
            warnings=1,
            suggestions=2,
        )

        with pytest.raises(AttributeError):
            verdict.passed = False

        with pytest.raises(AttributeError):
            verdict.verdict = "FAIL"


class TestFindSpecFiles:
    """Test find_spec_* functions."""

    def test_find_spec_draft_in_specs(self, tmp_path):
        """Find spec-draft.md in specs/ directory."""
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        draft_path = specs_dir / "spec-draft.md"
        draft_path.write_text("# Draft")

        result = find_spec_draft(tmp_path)

        assert result == draft_path

    def test_find_spec_draft_in_root(self, tmp_path):
        """Find spec-draft.md in project root."""
        draft_path = tmp_path / "spec-draft.md"
        draft_path.write_text("# Draft")

        result = find_spec_draft(tmp_path)

        assert result == draft_path

    def test_find_spec_draft_in_subdirectory(self, tmp_path):
        """Find spec-draft.md in specs/ subdirectory (backwards compat)."""
        subdir = tmp_path / "specs" / "feature-name"
        subdir.mkdir(parents=True)
        draft_path = subdir / "spec-draft.md"
        draft_path.write_text("# Draft")

        result = find_spec_draft(tmp_path)

        assert result == draft_path

    def test_find_spec_draft_not_found(self, tmp_path):
        """Return None when spec-draft.md doesn't exist."""
        result = find_spec_draft(tmp_path)

        assert result is None

    def test_find_spec_validated_in_specs(self, tmp_path):
        """Find spec-validated.md in specs/ directory."""
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        validated_path = specs_dir / "spec-validated.md"
        validated_path.write_text("# Validated")

        result = find_spec_validated(tmp_path)

        assert result == validated_path

    def test_find_spec_validation_report_in_specs(self, tmp_path):
        """Find spec-validation.md in specs/ directory."""
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        report_path = specs_dir / "spec-validation.md"
        report_path.write_text("# Report")

        result = find_spec_validation_report(tmp_path)

        assert result == report_path

    def test_prefers_specs_over_root(self, tmp_path):
        """Verify specs/ location is preferred over project root."""
        # Create in both locations
        (tmp_path / "spec-draft.md").write_text("# Root Draft")
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        specs_path = specs_dir / "spec-draft.md"
        specs_path.write_text("# Specs Draft")

        result = find_spec_draft(tmp_path)

        # Should prefer specs/ location
        assert result == specs_path


class TestFindSpecForCoding:
    """Test find_spec_for_coding() function for coding/validator agents.

    This function implements priority-based spec file discovery:
    1. specs/spec-validated.md (canonical spec workflow output)
    2. specs/app_spec.txt (external spec copied location)
    3. app_spec.txt (legacy fallback in project root)
    """

    def test_function_exists_with_correct_signature(self):
        """F1.1: Verify find_spec_for_coding function exists with proper typing."""
        import inspect
        from typing import Optional

        # Function should exist and be callable
        assert callable(find_spec_for_coding)

        # Check signature
        sig = inspect.signature(find_spec_for_coding)
        params = list(sig.parameters.keys())
        assert params == ["project_dir"]

        # Return type should be Optional[Path] (check via annotation)
        # Note: We can't easily verify Optional[Path] at runtime,
        # so we verify the function returns Path or None in other tests

    def test_returns_spec_validated_first_priority(self, tmp_path):
        """F1.2: Returns specs/spec-validated.md when it exists."""
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        spec_validated = specs_dir / "spec-validated.md"
        spec_validated.write_text("# Validated Spec")

        result = find_spec_for_coding(tmp_path)

        assert result == spec_validated
        assert result.exists()

    def test_returns_specs_app_spec_second_priority(self, tmp_path):
        """F1.3: Returns specs/app_spec.txt when spec-validated.md missing."""
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        # Only create specs/app_spec.txt (no spec-validated.md)
        app_spec = specs_dir / "app_spec.txt"
        app_spec.write_text("# App Spec")

        result = find_spec_for_coding(tmp_path)

        assert result == app_spec
        assert result.exists()

    def test_returns_root_app_spec_third_priority(self, tmp_path):
        """F1.4: Returns root app_spec.txt as legacy fallback."""
        # Only create root app_spec.txt (no specs/ files)
        app_spec = tmp_path / "app_spec.txt"
        app_spec.write_text("# Legacy App Spec")

        result = find_spec_for_coding(tmp_path)

        assert result == app_spec
        assert result.exists()

    def test_returns_none_when_no_spec_files_exist(self, tmp_path):
        """F1.5: Returns None when no spec files exist."""
        # Empty directory - no spec files
        result = find_spec_for_coding(tmp_path)

        assert result is None

    def test_priority_order_spec_validated_wins(self, tmp_path):
        """F1.6: spec-validated.md wins when multiple files exist."""
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()

        # Create all three files
        spec_validated = specs_dir / "spec-validated.md"
        spec_validated.write_text("# Validated Spec")
        specs_app_spec = specs_dir / "app_spec.txt"
        specs_app_spec.write_text("# Specs App Spec")
        root_app_spec = tmp_path / "app_spec.txt"
        root_app_spec.write_text("# Root App Spec")

        result = find_spec_for_coding(tmp_path)

        # Should return highest priority (spec-validated.md)
        assert result == spec_validated

    def test_has_proper_docstring(self):
        """F1.7: Function has docstring explaining search priority."""
        docstring = find_spec_for_coding.__doc__

        assert docstring is not None
        # Docstring should mention the three search locations
        assert "spec-validated.md" in docstring
        assert "app_spec.txt" in docstring
        # Should mention priority order
        assert "priority" in docstring.lower() or "Priority" in docstring

    def test_handles_nonexistent_directory(self, tmp_path):
        """ERR.1: Handles non-existent project directory gracefully."""
        nonexistent = tmp_path / "does_not_exist"

        # Should return None without exception
        result = find_spec_for_coding(nonexistent)

        assert result is None

    def test_specs_app_spec_over_root_app_spec(self, tmp_path):
        """Verify specs/app_spec.txt is preferred over root app_spec.txt."""
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()

        # Create both app_spec.txt files (but not spec-validated.md)
        specs_app_spec = specs_dir / "app_spec.txt"
        specs_app_spec.write_text("# Specs App Spec")
        root_app_spec = tmp_path / "app_spec.txt"
        root_app_spec.write_text("# Root App Spec")

        result = find_spec_for_coding(tmp_path)

        # Should return specs/app_spec.txt (priority 2 over priority 3)
        assert result == specs_app_spec

    def test_emits_deprecation_warning_for_root_app_spec(self, tmp_path, capsys):
        """F9.1: Verify deprecation warning when using root app_spec.txt."""
        import claude_agent.progress as progress_module

        # Reset the warning flag for this test
        progress_module._root_app_spec_warning_shown = False

        # Only create root app_spec.txt (legacy location)
        app_spec = tmp_path / "app_spec.txt"
        app_spec.write_text("# Legacy App Spec")

        result = find_spec_for_coding(tmp_path)

        # Should still return the file
        assert result == app_spec

        # Should emit warning to stderr
        captured = capsys.readouterr()
        assert "Warning: app_spec.txt found in project root" in captured.err
        assert "specs/app_spec.txt" in captured.err

    def test_deprecation_warning_only_shown_once(self, tmp_path, capsys):
        """F9.2: Verify deprecation warning only appears once per session."""
        import claude_agent.progress as progress_module

        # Reset the warning flag for this test
        progress_module._root_app_spec_warning_shown = False

        # Only create root app_spec.txt
        app_spec = tmp_path / "app_spec.txt"
        app_spec.write_text("# Legacy App Spec")

        # Call multiple times
        find_spec_for_coding(tmp_path)
        find_spec_for_coding(tmp_path)
        find_spec_for_coding(tmp_path)

        # Should only have one warning
        captured = capsys.readouterr()
        warning_count = captured.err.count("Warning: app_spec.txt found in project root")
        assert warning_count == 1

    def test_no_deprecation_warning_for_specs_location(self, tmp_path, capsys):
        """F9.3: Verify no warning when using specs/app_spec.txt."""
        import claude_agent.progress as progress_module

        # Reset the warning flag for this test
        progress_module._root_app_spec_warning_shown = False

        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        app_spec = specs_dir / "app_spec.txt"
        app_spec.write_text("# App Spec")

        result = find_spec_for_coding(tmp_path)

        # Should return the file
        assert result == app_spec

        # Should NOT emit warning
        captured = capsys.readouterr()
        assert "Warning" not in captured.err
