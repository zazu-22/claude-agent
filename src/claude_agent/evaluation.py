"""
Feature List Evaluation
=======================

Score feature lists against quality criteria to support Best-of-N sampling.

Usage Example
-------------
    from pathlib import Path
    from claude_agent.evaluation import load_and_evaluate, EvaluationWeights

    # Evaluate with default weights
    result = load_and_evaluate(Path("./my-project"))
    if result:
        print(f"Aggregate score: {result.aggregate_score:.2f}")
        print(f"Coverage: {result.coverage_score:.2f}")
        print(f"Testability: {result.testability_score:.2f}")

    # Evaluate with custom weights
    weights = EvaluationWeights(
        coverage=0.5,
        testability=0.2,
        granularity=0.2,
        independence=0.1,
    )
    result = load_and_evaluate(Path("./my-project"), weights=weights)
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class EvaluationWeights:
    """Configurable weights for evaluation criteria."""

    coverage: float = 0.4
    testability: float = 0.3
    granularity: float = 0.2
    independence: float = 0.1

    def __post_init__(self):
        """Validate that weights sum to 1.0 within tolerance."""
        total = self.coverage + self.testability + self.granularity + self.independence
        if not (0.99 <= total <= 1.01):  # Allow small float imprecision
            raise ValueError(f"Weights must sum to 1.0, got {total}")


@dataclass
class EvaluationResult:
    """Result of evaluating a feature list."""

    coverage_score: float
    testability_score: float
    granularity_score: float
    independence_score: float
    aggregate_score: float
    details: dict  # Per-criterion details for debugging


def calculate_spec_coverage(features: list[dict], spec: str) -> float:
    """
    Calculate how well features cover spec requirements.

    Algorithm:
    1. Extract requirement sentences from spec (heuristic: sentences with action verbs)
    2. For each feature, check if it references spec content
    3. Calculate percentage of requirements covered by at least one feature

    Args:
        features: List of feature dictionaries from feature_list.json
        spec: Raw specification text

    Returns:
        Float 0.0-1.0 representing coverage percentage
    """
    if not features or not spec:
        return 0.0

    # Extract requirement-like sentences from spec
    # Heuristic: Look for sentences with action verbs, "must", "should", "will"
    requirement_patterns = [
        r"(?:must|should|shall|will)\s+\w+",  # Modal verb patterns
        r"(?:user|system|app|application)\s+(?:can|should|must|will)",  # Subject patterns
        r"(?:allow|enable|support|provide|display|show|create|update|delete)",  # Action verbs
    ]

    requirements = set()
    sentences = re.split(r"[.!?]\s+", spec)
    for sentence in sentences:
        for pattern in requirement_patterns:
            if re.search(pattern, sentence, re.IGNORECASE):
                # Normalize and add
                normalized = sentence.strip().lower()[:100]  # Truncate for comparison
                if len(normalized) > 10:  # Skip very short matches
                    requirements.add(normalized)
                break

    if not requirements:
        # Fallback: count spec sections/headers as requirements
        headers = re.findall(r"^#+\s+(.+)$", spec, re.MULTILINE)
        requirements = set(h.lower() for h in headers if len(h) > 5)

    if not requirements:
        return 0.5  # Can't extract requirements, assume partial coverage

    # Check feature coverage
    covered = 0
    for req in requirements:
        req_words = set(re.findall(r"\w+", req))
        for feature in features:
            description = feature.get("description", "").lower()
            feature_words = set(re.findall(r"\w+", description))
            # Coverage if significant word overlap
            overlap = len(req_words & feature_words)
            if overlap >= min(3, len(req_words) // 2):
                covered += 1
                break

    return covered / len(requirements)


def calculate_testability_score(features: list[dict]) -> float:
    """
    Score features on testability (concrete steps, verifiable outcomes).

    Checks for:
    - Presence of test_steps field
    - Steps are concrete actions (not vague)
    - Verifiable outcomes described

    Args:
        features: List of feature dictionaries

    Returns:
        Float 0.0-1.0 representing average testability
    """
    if not features:
        return 0.0

    scores = []
    for feature in features:
        score = 0.0

        # Check for test steps
        test_steps = feature.get("test_steps", [])
        if test_steps:
            score += 0.3

            # Check for concrete actions
            action_verbs = [
                "click",
                "type",
                "enter",
                "select",
                "navigate",
                "verify",
                "check",
                "confirm",
                "submit",
                "open",
            ]
            concrete_steps = sum(
                1
                for step in test_steps
                if any(verb in step.lower() for verb in action_verbs)
            )
            if test_steps and concrete_steps / len(test_steps) >= 0.5:
                score += 0.3

        # Check for expected outcome
        # Fallback to description when expected_result is missing or empty,
        # since feature descriptions often contain verifiable outcome language
        # (e.g., "User should see...", "Form displays...")
        expected = feature.get("expected_result", "") or feature.get("description", "")
        verifiable_words = [
            "should",
            "displays",
            "shows",
            "appears",
            "returns",
            "contains",
            "equals",
            "matches",
            "visible",
            "enabled",
        ]
        if any(word in expected.lower() for word in verifiable_words):
            score += 0.4

        scores.append(score)

    return sum(scores) / len(scores)


def calculate_granularity_score(features: list[dict]) -> float:
    """
    Score features on appropriate granularity (not too large, not too small).

    Heuristics:
    - Too small: < 50 chars description, < 2 test steps
    - Too large: > 500 chars description, > 10 test steps, "and" in description
    - Ideal: 100-300 chars, 3-7 test steps

    Args:
        features: List of feature dictionaries

    Returns:
        Float 0.0-1.0 representing average granularity appropriateness
    """
    if not features:
        return 0.0

    scores = []
    for feature in features:
        description = feature.get("description", "")
        test_steps = feature.get("test_steps", [])

        desc_len = len(description)
        step_count = len(test_steps)

        score = 1.0

        # Penalize too small
        if desc_len < 50:
            score -= 0.3
        if step_count < 2:
            score -= 0.2

        # Penalize too large
        if desc_len > 500:
            score -= 0.3
        if step_count > 10:
            score -= 0.2

        # Penalize compound features (multiple "and")
        and_count = description.lower().count(" and ")
        if and_count >= 2:
            score -= 0.2 * min(and_count, 3)

        # Bonus for ideal range
        if 100 <= desc_len <= 300 and 3 <= step_count <= 7:
            score += 0.1

        scores.append(max(0.0, min(1.0, score)))

    return sum(scores) / len(scores)


def calculate_independence_score(features: list[dict]) -> float:
    """
    Score features on independence (can be implemented in isolation).

    Checks for:
    - Explicit dependencies field
    - References to other feature indices
    - Sequential language ("after", "before", "then")

    Args:
        features: List of feature dictionaries

    Returns:
        Float 0.0-1.0 where 1.0 = fully independent
    """
    if not features:
        return 0.0

    scores = []
    for feature in features:
        score = 1.0

        # Check for explicit dependencies
        dependencies = feature.get("dependencies", [])
        if dependencies:
            # Penalize based on number of dependencies
            score -= 0.1 * min(len(dependencies), 5)

        # Check for references to other features
        description = feature.get("description", "")
        test_steps_text = " ".join(feature.get("test_steps", []))
        full_text = f"{description} {test_steps_text}".lower()

        # Sequential language
        sequential_words = [
            "after",
            "before",
            "then",
            "following",
            "once",
            "requires",
            "depends on",
            "prerequisite",
        ]
        for word in sequential_words:
            if word in full_text:
                score -= 0.1

        # Feature index references
        feature_refs = re.findall(r"feature\s*#?\d+", full_text, re.IGNORECASE)
        score -= 0.1 * len(feature_refs)

        scores.append(max(0.0, min(1.0, score)))

    return sum(scores) / len(scores)


def evaluate_feature_list(
    features: list[dict],
    spec: str,
    weights: Optional[EvaluationWeights] = None,
) -> EvaluationResult:
    """
    Calculate aggregate score for a feature list.

    Args:
        features: List of feature dictionaries
        spec: Raw specification text
        weights: Optional custom weights (defaults to standard weights)

    Returns:
        EvaluationResult with all scores and aggregate
    """
    if weights is None:
        weights = EvaluationWeights()

    coverage = calculate_spec_coverage(features, spec)
    testability = calculate_testability_score(features)
    granularity = calculate_granularity_score(features)
    independence = calculate_independence_score(features)

    aggregate = (
        coverage * weights.coverage
        + testability * weights.testability
        + granularity * weights.granularity
        + independence * weights.independence
    )

    return EvaluationResult(
        coverage_score=coverage,
        testability_score=testability,
        granularity_score=granularity,
        independence_score=independence,
        aggregate_score=aggregate,
        details={
            "feature_count": len(features),
            "weights": {
                "coverage": weights.coverage,
                "testability": weights.testability,
                "granularity": weights.granularity,
                "independence": weights.independence,
            },
        },
    )


def load_and_evaluate(
    project_dir: Path,
    spec_path: Optional[Path] = None,
    weights: Optional[EvaluationWeights] = None,
) -> Optional[EvaluationResult]:
    """
    Load feature list and spec from project, evaluate.

    Args:
        project_dir: Project directory containing feature_list.json
        spec_path: Optional path to spec (defaults to project_dir/app_spec.txt)
        weights: Optional custom weights

    Returns:
        EvaluationResult or None if files missing
    """
    feature_list_path = project_dir / "feature_list.json"
    if not feature_list_path.exists():
        return None

    try:
        with open(feature_list_path) as f:
            features = json.load(f)
    except (json.JSONDecodeError, IOError):
        return None

    # Try multiple spec locations
    spec = ""
    spec_locations = [
        spec_path,
        project_dir / "specs" / "spec-validated.md",
        project_dir / "specs" / "app_spec.txt",
        project_dir / "app_spec.txt",
    ]

    for loc in spec_locations:
        if loc and loc.exists():
            spec = loc.read_text(encoding="utf-8")
            break

    return evaluate_feature_list(features, spec, weights)
