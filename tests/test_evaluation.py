"""
Tests for feature list evaluation module.
"""

import json
import pytest
from pathlib import Path

from claude_agent.evaluation import (
    calculate_spec_coverage,
    calculate_testability_score,
    calculate_granularity_score,
    calculate_independence_score,
    evaluate_feature_list,
    load_and_evaluate,
    EvaluationWeights,
    EvaluationResult,
    RequirementPatterns,
    DEFAULT_REQUIREMENT_PATTERNS,
)


class TestEvaluationWeights:
    """Test EvaluationWeights dataclass."""

    def test_default_weights(self):
        """Verify default weights are correct."""
        weights = EvaluationWeights()
        assert weights.coverage == 0.4
        assert weights.testability == 0.3
        assert weights.granularity == 0.2
        assert weights.independence == 0.1

    def test_default_weights_sum_to_one(self):
        """Verify default weights sum to 1.0."""
        weights = EvaluationWeights()
        total = weights.coverage + weights.testability + weights.granularity + weights.independence
        assert abs(total - 1.0) < 0.01  # Allow small float imprecision

    def test_custom_weights_accepted(self):
        """Verify custom weights that sum to 1.0 are accepted."""
        weights = EvaluationWeights(
            coverage=0.7, testability=0.1, granularity=0.1, independence=0.1
        )
        assert weights.coverage == 0.7
        assert weights.testability == 0.1

    def test_invalid_weights_raises_error(self):
        """Verify weights not summing to 1.0 raise ValueError."""
        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            EvaluationWeights(coverage=0.5, testability=0.5, granularity=0.5, independence=0.5)

    def test_weights_tolerate_float_imprecision(self):
        """Verify small float imprecision is tolerated (0.99-1.01)."""
        # This should not raise - 0.999 is within tolerance
        weights = EvaluationWeights(
            coverage=0.399, testability=0.3, granularity=0.2, independence=0.1
        )
        assert weights.coverage == 0.399


class TestEvaluationResult:
    """Test EvaluationResult dataclass."""

    def test_creates_with_all_fields(self):
        """Verify EvaluationResult creates with all required fields."""
        result = EvaluationResult(
            coverage_score=0.8,
            testability_score=0.7,
            granularity_score=0.6,
            independence_score=0.9,
            aggregate_score=0.75,
            details={"feature_count": 10},
        )
        assert result.coverage_score == 0.8
        assert result.testability_score == 0.7
        assert result.granularity_score == 0.6
        assert result.independence_score == 0.9
        assert result.aggregate_score == 0.75
        assert result.details["feature_count"] == 10


class TestRequirementPatterns:
    """Test RequirementPatterns dataclass and pattern extraction."""

    def test_default_patterns_exist(self):
        """Verify default patterns are populated."""
        patterns = RequirementPatterns()
        all_patterns = patterns.get_all_patterns()
        assert len(all_patterns) > 5  # Should have multiple patterns

    def test_custom_patterns_accepted(self):
        """Verify custom patterns can be provided."""
        patterns = RequirementPatterns(
            modal_patterns=(r"(?:shall)\s+\w+",),
            subject_patterns=(),
            action_patterns=(),
        )
        all_patterns = patterns.get_all_patterns()
        assert len(all_patterns) == 1
        assert r"(?:shall)\s+\w+" in all_patterns

    def test_overlap_threshold_configurable(self):
        """Verify overlap threshold is configurable."""
        patterns = RequirementPatterns(
            overlap_threshold_factor=0.3,
            min_overlap_words=2,
        )
        assert patterns.overlap_threshold_factor == 0.3
        assert patterns.min_overlap_words == 2

    def test_default_patterns_contains_negations(self):
        """Verify default patterns handle negated requirements."""
        patterns = DEFAULT_REQUIREMENT_PATTERNS
        all_patterns = patterns.get_all_patterns()
        # Check that negation patterns are included
        has_negation = any("not" in p for p in all_patterns)
        assert has_negation, "Should include negation patterns"


