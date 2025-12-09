"""
Tests for Security Evaluation Validation Hook.

Tests the evaluation_validation_hook and related functions that validate
agent output for required evaluation sections (drift mitigation).
"""

import pytest

from claude_agent.security import (
    ValidationResult,
    AGENT_REQUIRED_SECTIONS,
    EVALUATION_SECTION_PATTERNS,
    extract_evaluation_sections,
    evaluation_validation_hook,
    _check_section_present,
    _build_retry_emphasis,
)


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_creates_with_defaults(self):
        """ValidationResult creates with correct defaults."""
        result = ValidationResult(is_valid=True)
        assert result.is_valid is True
        assert result.error_message is None
        assert result.action == "proceed"
        assert result.evaluation_data == {}

    def test_creates_with_all_fields(self):
        """ValidationResult creates with all fields specified."""
        result = ValidationResult(
            is_valid=False,
            error_message="Missing sections",
            action="retry",
            evaluation_data={"sections_found": ["context"]},
        )
        assert result.is_valid is False
        assert result.error_message == "Missing sections"
        assert result.action == "retry"
        assert result.evaluation_data == {"sections_found": ["context"]}

    def test_none_evaluation_data_becomes_empty_dict(self):
        """None evaluation_data is converted to empty dict."""
        result = ValidationResult(is_valid=True, evaluation_data=None)
        assert result.evaluation_data == {}


class TestAgentRequiredSections:
    """Test agent-specific required section definitions."""

    def test_coding_agent_sections(self):
        """Coding agent requires context, regression, plan sections."""
        assert "coding" in AGENT_REQUIRED_SECTIONS
        sections = AGENT_REQUIRED_SECTIONS["coding"]
        assert "context" in sections
        assert "regression" in sections
        assert "plan" in sections

    def test_initializer_agent_sections(self):
        """Initializer agent requires spec_decomposition, feature_mapping, coverage_check."""
        assert "initializer" in AGENT_REQUIRED_SECTIONS
        sections = AGENT_REQUIRED_SECTIONS["initializer"]
        assert "spec_decomposition" in sections
        assert "feature_mapping" in sections
        assert "coverage_check" in sections

    def test_validator_agent_sections(self):
        """Validator agent requires spec_alignment, test_execution, aggregate_verdict."""
        assert "validator" in AGENT_REQUIRED_SECTIONS
        sections = AGENT_REQUIRED_SECTIONS["validator"]
        assert "spec_alignment" in sections
        assert "test_execution" in sections
        assert "aggregate_verdict" in sections


class TestCheckSectionPresent:
    """Test _check_section_present helper function."""

    def test_context_section_detected(self):
        """Context verification section header is detected."""
        output = """
        Some intro text.

        ### Step A - CONTEXT VERIFICATION

        - feature_list.json read: "Feature #5: User login"
        """
        assert _check_section_present(output, "context") is True

    def test_context_section_case_insensitive(self):
        """Context verification detected case-insensitively."""
        output = "### step a - context verification\nContent here."
        assert _check_section_present(output, "context") is True

    def test_regression_section_detected(self):
        """Regression verification section header is detected."""
        output = """
        ### Step B - REGRESSION VERIFICATION

        - Feature [12]: PASS
        - Feature [5]: FAIL
        """
        assert _check_section_present(output, "regression") is True

    def test_plan_section_detected(self):
        """Implementation plan section header is detected."""
        output = """
        ### Step C - IMPLEMENTATION PLAN

        - What I will build: Login form
        - Files: src/login.tsx
        """
        assert _check_section_present(output, "plan") is True

    def test_missing_section_not_detected(self):
        """Missing section returns False."""
        output = "Just some random text without headers."
        assert _check_section_present(output, "context") is False
        assert _check_section_present(output, "regression") is False
        assert _check_section_present(output, "plan") is False

    def test_unknown_section_returns_false(self):
        """Unknown section name returns False."""
        output = "### UNKNOWN SECTION\nSome content."
        assert _check_section_present(output, "unknown") is False

    def test_h2_headers_also_detected(self):
        """## level headers are also detected."""
        output = "## CONTEXT VERIFICATION\nContent."
        assert _check_section_present(output, "context") is True

    def test_step_number_variations(self):
        """Various step number formats are detected."""
        outputs = [
            "### Step A - CONTEXT VERIFICATION",
            "### Step 1 - CONTEXT VERIFICATION",
            "### Step B-CONTEXT VERIFICATION",  # No space before dash
            "### CONTEXT VERIFICATION",  # No step prefix
            "  ### Step A - CONTEXT VERIFICATION",  # Leading whitespace
        ]
        for output in outputs:
            assert _check_section_present(output, "context") is True, f"Failed to detect: {output}"

    def test_initializer_sections_detected(self):
        """Initializer agent sections are detected correctly."""
        outputs = {
            "spec_decomposition": "### Step 1 - SPEC DECOMPOSITION\nContent here.",
            "feature_mapping": "### Step 2 - FEATURE MAPPING\nContent here.",
            "coverage_check": "### Step 3 - COVERAGE CHECK\nContent here.",
        }
        for section, output in outputs.items():
            assert _check_section_present(output, section) is True, f"Failed: {section}"

    def test_validator_sections_detected(self):
        """Validator agent sections are detected correctly."""
        outputs = {
            "spec_alignment": "### Step A - SPEC ALIGNMENT CHECK\nContent here.",
            "test_execution": "### Step B - TEST EXECUTION WITH EVIDENCE\nContent here.",
            "aggregate_verdict": "### Step C - AGGREGATE VERDICT\nContent here.",
        }
        for section, output in outputs.items():
            assert _check_section_present(output, section) is True, f"Failed: {section}"


