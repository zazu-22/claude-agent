# Drift Mitigation Design Document

## Executive Summary

This document outlines a systematic approach to mitigating quality degradation in long-running agentic coding workflows. The design addresses three distinct failure modes that compound across multi-step, multi-session AI coding tasks.

## Problem Analysis

### Three Failure Modes

| Failure Mode | Description | How It Manifests |
|--------------|-------------|------------------|
| **Lossy Handoff Divergence** | When context passes between stateless sessions via artifacts, implicit intent is lost. Receiving sessions fill gaps with plausible-but-unverified assumptions. | Session N+1 interprets artifacts differently than Session N intended. Cumulative drift compounds silently. |
| **Stochastic Cascade Drift** | LLM outputs are probabilistic samples. Variance at step N becomes input at step N+1, compounding rather than converging. | "Refinement" passes branch into new trajectories rather than converging toward intent. |
| **Passive Instruction Decay** | LLMs can reason about what they should do, acknowledge instructions, then fail to execute them. | Agent identifies it should verify previous work, then skips directly to implementation. |

### Why Small Tasks Succeed

Small tasks terminate before drift mechanisms can compound:
- Constrained problem space limits ambiguity interpretation
- Few steps prevent variance cascade
- Single session avoids handoff loss

Large tasks fail not from capability limits but from **accumulated invisible drift** across steps and sessions.

### Current Claude-Agent Vulnerabilities

#### Lossy Handoff Points
| Handoff | Artifact | Lost Context |
|---------|----------|--------------|
| Initializer → Coding | `feature_list.json` | Why features decomposed this way, priorities |
| Session N → N+1 | `claude-progress.txt` | Full reasoning behind choices |
| Validator → Coding | `rejected_tests` array | Specific failure context |
| Spec → Initializer | `app_spec.txt` | User's mental model, unstated assumptions |

#### Stochastic Drift Points
1. **Feature list generation** - Single sample becomes entire project foundation
2. **Implementation architecture** - Each session's choices constrain future sessions
3. **Verification selection** - Which features to verify is stochastic
4. **Validator sampling** - Which 5-10 features tested affects verdict

#### Passive Instruction Points
Current prompts use passive language:
- "Get bearings: read spec, feature list, progress notes"
- "Verify previous work (run 1-2 core features)"
- "Read the specification carefully"

No enforcement mechanism ensures these are executed.

---

## Solution Architecture

### Four-Layer Mitigation Strategy

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 4: ENRICH                                             │
│ Capture evaluation output as handoff artifacts              │
│ Decision records, explicit assumptions, traceability        │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: FORCE                                              │
│ Mandatory evaluation checkpoints with explicit output       │
│ Gated progression, accountability, visible reasoning        │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: SAMPLE                                             │
│ Best-of-N generation with evaluation criteria               │
│ Exploit variance as search space, not fight it              │
├─────────────────────────────────────────────────────────────┤
│ Layer 1: CONSTRAIN                                          │
│ Lock invariants before allowing generative sampling         │
│ API contracts, schemas, architectural decisions             │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Components

### 1. Forced Evaluation Checkpoints

**Principle:** Transform passive instructions into mandatory evaluation sequences with explicit output requirements.

**Pattern:**
```
Step 1 - EVALUATE: State evidence for each requirement
Step 2 - VERIFY: Confirm prerequisites are met
Step 3 - PLAN: State intended actions with constraints
Step 4 - EXECUTE: Only now proceed

CRITICAL: Steps 1-3 are WORTHLESS unless actually performed.
```

**Evidence:** This pattern achieved 84% activation vs 20% for simple instructions in skill activation tests (4x improvement).

#### 1.1 Coding Agent Evaluation Sequence

```markdown
## MANDATORY SEQUENCE BEFORE IMPLEMENTATION

### Step 1 - CONTEXT VERIFICATION (explicit output required)
For each item, state the evidence you found:

- [ ] feature_list.json read:
  Quote: "[the specific feature I'm implementing, index and full text]"

- [ ] claude-progress.txt read:
  Quote: "[last session's status line and next steps]"

- [ ] Architectural constraints identified:
  Quote: "[key decisions from previous sessions that constrain this work]"

### Step 2 - REGRESSION VERIFICATION (explicit output required)
Run these verifications and state results:

- Feature [index of most recently passed]: PASS/FAIL
  Evidence: "[what you tested and saw]"

- Feature [index of critical-path feature]: PASS/FAIL
  Evidence: "[what you tested and saw]"

### Step 3 - IMPLEMENTATION PLAN (explicit output required)
Before writing code, state:
- What I will build: [specific description]
- Files I will modify: [list]
- How this connects to existing code: [description]
- Constraints I must honor: [list from Step 1]

### Step 4 - IMPLEMENT
ONLY NOW begin implementation.

CRITICAL: Steps 1-3 are WORTHLESS unless you actually performed them.
Skipping to implementation without evidence above is a FAILURE MODE.
```