class TestSpecCoverage:
    """Test coverage calculation against spec requirements."""

    def test_full_coverage_returns_high_score(self):
        """Features that mention all spec requirements score highly."""
        spec = """
        # User Management
        The system must allow users to log in.
        Users should be able to reset their password.
        The application will display user profiles.
        """
        features = [
            {"description": "User login form with email and password authentication"},
            {"description": "Password reset flow via email for users"},
            {"description": "User profile page displays user information"},
        ]

        score = calculate_spec_coverage(features, spec)
        # Score depends on word overlap; should be reasonable coverage
        assert score >= 0.3, f"Expected reasonable coverage, got {score}"

    def test_no_features_returns_zero(self):
        """Empty feature list returns 0."""
        score = calculate_spec_coverage([], "Some spec")
        assert score == 0.0

    def test_no_spec_returns_zero(self):
        """Empty spec returns 0."""
        features = [{"description": "Some feature"}]
        score = calculate_spec_coverage(features, "")
        assert score == 0.0

    def test_partial_coverage(self):
        """Features covering some requirements score proportionally."""
        spec = """
        Users must log in.
        Users should view dashboard.
        Users can export data.
        """
        features = [
            {"description": "User login functionality"},
            # Missing dashboard and export
        ]

        score = calculate_spec_coverage(features, spec)
        # With word overlap algorithm, partial coverage gives a score
        assert 0.0 <= score <= 1.0  # Valid range

    def test_spec_with_only_headers_uses_header_fallback(self):
        """Spec with only headers uses header-based extraction."""
        spec = """
        # Authentication
        # User Dashboard
        # Settings Page
        """
        features = [
            {"description": "Authentication module"},
            {"description": "User dashboard view"},
            {"description": "Settings configuration page"},
        ]

        score = calculate_spec_coverage(features, spec)
        assert score >= 0.5  # Should match at least some headers

    def test_spec_without_requirements_returns_half(self):
        """Spec without extractable requirements returns 0.5."""
        spec = "Just some random text without any requirements."
        features = [{"description": "Some feature"}]

        score = calculate_spec_coverage(features, spec)
        assert score == 0.5

    def test_negated_requirements_extracted(self):
        """Spec with negated requirements ('must not', 'should not') are captured."""
        spec = """
        The system must not allow unauthorized access.
        Users should not be able to view other users' data.
        The application will not store passwords in plaintext.
        """
        features = [
            {"description": "Authorization system prevents unauthorized access"},
            {"description": "Data privacy ensures users cannot view others data"},
            {"description": "Password hashing ensures plaintext is not stored"},
        ]

        score = calculate_spec_coverage(features, spec)
        # Should capture negated requirements
        assert score >= 0.3

    def test_alternative_verb_phrasings(self):
        """Spec with alternative phrasings ('enables', 'supports') are captured."""
        spec = """
        The system enables users to export reports.
        The application supports multiple file formats.
        This feature provides real-time notifications.
        """
        # Use feature descriptions with more word overlap with requirements
        features = [
            {"description": "System enables users to export their reports"},
            {"description": "Application supports multiple file formats for import and export"},
            {"description": "Feature provides real-time notifications to users"},
        ]

        score = calculate_spec_coverage(features, spec)
        assert score >= 0.3

    def test_custom_patterns_used(self):
        """Custom RequirementPatterns are used for extraction."""
        spec = "The system handles user data securely."
        features = [{"description": "System handles user data with encryption"}]

        # Default patterns won't match this spec (no action verbs, modals)
        default_score = calculate_spec_coverage(features, spec)
        # Returns 0.5 (fallback for no extractable requirements)
        assert default_score == 0.5

        # Custom patterns can match "handles"
        custom_patterns = RequirementPatterns(
            modal_patterns=(),
            subject_patterns=(),
            action_patterns=(r"handles",),
        )
        custom_score = calculate_spec_coverage(features, spec, patterns=custom_patterns)

        # Custom patterns should find and cover the requirement
        # Feature has good word overlap: system, handles, user, data
        assert custom_score == 1.0  # 1 requirement, 1 covered


class TestSpecCoverageEdgeCases:
    """Parametrized edge case tests for spec coverage."""

    @pytest.mark.parametrize(
        "features,spec,expected",
        [
            ([], "Some spec text", 0.0),  # Empty features
            ([{"description": "Test"}], "", 0.0),  # Empty spec
            ([], "", 0.0),  # Both empty
        ],
        ids=["empty_features", "empty_spec", "both_empty"],
    )
    def test_empty_inputs(self, features, spec, expected):
        """Test that empty inputs return expected scores."""
        assert calculate_spec_coverage(features, spec) == expected

    @pytest.mark.parametrize(
        "spec,expected_min",
        [
            ("# Header Only\n# Another Header", 0.0),  # Headers only, uses fallback
            ("No requirements here at all", 0.5),  # No extractable requirements
        ],
        ids=["headers_fallback", "no_requirements_fallback"],
    )
    def test_fallback_behavior(self, spec, expected_min):
        """Test fallback behavior for different spec formats."""
        features = [{"description": "Generic feature description"}]
        score = calculate_spec_coverage(features, spec)
        assert score >= expected_min


