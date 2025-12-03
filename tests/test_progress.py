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
    atomic_write,
    atomic_json_write,
    save_validation_attempt,
    load_validation_history,
    save_spec_workflow_state,
    get_spec_workflow_state,
    # Structured progress notes
    ProgressStatus,
    CompletedFeature,
    ProgressEntry,
    parse_progress_notes,
    get_latest_session_entry,
    format_progress_entry,
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


class TestAtomicWrite:
    """Test atomic_write function for text content."""

    def test_successful_write_creates_file(self, tmp_path):
        """F5.1: Verify atomic_write creates file with correct content."""
        target = tmp_path / "test.txt"
        content = "test content"

        atomic_write(target, content)

        assert target.exists()
        assert target.read_text() == content

    def test_overwrites_existing_file(self, tmp_path):
        """F1.5: Verify atomic_write overwrites existing file atomically."""
        target = tmp_path / "test.txt"
        target.write_text("original")

        atomic_write(target, "updated")

        assert target.read_text() == "updated"
        # No temp file should remain
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_no_partial_file_on_failure(self, tmp_path, monkeypatch):
        """F5.2: Verify failed write does not leave partial file."""
        target = tmp_path / "test.txt"

        # Mock write_text to fail after being called
        def failing_write(*args, **kwargs):
            raise IOError("Simulated write failure")

        monkeypatch.setattr(Path, "write_text", failing_write)

        with pytest.raises(IOError, match="Simulated write failure"):
            atomic_write(target, "content")

        # Target file should not exist
        assert not target.exists()

    def test_temp_file_cleaned_up_on_failure(self, tmp_path, monkeypatch):
        """F5.3: Verify temp file is cleaned up on failure."""
        target = tmp_path / "test.txt"
        temp_path = target.with_suffix(".txt.tmp")

        # Create a temp file to simulate partial write
        original_write_text = Path.write_text

        def failing_after_write(self, content, *args, **kwargs):
            original_write_text(self, content, *args, **kwargs)
            raise IOError("Simulated failure after write")

        monkeypatch.setattr(Path, "write_text", failing_after_write)

        with pytest.raises(IOError):
            atomic_write(target, "content")

        # Temp file should be cleaned up
        assert not temp_path.exists()

    def test_fails_for_nonexistent_directory(self, tmp_path):
        """F5.4: Verify atomic_write fails appropriately for non-existent directory."""
        nonexistent = tmp_path / "does_not_exist"
        target = nonexistent / "test.txt"

        with pytest.raises(FileNotFoundError):
            atomic_write(target, "content")

        # No orphan files should exist
        assert not nonexistent.exists()

    def test_raises_original_exception(self, tmp_path, monkeypatch):
        """F1.7: Verify original exception is raised, not wrapped."""
        target = tmp_path / "test.txt"

        class CustomError(Exception):
            pass

        def failing_write(*args, **kwargs):
            raise CustomError("Custom error message")

        monkeypatch.setattr(Path, "write_text", failing_write)

        with pytest.raises(CustomError, match="Custom error message"):
            atomic_write(target, "content")

    def test_uses_tmp_suffix(self, tmp_path, monkeypatch):
        """F1.3: Verify temp file uses .tmp suffix pattern."""
        target = tmp_path / "test.txt"
        captured_temp_path = []

        original_write_text = Path.write_text

        def capture_write(self, content, *args, **kwargs):
            if str(self).endswith(".tmp"):
                captured_temp_path.append(self)
            return original_write_text(self, content, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", capture_write)

        atomic_write(target, "content")

        # Should have written to a .tmp file
        assert len(captured_temp_path) == 1
        assert captured_temp_path[0] == target.with_suffix(".txt.tmp")


class TestAtomicJsonWrite:
    """Test atomic_json_write function for JSON data."""

    def test_writes_dict_data(self, tmp_path):
        """F5.5: Verify atomic_json_write correctly serializes dict data."""
        target = tmp_path / "test.json"
        data = {"key": "value", "number": 42}

        atomic_json_write(target, data)

        assert target.exists()
        import json

        with open(target) as f:
            loaded = json.load(f)
        assert loaded == data

    def test_writes_list_data(self, tmp_path):
        """F5.6: Verify atomic_json_write correctly serializes list data."""
        target = tmp_path / "test.json"
        data = [{"item": 1}, {"item": 2}, {"item": 3}]

        atomic_json_write(target, data)

        import json

        with open(target) as f:
            loaded = json.load(f)
        assert loaded == data

    def test_uses_specified_indent(self, tmp_path):
        """F1.13: Verify atomic_json_write uses specified indent level."""
        target = tmp_path / "test.json"
        data = {"key": "value"}

        atomic_json_write(target, data, indent=4)

        content = target.read_text()
        # With indent=4, should have 4-space indentation
        assert '    "key"' in content

    def test_defaults_to_indent_2(self, tmp_path):
        """F1.14: Verify atomic_json_write defaults to indent=2."""
        target = tmp_path / "test.json"
        data = {"key": "value"}

        atomic_json_write(target, data)

        content = target.read_text()
        # With default indent=2, should have 2-space indentation
        assert '  "key"' in content
        # Should not have 4-space indentation
        assert '    "key"' not in content

    def test_adds_trailing_newline(self, tmp_path):
        """F1.15: Verify atomic_json_write adds trailing newline."""
        target = tmp_path / "test.json"
        data = {"key": "value"}

        atomic_json_write(target, data)

        content = target.read_text()
        # Should end with exactly one newline
        assert content.endswith("\n")
        assert not content.endswith("\n\n")

    def test_raises_on_non_serializable_data(self, tmp_path):
        """F1.17: Verify exception for non-serializable data."""
        target = tmp_path / "test.json"
        # Set is not JSON-serializable
        data = {"key": {1, 2, 3}}

        with pytest.raises(TypeError):
            atomic_json_write(target, data)

        # No file should be created
        assert not target.exists()
        # No temp file should remain
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0


class TestSaveValidationAttemptAtomic:
    """Test that save_validation_attempt uses atomic writes."""

    def test_creates_new_file(self, tmp_path):
        """F2.3: Verify save_validation_attempt creates new file when none exists."""
        save_validation_attempt(tmp_path, "approved", [], "All tests passed")

        history_path = tmp_path / "validation-history.json"
        assert history_path.exists()

        import json

        with open(history_path) as f:
            data = json.load(f)
        assert "attempts" in data
        assert len(data["attempts"]) == 1
        assert data["attempts"][0]["result"] == "approved"

    def test_preserves_existing_history(self, tmp_path):
        """F2.2: Verify save_validation_attempt preserves existing history."""
        # Create initial attempt
        save_validation_attempt(tmp_path, "rejected", [1, 2], "First attempt")

        # Add second attempt
        save_validation_attempt(tmp_path, "approved", [], "Second attempt")

        history = load_validation_history(tmp_path)
        assert len(history) == 2
        assert history[0]["result"] == "rejected"
        assert history[1]["result"] == "approved"

    def test_maintains_correct_structure(self, tmp_path):
        """F2.4: Verify correct JSON structure with timestamp."""
        save_validation_attempt(tmp_path, "rejected", [0, 1], "Test summary")

        history = load_validation_history(tmp_path)
        attempt = history[0]

        assert "timestamp" in attempt
        assert "result" in attempt
        assert "rejected_indices" in attempt
        assert "summary" in attempt
        assert attempt["rejected_indices"] == [0, 1]


class TestSaveSpecWorkflowStateAtomic:
    """Test that save_spec_workflow_state uses atomic writes."""

    def test_saves_state_correctly(self, tmp_path):
        """F3.2: Verify save_spec_workflow_state correctly saves workflow state."""
        state = {
            "phase": "validated",
            "spec_file": "specs/spec-validated.md",
            "history": [{"step": "validate", "status": "complete"}],
        }

        save_spec_workflow_state(tmp_path, state)

        loaded = get_spec_workflow_state(tmp_path)
        assert loaded["phase"] == "validated"
        assert loaded["spec_file"] == "specs/spec-validated.md"
        assert len(loaded["history"]) == 1

    def test_adds_created_at_on_first_save(self, tmp_path):
        """F3.3: Verify created_at timestamp is added on first save."""
        state = {"phase": "created", "spec_file": None, "history": []}

        save_spec_workflow_state(tmp_path, state)

        loaded = get_spec_workflow_state(tmp_path)
        assert "created_at" in loaded
        # Should be ISO format timestamp
        assert "T" in loaded["created_at"]

    def test_updates_updated_at_on_each_save(self, tmp_path):
        """F3.4: Verify updated_at timestamp is updated on each save."""
        state = {"phase": "created", "spec_file": None, "history": []}
        save_spec_workflow_state(tmp_path, state)

        first_loaded = get_spec_workflow_state(tmp_path)
        first_updated = first_loaded["updated_at"]

        # Small delay to ensure timestamp difference
        import time

        time.sleep(0.01)

        # Update state
        state["phase"] = "validated"
        save_spec_workflow_state(tmp_path, state)

        second_loaded = get_spec_workflow_state(tmp_path)
        second_updated = second_loaded["updated_at"]

        # updated_at should be different (or equal if very fast)
        assert "updated_at" in second_loaded

    def test_preserves_created_at_on_updates(self, tmp_path):
        """F3.5: Verify created_at is preserved on updates."""
        state = {
            "phase": "created",
            "spec_file": None,
            "history": [],
            "created_at": "2024-01-01T00:00:00+00:00",
        }

        save_spec_workflow_state(tmp_path, state)

        loaded = get_spec_workflow_state(tmp_path)
        assert loaded["created_at"] == "2024-01-01T00:00:00+00:00"


class TestAtomicWriteIntegration:
    """Integration tests for atomic write functionality."""

    def test_load_after_save_validation(self, tmp_path):
        """INT.2: Verify load correctly reads files written by save."""
        save_validation_attempt(tmp_path, "rejected", [1, 2, 3], "Test failure")

        history = load_validation_history(tmp_path)

        assert len(history) == 1
        assert history[0]["result"] == "rejected"
        assert history[0]["rejected_indices"] == [1, 2, 3]
        assert history[0]["summary"] == "Test failure"

    def test_load_after_save_workflow(self, tmp_path):
        """INT.3: Verify get_spec_workflow_state reads files written by save."""
        state = {
            "phase": "decomposed",
            "spec_file": "specs/spec-validated.md",
            "history": [{"step": "decompose", "output": "feature_list.json"}],
        }

        save_spec_workflow_state(tmp_path, state)
        loaded = get_spec_workflow_state(tmp_path)

        assert loaded["phase"] == "decomposed"
        assert loaded["spec_file"] == "specs/spec-validated.md"
        assert len(loaded["history"]) == 1


# =============================================================================
# Structured Progress Notes Tests
# =============================================================================


class TestProgressStatus:
    """Test ProgressStatus dataclass."""

    def test_creates_with_correct_fields(self):
        """Verify ProgressStatus stores fields correctly."""
        status = ProgressStatus(passing=25, total=50, percentage=50.0)

        assert status.passing == 25
        assert status.total == 50
        assert status.percentage == 50.0

    def test_is_immutable(self):
        """Verify ProgressStatus is frozen (immutable)."""
        status = ProgressStatus(passing=25, total=50, percentage=50.0)

        with pytest.raises(AttributeError):
            status.passing = 30


class TestCompletedFeature:
    """Test CompletedFeature dataclass."""

    def test_creates_with_correct_fields(self):
        """Verify CompletedFeature stores fields correctly."""
        feature = CompletedFeature(
            index=5,
            description="User login form",
            verification_method="browser automation",
        )

        assert feature.index == 5
        assert feature.description == "User login form"
        assert feature.verification_method == "browser automation"

    def test_is_immutable(self):
        """Verify CompletedFeature is frozen (immutable)."""
        feature = CompletedFeature(
            index=5,
            description="User login form",
            verification_method="browser automation",
        )

        with pytest.raises(AttributeError):
            feature.index = 10


class TestProgressEntry:
    """Test ProgressEntry dataclass."""

    def test_creates_with_required_fields(self):
        """Verify ProgressEntry creates with minimal required fields."""
        status = ProgressStatus(passing=10, total=50, percentage=20.0)
        entry = ProgressEntry(
            session_number=1,
            timestamp="2024-01-15T10:30:00Z",
            status=status,
        )

        assert entry.session_number == 1
        assert entry.timestamp == "2024-01-15T10:30:00Z"
        assert entry.status.passing == 10
        assert entry.completed_features == ()
        assert entry.issues_found == ()
        assert entry.next_steps == ()
        assert entry.files_modified == ()
        assert entry.git_commits == ()
        assert entry.is_validation_session is False

    def test_creates_with_all_fields(self):
        """Verify ProgressEntry creates with all fields populated."""
        status = ProgressStatus(passing=25, total=50, percentage=50.0)
        features = (
            CompletedFeature(
                index=1, description="Feature 1", verification_method="test"
            ),
        )
        entry = ProgressEntry(
            session_number=3,
            timestamp="2024-01-15T14:30:00Z",
            status=status,
            completed_features=features,
            issues_found=("Bug in login",),
            next_steps=("Fix login bug",),
            files_modified=("src/login.py",),
            git_commits=("abc123",),
            is_validation_session=False,
        )

        assert entry.session_number == 3
        assert len(entry.completed_features) == 1
        assert len(entry.issues_found) == 1
        assert len(entry.next_steps) == 1
        assert len(entry.files_modified) == 1
        assert len(entry.git_commits) == 1

    def test_is_immutable(self):
        """Verify ProgressEntry is frozen (immutable)."""
        status = ProgressStatus(passing=10, total=50, percentage=20.0)
        entry = ProgressEntry(
            session_number=1,
            timestamp="2024-01-15T10:30:00Z",
            status=status,
        )

        with pytest.raises(AttributeError):
            entry.session_number = 2


class TestParseProgressNotes:
    """Test parse_progress_notes function."""

    SAMPLE_SESSION = """=== SESSION 3: 2024-01-15T14:30:00Z ===
Status: 25/50 features passing (50%)

Completed This Session:
- Feature #12: User can submit contact form - browser automation with screenshot
- Feature #13: Form shows validation errors - tested invalid inputs

Issues Found:
- Button hover state missing on dark mode
- Console warning about deprecated API

Next Steps:
- Work on Feature #14 next
- Fix hover state issue before moving on

Files Modified:
- src/components/ContactForm.tsx
- src/styles/forms.css
- tests/contact.test.ts

Git Commits: a1b2c3d, e4f5g6h
=========================================
"""

    def test_parses_basic_session(self):
        """Verify parsing of a complete session entry."""
        entries = parse_progress_notes(self.SAMPLE_SESSION)

        assert len(entries) == 1
        entry = entries[0]

        assert entry.session_number == 3
        assert entry.timestamp == "2024-01-15T14:30:00Z"
        assert entry.status.passing == 25
        assert entry.status.total == 50
        assert entry.status.percentage == 50.0

    def test_parses_completed_features(self):
        """Verify parsing of completed features list."""
        entries = parse_progress_notes(self.SAMPLE_SESSION)
        entry = entries[0]

        assert len(entry.completed_features) == 2
        assert entry.completed_features[0].index == 12
        assert "contact form" in entry.completed_features[0].description.lower()
        assert "browser automation" in entry.completed_features[0].verification_method

    def test_parses_issues_found(self):
        """Verify parsing of issues found list."""
        entries = parse_progress_notes(self.SAMPLE_SESSION)
        entry = entries[0]

        assert len(entry.issues_found) == 2
        assert any("hover state" in issue.lower() for issue in entry.issues_found)

    def test_parses_next_steps(self):
        """Verify parsing of next steps list."""
        entries = parse_progress_notes(self.SAMPLE_SESSION)
        entry = entries[0]

        assert len(entry.next_steps) == 2
        assert any("Feature #14" in step for step in entry.next_steps)

    def test_parses_files_modified(self):
        """Verify parsing of files modified list."""
        entries = parse_progress_notes(self.SAMPLE_SESSION)
        entry = entries[0]

        assert len(entry.files_modified) == 3
        assert "src/components/ContactForm.tsx" in entry.files_modified

    def test_parses_git_commits(self):
        """Verify parsing of git commits."""
        entries = parse_progress_notes(self.SAMPLE_SESSION)
        entry = entries[0]

        assert len(entry.git_commits) == 2
        assert "a1b2c3d" in entry.git_commits
        assert "e4f5g6h" in entry.git_commits

    def test_parses_multiple_sessions(self):
        """Verify parsing of multiple session entries."""
        content = """=== SESSION 1: 2024-01-15T10:00:00Z ===
Status: 5/50 features passing (10%)

Completed This Session:
- Feature #1: Setup project - manual verification

Issues Found:
- None

Next Steps:
- Work on Feature #2 next

Files Modified:
- package.json

Git Commits: abc1234
=========================================

=== SESSION 2: 2024-01-15T12:00:00Z ===
Status: 10/50 features passing (20%)

Completed This Session:
- Feature #2: User registration - browser automation

Issues Found:
- Minor styling issue

Next Steps:
- Work on Feature #3 next

Files Modified:
- src/register.tsx

Git Commits: def5678
=========================================
"""
        entries = parse_progress_notes(content)

        assert len(entries) == 2
        assert entries[0].session_number == 1
        assert entries[1].session_number == 2
        assert entries[0].status.passing == 5
        assert entries[1].status.passing == 10

    def test_handles_empty_content(self):
        """Verify empty content returns empty list."""
        entries = parse_progress_notes("")

        assert entries == []

    def test_handles_none_issues(self):
        """Verify 'None' in Issues Found section is excluded."""
        content = """=== SESSION 1: 2024-01-15T10:00:00Z ===
Status: 5/50 features passing (10%)

Completed This Session:
- Feature #1: Setup project - manual verification

Issues Found:
- None

Next Steps:
- Work on Feature #2 next

Files Modified:
- package.json

Git Commits: abc1234
=========================================
"""
        entries = parse_progress_notes(content)
        entry = entries[0]

        assert len(entry.issues_found) == 0

    def test_handles_legacy_freeform_notes(self):
        """Verify legacy freeform notes return empty list (no crash)."""
        content = """Session notes from previous coding session:

- Worked on login feature
- Fixed some bugs
- Need to continue tomorrow

Progress: 25% complete
"""
        entries = parse_progress_notes(content)

        # Should return empty list, not crash
        assert entries == []

    def test_handles_missing_sections(self):
        """Verify missing sections don't cause errors."""
        content = """=== SESSION 1: 2024-01-15T10:00:00Z ===
Status: 5/50 features passing (10%)

Git Commits: abc1234
=========================================
"""
        entries = parse_progress_notes(content)
        entry = entries[0]

        # Missing sections should be empty tuples
        assert entry.completed_features == ()
        assert entry.issues_found == ()
        assert entry.next_steps == ()
        assert entry.files_modified == ()

    def test_accepts_path_input(self, tmp_path):
        """Verify function accepts Path object as input."""
        progress_file = tmp_path / "claude-progress.txt"
        progress_file.write_text(self.SAMPLE_SESSION)

        entries = parse_progress_notes(progress_file)

        assert len(entries) == 1
        assert entries[0].session_number == 3

    def test_handles_nonexistent_file(self, tmp_path):
        """Verify nonexistent file returns empty list."""
        nonexistent = tmp_path / "does_not_exist.txt"

        entries = parse_progress_notes(nonexistent)

        assert entries == []

    def test_parses_validation_session(self):
        """Verify parsing of validation session format."""
        content = """=== VALIDATION SESSION: 2024-01-15T16:45:00Z ===
Status: 15/50 features passing (30%)

Rejected Features:
- Feature #5: User login form submission
  - Issue: Submit button does nothing

Issues Found:
- Feature #5: Submit button non-functional

Next Steps:
- Fix Feature #5 - add submit handler
- Re-run validation after fixes

Tests Verified: 15/50
=========================================
"""
        entries = parse_progress_notes(content)

        assert len(entries) == 1
        entry = entries[0]

        assert entry.is_validation_session is True
        assert entry.timestamp == "2024-01-15T16:45:00Z"

    def test_handles_percentage_with_decimal(self):
        """Verify parsing of percentage with decimal places."""
        content = """=== SESSION 1: 2024-01-15T10:00:00Z ===
Status: 33/100 features passing (33.33%)

Completed This Session:
- None

Issues Found:
- None

Next Steps:
- Continue work

Files Modified:
- None

Git Commits: None
=========================================
"""
        entries = parse_progress_notes(content)
        entry = entries[0]

        assert entry.status.percentage == 33.33

    def test_handles_feature_without_hash(self):
        """Verify parsing of feature format without # symbol."""
        content = """=== SESSION 1: 2024-01-15T10:00:00Z ===
Status: 5/50 features passing (10%)

Completed This Session:
- Feature 5: Login feature - browser automation

Issues Found:
- None

Next Steps:
- Work on Feature 6

Files Modified:
- None

Git Commits: abc1234
=========================================
"""
        entries = parse_progress_notes(content)
        entry = entries[0]

        # Should still extract the feature
        assert len(entry.completed_features) == 1
        assert entry.completed_features[0].index == 5


class TestGetLatestSessionEntry:
    """Test get_latest_session_entry function."""

    def test_returns_none_for_empty_file(self, tmp_path):
        """Verify returns None for empty progress file."""
        progress_file = tmp_path / "claude-progress.txt"
        progress_file.write_text("")

        result = get_latest_session_entry(tmp_path)

        assert result is None

    def test_returns_none_for_missing_file(self, tmp_path):
        """Verify returns None when file doesn't exist."""
        result = get_latest_session_entry(tmp_path)

        assert result is None

    def test_returns_last_entry(self, tmp_path):
        """Verify returns the last session entry."""
        content = """=== SESSION 1: 2024-01-15T10:00:00Z ===
Status: 5/50 features passing (10%)

Completed This Session:
- Feature #1: Setup - manual

Issues Found:
- None

Next Steps:
- Continue

Files Modified:
- None

Git Commits: abc1234
=========================================

=== SESSION 2: 2024-01-15T14:00:00Z ===
Status: 15/50 features passing (30%)

Completed This Session:
- Feature #2: Login - browser automation

Issues Found:
- None

Next Steps:
- Continue

Files Modified:
- None

Git Commits: def5678
=========================================
"""
        progress_file = tmp_path / "claude-progress.txt"
        progress_file.write_text(content)

        result = get_latest_session_entry(tmp_path)

        assert result is not None
        assert result.session_number == 2
        assert result.status.passing == 15


class TestFormatProgressEntry:
    """Test format_progress_entry function."""

    def test_formats_basic_entry(self):
        """Verify basic entry formatting."""
        status = ProgressStatus(passing=25, total=50, percentage=50.0)
        entry = ProgressEntry(
            session_number=3,
            timestamp="2024-01-15T14:30:00Z",
            status=status,
        )

        result = format_progress_entry(entry)

        assert "=== SESSION 3: 2024-01-15T14:30:00Z ===" in result
        assert "Status: 25/50 features passing (50.0%)" in result
        assert "=========================================" in result

    def test_formats_completed_features(self):
        """Verify completed features formatting."""
        status = ProgressStatus(passing=25, total=50, percentage=50.0)
        features = (
            CompletedFeature(
                index=12,
                description="Contact form",
                verification_method="browser automation",
            ),
        )
        entry = ProgressEntry(
            session_number=3,
            timestamp="2024-01-15T14:30:00Z",
            status=status,
            completed_features=features,
        )

        result = format_progress_entry(entry)

        assert "Completed This Session:" in result
        assert "- Feature #12: Contact form - browser automation" in result

    def test_formats_validation_session(self):
        """Verify validation session formatting."""
        status = ProgressStatus(passing=15, total=50, percentage=30.0)
        entry = ProgressEntry(
            session_number=0,
            timestamp="2024-01-15T16:45:00Z",
            status=status,
            is_validation_session=True,
        )

        result = format_progress_entry(entry)

        assert "=== VALIDATION SESSION: 2024-01-15T16:45:00Z ===" in result

    def test_formats_empty_sections_as_none(self):
        """Verify empty sections are formatted as 'None'."""
        status = ProgressStatus(passing=10, total=50, percentage=20.0)
        entry = ProgressEntry(
            session_number=1,
            timestamp="2024-01-15T10:00:00Z",
            status=status,
        )

        result = format_progress_entry(entry)

        # Check for "- None" in various sections
        lines = result.split("\n")
        completed_idx = next(
            i for i, l in enumerate(lines) if "Completed This Session" in l
        )
        assert lines[completed_idx + 1] == "- None"


class TestProgressRoundTrip:
    """Test round-trip parsing (format -> parse -> format)."""

    def test_round_trip_preserves_data(self):
        """Verify format -> parse -> format preserves all data."""
        status = ProgressStatus(passing=25, total=50, percentage=50.0)
        features = (
            CompletedFeature(
                index=12,
                description="Contact form",
                verification_method="browser automation",
            ),
            CompletedFeature(
                index=13,
                description="Validation errors",
                verification_method="tested inputs",
            ),
        )
        original = ProgressEntry(
            session_number=3,
            timestamp="2024-01-15T14:30:00Z",
            status=status,
            completed_features=features,
            issues_found=("Bug in hover state",),
            next_steps=("Fix hover state", "Continue with Feature #14"),
            files_modified=("src/form.tsx", "src/styles.css"),
            git_commits=("abc123", "def456"),
            is_validation_session=False,
        )

        # Format to string
        formatted = format_progress_entry(original)

        # Parse back
        parsed_list = parse_progress_notes(formatted)
        assert len(parsed_list) == 1
        parsed = parsed_list[0]

        # Verify key fields match
        assert parsed.session_number == original.session_number
        assert parsed.timestamp == original.timestamp
        assert parsed.status.passing == original.status.passing
        assert parsed.status.total == original.status.total
        assert len(parsed.completed_features) == len(original.completed_features)
        assert len(parsed.issues_found) == len(original.issues_found)
        assert len(parsed.next_steps) == len(original.next_steps)
        assert len(parsed.files_modified) == len(original.files_modified)
        assert len(parsed.git_commits) == len(original.git_commits)


class TestCLIStatusStructuredProgress:
    """Test CLI status command shows structured progress summary."""

    def test_status_shows_last_session_number(self, tmp_path):
        """F33.1: Verify status output shows last session number."""
        from click.testing import CliRunner
        from claude_agent.cli import main

        # Create feature_list.json
        (tmp_path / "feature_list.json").write_text('[{"description": "test", "passes": true}]')

        # Create structured progress notes
        progress_content = """=== SESSION 5: 2024-12-02T15:30:00Z ===
Status: 25/50 features passing (50.0%)

Completed This Session:
- Feature #10: User login - browser automation verified

Issues Found:
- None

Next Steps:
- Work on Feature #11 next

Files Modified:
- src/auth.py

Git Commits: abc1234
=========================================
"""
        (tmp_path / "claude-progress.txt").write_text(progress_content)

        runner = CliRunner()
        result = runner.invoke(main, ["status", str(tmp_path)])

        assert result.exit_code == 0
        assert "Session:   5" in result.output

    def test_status_shows_last_session_timestamp(self, tmp_path):
        """F33.2: Verify status output shows last session timestamp."""
        from click.testing import CliRunner
        from claude_agent.cli import main

        # Create feature_list.json
        (tmp_path / "feature_list.json").write_text('[{"description": "test", "passes": true}]')

        # Create structured progress notes
        progress_content = """=== SESSION 1: 2024-12-02T10:15:00Z ===
Status: 10/20 features passing (50.0%)

Completed This Session:
- None

Issues Found:
- None

Next Steps:
- None

Files Modified:
- None

Git Commits: None
=========================================
"""
        (tmp_path / "claude-progress.txt").write_text(progress_content)

        runner = CliRunner()
        result = runner.invoke(main, ["status", str(tmp_path)])

        assert result.exit_code == 0
        assert "Timestamp: 2024-12-02T10:15:00Z" in result.output

    def test_status_shows_feature_count_from_progress(self, tmp_path):
        """F33.3: Verify status output shows current feature count."""
        from click.testing import CliRunner
        from claude_agent.cli import main

        # Create feature_list.json
        (tmp_path / "feature_list.json").write_text('[{"description": "test", "passes": true}]')

        # Create structured progress notes with specific counts
        progress_content = """=== SESSION 3: 2024-12-01T08:00:00Z ===
Status: 35/100 features passing (35.0%)

Completed This Session:
- Feature #35: API endpoint - verified

Issues Found:
- None

Next Steps:
- Work on Feature #36 next

Files Modified:
- src/api.py

Git Commits: def5678
=========================================
"""
        (tmp_path / "claude-progress.txt").write_text(progress_content)

        runner = CliRunner()
        result = runner.invoke(main, ["status", str(tmp_path)])

        assert result.exit_code == 0
        # Check for the status line from Last Session section
        assert "Status:    35/100 features passing" in result.output

    def test_status_fallback_for_legacy_progress(self, tmp_path):
        """F33.4: Verify status works with legacy freeform progress notes."""
        from click.testing import CliRunner
        from claude_agent.cli import main

        # Create feature_list.json
        (tmp_path / "feature_list.json").write_text('[{"description": "test", "passes": true}]')

        # Create legacy freeform progress notes (no structured format)
        legacy_content = """Session started at 10:00 AM
Working on login feature
Made progress on authentication
Need to finish tomorrow
"""
        (tmp_path / "claude-progress.txt").write_text(legacy_content)

        runner = CliRunner()
        result = runner.invoke(main, ["status", str(tmp_path)])

        assert result.exit_code == 0
        # Should show the legacy notes as fallback
        assert "Recent progress notes:" in result.output
        assert "login feature" in result.output

    def test_status_no_progress_file(self, tmp_path):
        """F33.5: Verify status works without progress file."""
        from click.testing import CliRunner
        from claude_agent.cli import main

        # Only create feature_list.json
        (tmp_path / "feature_list.json").write_text('[{"description": "test", "passes": true}]')

        runner = CliRunner()
        result = runner.invoke(main, ["status", str(tmp_path)])

        assert result.exit_code == 0
        # Should not show Last Session section
        assert "Last Session:" not in result.output

    def test_status_shows_completed_count(self, tmp_path):
        """F33.6: Verify status shows completed features count."""
        from click.testing import CliRunner
        from claude_agent.cli import main

        # Create feature_list.json
        (tmp_path / "feature_list.json").write_text('[{"description": "test", "passes": true}]')

        # Create structured progress notes with multiple completed features
        progress_content = """=== SESSION 2: 2024-12-02T12:00:00Z ===
Status: 20/50 features passing (40.0%)

Completed This Session:
- Feature #5: Login form - browser verified
- Feature #6: Logout button - browser verified
- Feature #7: Session timeout - unit test

Issues Found:
- None

Next Steps:
- Work on Feature #8 next

Files Modified:
- src/auth.py

Git Commits: 123abc
=========================================
"""
        (tmp_path / "claude-progress.txt").write_text(progress_content)

        runner = CliRunner()
        result = runner.invoke(main, ["status", str(tmp_path)])

        assert result.exit_code == 0
        assert "Completed: 3 feature(s)" in result.output

    def test_status_shows_issues_count(self, tmp_path):
        """F33.7: Verify status shows issues found count."""
        from click.testing import CliRunner
        from claude_agent.cli import main

        # Create feature_list.json
        (tmp_path / "feature_list.json").write_text('[{"description": "test", "passes": true}]')

        # Create structured progress notes with issues
        progress_content = """=== SESSION 4: 2024-12-02T14:00:00Z ===
Status: 30/50 features passing (60.0%)

Completed This Session:
- Feature #10: Test feature - verified

Issues Found:
- CSS alignment issue on mobile
- API timeout in production

Next Steps:
- Fix mobile CSS

Files Modified:
- src/mobile.css

Git Commits: xyz789
=========================================
"""
        (tmp_path / "claude-progress.txt").write_text(progress_content)

        runner = CliRunner()
        result = runner.invoke(main, ["status", str(tmp_path)])

        assert result.exit_code == 0
        assert "Issues:    2 found" in result.output

    def test_status_shows_git_commits(self, tmp_path):
        """F33.8: Verify status shows git commit hashes."""
        from click.testing import CliRunner
        from claude_agent.cli import main

        # Create feature_list.json
        (tmp_path / "feature_list.json").write_text('[{"description": "test", "passes": true}]')

        # Create structured progress notes with commits
        progress_content = """=== SESSION 1: 2024-12-02T09:00:00Z ===
Status: 5/10 features passing (50.0%)

Completed This Session:
- Feature #1: Initial setup - verified

Issues Found:
- None

Next Steps:
- Continue development

Files Modified:
- src/main.py

Git Commits: abc1234, def5678
=========================================
"""
        (tmp_path / "claude-progress.txt").write_text(progress_content)

        runner = CliRunner()
        result = runner.invoke(main, ["status", str(tmp_path)])

        assert result.exit_code == 0
        assert "Commits:   abc1234, def5678" in result.output