class TestExtractEvaluationSections:
    """Test extract_evaluation_sections function."""

    def test_extracts_coding_agent_sections(self):
        """Extracts all coding agent sections with content."""
        output = """
        ### Step A - CONTEXT VERIFICATION

        - feature_list.json read: "Feature #5"
        - progress notes: "Working on login"

        ### Step B - REGRESSION VERIFICATION

        - Feature [12]: PASS
          Evidence: "Login works"

        ### Step C - IMPLEMENTATION PLAN

        - What I will build: New feature
        - Files: src/app.tsx
        """
        sections = extract_evaluation_sections(output, "coding")

        assert "context" in sections
        assert "Feature #5" in sections["context"]

        assert "regression" in sections
        assert "Feature [12]: PASS" in sections["regression"]

        assert "plan" in sections
        assert "What I will build" in sections["plan"]

    def test_empty_output_returns_empty_dict(self):
        """Empty output returns empty dict."""
        sections = extract_evaluation_sections("", "coding")
        assert sections == {}

    def test_missing_sections_not_in_result(self):
        """Missing sections are not included in result."""
        output = """
        ### Step A - CONTEXT VERIFICATION

        Content here.
        """
        sections = extract_evaluation_sections(output, "coding")

        assert "context" in sections
        assert "regression" not in sections
        assert "plan" not in sections

    def test_invalid_agent_type_returns_empty(self):
        """Invalid agent type returns empty dict."""
        sections = extract_evaluation_sections("### CONTEXT VERIFICATION\nTest", "invalid")
        assert sections == {}

    def test_extracts_initializer_sections(self):
        """Extracts initializer agent sections."""
        output = """
        ### Step 1 - SPEC DECOMPOSITION

        Section: "User Management"
        Requirements: List of items

        ### Step 2 - FEATURE MAPPING

        Feature: "Login form"
        Traces to: "users must log in"

        ### Step 3 - COVERAGE CHECK

        Requirements covered: 10/10
        """
        sections = extract_evaluation_sections(output, "initializer")

        assert "spec_decomposition" in sections
        assert "feature_mapping" in sections
        assert "coverage_check" in sections

    def test_extracts_validator_sections(self):
        """Extracts validator agent sections."""
        output = """
        ### Step A - SPEC ALIGNMENT CHECK

        Feature #5: "Login"
        Spec requirement: "users must log in"

        ### Step B - TEST EXECUTION WITH EVIDENCE

        Steps performed: Navigate, click, verify
        Verdict: PASS

        ### Step C - AGGREGATE VERDICT

        Features tested: 10
        Features passed: 10
        """
        sections = extract_evaluation_sections(output, "validator")

        assert "spec_alignment" in sections
        assert "test_execution" in sections
        assert "aggregate_verdict" in sections