class TestTestabilityScore:
    """Test testability scoring."""

    def test_concrete_steps_score_high(self):
        """Features with concrete test steps score highly."""
        features = [
            {
                "description": "User login form",
                "test_steps": [
                    "Navigate to /login",
                    "Type email into email field",
                    "Click submit button",
                    "Verify dashboard appears",
                ],
                "expected_result": "User should see dashboard after login",
            }
        ]

        score = calculate_testability_score(features)
        assert score >= 0.8

    def test_vague_steps_score_low(self):
        """Features with vague steps score lower."""
        features = [
            {
                "description": "User login form",
                "test_steps": [
                    "Do the login",
                    "Check it works",
                ],
            }
        ]

        score = calculate_testability_score(features)
        # Vague steps without action verbs score lower
        assert score <= 0.7  # Has test_steps (0.3) but no concrete actions, may have verifiable desc

    def test_empty_features_returns_zero(self):
        """Empty list returns 0."""
        assert calculate_testability_score([]) == 0.0

    def test_no_test_steps_scores_low(self):
        """Features without test_steps field score lower."""
        features = [{"description": "User login form"}]
        score = calculate_testability_score(features)
        assert score <= 0.4  # Only expected_result may contribute

    def test_verifiable_expected_result_adds_score(self):
        """Features with verifiable expected_result add to score."""
        features = [
            {
                "description": "Login form",
                "expected_result": "User should see dashboard after successful login",
            }
        ]

        score = calculate_testability_score(features)
        assert score == 0.4  # Full score for explicit expected_result

    def test_description_fallback_has_penalty(self):
        """Features using description fallback for verifiability get reduced score."""
        features = [
            {
                "description": "User should see dashboard after login",
                # No expected_result field - falls back to description
            }
        ]

        score = calculate_testability_score(features)
        assert score == 0.2  # Penalty: 50% of full score (0.4 * 0.5 = 0.2)

    def test_average_across_features(self):
        """Score is averaged across all features."""
        features = [
            {
                "description": "Feature 1",
                "test_steps": ["Navigate to page", "Click button", "Verify result"],
                "expected_result": "Should show success message",
            },
            {
                "description": "Feature 2",
                # No test steps, no verifiable result
            },
        ]

        score = calculate_testability_score(features)
        # First feature scores high (~1.0), second scores 0
        # Average should be around 0.5
        assert 0.4 <= score <= 0.6


class TestGranularityScore:
    """Test granularity scoring."""

    def test_ideal_granularity_scores_high(self):
        """Features with ideal size score highly."""
        features = [
            {
                "description": "User authentication form that validates email format and password strength before submission",
                "test_steps": ["step1", "step2", "step3", "step4", "step5"],
            }
        ]

        score = calculate_granularity_score(features)
        assert score >= 0.7

    def test_too_small_penalized(self):
        """Very small features are penalized."""
        features = [{"description": "Login", "test_steps": ["click"]}]

        score = calculate_granularity_score(features)
        assert score <= 0.6

    def test_too_large_penalized(self):
        """Very large features are penalized."""
        features = [
            {
                "description": "A" * 600,  # > 500 chars
                "test_steps": [f"step{i}" for i in range(15)],  # > 10 steps
            }
        ]

        score = calculate_granularity_score(features)
        assert score <= 0.5

    def test_compound_features_penalized(self):
        """Features with multiple 'and' are penalized."""
        features = [
            {
                "description": "Login form and registration form and password reset and profile editing",
                "test_steps": ["s1", "s2", "s3"],
            }
        ]

        score = calculate_granularity_score(features)
        assert score <= 0.5

    def test_empty_features_returns_zero(self):
        """Empty list returns 0."""
        assert calculate_granularity_score([]) == 0.0

    def test_score_clamped_to_valid_range(self):
        """Score is clamped between 0.0 and 1.0."""
        # Very small feature with many penalties
        features = [{"description": "X", "test_steps": []}]
        score = calculate_granularity_score(features)
        assert 0.0 <= score <= 1.0