#### 1.2 Initializer Agent Evaluation Sequence

```markdown
## MANDATORY FEATURE GENERATION SEQUENCE

### Step 1 - SPEC DECOMPOSITION (explicit output required)
For each section of the spec, list:
- Section: "[quote section header]"
- Key requirements: "[list requirements in this section]"
- Ambiguities found: "[list anything unclear]"

### Step 2 - FEATURE MAPPING (explicit output required)
For EACH feature you generate, state:
- Feature: "[description]"
- Traces to spec section: "[quote the specific spec text this implements]"
- Why this granularity: "[why this is one feature vs split/combined]"

### Step 3 - COVERAGE CHECK (explicit output required)
- Spec requirements covered: [count] / [total]
- Any requirements NOT covered by a feature: "[list]"

### Step 4 - GENERATE feature_list.json
ONLY NOW write the feature list.

CRITICAL: Features without spec traceability in Step 2 are DRIFT RISKS.
```

#### 1.3 Validator Agent Evaluation Sequence

```markdown
## MANDATORY VALIDATION SEQUENCE

### Step 1 - SPEC ALIGNMENT CHECK (explicit output required)
For each feature I will test:
- Feature: "[description]"
- Original spec requirement: "[quote]"
- What "working" looks like: "[specific observable behavior]"

### Step 2 - TEST EXECUTION (explicit output required)
For each tested feature:
- Steps performed: "[list]"
- Expected result: "[from Step 1]"
- Actual result: "[what I observed]"
- Screenshot evidence: [attached]
- Verdict for this feature: PASS/FAIL

### Step 3 - AGGREGATE VERDICT (explicit output required)
- Features tested: [count]
- Features passed: [count]
- Features failed: [list with specific reasons]
- Overall verdict: APPROVED/REJECTED/CONTINUE/NEEDS_VERIFICATION
- Reasoning: "[why this verdict given the evidence]"

CRITICAL: A verdict without Step 2 evidence is NOT TRUSTWORTHY.
```

---

### 2. Architecture Lock Phase

**Principle:** Identify what MUST be invariant and lock it before allowing generative sampling on variables.

**New Phase:** Insert between Initializer and first Coding session.

#### 2.1 Architecture Lock Agent

**Purpose:** Establish hard constraints that all coding sessions must honor.

**Outputs:**
- `architecture/contracts.yaml` - API surface definitions
- `architecture/schemas.yaml` - Data model definitions
- `architecture/decisions.yaml` - Key architectural decisions with rationale

**Invariants to Lock:**
| Category | Examples | Why Lock |
|----------|----------|----------|
| API Contracts | Endpoints, request/response types | Prevents interface drift |
| Data Models | Database schema, entity relationships | Prevents schema conflicts |
| Core Abstractions | Service boundaries, module structure | Prevents architectural fragmentation |
| Technology Choices | Framework, key libraries | Prevents incompatible choices |

**Coding Agent Constraint:**
```markdown
Before implementing ANY feature, verify against architecture/:
- Does this respect the API contract? Quote relevant section.
- Does this use the defined data models? Quote relevant section.
- Does this follow established decisions? Quote relevant section.

If implementation requires changing an invariant, STOP and document why.
Do NOT silently deviate from locked architecture.
```

---

### 3. Decision Record Protocol

**Principle:** Capture WHY decisions were made, not just WHAT was done.

#### 3.1 Decision Record Format

```yaml
# decisions.yaml - append-only log of architectural decisions
decisions:
  - id: DR-001
    timestamp: 2024-01-15T10:23:00Z
    session: 2
    topic: "Form handling library"
    choice: "React Hook Form"
    alternatives_considered:
      - "Formik - rejected due to bundle size"
      - "Native forms - rejected due to validation complexity"
    rationale: "Spec mentions complex validation requirements (see SPEC.md line 45)"
    constraints_created:
      - "All forms must use RHF patterns"
      - "Validation schemas must use zod (RHF integration)"
    affects_features: [5, 12, 23]
```

