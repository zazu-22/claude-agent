# Drift Mitigation Feature Sprint - GitHub Issues Plan

This document outlines the GitHub issues required to implement the drift mitigation design from `drift-mitigation-design.md`.

---

## Labels Setup

### Priority Labels
| Label | Color | Description |
|-------|-------|-------------|
| `priority:critical` | `#B60205` | Must be completed for MVP |
| `priority:high` | `#D93F0B` | Important for feature completeness |
| `priority:medium` | `#FBCA04` | Nice to have, can be deferred |
| `priority:low` | `#0E8A16` | Future enhancement |

### Type Labels
| Label | Color | Description |
|-------|-------|-------------|
| `type:feature` | `#1D76DB` | New feature implementation |
| `type:enhancement` | `#5319E7` | Enhancement to existing functionality |
| `type:documentation` | `#0075CA` | Documentation updates |
| `type:refactor` | `#D4C5F9` | Code refactoring |
| `type:testing` | `#BFD4F2` | Test additions or improvements |

### Component Labels
| Label | Color | Description |
|-------|-------|-------------|
| `component:prompts` | `#C2E0C6` | Prompt template changes |
| `component:agent` | `#E99695` | Core agent.py changes |
| `component:security` | `#F9D0C4` | Security module changes |
| `component:progress` | `#FEF2C0` | Progress tracking changes |
| `component:config` | `#D4C5F9` | Configuration changes |

### Phase Labels
| Label | Color | Description |
|-------|-------|-------------|
| `phase:1-foundation` | `#006B75` | Phase 1 - Foundation |
| `phase:2-init-quality` | `#0E8A16` | Phase 2 - Initialization Quality |
| `phase:3-architecture` | `#1D76DB` | Phase 3 - Architectural Stability |
| `phase:4-validation` | `#5319E7` | Phase 4 - Validation Quality |

### Status Labels
| Label | Color | Description |
|-------|-------|-------------|
| `status:blocked` | `#B60205` | Blocked by dependency |
| `status:ready` | `#0E8A16` | Ready for implementation |
| `status:in-review` | `#FBCA04` | In code review |

---

## Quality Standards

### Test Coverage Requirements
All new modules must achieve **≥80% test coverage**. This applies to:
- New Python modules (metrics.py, evaluation.py, decisions.py)
- Modified core modules (progress.py, security.py, agent.py)
- Integration tests for new agent phases

### Definition of Done
- Unit tests pass locally and in CI
- Test coverage meets ≥80% threshold
- Code follows project style guidelines (see AGENTS.md)

---

## Epic Issues

### Epic 1: Forced Evaluation Checkpoints
**Description:** Implement mandatory evaluation sequences with explicit output requirements across all agent types to prevent passive instruction decay.

**Labels:** `type:feature`, `priority:critical`

---

### Epic 2: Architecture Lock System
**Description:** Implement architecture locking phase and decision record protocol to prevent stochastic cascade drift.

**Labels:** `type:feature`, `priority:high`

---

### Epic 3: Handoff Enrichment & Metrics
**Description:** Enhance handoff artifacts and implement drift detection metrics to address lossy handoff divergence.

**Labels:** `type:feature`, `priority:high`

---

### Epic 4: Best-of-N Sampling
**Description:** Implement multi-sample generation with evaluation criteria for feature list generation.

**Labels:** `type:feature`, `priority:medium`

---

## Phase 1: Foundation Issues

### Issue 1.1: Coding Agent Forced Evaluation Sequence

**Title:** `[Phase 1] Implement forced evaluation sequence in Coding Agent prompt`

**Labels:** `phase:1-foundation`, `priority:critical`, `type:feature`, `component:prompts`

**Authorization Context:**
- References: drift-mitigation-design.md Section 1.1
- Approved in design review
- No external dependencies or API changes

**Description:**
Transform the passive instructions in `prompts/coding.md` into mandatory evaluation sequences with explicit output requirements.