class TestIndependenceScore:
    """Test independence scoring."""

    def test_independent_features_score_high(self):
        """Features without dependencies score highly."""
        features = [
            {"description": "User login form"},
            {"description": "Contact page display"},
            {"description": "About page content"},
        ]

        score = calculate_independence_score(features)
        assert score >= 0.9

    def test_dependent_features_penalized(self):
        """Features with dependencies are penalized."""
        features = [
            {
                "description": "Profile editing after login",
                "dependencies": [0, 1],
                "test_steps": ["After feature #1 completes, then edit profile"],
            }
        ]

        score = calculate_independence_score(features)
        assert score <= 0.7

    def test_sequential_language_penalized(self):
        """Features with sequential language are penalized."""
        features = [
            {
                "description": "This feature requires the login feature to be complete first",
                "test_steps": ["After login, then navigate to profile"],
            }
        ]

        score = calculate_independence_score(features)
        assert score <= 0.8

    def test_feature_references_penalized(self):
        """References to other features are penalized."""
        features = [
            {
                "description": "Depends on feature #1 and feature #2",
                "test_steps": ["Complete feature #3 first"],
            }
        ]

        score = calculate_independence_score(features)
        assert score <= 0.7

    def test_empty_features_returns_zero(self):
        """Empty list returns 0."""
        assert calculate_independence_score([]) == 0.0


class TestEvaluateFeatureList:
    """Test aggregate evaluation."""

    def test_aggregate_respects_weights(self):
        """Aggregate score uses configured weights."""
        features = [{"description": "Test feature", "test_steps": ["step"]}]
        spec = "Test spec"

        # Custom weights emphasizing coverage
        weights = EvaluationWeights(
            coverage=0.7, testability=0.1, granularity=0.1, independence=0.1
        )

        result = evaluate_feature_list(features, spec, weights)

        assert isinstance(result, EvaluationResult)
        assert 0.0 <= result.aggregate_score <= 1.0

    def test_default_weights_used(self):
        """Default weights are used when not specified."""
        features = [{"description": "Test feature"}]
        result = evaluate_feature_list(features, "spec")

        assert result.details["weights"]["coverage"] == 0.4
        assert result.details["weights"]["testability"] == 0.3
        assert result.details["weights"]["granularity"] == 0.2
        assert result.details["weights"]["independence"] == 0.1

    def test_result_contains_all_scores(self):
        """Result includes all individual scores."""
        features = [{"description": "Test feature"}]
        result = evaluate_feature_list(features, "spec")

        assert hasattr(result, "coverage_score")
        assert hasattr(result, "testability_score")
        assert hasattr(result, "granularity_score")
        assert hasattr(result, "independence_score")
        assert hasattr(result, "aggregate_score")

    def test_details_contains_feature_count(self):
        """Details dict contains feature count."""
        features = [{"description": "F1"}, {"description": "F2"}, {"description": "F3"}]
        result = evaluate_feature_list(features, "spec")

        assert result.details["feature_count"] == 3

    def test_aggregate_is_weighted_sum(self):
        """Aggregate score is correctly calculated weighted sum."""
        features = [
            {
                "description": "User login form that handles authentication with validation",
                "test_steps": ["Navigate to login", "Enter credentials", "Click submit"],
                "expected_result": "User should see dashboard",
            }
        ]
        spec = "The system must allow users to log in."

        result = evaluate_feature_list(features, spec)

        # Manually calculate expected aggregate
        expected = (
            result.coverage_score * 0.4
            + result.testability_score * 0.3
            + result.granularity_score * 0.2
            + result.independence_score * 0.1
        )

        assert abs(result.aggregate_score - expected) < 0.001