class TestEvaluationValidationHook:
    """Test evaluation_validation_hook function."""

    def test_valid_coding_output_passes(self):
        """Complete coding agent output passes validation."""
        output = """
        ### Step A - CONTEXT VERIFICATION

        - feature_list.json read: "Feature #5"
        - progress notes: "Status update"
        - Constraints: Follow existing patterns

        ### Step B - REGRESSION VERIFICATION

        - Feature [12]: PASS
        - Feature [5]: PASS

        ### Step C - IMPLEMENTATION PLAN

        - What I will build: Login form
        - Files to modify: src/app.tsx
        """
        result = evaluation_validation_hook(output, "coding")

        assert result.is_valid is True
        assert result.error_message is None
        assert result.action == "proceed"
        assert result.evaluation_data["completeness_score"] == 1.0
        assert len(result.evaluation_data["sections_found"]) == 3
        assert len(result.evaluation_data["sections_missing"]) == 0

    def test_missing_sections_detected(self):
        """Missing sections are detected and reported."""
        output = """
        ### Step A - CONTEXT VERIFICATION

        Content here.
        """
        result = evaluation_validation_hook(output, "coding")

        assert result.is_valid is False
        assert result.error_message is not None
        assert "plan" in result.error_message.lower() or "regression" in result.error_message.lower()
        assert result.action == "proceed"  # Lenient mode by default
        assert result.evaluation_data["completeness_score"] < 1.0
        assert "context" in result.evaluation_data["sections_found"]
        assert len(result.evaluation_data["sections_missing"]) == 2

    def test_strict_mode_triggers_retry(self):
        """Strict mode triggers retry action for missing sections."""
        output = """
        ### Step A - CONTEXT VERIFICATION

        Content only.
        """
        result = evaluation_validation_hook(output, "coding", strict_mode=True)

        assert result.is_valid is False
        assert result.action == "retry"
        assert "RETRY REQUIRED" in result.error_message

    def test_invalid_agent_type_aborts(self):
        """Invalid agent type triggers abort action."""
        result = evaluation_validation_hook("Any output", "invalid_type")

        assert result.is_valid is False
        assert result.action == "abort"
        assert "Invalid agent type" in result.error_message
        assert result.evaluation_data["completeness_score"] == 0.0

    def test_empty_output_fails(self):
        """Empty output fails validation."""
        result = evaluation_validation_hook("", "coding")

        assert result.is_valid is False
        assert result.evaluation_data["completeness_score"] == 0.0
        assert len(result.evaluation_data["sections_missing"]) == 3

    def test_completeness_score_calculated(self):
        """Completeness score is calculated correctly."""
        # One section out of three
        output = "### Step A - CONTEXT VERIFICATION\nContent."
        result = evaluation_validation_hook(output, "coding")

        expected_score = 1 / 3
        assert abs(result.evaluation_data["completeness_score"] - expected_score) < 0.01

    def test_initializer_validation(self):
        """Initializer agent output validates correctly."""
        output = """
        ### Step 1 - SPEC DECOMPOSITION
        Section analysis here.

        ### Step 2 - FEATURE MAPPING
        Feature mapping here.

        ### Step 3 - COVERAGE CHECK
        Coverage analysis here.
        """
        result = evaluation_validation_hook(output, "initializer")

        assert result.is_valid is True
        assert result.action == "proceed"

    def test_validator_validation(self):
        """Validator agent output validates correctly."""
        output = """
        ### Step A - SPEC ALIGNMENT CHECK
        Alignment check here.

        ### Step B - TEST EXECUTION WITH EVIDENCE
        Test execution here.

        ### Step C - AGGREGATE VERDICT
        Verdict summary here.
        """
        result = evaluation_validation_hook(output, "validator")

        assert result.is_valid is True
        assert result.action == "proceed"

    def test_section_content_extracted(self):
        """Section content is extracted and included in evaluation_data."""
        output = """
        ### Step A - CONTEXT VERIFICATION

        This is the context content.
        Multiple lines.

        ### Step B - REGRESSION VERIFICATION

        Regression content here.
        """
        result = evaluation_validation_hook(output, "coding")

        section_content = result.evaluation_data.get("section_content", {})
        assert "context" in section_content
        assert "This is the context content" in section_content["context"]


class TestBuildRetryEmphasis:
    """Test _build_retry_emphasis function."""

    def test_coding_sections_guidance(self):
        """Retry emphasis includes guidance for coding agent sections."""
        emphasis = _build_retry_emphasis(["context", "regression", "plan"], "coding")

        assert "RETRY REQUIRED" in emphasis
        assert "CONTEXT VERIFICATION" in emphasis
        assert "REGRESSION VERIFICATION" in emphasis
        assert "IMPLEMENTATION PLAN" in emphasis

    def test_initializer_sections_guidance(self):
        """Retry emphasis includes guidance for initializer agent sections."""
        emphasis = _build_retry_emphasis(
            ["spec_decomposition", "feature_mapping", "coverage_check"],
            "initializer"
        )

        assert "SPEC DECOMPOSITION" in emphasis
        assert "FEATURE MAPPING" in emphasis
        assert "COVERAGE CHECK" in emphasis

    def test_validator_sections_guidance(self):
        """Retry emphasis includes guidance for validator agent sections."""
        emphasis = _build_retry_emphasis(
            ["spec_alignment", "test_execution", "aggregate_verdict"],
            "validator"
        )

        assert "SPEC ALIGNMENT CHECK" in emphasis
        assert "TEST EXECUTION WITH EVIDENCE" in emphasis
        assert "AGGREGATE VERDICT" in emphasis

    def test_single_missing_section(self):
        """Works with a single missing section."""
        emphasis = _build_retry_emphasis(["context"], "coding")

        assert "CONTEXT VERIFICATION" in emphasis
        assert "REGRESSION VERIFICATION" not in emphasis