**Implementation Steps:**
1. [ ] Read current `prompts/coding.md` to understand existing structure
2. [ ] Add "MANDATORY SEQUENCE BEFORE IMPLEMENTATION" section with:
   - Step 1: Context Verification (explicit output required)
   - Step 2: Regression Verification (explicit output required)
   - Step 3: Implementation Plan (explicit output required)
   - Step 4: Execute gate
3. [ ] Add checkbox format for each verification item
4. [ ] Add "CRITICAL" warning about skipping steps
5. [ ] Update prompt variables as needed (e.g., `{{last_passed_feature}}`)
6. [ ] Test prompt with sample run

**Validation:**
- [ ] Prompt compiles without syntax errors
- [ ] Agent output includes all evaluation sections
- [ ] Evidence quotes are present in output

**Acceptance Criteria:**
- Coding agent prompt includes mandatory 4-step evaluation sequence
- Each step requires explicit quoted evidence in output
- CRITICAL warning about step skipping is present
- Prompt template variables are documented

**Dependencies:** None

**Estimated Complexity:** Medium

**Files to Modify:**
- `src/claude_agent/prompts/coding.md`

---

### Issue 1.2: Enhanced Progress Notes Structure

**Title:** `[Phase 1] Implement enhanced progress notes structure in progress.py`

**Labels:** `phase:1-foundation`, `priority:critical`, `type:feature`, `component:progress`

**Authorization Context:**
- References: drift-mitigation-design.md Section 5.1
- Backwards compatible - extends existing format
- No breaking changes to file format

**Description:**
Update `progress.py` to generate and parse enhanced progress notes that capture evaluation artifacts from forced evaluation.

**Implementation Steps:**
1. [ ] Read current `progress.py` to understand existing functions
2. [ ] Define `SessionProgress` dataclass with new fields:
   - `context_verification`: dict
   - `regression_results`: list
   - `implementation_plan`: dict
   - `assumptions`: list
   - `handoff_notes`: dict
3. [ ] Update `write_progress_notes()` to include new sections
4. [ ] Update `read_progress_notes()` to parse new sections
5. [ ] Add `format_session_progress()` function for markdown output
6. [ ] Maintain backwards compatibility with existing progress files
7. [ ] Add unit tests for new functions

**Validation:**
- [ ] Existing progress files can still be read
- [ ] New progress files include all enhanced sections
- [ ] Round-trip test: write then read produces identical data

**Acceptance Criteria:**
- SessionProgress dataclass captures all evaluation artifacts
- Progress notes include Context, Regression, Plan, Assumptions, Handoff sections
- Backwards compatible with existing progress files
- Unit tests for new functionality

**Dependencies:** None

**Estimated Complexity:** Medium

**Files to Modify:**
- `src/claude_agent/progress.py`
- `tests/test_progress.py` (create if not exists)

---

### Issue 1.3: Basic Metrics Tracking

**Title:** `[Phase 1] Implement basic drift detection metrics tracking`

**Labels:** `phase:1-foundation`, `priority:high`, `type:feature`, `component:progress`

**Authorization Context:**
- References: drift-mitigation-design.md Section 6
- New functionality, no breaking changes
- Metrics stored in project directory

**Description:**
Add metrics tracking to measure regression rate, session velocity, and other drift indicators.

**Implementation Steps:**
1. [ ] Create `metrics.py` module with:
   - `DriftMetrics` dataclass
   - `SessionMetrics` dataclass
   - `ValidationMetrics` dataclass
2. [ ] Implement `record_session_metrics()` function
3. [ ] Implement `record_validation_metrics()` function
4. [ ] Implement `load_metrics()` and `save_metrics()` (JSON format)
5. [ ] Implement `calculate_drift_indicators()` for trend analysis
6. [ ] Add metrics file path to config (`drift-metrics.json`)
7. [ ] Add unit tests