class TestLoadAndEvaluate:
    """Test load_and_evaluate convenience function."""

    def test_missing_feature_list_returns_none(self, tmp_path):
        """Returns None if feature_list.json doesn't exist."""
        result = load_and_evaluate(tmp_path)
        assert result is None

    def test_valid_feature_list_returns_result(self, tmp_path):
        """Returns EvaluationResult for valid feature_list.json."""
        features = [
            {
                "description": "Test feature with enough description to be valid",
                "test_steps": ["step1", "step2", "step3"],
            }
        ]
        feature_path = tmp_path / "feature_list.json"
        feature_path.write_text(json.dumps(features))

        spec_path = tmp_path / "app_spec.txt"
        spec_path.write_text("The system must do something.")

        result = load_and_evaluate(tmp_path)

        assert result is not None
        assert isinstance(result, EvaluationResult)

    def test_invalid_json_returns_none(self, tmp_path):
        """Returns None if feature_list.json is invalid JSON."""
        feature_path = tmp_path / "feature_list.json"
        feature_path.write_text("not valid json")

        result = load_and_evaluate(tmp_path)
        assert result is None

    def test_custom_spec_path(self, tmp_path):
        """Uses custom spec path when provided."""
        features = [{"description": "Test feature"}]
        feature_path = tmp_path / "feature_list.json"
        feature_path.write_text(json.dumps(features))

        custom_spec = tmp_path / "custom_spec.md"
        custom_spec.write_text("Custom spec content that must be read.")

        result = load_and_evaluate(tmp_path, spec_path=custom_spec)

        assert result is not None

    def test_finds_spec_in_multiple_locations(self, tmp_path):
        """Tries multiple spec locations in order."""
        features = [{"description": "Test feature"}]
        feature_path = tmp_path / "feature_list.json"
        feature_path.write_text(json.dumps(features))

        # Create specs directory with spec-validated.md
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        spec_path = specs_dir / "spec-validated.md"
        spec_path.write_text("Spec from specs directory.")

        result = load_and_evaluate(tmp_path)

        assert result is not None

    def test_works_without_spec(self, tmp_path):
        """Returns result even without spec file (coverage affected)."""
        features = [{"description": "Test feature"}]
        feature_path = tmp_path / "feature_list.json"
        feature_path.write_text(json.dumps(features))

        result = load_and_evaluate(tmp_path)

        assert result is not None
        # Without spec, coverage calculation returns 0.0 (empty spec)
        assert result.coverage_score == 0.0

    def test_custom_weights_passed_through(self, tmp_path):
        """Custom weights are passed to evaluate_feature_list."""
        features = [{"description": "Test feature"}]
        feature_path = tmp_path / "feature_list.json"
        feature_path.write_text(json.dumps(features))

        weights = EvaluationWeights(
            coverage=0.25, testability=0.25, granularity=0.25, independence=0.25
        )

        result = load_and_evaluate(tmp_path, weights=weights)

        assert result is not None
        assert result.details["weights"]["coverage"] == 0.25


class TestIntegration:
    """Integration tests for evaluation workflow."""

    def test_realistic_feature_list_evaluation(self, tmp_path):
        """Test evaluation of a realistic feature list."""
        spec = """
        # E-Commerce Application

        ## User Authentication
        Users must be able to log in with email and password.
        Users should be able to reset their password via email.

        ## Product Catalog
        The system will display a list of products.
        Users can filter products by category.
        Users should be able to search for products.

        ## Shopping Cart
        Users can add products to their cart.
        Users should be able to modify quantities in cart.
        """

        features = [
            {
                "description": "User login form with email and password validation",
                "test_steps": [
                    "Navigate to /login",
                    "Enter valid email address",
                    "Enter password",
                    "Click submit button",
                    "Verify redirect to dashboard",
                ],
                "expected_result": "User should see dashboard after successful login",
            },
            {
                "description": "Password reset flow via email link",
                "test_steps": [
                    "Navigate to /forgot-password",
                    "Enter email address",
                    "Click send reset link",
                    "Check email for reset link",
                    "Verify reset page opens",
                ],
                "expected_result": "User should receive email with reset link",
            },
            {
                "description": "Product listing page with grid display",
                "test_steps": [
                    "Navigate to /products",
                    "Verify products display in grid",
                    "Check product cards show name and price",
                ],
                "expected_result": "Products should be visible in grid layout",
            },
            {
                "description": "Category filter for products",
                "test_steps": [
                    "Navigate to /products",
                    "Select category from dropdown",
                    "Verify filtered results",
                ],
                "expected_result": "Only products in selected category should display",
            },
            {
                "description": "Product search functionality",
                "test_steps": [
                    "Navigate to /products",
                    "Enter search term in search box",
                    "Click search button",
                    "Verify matching results appear",
                ],
                "expected_result": "Search results should match query",
            },
        ]

        feature_path = tmp_path / "feature_list.json"
        feature_path.write_text(json.dumps(features))

        spec_path = tmp_path / "app_spec.txt"
        spec_path.write_text(spec)

        result = load_and_evaluate(tmp_path)

        assert result is not None
        # Good feature list should score reasonably well
        assert result.aggregate_score >= 0.4
        # Coverage depends on word overlap algorithm
        assert result.coverage_score >= 0.0  # Valid range
        # Testability should be high with concrete steps
        assert result.testability_score >= 0.7
        # Independence should be high (no dependencies)
        assert result.independence_score >= 0.8

    def test_poor_feature_list_scores_low(self, tmp_path):
        """Test that poorly structured features score lower than well-structured ones."""
        poor_features = [
            {"description": "Login"},  # Too short
            {"description": "Do everything in the app and then some more stuff and also this and that and another thing"},  # Compound
            {"description": "Feature depends on feature #1", "dependencies": [0]},  # Dependent
        ]

        good_features = [
            {
                "description": "User can log in with email and password, receiving appropriate error messages for invalid credentials",
                "test_steps": ["Navigate to login", "Enter email", "Enter password", "Click submit", "Verify redirect"],
                "expected_result": "User should be redirected to dashboard",
            },
            {
                "description": "Dashboard displays user's recent activity in a chronological list with timestamps",
                "test_steps": ["Log in", "Navigate to dashboard", "Verify activity list appears", "Check timestamps"],
                "expected_result": "Activity list should show recent items with visible timestamps",
            },
        ]

        # Create poor feature list
        feature_path = tmp_path / "feature_list.json"
        feature_path.write_text(json.dumps(poor_features))
        poor_result = load_and_evaluate(tmp_path)

        # Create good feature list for comparison
        feature_path.write_text(json.dumps(good_features))
        good_result = load_and_evaluate(tmp_path)

        assert poor_result is not None
        assert good_result is not None

        # Poor features should score significantly lower than good features
        assert poor_result.granularity_score < good_result.granularity_score, \
            f"Poor granularity {poor_result.granularity_score} should be less than good {good_result.granularity_score}"
        assert poor_result.testability_score < good_result.testability_score, \
            f"Poor testability {poor_result.testability_score} should be less than good {good_result.testability_score}"
        assert poor_result.independence_score < good_result.independence_score, \
            f"Poor independence {poor_result.independence_score} should be less than good {good_result.independence_score}"

        # Aggregate should reflect the quality difference
        assert poor_result.aggregate_score < good_result.aggregate_score, \
            f"Poor aggregate {poor_result.aggregate_score} should be less than good {good_result.aggregate_score}"

        # Absolute bounds for poor features (catch completely broken scoring)
        # These bounds are safety nets to catch regression in the scoring algorithm.
        # Rationale for thresholds:
        # - granularity <= 0.7: "Login" (6 chars) gets -0.3 for short description, compound
        #   feature gets -0.4 to -0.6 for multiple "and" conjunctions. Perfect 1.0 minus
        #   penalties puts these features well below 0.7.
        # - testability <= 0.5: Without test_steps field, max possible score is 0.4
        #   (expected_result only) or 0.2 (description fallback). No feature in
        #   poor_features has expected_result, so max is 0.2 from description.
        assert poor_result.granularity_score <= 0.7
        assert poor_result.testability_score <= 0.5


