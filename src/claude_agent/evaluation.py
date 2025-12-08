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
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RequirementPatterns:
    """Configurable patterns for requirement extraction from specs.

    Patterns are regular expressions used to identify requirement sentences.
    Default patterns cover common requirement phrasings including modal verbs,
    subject patterns, action verbs, and negations.

    Word Overlap Algorithm Limitation
    ---------------------------------
    The coverage algorithm uses simple word overlap matching. This means:
    - "authenticate" vs "authentication" are treated as different words
    - Stemming/lemmatization is NOT applied

    For more robust text matching, consider using a library like nltk with
    stemming, though this adds a dependency. The current algorithm works well
    for specs and features that use consistent terminology.
    """

    # Modal verb patterns (must, should, shall, will)
    modal_patterns: tuple[str, ...] = (
        r"(?:must|should|shall|will)\s+\w+",
        r"(?:must|should|shall|will)\s+not\s+\w+",  # Negated requirements
    )

    # Subject patterns (user/system can/should/must/will)
    subject_patterns: tuple[str, ...] = (
        r"(?:user|system|app|application)\s+(?:can|should|must|will)",
        r"(?:user|system|app|application)\s+(?:cannot|can't|should\s+not|must\s+not)",
    )

    # Action verb patterns (various phrasings)
    action_patterns: tuple[str, ...] = (
        r"(?:allow|enable|support|provide|display|show|create|update|delete)",
        r"(?:allows|enables|supports|provides|displays|shows|creates|updates|deletes)",
        r"(?:allowing|enabling|supporting|providing|displaying|showing|creating|updating|deleting)",
        r"(?:prevent|prohibit|restrict|block|disable|hide|remove)",
        r"(?:prevents|prohibits|restricts|blocks|disables|hides|removes)",
    )

    # Word overlap threshold factor (multiplied by requirement word count)
    # The threshold is: min(max_overlap_words, max(min_overlap_words, word_count * factor))
    # This ensures small requirements need fewer matching words while capping large ones
    overlap_threshold_factor: float = 0.5

    # Minimum overlap words required
    min_overlap_words: int = 2

    # Maximum overlap words required (caps the threshold for long requirements)
    max_overlap_words: int = 3

    # Threshold ratio for concrete test steps (steps with action verbs / total steps)
    # Used in testability scoring - features with this ratio or higher score better
    concrete_steps_threshold: float = 0.5

    # Verifiable words used to detect testable outcomes in expected_result/description
    verifiable_words: tuple[str, ...] = (
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
    )

    def get_all_patterns(self) -> list[str]:
        """Return all patterns as a combined list."""
        return list(self.modal_patterns) + list(self.subject_patterns) + list(self.action_patterns)

    def get_compiled_patterns(self) -> list[re.Pattern]:
        """Return pre-compiled regex patterns for better performance.

        Compiles patterns once and caches them. For large specs, this avoids
        the overhead of recompiling patterns on every sentence.
        """
        # Note: Can't use lru_cache on frozen dataclass methods, so we compile fresh
        # but this is still faster than inline re.search with pattern strings
        return [re.compile(p, re.IGNORECASE) for p in self.get_all_patterns()]


# Default patterns instance for convenience
DEFAULT_REQUIREMENT_PATTERNS = RequirementPatterns()

# Pre-compiled patterns for default instance (cached for performance)
_DEFAULT_COMPILED_PATTERNS: list[re.Pattern] | None = None


def get_default_compiled_patterns() -> list[re.Pattern]:
    """Get pre-compiled patterns for the default RequirementPatterns instance.

    This caches the compiled patterns globally for better performance when
    using default patterns across multiple calls.
    """
    global _DEFAULT_COMPILED_PATTERNS
    if _DEFAULT_COMPILED_PATTERNS is None:
        _DEFAULT_COMPILED_PATTERNS = DEFAULT_REQUIREMENT_PATTERNS.get_compiled_patterns()
    return _DEFAULT_COMPILED_PATTERNS

# =============================================================================
# Constants
# =============================================================================

# Truncation length for requirement normalization during coverage calculation
REQUIREMENT_TRUNCATION_LENGTH = 100