**Validation:**
- [ ] Metrics file is created and updated correctly
- [ ] Metrics can be loaded from existing file
- [ ] Drift indicators calculate correctly from sample data

**Acceptance Criteria:**
- Metrics module tracks: regression rate, session velocity, assumption mismatches
- JSON storage format matches design spec
- Drift indicators function returns meaningful values
- Unit tests cover core functionality

**Dependencies:** None

**Estimated Complexity:** Medium

**Files to Create:**
- `src/claude_agent/metrics.py`
- `tests/test_metrics.py`

**Files to Modify:**
- `src/claude_agent/config.py` (add metrics_file config)

---

### Issue 1.4: Integrate Metrics with Agent Session

**Title:** `[Phase 1] Integrate metrics tracking into agent session flow`

**Labels:** `phase:1-foundation`, `priority:high`, `type:enhancement`, `component:agent`

**Authorization Context:**
- References: drift-mitigation-design.md Section 6
- Depends on Issue 1.3
- Modifies agent.py session flow

**Description:**
Integrate metrics tracking into the agent session lifecycle to automatically record session data.

**Implementation Steps:**
1. [ ] Import metrics module in `agent.py`
2. [ ] Add metrics recording at session start (features attempted)
3. [ ] Add metrics recording at session end (features completed, regressions)
4. [ ] Parse agent output for evaluation sections present
5. [ ] Record validation attempts when validator runs
6. [ ] Add `--metrics` CLI flag to display drift indicators
7. [ ] Update `status` command to show metrics summary

**Validation:**
- [ ] Metrics file updates after each session
- [ ] `claude-agent status` shows metrics summary
- [ ] Metrics persist across sessions

**Acceptance Criteria:**
- Session metrics automatically recorded in agent.py
- Validation metrics recorded during validator runs
- CLI status command displays drift indicators
- Metrics persist in drift-metrics.json

**Dependencies:** Issue 1.3

**Estimated Complexity:** Medium

**Files to Modify:**
- `src/claude_agent/agent.py`
- `src/claude_agent/cli.py`

---

## Phase 2: Initialization Quality Issues

### Issue 2.1: Initializer Agent Forced Evaluation Sequence

**Title:** `[Phase 2] Implement forced evaluation sequence in Initializer Agent prompt`

**Labels:** `phase:2-init-quality`, `priority:critical`, `type:feature`, `component:prompts`

**Authorization Context:**
- References: drift-mitigation-design.md Section 1.2
- Similar pattern to Issue 1.1
- No external dependencies

**Description:**
Add mandatory evaluation sequence to initializer prompt for spec traceability.

**Implementation Steps:**
1. [ ] Read current `prompts/initializer.md`
2. [ ] Add "MANDATORY FEATURE GENERATION SEQUENCE" section with:
   - Step 1: Spec Decomposition (explicit output required)
   - Step 2: Feature Mapping with traceability (explicit output required)
   - Step 3: Coverage Check (explicit output required)
   - Step 4: Generate gate
3. [ ] Require spec quote for each feature
4. [ ] Add coverage count verification
5. [ ] Add CRITICAL warning about untraceable features
6. [ ] Test with sample spec

**Validation:**
- [ ] Agent output includes spec decomposition
- [ ] Each feature has spec traceability quote
- [ ] Coverage check section present with counts

**Acceptance Criteria:**
- Initializer prompt includes 4-step mandatory sequence
- Each feature must trace to specific spec text
- Coverage check verifies all spec requirements covered
- CRITICAL warning about drift risks present

**Dependencies:** None (can run parallel to Phase 1)

**Estimated Complexity:** Medium

**Files to Modify:**
- `src/claude_agent/prompts/initializer.md`

---

### Issue 2.2: Feature List Evaluation Criteria

**Title:** `[Phase 2] Implement feature list evaluation scoring functions`