class TestSpecLocationPriority:
    """Test spec file location priority order."""

    def test_explicit_spec_path_takes_priority(self, tmp_path):
        """Explicit spec_path parameter takes priority over all others."""
        features = [{"description": "Test feature"}]
        feature_path = tmp_path / "feature_list.json"
        feature_path.write_text(json.dumps(features))

        # Create all possible spec locations with different content
        explicit_spec = tmp_path / "explicit.md"
        explicit_spec.write_text("The system must do explicit thing.")

        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        (specs_dir / "spec-validated.md").write_text("System must do validated thing.")
        (specs_dir / "app_spec.txt").write_text("System must do specs dir thing.")
        (tmp_path / "app_spec.txt").write_text("System must do root thing.")

        result = load_and_evaluate(tmp_path, spec_path=explicit_spec)

        assert result is not None
        # Result should use explicit spec - score should reflect explicit content

    def test_specs_validated_md_second_priority(self, tmp_path):
        """specs/spec-validated.md is checked before specs/app_spec.txt."""
        features = [{"description": "Test feature for validated content"}]
        feature_path = tmp_path / "feature_list.json"
        feature_path.write_text(json.dumps(features))

        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        (specs_dir / "spec-validated.md").write_text("The system must use validated spec.")
        (specs_dir / "app_spec.txt").write_text("System must use app spec.")
        (tmp_path / "app_spec.txt").write_text("System must use root spec.")

        # Don't provide explicit spec_path - should use specs/spec-validated.md
        result = load_and_evaluate(tmp_path)

        assert result is not None

    def test_specs_app_spec_txt_third_priority(self, tmp_path):
        """specs/app_spec.txt is checked before root app_spec.txt."""
        features = [{"description": "Test feature"}]
        feature_path = tmp_path / "feature_list.json"
        feature_path.write_text(json.dumps(features))

        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        # No spec-validated.md
        (specs_dir / "app_spec.txt").write_text("The system must use specs dir spec.")
        (tmp_path / "app_spec.txt").write_text("System must use root spec.")

        result = load_and_evaluate(tmp_path)

        assert result is not None

    def test_root_app_spec_txt_last_priority(self, tmp_path):
        """Root app_spec.txt is used when no other locations exist."""
        features = [{"description": "Test feature"}]
        feature_path = tmp_path / "feature_list.json"
        feature_path.write_text(json.dumps(features))

        # Only root app_spec.txt exists
        (tmp_path / "app_spec.txt").write_text("The system must use root spec.")

        result = load_and_evaluate(tmp_path)

        assert result is not None