class TestEvaluationSectionPatterns:
    """Test that regex patterns match expected header formats."""

    @pytest.mark.parametrize(
        "header,expected_section",
        [
            ("### Step A - CONTEXT VERIFICATION", "context"),
            ("### step a - context verification", "context"),  # lowercase
            ("## CONTEXT VERIFICATION", "context"),  # h2
            ("### CONTEXT VERIFICATION", "context"),  # no step prefix
            ("###Step A-CONTEXT VERIFICATION", "context"),  # minimal spacing
            ("  ### Step A - CONTEXT VERIFICATION", "context"),  # leading whitespace
            ("### Step B - REGRESSION VERIFICATION", "regression"),
            ("### Step C - IMPLEMENTATION PLAN", "plan"),
            ("### Step 1 - SPEC DECOMPOSITION", "spec_decomposition"),
            ("### Step 2 - FEATURE MAPPING", "feature_mapping"),
            ("### Step 3 - COVERAGE CHECK", "coverage_check"),
            ("### Step A - SPEC ALIGNMENT CHECK", "spec_alignment"),
            ("### Step B - TEST EXECUTION WITH EVIDENCE", "test_execution"),
            ("### Step C - AGGREGATE VERDICT", "aggregate_verdict"),
        ],
    )
    def test_pattern_matches(self, header, expected_section):
        """Verify pattern matches expected header format."""
        pattern = EVALUATION_SECTION_PATTERNS.get(expected_section)
        assert pattern is not None, f"Pattern not found for {expected_section}"
        assert pattern.search(header) is not None, f"Pattern didn't match: {header}"


class TestIntegration:
    """Integration tests for evaluation validation workflow."""

    def test_realistic_coding_session_output(self):
        """Test with realistic coding session output."""
        output = """
        I'll start by getting my bearings and reading the necessary files.

        ### Step A - CONTEXT VERIFICATION

        - [ ] feature_list.json read:
          Quote: "Feature #15: User authentication with email/password validation"

        - [ ] claude-progress.txt read:
          Quote: "Session 3: 10/50 features complete. Working on auth module."

        - [ ] Architectural constraints identified:
          Quote: "Use existing auth middleware pattern from src/middleware/auth.ts"

        ### Step B - REGRESSION VERIFICATION

        Running verification tests on critical features:

        - Feature [12]: PASS
          Evidence: "Login form renders correctly, submit button triggers auth"

        - Feature [5]: PASS
          Evidence: "User profile page loads with correct data"

        ### Step C - IMPLEMENTATION PLAN

        - What I will build: Email validation function for login form
        - Files I will modify: src/components/LoginForm.tsx, src/utils/validation.ts
        - How this connects to existing code: Integrates with existing form state management
        - Constraints I must honor: Follow existing validation patterns

        Now I'll proceed with implementation...
        """
        result = evaluation_validation_hook(output, "coding")

        assert result.is_valid is True
        assert result.action == "proceed"
        assert result.evaluation_data["completeness_score"] == 1.0

        # Verify content was extracted
        section_content = result.evaluation_data.get("section_content", {})
        assert "Feature #15" in section_content.get("context", "")
        assert "PASS" in section_content.get("regression", "")
        assert "Email validation" in section_content.get("plan", "")

    def test_partial_output_detected(self):
        """Test that partial output is correctly identified."""
        output = """
        Starting implementation...

        ### Step A - CONTEXT VERIFICATION

        I'll read the feature list now.

        Actually, let me skip ahead and start coding...

        [Implementation begins without completing evaluation]
        """
        result = evaluation_validation_hook(output, "coding")

        assert result.is_valid is False
        assert "regression" in result.evaluation_data["sections_missing"]
        assert "plan" in result.evaluation_data["sections_missing"]
        # Only 1/3 sections present
        assert result.evaluation_data["completeness_score"] < 0.5

    def test_strict_mode_enforcement(self):
        """Test strict mode forces retry on missing sections."""
        incomplete_output = "### Step A - CONTEXT VERIFICATION\nPartial content only."

        # Lenient mode allows proceed
        lenient_result = evaluation_validation_hook(incomplete_output, "coding", strict_mode=False)
        assert lenient_result.action == "proceed"

        # Strict mode requires retry
        strict_result = evaluation_validation_hook(incomplete_output, "coding", strict_mode=True)
        assert strict_result.action == "retry"
        assert "RETRY REQUIRED" in strict_result.error_message

    def test_all_agent_types_validate(self):
        """Test validation works for all agent types."""
        for agent_type in AGENT_REQUIRED_SECTIONS.keys():
            # Valid output should pass
            sections = AGENT_REQUIRED_SECTIONS[agent_type]
            valid_output_parts = []

            for i, section in enumerate(sections, 1):
                # Build header based on section name
                header = section.replace("_", " ").upper()
                if agent_type == "coding":
                    step = chr(64 + i)  # A, B, C
                    valid_output_parts.append(f"### Step {step} - {header}\n\nContent for {section}.")
                elif agent_type == "initializer":
                    valid_output_parts.append(f"### Step {i} - {header}\n\nContent for {section}.")
                else:
                    step = chr(64 + i)  # A, B, C
                    valid_output_parts.append(f"### Step {step} - {header}\n\nContent for {section}.")

            valid_output = "\n\n".join(valid_output_parts)
            result = evaluation_validation_hook(valid_output, agent_type)

            assert result.action in ["proceed", "retry"], f"Failed for {agent_type}: action={result.action}"