**Labels:** `phase:2-init-quality`, `priority:high`, `type:feature`, `component:agent`

**Authorization Context:**
- References: drift-mitigation-design.md Section 4.2
- New module for evaluation logic
- Supports Best-of-N sampling

**Description:**
Implement evaluation criteria functions to score generated feature lists.

**Implementation Steps:**
1. [ ] Create `evaluation.py` module
2. [ ] Implement `calculate_spec_coverage(features, spec)`:
   - Parse spec for requirements
   - Match features to requirements
   - Return coverage percentage
3. [ ] Implement `calculate_testability_score(features)`:
   - Check for concrete test steps
   - Check for verifiable outcomes
   - Return 0-1 score
4. [ ] Implement `calculate_granularity_score(features)`:
   - Check feature complexity indicators
   - Penalize too large or too small
   - Return 0-1 score
5. [ ] Implement `calculate_independence_score(features)`:
   - Check for feature dependencies
   - Return 0-1 score
6. [ ] Implement `evaluate_feature_list()` combining all scores
7. [ ] Add configurable weights to config.py
8. [ ] Add unit tests with sample feature lists

**Validation:**
- [ ] Sample feature list scores correctly
- [ ] Edge cases handled (empty list, single feature)
- [ ] Scores are between 0 and 1

**Acceptance Criteria:**
- Four evaluation functions implemented
- Weighted aggregate score function
- Configurable weights in config
- Unit tests with >80% coverage

**Dependencies:** None

**Estimated Complexity:** High

**Files to Create:**
- `src/claude_agent/evaluation.py`
- `tests/test_evaluation.py`

**Files to Modify:**
- `src/claude_agent/config.py`

---

### Issue 2.3: Best-of-N Feature List Sampling

**Title:** `[Phase 2] Implement Best-of-N sampling for feature list generation`

**Labels:** `phase:2-init-quality`, `priority:medium`, `type:feature`, `component:agent`

**Authorization Context:**
- References: drift-mitigation-design.md Section 4.1
- Requires evaluation module (Issue 2.2)
- Increases API calls (cost consideration)

**Cost Analysis:**
| Samples (N) | API Cost Multiplier | Estimated Cost Increase |
|-------------|---------------------|-------------------------|
| 1 (baseline) | 1x | $0 (current behavior) |
| 3 (default) | ~3x | +$0.15-0.45 per init* |
| 5 (high quality) | ~5x | +$0.30-0.75 per init* |

*Estimated based on Claude Sonnet pricing (~$3/1M input, $15/1M output) with typical spec size of 2-5K tokens.
Actual costs vary based on spec complexity and feature count.

**Recommendations:**
- Default to N=3 as balance between quality and cost
- Add `--no-sampling` flag for cost-sensitive projects
- Log candidate scores to help users tune N value
- Consider caching spec parsing to reduce redundant token usage

**Description:**
Implement multi-sample generation for feature lists with automatic selection of best candidate.

**Implementation Steps:**
1. [ ] Add `sampling` config section:
   - `feature_list_samples`: int (default 3)
   - `score_threshold`: float (default 0.7)
2. [ ] Implement `generate_feature_list_with_sampling()` in agent.py:
   - Generate N candidates
   - Score each with evaluation.py
   - Select best above threshold
   - Raise `NeedsSpecRefinement` if none qualify
3. [ ] Add `--no-sampling` CLI flag for single-shot mode
4. [ ] Add `--samples N` CLI flag to override config
5. [ ] Log all candidate scores for debugging
6. [ ] Add integration test

**Validation:**
- [ ] Multiple candidates generated
- [ ] Best candidate selected correctly
- [ ] Threshold enforcement works
- [ ] Single-shot mode works when disabled

**Acceptance Criteria:**
- Config supports sampling configuration
- N candidates generated and scored
- Best candidate selected or error raised
- CLI flags for control
- Sampling can be disabled

**Dependencies:** Issue 2.2