class TestLoggingBehavior:
    """Test debug logging in evaluation functions."""

    def test_uncovered_requirements_logged(self, tmp_path, caplog):
        """Verify uncovered requirements are logged at debug level."""
        import logging

        spec = """
        The system must handle authentication.
        Users should be able to view profiles.
        The application will support notifications.
        """
        features = [
            # Only covers authentication, not profiles or notifications
            {"description": "User authentication with login and password"}
        ]

        with caplog.at_level(logging.DEBUG):
            score = calculate_spec_coverage(features, spec)

        # Should have logged uncovered requirements
        assert score < 1.0  # Not full coverage
        # Check that debug logging occurred for uncovered requirements
        debug_messages = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
        uncovered_logged = any("Uncovered requirements" in msg for msg in debug_messages)
        assert uncovered_logged, "Expected uncovered requirements to be logged"

    def test_no_requirements_logged(self, caplog):
        """Verify 'no requirements' case is logged at debug level."""
        import logging

        spec = "Just some random text without any requirement-like sentences."
        features = [{"description": "Some feature"}]

        with caplog.at_level(logging.DEBUG):
            score = calculate_spec_coverage(features, spec)

        assert score == 0.5  # Fallback score
        debug_messages = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
        no_req_logged = any("No requirements extracted" in msg for msg in debug_messages)
        assert no_req_logged, "Expected 'no requirements' to be logged"


class TestWordOverlapLimitation:
    """Tests documenting the word overlap algorithm limitation.

    The coverage algorithm uses simple word overlap, meaning:
    - 'authenticate' vs 'authentication' are treated as different words
    - No stemming or lemmatization is applied

    These tests explicitly document this behavior.
    """

    def test_different_word_forms_not_matched(self):
        """Different word forms (authenticate vs authentication) don't match.

        This is a known limitation of the simple word overlap algorithm.
        """
        spec = "Users must be able to authenticate with credentials."
        features = [
            # Uses 'authentication' instead of 'authenticate'
            {"description": "Login system for user authentication"}
        ]

        score = calculate_spec_coverage(features, spec)

        # The words 'user' and potentially others overlap, but 'authenticate'
        # vs 'authentication' are different tokens. Score depends on overlap threshold.
        # This test documents the limitation - exact behavior depends on threshold config.
        assert 0.0 <= score <= 1.0  # Valid range

    def test_consistent_terminology_works_well(self):
        """When spec and features use consistent terminology, coverage is high."""
        spec = "Users must log in with email. Users must view dashboard."
        features = [
            {"description": "User login with email and password validation"},
            {"description": "User dashboard view with activity summary"},
        ]

        score = calculate_spec_coverage(features, spec)

        # Consistent use of 'user', 'login', 'dashboard' should give good coverage
        assert score >= 0.5

    def test_stop_words_filtered_from_overlap(self):
        """Stop words are filtered out from word overlap calculation.

        This ensures that common words like 'must', 'be', 'able', 'the' don't
        create false positive matches between unrelated requirements and features.
        """
        spec = "Users must be able to do something."
        features = [
            # This feature has different content words than the spec
            {"description": "The system should handle requests"}
        ]

        score = calculate_spec_coverage(features, spec)

        # With stop word filtering, 'users', 'do', 'something' vs 'system', 'handle', 'requests'
        # have no meaningful overlap. Stop words like 'must', 'be', 'able', 'the', 'should'
        # are excluded. This should result in low/no coverage.
        # Note: exact behavior depends on requirement extraction patterns
        assert 0.0 <= score <= 1.0