# Granularity scoring constants
# Penalty factor applied per "and" conjunction in feature descriptions
# Rationale: Multiple "and" conjunctions indicate compound features that
# should be split. The penalty increases with count but caps at 3 to avoid
# over-penalizing (e.g., 2 ands = -0.4, 3+ ands = -0.6 max)
COMPOUND_FEATURE_PENALTY_FACTOR = 0.2
COMPOUND_FEATURE_MAX_PENALTY_COUNT = 3

# Testability scoring constants
# These weights determine how different aspects contribute to testability score
TESTABILITY_SCORE_HAS_STEPS = 0.3  # Score for having test_steps field
TESTABILITY_SCORE_CONCRETE_STEPS = 0.3  # Score for having concrete action verbs
TESTABILITY_SCORE_EXPECTED_RESULT = 0.4  # Score for verifiable expected_result
TESTABILITY_SCORE_DESCRIPTION_FALLBACK = 0.2  # Reduced score when using description fallback

# Stop words to exclude from word overlap matching in coverage calculation
# These common words add noise and can cause false positive matches between
# unrelated requirements and features (e.g., "must be able to" matches anything)
STOP_WORDS = frozenset({
    "must", "should", "shall", "will", "can", "may",  # Modal verbs
    "be", "is", "are", "was", "were", "been",  # Be verbs
    "the", "a", "an",  # Articles
    "to", "of", "and", "or", "in", "on", "for", "with", "by",  # Prepositions/conjunctions
    "that", "this", "it", "they", "them", "their",  # Pronouns
    "able", "not",  # Common requirement words
})


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


def calculate_spec_coverage(
    features: list[dict],
    spec: str,
    patterns: Optional[RequirementPatterns] = None,
) -> float:
    """
    Calculate how well features cover spec requirements.

    Algorithm:
    1. Extract requirement sentences from spec (heuristic: sentences with action verbs)
    2. For each feature, check if it references spec content
    3. Calculate percentage of requirements covered by at least one feature

    Args:
        features: List of feature dictionaries from feature_list.json
        spec: Raw specification text
        patterns: Optional custom patterns for requirement extraction

    Returns:
        Float 0.0-1.0 representing coverage percentage
    """
    if not features or not spec:
        return 0.0

    if patterns is None:
        patterns = DEFAULT_REQUIREMENT_PATTERNS

    # Extract requirement-like sentences from spec using pre-compiled patterns
    # Use cached compiled patterns for default instance, otherwise compile fresh
    if patterns is DEFAULT_REQUIREMENT_PATTERNS:
        compiled_patterns = get_default_compiled_patterns()
    else:
        compiled_patterns = patterns.get_compiled_patterns()

    requirements = set()
    sentences = re.split(r"[.!?]\s+", spec)
    for sentence in sentences:
        for pattern in compiled_patterns:
            if pattern.search(sentence):
                # Normalize and add
                normalized = sentence.strip().lower()[:REQUIREMENT_TRUNCATION_LENGTH]
                if len(normalized) > 10:  # Skip very short matches
                    requirements.add(normalized)
                break

    if not requirements:
        # Fallback: count spec sections/headers as requirements
        headers = re.findall(r"^#+\s+(.+)$", spec, re.MULTILINE)
        requirements = set(h.lower() for h in headers if len(h) > 5)

    if not requirements:
        logger.debug("No requirements extracted from spec, returning 0.5")
        return 0.5  # Can't extract requirements, assume unknown coverage

    # Check feature coverage
    covered = 0
    uncovered_requirements: list[str] = []

    for req in requirements:
        # Extract words and filter out stop words to focus on meaningful content
        req_words = set(re.findall(r"\w+", req)) - STOP_WORDS
        # Calculate dynamic threshold based on requirement length (after stop word removal)
        # Formula: min(max_overlap, max(min_overlap, word_count * factor))
        # This caps threshold for long requirements while having a minimum for short ones
        threshold = min(
            patterns.max_overlap_words,
            max(
                patterns.min_overlap_words,
                int(len(req_words) * patterns.overlap_threshold_factor),
            ),
        )
        is_covered = False

        for feature in features:
            description = feature.get("description") or ""  # Handle None values
            # Filter stop words from feature description as well
            feature_words = set(re.findall(r"\w+", description.lower())) - STOP_WORDS
            # Coverage if significant word overlap
            overlap = len(req_words & feature_words)
            if overlap >= threshold:
                covered += 1
                is_covered = True
                break

        if not is_covered:
            uncovered_requirements.append(req[:80])  # Truncate for logging

    # Log coverage misses for debugging
    if uncovered_requirements:
        logger.debug(
            "Uncovered requirements (%d of %d):\n  - %s",
            len(uncovered_requirements),
            len(requirements),
            "\n  - ".join(uncovered_requirements[:10]),  # Limit log output
        )

    return covered / len(requirements)


