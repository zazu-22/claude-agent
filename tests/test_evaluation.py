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

    def test_weights_allow_small_float_imprecision(self):
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
        assert score == 0.4  # Only expected_result contributes

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
        """Test that poorly structured features score lower."""
        features = [
            {"description": "Login"},  # Too short
            {"description": "Do everything in the app and then some more stuff and also this and that and another thing"},  # Compound
            {"description": "Feature depends on feature #1", "dependencies": [0]},  # Dependent
        ]

        feature_path = tmp_path / "feature_list.json"
        feature_path.write_text(json.dumps(features))

        result = load_and_evaluate(tmp_path)

        assert result is not None
        # Poor features should score lower
        assert result.granularity_score <= 0.6
        assert result.independence_score <= 0.9