**Estimated Complexity:** High

**Files to Modify:**
- `src/claude_agent/agent.py`
- `src/claude_agent/config.py`
- `src/claude_agent/cli.py`

---

## Phase 3: Architectural Stability Issues

### Issue 3.1: Architecture Lock Agent Prompt

**Title:** `[Phase 3] Create Architecture Lock Agent prompt template`

**Labels:** `phase:3-architecture`, `priority:high`, `type:feature`, `component:prompts`

**Authorization Context:**
- References: drift-mitigation-design.md Section 2.1
- New prompt file
- Defines new agent phase

**Description:**
Create the prompt template for the new Architecture Lock Agent that runs between Initializer and first Coding session.

**Implementation Steps:**
1. [ ] Create `prompts/architect.md` with:
   - Purpose statement
   - Input requirements (spec, feature list)
   - Output requirements (contracts.yaml, schemas.yaml, decisions.yaml)
2. [ ] Define evaluation sequence for architect:
   - Step 1: Identify API boundaries
   - Step 2: Identify data models
   - Step 3: Identify architectural decisions
   - Step 4: Generate lock files
3. [ ] Add YAML format specifications for each output file
4. [ ] Add constraints for what should/shouldn't be locked
5. [ ] Add handoff instructions for coding agent

**Validation:**
- [ ] Prompt produces valid YAML outputs
- [ ] All three lock files generated
- [ ] Decisions include rationale

**Acceptance Criteria:**
- Architect prompt defines clear outputs
- Evaluation sequence ensures thorough analysis
- Lock file formats match design spec
- Handoff to coding agent documented

**Dependencies:** None

**Estimated Complexity:** Medium

**Files to Create:**
- `src/claude_agent/prompts/architect.md`

---

### Issue 3.2: Architecture Lock Phase in Agent Flow

**Title:** `[Phase 3] Implement architecture lock phase in agent session flow`

**Labels:** `phase:3-architecture`, `priority:high`, `type:feature`, `component:agent`

**Authorization Context:**
- References: drift-mitigation-design.md Section 2.1
- Requires architect prompt (Issue 3.1)
- Modifies session flow

**Description:**
Add new Architecture Lock phase to agent session flow that runs once after initialization.

**Implementation Steps:**
1. [ ] Add `architecture_locked` flag to project state
2. [ ] Add `architecture/` directory creation
3. [ ] Implement `run_architect_agent()` function:
   - Load architect prompt
   - Run agent session
   - Parse and save YAML outputs
   - Set architecture_locked flag
4. [ ] Update session flow in `run_agent()`:
   - Check for feature_list.json
   - Check for architecture_locked
   - Run architect if features exist but not locked
5. [ ] Add `--skip-architecture` flag for backwards compatibility
6. [ ] Add integration test

**Validation:**
- [ ] Architect runs after initializer
- [ ] Architecture files created in architecture/
- [ ] Subsequent sessions skip architect phase
- [ ] Skip flag works correctly

**Acceptance Criteria:**
- Architecture lock phase runs once after initialization
- Three YAML files created in architecture/
- Phase skipped on subsequent sessions
- Backwards compatible with existing projects

**Dependencies:** Issue 3.1

**Estimated Complexity:** High

**Files to Modify:**
- `src/claude_agent/agent.py`
- `src/claude_agent/cli.py`

---

### Issue 3.3: Decision Record Protocol

**Title:** `[Phase 3] Implement decision record protocol for coding sessions`

**Labels:** `phase:3-architecture`, `priority:medium`, `type:feature`, `component:progress`

**Authorization Context:**
- References: drift-mitigation-design.md Section 3
- Append-only decision log
- Required by coding agent

**Description:**
Implement decision record storage and retrieval for tracking architectural decisions made during coding sessions.

**Implementation Steps:**
1. [ ] Create `DecisionRecord` dataclass:
   - id, timestamp, session, topic
   - choice, alternatives_considered
   - rationale, constraints_created
   - affects_features
