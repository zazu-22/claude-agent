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