#### 3.2 Decision Record Requirements

Coding agent must create a decision record when:
- Choosing between multiple valid implementation approaches
- Adding a new dependency
- Establishing a pattern that future features should follow
- Deviating from an existing pattern (with justification)

---

### 4. Best-of-N Sampling

**Principle:** Accept that outputs are probabilistic samples. Generate multiple, evaluate against criteria, select best.

#### 4.1 Feature List Sampling

**Current:** Single generation becomes project foundation.

**Proposed:**
1. Generate 3 feature lists from same spec
2. Score each against criteria:
   - **Coverage:** % of spec requirements represented
   - **Testability:** Are test steps concrete and verifiable?
   - **Granularity:** Right size for single-session implementation?
   - **Independence:** Can features be implemented in isolation?
3. Select highest-scoring list
4. If no list scores above threshold, refine spec and retry

**Implementation:**
```python
async def generate_feature_list_with_sampling(spec: str, n: int = 3) -> FeatureList:
    candidates = []
    for i in range(n):
        features = await run_initializer_agent(spec)
        score = evaluate_feature_list(features, spec)
        candidates.append((features, score))

    best = max(candidates, key=lambda x: x[1])
    if best[1] < THRESHOLD:
        raise NeedsSpecRefinement(f"Best score {best[1]} below threshold")
    return best[0]
```

#### 4.2 Evaluation Criteria Functions

```python
def evaluate_feature_list(features: list, spec: str) -> float:
    scores = {
        'coverage': calculate_spec_coverage(features, spec),
        'testability': calculate_testability_score(features),
        'granularity': calculate_granularity_score(features),
        'independence': calculate_independence_score(features),
    }
    weights = {'coverage': 0.4, 'testability': 0.3, 'granularity': 0.2, 'independence': 0.1}
    return sum(scores[k] * weights[k] for k in scores)
```

---

### 5. Handoff Artifact Enrichment

**Principle:** Evaluation output becomes part of handoff artifacts, preserving reasoning.

#### 5.1 Enhanced Progress Notes Structure

```markdown
=== SESSION N: [timestamp] ===
Status: X/Y features passing (Z%)

## Context Verification (from forced evaluation)
- Feature list state: [quoted evidence]
- Previous session status: [quoted evidence]
- Architectural constraints: [quoted evidence]

## Regression Verification Results
- Feature [X]: PASS - [evidence]
- Feature [Y]: PASS - [evidence]

## Implementation Plan (stated before coding)
- Target feature: [index and description]
- Files to modify: [list]
- Constraints honored: [list]

## Implementation Outcome
- Completed: [description]
- Decisions made: [reference to decisions.yaml entries]
- Issues encountered: [list]

## Handoff Notes for Next Session
- Current state: [description]
- Known issues: [list]
- Suggested next feature: [index]
- Warnings: [anything the next session should know]

=========================================
```

#### 5.2 Explicit Assumptions Log

Each session must state assumptions being made:

```markdown
## Assumptions This Session
- Database schema in migrations/ is canonical (verified by checking [file])
- Auth flow uses JWT (inferred from token.ts line 23)
- Error format follows errors.ts pattern (verified by checking [file])
- Previous session's feature [X] is working (verified by running test)
```

---

### 6. Drift Detection Metrics

**Principle:** Make drift visible through measurement.

#### 6.1 Metrics to Track

| Metric | Description | Drift Signal |
|--------|-------------|--------------|
| Regression rate | % of verifications that catch failures | High = drift occurring |
| Rejection cycles | Validator rejections before approval | Increasing = drift accumulating |
| Session velocity | Features per session over time | Decreasing = complexity/drift |
| Assumption mismatches | Stated assumptions that prove wrong | High = handoff loss |
| Architecture deviations | Locked constraints violated | Any = drift from invariants |

#### 6.2 Metrics Storage

```json
{
  "sessions": [
    {
      "session_id": 5,
      "timestamp": "2024-01-15T14:30:00Z",
      "features_attempted": 1,
      "features_completed": 1,
      "regressions_caught": 0,
      "assumptions_stated": 4,
      "assumptions_violated": 0,
      "architecture_deviations": 0,
      "evaluation_sections_present": ["context", "regression", "plan"]
    }
  ],
  "validation_attempts": [
    {
      "attempt": 1,
      "verdict": "REJECTED",
      "features_tested": 8,
      "features_failed": 2,
      "failure_reasons": ["drift from spec", "regression"]
    }
  ]
}
```