2. [ ] Implement `append_decision()` function
3. [ ] Implement `load_decisions()` function
4. [ ] Implement `get_relevant_decisions(feature_index)` function
5. [ ] Add YAML storage format
6. [ ] Add decision record instructions to coding prompt
7. [ ] Add unit tests

**Validation:**
- [ ] Decisions append correctly
- [ ] Decisions load from file
- [ ] Feature-relevant decisions filter correctly

**Acceptance Criteria:**
- DecisionRecord dataclass matches design spec
- Append-only log in architecture/decisions.yaml
- Coding prompt includes decision record instructions
- Functions to query decisions by feature

**Dependencies:** Issue 3.1

**Estimated Complexity:** Medium

**Files to Create:**
- `src/claude_agent/decisions.py`
- `tests/test_decisions.py`

**Files to Modify:**
- `src/claude_agent/prompts/coding.md`

---

### Issue 3.4: Architecture Constraint Validation in Coding Agent

**Title:** `[Phase 3] Add architecture constraint validation to coding agent prompt`

**Labels:** `phase:3-architecture`, `priority:medium`, `type:enhancement`, `component:prompts`

**Authorization Context:**
- References: drift-mitigation-design.md Section 2.1
- Extends coding prompt
- Depends on architecture files

**Description:**
Update coding agent prompt to require verification against locked architecture before implementation.

**Implementation Steps:**
1. [ ] Add architecture verification to Step 1 of coding evaluation:
   - Read contracts.yaml and quote relevant section
   - Read schemas.yaml and quote relevant section
   - Read decisions.yaml and quote relevant constraints
2. [ ] Add "Architecture Deviation Check" to Step 3:
   - State if implementation requires changing locked invariant
   - If yes, document why and STOP
3. [ ] Add conditional logic for projects without architecture/
4. [ ] Test with sample project

**Validation:**
- [ ] Agent quotes architecture files in output
- [ ] Deviation detection works
- [ ] Graceful fallback when architecture/ missing

**Acceptance Criteria:**
- Coding prompt requires architecture verification
- Explicit quotes from lock files in output
- Deviation handling documented
- Backwards compatible with non-locked projects

**Dependencies:** Issue 3.2

**Estimated Complexity:** Low

**Files to Modify:**
- `src/claude_agent/prompts/coding.md`

---

## Phase 4: Validation Quality Issues

### Issue 4.1: Validator Agent Forced Evaluation Sequence

**Title:** `[Phase 4] Implement forced evaluation sequence in Validator Agent prompt`

**Labels:** `phase:4-validation`, `priority:high`, `type:feature`, `component:prompts`

**Authorization Context:**
- References: drift-mitigation-design.md Section 1.3
- Similar pattern to Issues 1.1 and 2.1
- Improves verdict reliability

**Description:**
Add mandatory evaluation sequence to validator prompt for evidence-based verdicts.

**Implementation Steps:**
1. [ ] Read current `prompts/validator.md`
2. [ ] Add "MANDATORY VALIDATION SEQUENCE" section with:
   - Step 1: Spec Alignment Check (explicit output required)
   - Step 2: Test Execution with evidence (explicit output required)
   - Step 3: Aggregate Verdict with reasoning (explicit output required)
3. [ ] Require screenshot evidence reference for each test
4. [ ] Require specific failure reasons for REJECTED verdict
5. [ ] Add CRITICAL warning about verdicts without evidence
6. [ ] Test with sample validation run

**Validation:**
- [ ] Agent output includes spec alignment section
- [ ] Test execution includes evidence for each feature
- [ ] Aggregate verdict includes reasoning

**Acceptance Criteria:**
- Validator prompt includes 3-step mandatory sequence
- Each tested feature has explicit pass/fail evidence
- Verdicts require reasoning
- CRITICAL warning about untrusted verdicts