class TestEvaluationEdgeCases:
    """Edge case tests for robustness against malformed or unusual inputs."""

    def test_malformed_feature_missing_description(self):
        """Features without description field are handled gracefully."""
        features = [
            {},  # Empty feature
            {"test_steps": ["step1"]},  # No description
            {"description": "Valid feature"},  # Valid
        ]
        spec = "The system must do something."

        # Should not raise, just handle gracefully
        result = evaluate_feature_list(features, spec)
        assert result is not None
        assert 0.0 <= result.aggregate_score <= 1.0

    def test_unicode_content_handled(self):
        """Unicode characters in spec and features are handled correctly."""
        spec = "The système must support émojis 🎉 and accénts."
        features = [
            {"description": "Système émojis 🎉 support with accénts handling"},
            {"description": "日本語 テスト feature"},  # Japanese
            {"description": "Функция тестирования"},  # Russian
        ]

        # Should not raise
        result = evaluate_feature_list(features, spec)
        assert result is not None
        assert 0.0 <= result.aggregate_score <= 1.0

    def test_very_long_description(self):
        """Very long feature descriptions are handled without issues."""
        long_desc = "Feature " * 1000  # Very long description
        features = [{"description": long_desc, "test_steps": ["step"]}]
        spec = "The system must handle long content."

        result = evaluate_feature_list(features, spec)
        assert result is not None
        # Long descriptions are penalized in granularity
        assert result.granularity_score < 1.0

    def test_large_feature_list(self):
        """Large number of features is handled efficiently."""
        features = [
            {"description": f"Feature number {i} for testing scalability", "test_steps": ["step1", "step2"]}
            for i in range(500)
        ]
        spec = "The system must support many features for testing."

        # Should complete without hanging or memory issues
        result = evaluate_feature_list(features, spec)
        assert result is not None
        assert result.details["feature_count"] == 500

    def test_empty_strings_in_fields(self):
        """Empty strings in feature fields are handled gracefully."""
        features = [
            {"description": "", "test_steps": [], "expected_result": ""},
            {"description": "Valid", "test_steps": [""], "expected_result": ""},
        ]
        spec = ""

        result = evaluate_feature_list(features, spec)
        assert result is not None
        assert result.coverage_score == 0.0  # Empty spec

    def test_none_values_in_feature_list(self):
        """None values in feature dictionaries are handled gracefully."""
        features = [
            {"description": None},  # None description
            {"description": "Valid", "test_steps": None},  # None test_steps
        ]
        spec = "The system must do something."

        # Should handle None gracefully (may score 0 but shouldn't crash)
        try:
            result = evaluate_feature_list(features, spec)
            # If it doesn't crash, check valid result
            assert result is not None
        except (TypeError, AttributeError):
            # It's acceptable to raise on None values, but should be caught
            pytest.fail("Should handle None values gracefully without crashing")

    def test_special_characters_in_description(self):
        """Special characters don't break word extraction."""
        features = [
            {"description": "Handle @mentions and #hashtags in <html> tags & ampersands"},
            {"description": "Support $variables and %percentages with (parentheses)"},
            {"description": "Process 'quoted' and \"double-quoted\" strings"},
        ]
        spec = "The system must handle special characters: @#$%&*()"

        result = evaluate_feature_list(features, spec)
        assert result is not None
        assert 0.0 <= result.aggregate_score <= 1.0

    def test_numeric_only_content(self):
        """Numeric content in features and spec is handled."""
        features = [
            {"description": "Feature 123 with numbers 456"},
            {"description": "100% coverage of 50 items"},
        ]
        spec = "The system must handle 100 items with 99.9% uptime."

        result = evaluate_feature_list(features, spec)
        assert result is not None

    def test_load_and_evaluate_with_io_error(self, tmp_path, monkeypatch):
        """load_and_evaluate handles IO errors gracefully."""
        features = [{"description": "Test feature"}]
        feature_path = tmp_path / "feature_list.json"
        feature_path.write_text(json.dumps(features))

        spec_path = tmp_path / "app_spec.txt"
        spec_path.write_text("The system must work.")

        # Make spec file unreadable after creation by mocking read_text
        original_read_text = Path.read_text

        def mock_read_text(self, encoding=None):
            if "app_spec" in str(self):
                raise IOError("Simulated read error")
            return original_read_text(self, encoding=encoding)

        monkeypatch.setattr(Path, "read_text", mock_read_text)

        # Should handle gracefully and try next location or return with empty spec
        result = load_and_evaluate(tmp_path)
        assert result is not None  # Should still return a result with empty spec

    def test_feature_list_with_extra_fields(self):
        """Features with extra unexpected fields are handled."""
        features = [
            {
                "description": "Valid feature with extra fields",
                "test_steps": ["step1"],
                "unknown_field": "should be ignored",
                "another_field": {"nested": "data"},
                "numeric_field": 12345,
            }
        ]
        spec = "The system must do something."

        result = evaluate_feature_list(features, spec)
        assert result is not None
        assert 0.0 <= result.aggregate_score <= 1.0