def calculate_testability_score(
    features: list[dict],
    patterns: Optional[RequirementPatterns] = None,
) -> float:
    """
    Score features on testability (concrete steps, verifiable outcomes).

    Checks for:
    - Presence of test_steps field
    - Steps are concrete actions (not vague)
    - Verifiable outcomes described

    Args:
        features: List of feature dictionaries
        patterns: Optional custom patterns (uses DEFAULT_REQUIREMENT_PATTERNS if None)

    Returns:
        Float 0.0-1.0 representing average testability
    """
    if not features:
        return 0.0

    if patterns is None:
        patterns = DEFAULT_REQUIREMENT_PATTERNS

    scores = []
    for feature in features:
        score = 0.0

        # Check for test steps (handle explicit None)
        test_steps = feature.get("test_steps") or []
        if test_steps:
            score += TESTABILITY_SCORE_HAS_STEPS

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
            if test_steps and concrete_steps / len(test_steps) >= patterns.concrete_steps_threshold:
                score += TESTABILITY_SCORE_CONCRETE_STEPS

        # Check for expected outcome
        # Prefer explicit expected_result field; fall back to description with penalty
        expected_result = feature.get("expected_result") or ""
        description = feature.get("description") or ""

        if expected_result and any(
            word in expected_result.lower() for word in patterns.verifiable_words
        ):
            # Full score for explicit expected_result with verifiable language
            score += TESTABILITY_SCORE_EXPECTED_RESULT
        elif description and any(
            word in description.lower() for word in patterns.verifiable_words
        ):
            # Reduced score when falling back to description
            # Description may be verbose without concrete expected outcomes
            score += TESTABILITY_SCORE_DESCRIPTION_FALLBACK

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
        description = feature.get("description") or ""
        test_steps = feature.get("test_steps") or []

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
            score -= COMPOUND_FEATURE_PENALTY_FACTOR * min(and_count, COMPOUND_FEATURE_MAX_PENALTY_COUNT)

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
        dependencies = feature.get("dependencies") or []
        if dependencies:
            # Penalize based on number of dependencies
            score -= 0.1 * min(len(dependencies), 5)

        # Check for references to other features
        description = feature.get("description") or ""
        test_steps_text = " ".join(feature.get("test_steps") or [])
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
    patterns: Optional[RequirementPatterns] = None,
) -> EvaluationResult:
    """
    Calculate aggregate score for a feature list.

    Args:
        features: List of feature dictionaries
        spec: Raw specification text
        weights: Optional custom weights (defaults to standard weights)
        patterns: Optional custom patterns for requirement extraction and testability

    Returns:
        EvaluationResult with all scores and aggregate
    """
    if weights is None:
        weights = EvaluationWeights()

    coverage = calculate_spec_coverage(features, spec, patterns)
    testability = calculate_testability_score(features, patterns)
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
        with open(feature_list_path, encoding="utf-8") as f:
            features = json.load(f)
    except (json.JSONDecodeError, IOError, UnicodeDecodeError) as e:
        logger.debug(f"Failed to load feature list from {feature_list_path}: {e}")
        return None

    # Try multiple spec locations with error handling
    spec = ""
    spec_locations = [
        spec_path,
        project_dir / "specs" / "spec-validated.md",
        project_dir / "specs" / "app_spec.txt",
        project_dir / "app_spec.txt",
    ]

    for loc in spec_locations:
        if loc and loc.exists():
            try:
                spec = loc.read_text(encoding="utf-8")
                break
            except (IOError, UnicodeDecodeError) as e:
                logger.debug(f"Failed to read spec from {loc}: {e}")
                continue  # Try next location

    return evaluate_feature_list(features, spec, weights)