**Dependencies:** None (can run parallel to Phase 3)

**Estimated Complexity:** Medium

**Files to Modify:**
- `src/claude_agent/prompts/validator.md`

---

### Issue 4.2: Evaluation Validation Hook

**Title:** `[Phase 4] Implement evaluation validation hook in security.py`

**Labels:** `phase:4-validation`, `priority:medium`, `type:feature`, `component:security`

**Authorization Context:**
- References: drift-mitigation-design.md Section 7
- Enforces evaluation compliance
- Can trigger retry

**Description:**
Implement a validation hook that verifies agent output contains required evaluation sections.

**Implementation Steps:**
1. [ ] Define `ValidationResult` dataclass:
   - valid: bool
   - error: str (optional)
   - action: str (retry_with_emphasis, continue, fail)
   - evaluation_data: dict (optional)
2. [ ] Implement `evaluation_validation_hook()`:
   - Define required sections per phase
   - Parse agent output for section presence
   - Return ValidationResult
3. [ ] Implement `extract_evaluation_sections()`:
   - Parse markdown output
   - Extract structured data from evaluation sections
4. [ ] Integrate hook into agent session flow
5. [ ] Add retry logic with emphasis on missing sections
6. [ ] Add unit tests

**Validation:**
- [ ] Hook detects missing sections
- [ ] Retry with emphasis works
- [ ] Extraction produces valid data
- [ ] Hook doesn't block valid output

**Acceptance Criteria:**
- Hook validates presence of required sections
- Missing sections trigger retry with emphasis
- Evaluation data extracted for handoff enrichment
- All three agent phases supported

**Dependencies:** Issue 1.1, 2.1, 4.1 (prompt changes)

**Estimated Complexity:** High

**Files to Modify:**
- `src/claude_agent/security.py`
- `src/claude_agent/agent.py`
- `tests/test_security.py`

---

### Issue 4.3: Drift Detection Dashboard CLI

**Title:** `[Phase 4] Implement drift detection dashboard in CLI`

**Labels:** `phase:4-validation`, `priority:low`, `type:feature`, `component:agent`

**Authorization Context:**
- References: drift-mitigation-design.md Section 6
- Depends on metrics tracking (Issue 1.3)
- CLI-only output

**Description:**
Add a dashboard view to the CLI that displays drift detection metrics and trends.

**Implementation Steps:**
1. [ ] Add `claude-agent drift` command
2. [ ] Implement dashboard display:
   - Session count and date range
   - Regression rate trend (last 5 sessions)
   - Session velocity trend
   - Validator rejection rate
   - Architecture deviation count
3. [ ] Add color coding for concerning trends (red/yellow/green)
4. [ ] Add `--json` flag for machine-readable output
5. [ ] Add sparkline graphs for trends (optional)
6. [ ] Add documentation

**Validation:**
- [ ] Dashboard displays with sample data
- [ ] Trends calculate correctly
- [ ] JSON output is valid
- [ ] Empty metrics handled gracefully

**Acceptance Criteria:**
- `claude-agent drift` command shows metrics dashboard
- Trends displayed for key indicators
- Color coding for health status
- JSON output supported

**Dependencies:** Issue 1.3, 1.4

**Estimated Complexity:** Medium

**Files to Modify:**
- `src/claude_agent/cli.py`
- `src/claude_agent/metrics.py`

---

## Documentation Issues

### Issue D.1: Update AGENTS.md with Drift Mitigation

**Title:** `[Docs] Update AGENTS.md with drift mitigation architecture`

**Labels:** `type:documentation`, `priority:medium`

**Description:**
Update the main AGENTS.md file with documentation of the drift mitigation system.

**Implementation Steps:**
1. [ ] Add "Drift Mitigation" section
2. [ ] Document four-layer architecture
3. [ ] Document forced evaluation sequences
4. [ ] Document architecture lock phase
5. [ ] Document metrics and dashboard
6. [ ] Add troubleshooting for drift issues