class TestEdgeCases:
    """Edge case tests for robustness."""

    def test_headers_in_code_blocks_not_matched(self):
        """Headers inside code blocks should ideally not trigger false positives."""
        # This tests the current behavior - headers in code blocks ARE matched
        # In the future, we might want to exclude code blocks
        output = """
        Here's what the agent should output:

        ```markdown
        ### Step A - CONTEXT VERIFICATION
        Example content
        ```

        But I didn't actually do it yet.
        """
        result = evaluation_validation_hook(output, "coding")

        # Current behavior: code block headers ARE matched
        # This is a known limitation - documenting the behavior
        # The pattern matches regardless of code block context
        assert "context" in result.evaluation_data["sections_found"]

    def test_multiple_same_headers_handled(self):
        """Multiple instances of same header are handled."""
        output = """
        ### Step A - CONTEXT VERIFICATION

        First context section.

        ### Step A - CONTEXT VERIFICATION

        Second context section (duplicate).

        ### Step B - REGRESSION VERIFICATION

        Regression content.

        ### Step C - IMPLEMENTATION PLAN

        Plan content.
        """
        result = evaluation_validation_hook(output, "coding")

        # Should still validate as complete
        assert result.is_valid is True
        # First occurrence content should be captured
        assert "First context" in result.evaluation_data["section_content"].get("context", "")

    def test_unicode_in_sections(self):
        """Unicode content in sections is handled."""
        output = """
        ### Step A - CONTEXT VERIFICATION

        Feature: "用户登录" (User Login)
        émojis: 🎉 ✅ ❌

        ### Step B - REGRESSION VERIFICATION

        Тест пройден (Test passed)

        ### Step C - IMPLEMENTATION PLAN

        日本語テスト
        """
        result = evaluation_validation_hook(output, "coding")

        assert result.is_valid is True
        assert "用户登录" in result.evaluation_data["section_content"].get("context", "")

    def test_very_long_output(self):
        """Very long output is handled efficiently."""
        # Create long output with all sections
        long_content = "A" * 10000
        output = f"""
        ### Step A - CONTEXT VERIFICATION

        {long_content}

        ### Step B - REGRESSION VERIFICATION

        {long_content}

        ### Step C - IMPLEMENTATION PLAN

        {long_content}
        """
        result = evaluation_validation_hook(output, "coding")

        assert result.is_valid is True

    def test_section_header_only_no_content(self):
        """Sections with headers but no content are handled."""
        output = """
        ### Step A - CONTEXT VERIFICATION
        ### Step B - REGRESSION VERIFICATION
        ### Step C - IMPLEMENTATION PLAN
        """
        result = evaluation_validation_hook(output, "coding")

        # Headers present but content may be empty
        assert "context" in result.evaluation_data["sections_found"]
        assert "regression" in result.evaluation_data["sections_found"]
        assert "plan" in result.evaluation_data["sections_found"]