---

### 7. Validation Hook

**Principle:** Verify that forced evaluation actually occurred before allowing progression.

#### 7.1 Hook Implementation

```python
async def evaluation_validation_hook(agent_output: str, phase: str) -> ValidationResult:
    """
    Parse agent output to verify required evaluation sections are present.
    Returns error if sections missing, allowing retry or escalation.
    """
    required_sections = {
        'coding': ['CONTEXT VERIFICATION', 'REGRESSION VERIFICATION', 'IMPLEMENTATION PLAN'],
        'initializer': ['SPEC DECOMPOSITION', 'FEATURE MAPPING', 'COVERAGE CHECK'],
        'validator': ['SPEC ALIGNMENT CHECK', 'TEST EXECUTION', 'AGGREGATE VERDICT'],
    }

    missing = []
    for section in required_sections[phase]:
        if section not in agent_output:
            missing.append(section)

    if missing:
        return ValidationResult(
            valid=False,
            error=f"Missing required evaluation sections: {missing}",
            action="retry_with_emphasis"
        )

    # Extract and store evaluation content for handoff enrichment
    evaluation_data = extract_evaluation_sections(agent_output, phase)
    return ValidationResult(valid=True, evaluation_data=evaluation_data)
```

---

## Implementation Phases

### Phase 1: Foundation (High Impact, Lower Complexity)
1. **Forced evaluation in Coding Agent** - Highest frequency, most vulnerable
2. **Enhanced progress notes structure** - Captures evaluation artifacts
3. **Basic metrics tracking** - Regression rate, session velocity

### Phase 2: Initialization Quality (High Impact, Medium Complexity)
4. **Forced evaluation in Initializer Agent** - Spec traceability
5. **Best-of-N feature list sampling** - Reduce foundation variance
6. **Coverage scoring** - Automated evaluation criteria

### Phase 3: Architectural Stability (Medium Impact, Higher Complexity)
7. **Architecture Lock Phase** - New agent phase
8. **Decision Record Protocol** - Capture rationale
9. **Constraint validation in Coding Agent** - Honor locked decisions

### Phase 4: Validation Quality (Medium Impact, Medium Complexity)
10. **Forced evaluation in Validator Agent** - Evidence-based verdicts
11. **Validation hook** - Verify evaluations occurred
12. **Drift detection dashboard** - Visibility into metrics

---

## Success Criteria

| Metric | Current (Estimated) | Target |
|--------|---------------------|--------|
| Instruction execution rate | ~50% (passive) | >85% (forced) |
| Regression catch rate | Unknown | Track and improve |
| Validator rejection cycles | Unknown | Decreasing trend |
| Handoff context preserved | Minimal | Explicit evaluation artifacts |
| Architecture drift | Untracked | Zero deviations from locked invariants |

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Verbose output from forced evaluation | Accept verbosity for reliability; can summarize in UI |
| Increased token usage | Offset by reduced rework from drift |
| Agent gaming the evaluation | Validation hook checks for substantive content |
| Over-constraining creativity | Only lock true invariants; preserve variable space |
| Complexity of multi-sample generation | Start with feature list only; expand if proven |

---

## References

- [Drift Musings Reddit Writeup](internal) - Lossy Handoff Divergence, Stochastic Cascade Drift
- [How to Make Claude Code Skills Activate Reliably](https://scottspence.com/posts/how-to-make-claude-code-skills-activate-reliably) - Forced evaluation pattern
- [Svelte Claude Skills Hook](https://github.com/spences10/svelte-claude-skills/blob/main/.claude/hooks/skill-forced-eval-hook.sh) - Implementation reference

---

## Appendix: File Changes Summary

| File | Changes |
|------|---------|
| `prompts/coding.md` | Add forced evaluation sequence |
| `prompts/initializer.md` | Add forced evaluation sequence |
| `prompts/validator.md` | Add forced evaluation sequence |
| `prompts/architect.md` | NEW - Architecture Lock agent |
| `agent.py` | Add architecture lock phase, sampling logic |
| `progress.py` | Enhanced progress notes, metrics tracking |
| `security.py` | Evaluation validation hook |
| `config.py` | Sampling and metrics configuration |