**Acceptance Criteria:**
- AGENTS.md includes drift mitigation documentation
- All new components documented
- Troubleshooting section added

**Dependencies:** All Phase 1-4 issues

---

### Issue D.2: Create Migration Guide

**Title:** `[Docs] Create migration guide for existing projects`

**Labels:** `type:documentation`, `priority:high`

**Description:**
Create documentation for migrating existing claude-agent projects to the new drift mitigation system.

**Implementation Steps:**
1. [ ] Document backwards compatibility
2. [ ] Document architecture lock for existing projects
3. [ ] Document metrics initialization
4. [ ] Provide migration commands

**Acceptance Criteria:**
- Clear migration path documented
- No breaking changes for existing projects
- Step-by-step migration guide

**Dependencies:** All Phase 1-4 issues

---

## Dependency Graph

```
Phase 1 (Foundation)
├── Issue 1.1: Coding Agent Forced Eval ──────────────────────┐
├── Issue 1.2: Enhanced Progress Notes                        │
├── Issue 1.3: Basic Metrics Tracking                         │
└── Issue 1.4: Integrate Metrics ─────────────────────────────┼── Issue 4.2 (Hook)
         └── depends on 1.3                                   │
                                                              │
Phase 2 (Init Quality)                                        │
├── Issue 2.1: Initializer Agent Forced Eval ─────────────────┤
├── Issue 2.2: Feature List Evaluation                        │
└── Issue 2.3: Best-of-N Sampling                             │
         └── depends on 2.2                                   │
                                                              │
Phase 3 (Architecture)                                        │
├── Issue 3.1: Architect Prompt                               │
├── Issue 3.2: Architecture Lock Phase                        │
│        └── depends on 3.1                                   │
├── Issue 3.3: Decision Record Protocol                       │
│        └── depends on 3.1                                   │
└── Issue 3.4: Constraint Validation                          │
         └── depends on 3.2                                   │
                                                              │
Phase 4 (Validation)                                          │
├── Issue 4.1: Validator Agent Forced Eval ───────────────────┘
├── Issue 4.2: Evaluation Validation Hook
│        └── depends on 1.1, 2.1, 4.1
└── Issue 4.3: Drift Dashboard
         └── depends on 1.3, 1.4

Documentation
├── Issue D.1: Update AGENTS.md ──── depends on all phases
└── Issue D.2: Migration Guide ──── depends on all phases
```

---

## Sprint Planning Recommendation

### Sprint 1 (Foundation)
- Issue 1.1: Coding Agent Forced Eval
- Issue 1.2: Enhanced Progress Notes
- Issue 1.3: Basic Metrics Tracking
- Issue 2.1: Initializer Agent Forced Eval (can parallel)

### Sprint 2 (Integration & Init Quality)
- Issue 1.4: Integrate Metrics
- Issue 2.2: Feature List Evaluation
- Issue 4.1: Validator Agent Forced Eval (can parallel)

### Sprint 3 (Architecture)
- Issue 3.1: Architect Prompt
- Issue 3.2: Architecture Lock Phase
- Issue 3.3: Decision Record Protocol
- Issue 2.3: Best-of-N Sampling

### Sprint 4 (Validation & Polish)
- Issue 3.4: Constraint Validation
- Issue 4.2: Evaluation Validation Hook
- Issue 4.3: Drift Dashboard
- Issue D.1: Update AGENTS.md
- Issue D.2: Migration Guide

---

## Acceptance Testing

Before marking the feature complete, verify:

1. [ ] New project uses forced evaluation in all agents
2. [ ] Architecture lock phase runs after initialization
3. [ ] Metrics tracked across sessions
4. [ ] Drift dashboard shows meaningful data
5. [ ] Existing projects continue to work
6. [ ] Documentation is complete and accurate
