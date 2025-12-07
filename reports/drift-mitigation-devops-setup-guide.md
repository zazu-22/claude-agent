# DevOps Setup Guide: Drift Mitigation Feature Sprint

This document provides step-by-step instructions for the DevOps team to set up GitHub issues, labels, milestones, and project board for the Drift Mitigation feature sprint.

---

## Overview

**Feature:** Drift Mitigation System for Claude Agent
**Reference:** `reports/drift-mitigation-design.md`
**Issues Plan:** `reports/drift-mitigation-github-issues-plan.md`
**Total Issues:** 17 (13 implementation + 2 epic + 2 documentation)
**Estimated Sprints:** 4

---

## Prerequisites

1. GitHub repository access with admin permissions
2. GitHub CLI (`gh`) installed and authenticated
3. Access to create labels, milestones, and projects

---

## Step 1: Create Labels

Create the following labels in the repository. Use the GitHub CLI or web interface.

### Using GitHub CLI

```bash
# Navigate to the repository
cd /path/to/claude-agent

# Priority Labels
gh label create "priority:critical" --color "B60205" --description "Must be completed for MVP"
gh label create "priority:high" --color "D93F0B" --description "Important for feature completeness"
gh label create "priority:medium" --color "FBCA04" --description "Nice to have, can be deferred"
gh label create "priority:low" --color "0E8A16" --description "Future enhancement"

# Type Labels
gh label create "type:feature" --color "1D76DB" --description "New feature implementation"
gh label create "type:enhancement" --color "5319E7" --description "Enhancement to existing functionality"
gh label create "type:documentation" --color "0075CA" --description "Documentation updates"
gh label create "type:refactor" --color "D4C5F9" --description "Code refactoring"
gh label create "type:testing" --color "BFD4F2" --description "Test additions or improvements"

# Component Labels
gh label create "component:prompts" --color "C2E0C6" --description "Prompt template changes"
gh label create "component:agent" --color "E99695" --description "Core agent.py changes"
gh label create "component:security" --color "F9D0C4" --description "Security module changes"
gh label create "component:progress" --color "FEF2C0" --description "Progress tracking changes"
gh label create "component:config" --color "D4C5F9" --description "Configuration changes"

# Phase Labels
gh label create "phase:1-foundation" --color "006B75" --description "Phase 1 - Foundation"
gh label create "phase:2-init-quality" --color "0E8A16" --description "Phase 2 - Initialization Quality"
gh label create "phase:3-architecture" --color "1D76DB" --description "Phase 3 - Architectural Stability"
gh label create "phase:4-validation" --color "5319E7" --description "Phase 4 - Validation Quality"

# Status Labels
gh label create "status:blocked" --color "B60205" --description "Blocked by dependency"
gh label create "status:ready" --color "0E8A16" --description "Ready for implementation"
gh label create "status:in-review" --color "FBCA04" --description "In code review"

# Epic Label
gh label create "epic" --color "3E4B9E" --description "Epic issue tracking multiple sub-issues"
```

### Verification

```bash
gh label list
```

Expected output: 21 labels created

---

## Step 2: Create Milestones

Create milestones for each sprint.

```bash
# Sprint 1: Foundation
gh api repos/{owner}/{repo}/milestones -f title="Sprint 1: Foundation" \
  -f description="Forced evaluation in Coding Agent, Enhanced Progress Notes, Basic Metrics, Initializer Forced Eval" \
  -f due_on="$(date -d '+2 weeks' -Iseconds)"

# Sprint 2: Integration & Init Quality
gh api repos/{owner}/{repo}/milestones -f title="Sprint 2: Integration & Init Quality" \
  -f description="Metrics Integration, Feature List Evaluation, Validator Forced Eval"

# Sprint 3: Architecture
gh api repos/{owner}/{repo}/milestones -f title="Sprint 3: Architecture" \
  -f description="Architect Prompt, Architecture Lock Phase, Decision Records, Best-of-N Sampling"

# Sprint 4: Validation & Polish
gh api repos/{owner}/{repo}/milestones -f title="Sprint 4: Validation & Polish" \
  -f description="Constraint Validation, Evaluation Hook, Drift Dashboard, Documentation"
```

---

## Step 3: Create Epic Issues

Create parent epic issues to track related work.

### Epic 1: Forced Evaluation Checkpoints

```bash
gh issue create \
  --title "Epic: Forced Evaluation Checkpoints" \
  --label "epic,type:feature,priority:critical" \
  --body "$(cat <<'EOF'
## Overview
Implement mandatory evaluation sequences with explicit output requirements across all agent types to prevent passive instruction decay.

## Related Issues
- [ ] #XX - [Phase 1] Coding Agent Forced Evaluation Sequence
- [ ] #XX - [Phase 2] Initializer Agent Forced Evaluation Sequence
- [ ] #XX - [Phase 4] Validator Agent Forced Evaluation Sequence
- [ ] #XX - [Phase 4] Evaluation Validation Hook

## Success Criteria
- All three agent types have forced evaluation sequences
- Validation hook enforces evaluation compliance
- Instruction execution rate increases from ~50% to >85%

## Reference
See `reports/drift-mitigation-design.md` Section 1
EOF
)"
```

### Epic 2: Architecture Lock System

```bash
gh issue create \
  --title "Epic: Architecture Lock System" \
  --label "epic,type:feature,priority:high" \
  --body "$(cat <<'EOF'
## Overview
Implement architecture locking phase and decision record protocol to prevent stochastic cascade drift.

## Related Issues
- [ ] #XX - [Phase 3] Architecture Lock Agent Prompt
- [ ] #XX - [Phase 3] Architecture Lock Phase in Agent Flow
- [ ] #XX - [Phase 3] Decision Record Protocol
- [ ] #XX - [Phase 3] Architecture Constraint Validation

## Success Criteria
- Architecture lock phase runs after initialization
- Decision records capture rationale for choices
- Coding agent validates against locked constraints
- Zero architecture deviations tracked

## Reference
See `reports/drift-mitigation-design.md` Sections 2-3
EOF
)"
```

---

## Step 4: Create Implementation Issues

Create all implementation issues. The following script creates all issues with proper labels and bodies.

### Phase 1 Issues

```bash
# Issue 1.1: Coding Agent Forced Evaluation Sequence
gh issue create \
  --title "[Phase 1] Implement forced evaluation sequence in Coding Agent prompt" \
  --label "phase:1-foundation,priority:critical,type:feature,component:prompts,status:ready" \
  --milestone "Sprint 1: Foundation" \
  --body "$(cat <<'EOF'
## Authorization Context
- References: drift-mitigation-design.md Section 1.1
- Approved in design review
- No external dependencies or API changes

## Description
Transform the passive instructions in `prompts/coding.md` into mandatory evaluation sequences with explicit output requirements.

## Implementation Steps
- [ ] Read current `prompts/coding.md` to understand existing structure
- [ ] Add "MANDATORY SEQUENCE BEFORE IMPLEMENTATION" section with:
  - Step 1: Context Verification (explicit output required)
  - Step 2: Regression Verification (explicit output required)
  - Step 3: Implementation Plan (explicit output required)
  - Step 4: Execute gate
- [ ] Add checkbox format for each verification item
- [ ] Add "CRITICAL" warning about skipping steps
- [ ] Update prompt variables as needed (e.g., `{{last_passed_feature}}`)
- [ ] Test prompt with sample run

## Validation
- [ ] Prompt compiles without syntax errors
- [ ] Agent output includes all evaluation sections
- [ ] Evidence quotes are present in output

## Acceptance Criteria
- [ ] Coding agent prompt includes mandatory 4-step evaluation sequence
- [ ] Each step requires explicit quoted evidence in output
- [ ] CRITICAL warning about step skipping is present
- [ ] Prompt template variables are documented

## Dependencies
None

## Files to Modify
- `src/claude_agent/prompts/coding.md`
EOF
)"

# Issue 1.2: Enhanced Progress Notes Structure
gh issue create \
  --title "[Phase 1] Implement enhanced progress notes structure in progress.py" \
  --label "phase:1-foundation,priority:critical,type:feature,component:progress,status:ready" \
  --milestone "Sprint 1: Foundation" \
  --body "$(cat <<'EOF'
## Authorization Context
- References: drift-mitigation-design.md Section 5.1
- Backwards compatible - extends existing format
- No breaking changes to file format

## Description
Update `progress.py` to generate and parse enhanced progress notes that capture evaluation artifacts from forced evaluation.

## Implementation Steps
- [ ] Read current `progress.py` to understand existing functions
- [ ] Define `SessionProgress` dataclass with new fields:
  - `context_verification`: dict
  - `regression_results`: list
  - `implementation_plan`: dict
  - `assumptions`: list
  - `handoff_notes`: dict
- [ ] Update `write_progress_notes()` to include new sections
- [ ] Update `read_progress_notes()` to parse new sections
- [ ] Add `format_session_progress()` function for markdown output
- [ ] Maintain backwards compatibility with existing progress files
- [ ] Add unit tests for new functions

## Validation
- [ ] Existing progress files can still be read
- [ ] New progress files include all enhanced sections
- [ ] Round-trip test: write then read produces identical data

## Acceptance Criteria
- [ ] SessionProgress dataclass captures all evaluation artifacts
- [ ] Progress notes include Context, Regression, Plan, Assumptions, Handoff sections
- [ ] Backwards compatible with existing progress files
- [ ] Unit tests for new functionality

## Dependencies
None

## Files to Modify
- `src/claude_agent/progress.py`
- `tests/test_progress.py` (create if not exists)
EOF
)"

# Issue 1.3: Basic Metrics Tracking
gh issue create \
  --title "[Phase 1] Implement basic drift detection metrics tracking" \
  --label "phase:1-foundation,priority:high,type:feature,component:progress,status:ready" \
  --milestone "Sprint 1: Foundation" \
  --body "$(cat <<'EOF'
## Authorization Context
- References: drift-mitigation-design.md Section 6
- New functionality, no breaking changes
- Metrics stored in project directory

## Description
Add metrics tracking to measure regression rate, session velocity, and other drift indicators.

## Implementation Steps
- [ ] Create `metrics.py` module with:
  - `DriftMetrics` dataclass
  - `SessionMetrics` dataclass
  - `ValidationMetrics` dataclass
- [ ] Implement `record_session_metrics()` function
- [ ] Implement `record_validation_metrics()` function
- [ ] Implement `load_metrics()` and `save_metrics()` (JSON format)
- [ ] Implement `calculate_drift_indicators()` for trend analysis
- [ ] Add metrics file path to config (`drift-metrics.json`)
- [ ] Add unit tests

## Validation
- [ ] Metrics file is created and updated correctly
- [ ] Metrics can be loaded from existing file
- [ ] Drift indicators calculate correctly from sample data

## Acceptance Criteria
- [ ] Metrics module tracks: regression rate, session velocity, assumption mismatches
- [ ] JSON storage format matches design spec
- [ ] Drift indicators function returns meaningful values
- [ ] Unit tests cover core functionality

## Dependencies
None

## Files to Create
- `src/claude_agent/metrics.py`
- `tests/test_metrics.py`

## Files to Modify
- `src/claude_agent/config.py` (add metrics_file config)
EOF
)"

# Issue 1.4: Integrate Metrics with Agent Session
gh issue create \
  --title "[Phase 1] Integrate metrics tracking into agent session flow" \
  --label "phase:1-foundation,priority:high,type:enhancement,component:agent,status:blocked" \
  --milestone "Sprint 1: Foundation" \
  --body "$(cat <<'EOF'
## Authorization Context
- References: drift-mitigation-design.md Section 6
- Depends on Issue 1.3
- Modifies agent.py session flow

## Description
Integrate metrics tracking into the agent session lifecycle to automatically record session data.

## Implementation Steps
- [ ] Import metrics module in `agent.py`
- [ ] Add metrics recording at session start (features attempted)
- [ ] Add metrics recording at session end (features completed, regressions)
- [ ] Parse agent output for evaluation sections present
- [ ] Record validation attempts when validator runs
- [ ] Add `--metrics` CLI flag to display drift indicators
- [ ] Update `status` command to show metrics summary

## Validation
- [ ] Metrics file updates after each session
- [ ] `claude-agent status` shows metrics summary
- [ ] Metrics persist across sessions

## Acceptance Criteria
- [ ] Session metrics automatically recorded in agent.py
- [ ] Validation metrics recorded during validator runs
- [ ] CLI status command displays drift indicators
- [ ] Metrics persist in drift-metrics.json

## Dependencies
- Issue 1.3: Basic Metrics Tracking

## Files to Modify
- `src/claude_agent/agent.py`
- `src/claude_agent/cli.py`
EOF
)"
```

### Phase 2 Issues

```bash
# Issue 2.1: Initializer Agent Forced Evaluation Sequence
gh issue create \
  --title "[Phase 2] Implement forced evaluation sequence in Initializer Agent prompt" \
  --label "phase:2-init-quality,priority:critical,type:feature,component:prompts,status:ready" \
  --milestone "Sprint 1: Foundation" \
  --body "$(cat <<'EOF'
## Authorization Context
- References: drift-mitigation-design.md Section 1.2
- Similar pattern to Issue 1.1
- No external dependencies

## Description
Add mandatory evaluation sequence to initializer prompt for spec traceability.

## Implementation Steps
- [ ] Read current `prompts/initializer.md`
- [ ] Add "MANDATORY FEATURE GENERATION SEQUENCE" section with:
  - Step 1: Spec Decomposition (explicit output required)
  - Step 2: Feature Mapping with traceability (explicit output required)
  - Step 3: Coverage Check (explicit output required)
  - Step 4: Generate gate
- [ ] Require spec quote for each feature
- [ ] Add coverage count verification
- [ ] Add CRITICAL warning about untraceable features
- [ ] Test with sample spec

## Validation
- [ ] Agent output includes spec decomposition
- [ ] Each feature has spec traceability quote
- [ ] Coverage check section present with counts

## Acceptance Criteria
- [ ] Initializer prompt includes 4-step mandatory sequence
- [ ] Each feature must trace to specific spec text
- [ ] Coverage check verifies all spec requirements covered
- [ ] CRITICAL warning about drift risks present

## Dependencies
None (can run parallel to Phase 1)

## Files to Modify
- `src/claude_agent/prompts/initializer.md`
EOF
)"

# Issue 2.2: Feature List Evaluation Criteria
gh issue create \
  --title "[Phase 2] Implement feature list evaluation scoring functions" \
  --label "phase:2-init-quality,priority:high,type:feature,component:agent,status:ready" \
  --milestone "Sprint 2: Integration & Init Quality" \
  --body "$(cat <<'EOF'
## Authorization Context
- References: drift-mitigation-design.md Section 4.2
- New module for evaluation logic
- Supports Best-of-N sampling

## Description
Implement evaluation criteria functions to score generated feature lists.

## Implementation Steps
- [ ] Create `evaluation.py` module
- [ ] Implement `calculate_spec_coverage(features, spec)`:
  - Parse spec for requirements
  - Match features to requirements
  - Return coverage percentage
- [ ] Implement `calculate_testability_score(features)`:
  - Check for concrete test steps
  - Check for verifiable outcomes
  - Return 0-1 score
- [ ] Implement `calculate_granularity_score(features)`:
  - Check feature complexity indicators
  - Penalize too large or too small
  - Return 0-1 score
- [ ] Implement `calculate_independence_score(features)`:
  - Check for feature dependencies
  - Return 0-1 score
- [ ] Implement `evaluate_feature_list()` combining all scores
- [ ] Add configurable weights to config.py
- [ ] Add unit tests with sample feature lists

## Validation
- [ ] Sample feature list scores correctly
- [ ] Edge cases handled (empty list, single feature)
- [ ] Scores are between 0 and 1

## Acceptance Criteria
- [ ] Four evaluation functions implemented
- [ ] Weighted aggregate score function
- [ ] Configurable weights in config
- [ ] Unit tests with >80% coverage

## Dependencies
None

## Files to Create
- `src/claude_agent/evaluation.py`
- `tests/test_evaluation.py`

## Files to Modify
- `src/claude_agent/config.py`
EOF
)"

# Issue 2.3: Best-of-N Feature List Sampling
gh issue create \
  --title "[Phase 2] Implement Best-of-N sampling for feature list generation" \
  --label "phase:2-init-quality,priority:medium,type:feature,component:agent,status:blocked" \
  --milestone "Sprint 3: Architecture" \
  --body "$(cat <<'EOF'
## Authorization Context
- References: drift-mitigation-design.md Section 4.1
- Requires evaluation module (Issue 2.2)
- Increases API calls (cost consideration)

## Description
Implement multi-sample generation for feature lists with automatic selection of best candidate.

## Implementation Steps
- [ ] Add `sampling` config section:
  - `feature_list_samples`: int (default 3)
  - `score_threshold`: float (default 0.7)
- [ ] Implement `generate_feature_list_with_sampling()` in agent.py:
  - Generate N candidates
  - Score each with evaluation.py
  - Select best above threshold
  - Raise `NeedsSpecRefinement` if none qualify
- [ ] Add `--no-sampling` CLI flag for single-shot mode
- [ ] Add `--samples N` CLI flag to override config
- [ ] Log all candidate scores for debugging
- [ ] Add integration test

## Validation
- [ ] Multiple candidates generated
- [ ] Best candidate selected correctly
- [ ] Threshold enforcement works
- [ ] Single-shot mode works when disabled

## Acceptance Criteria
- [ ] Config supports sampling configuration
- [ ] N candidates generated and scored
- [ ] Best candidate selected or error raised
- [ ] CLI flags for control
- [ ] Sampling can be disabled

## Dependencies
- Issue 2.2: Feature List Evaluation Criteria

## Files to Modify
- `src/claude_agent/agent.py`
- `src/claude_agent/config.py`
- `src/claude_agent/cli.py`
EOF
)"
```

### Phase 3 Issues

```bash
# Issue 3.1: Architecture Lock Agent Prompt
gh issue create \
  --title "[Phase 3] Create Architecture Lock Agent prompt template" \
  --label "phase:3-architecture,priority:high,type:feature,component:prompts,status:ready" \
  --milestone "Sprint 3: Architecture" \
  --body "$(cat <<'EOF'
## Authorization Context
- References: drift-mitigation-design.md Section 2.1
- New prompt file
- Defines new agent phase

## Description
Create the prompt template for the new Architecture Lock Agent that runs between Initializer and first Coding session.

## Implementation Steps
- [ ] Create `prompts/architect.md` with:
  - Purpose statement
  - Input requirements (spec, feature list)
  - Output requirements (contracts.yaml, schemas.yaml, decisions.yaml)
- [ ] Define evaluation sequence for architect:
  - Step 1: Identify API boundaries
  - Step 2: Identify data models
  - Step 3: Identify architectural decisions
  - Step 4: Generate lock files
- [ ] Add YAML format specifications for each output file
- [ ] Add constraints for what should/shouldn't be locked
- [ ] Add handoff instructions for coding agent

## Validation
- [ ] Prompt produces valid YAML outputs
- [ ] All three lock files generated
- [ ] Decisions include rationale

## Acceptance Criteria
- [ ] Architect prompt defines clear outputs
- [ ] Evaluation sequence ensures thorough analysis
- [ ] Lock file formats match design spec
- [ ] Handoff to coding agent documented

## Dependencies
None

## Files to Create
- `src/claude_agent/prompts/architect.md`
EOF
)"

# Issue 3.2: Architecture Lock Phase in Agent Flow
gh issue create \
  --title "[Phase 3] Implement architecture lock phase in agent session flow" \
  --label "phase:3-architecture,priority:high,type:feature,component:agent,status:blocked" \
  --milestone "Sprint 3: Architecture" \
  --body "$(cat <<'EOF'
## Authorization Context
- References: drift-mitigation-design.md Section 2.1
- Requires architect prompt (Issue 3.1)
- Modifies session flow

## Description
Add new Architecture Lock phase to agent session flow that runs once after initialization.

## Implementation Steps
- [ ] Add `architecture_locked` flag to project state
- [ ] Add `architecture/` directory creation
- [ ] Implement `run_architect_agent()` function:
  - Load architect prompt
  - Run agent session
  - Parse and save YAML outputs
  - Set architecture_locked flag
- [ ] Update session flow in `run_agent()`:
  - Check for feature_list.json
  - Check for architecture_locked
  - Run architect if features exist but not locked
- [ ] Add `--skip-architecture` flag for backwards compatibility
- [ ] Add integration test

## Validation
- [ ] Architect runs after initializer
- [ ] Architecture files created in architecture/
- [ ] Subsequent sessions skip architect phase
- [ ] Skip flag works correctly

## Acceptance Criteria
- [ ] Architecture lock phase runs once after initialization
- [ ] Three YAML files created in architecture/
- [ ] Phase skipped on subsequent sessions
- [ ] Backwards compatible with existing projects

## Dependencies
- Issue 3.1: Architecture Lock Agent Prompt

## Files to Modify
- `src/claude_agent/agent.py`
- `src/claude_agent/cli.py`
EOF
)"

# Issue 3.3: Decision Record Protocol
gh issue create \
  --title "[Phase 3] Implement decision record protocol for coding sessions" \
  --label "phase:3-architecture,priority:medium,type:feature,component:progress,status:blocked" \
  --milestone "Sprint 3: Architecture" \
  --body "$(cat <<'EOF'
## Authorization Context
- References: drift-mitigation-design.md Section 3
- Append-only decision log
- Required by coding agent

## Description
Implement decision record storage and retrieval for tracking architectural decisions made during coding sessions.

## Implementation Steps
- [ ] Create `DecisionRecord` dataclass:
  - id, timestamp, session, topic
  - choice, alternatives_considered
  - rationale, constraints_created
  - affects_features
- [ ] Implement `append_decision()` function
- [ ] Implement `load_decisions()` function
- [ ] Implement `get_relevant_decisions(feature_index)` function
- [ ] Add YAML storage format
- [ ] Add decision record instructions to coding prompt
- [ ] Add unit tests

## Validation
- [ ] Decisions append correctly
- [ ] Decisions load from file
- [ ] Feature-relevant decisions filter correctly

## Acceptance Criteria
- [ ] DecisionRecord dataclass matches design spec
- [ ] Append-only log in architecture/decisions.yaml
- [ ] Coding prompt includes decision record instructions
- [ ] Functions to query decisions by feature

## Dependencies
- Issue 3.1: Architecture Lock Agent Prompt

## Files to Create
- `src/claude_agent/decisions.py`
- `tests/test_decisions.py`

## Files to Modify
- `src/claude_agent/prompts/coding.md`
EOF
)"

# Issue 3.4: Architecture Constraint Validation
gh issue create \
  --title "[Phase 3] Add architecture constraint validation to coding agent prompt" \
  --label "phase:3-architecture,priority:medium,type:enhancement,component:prompts,status:blocked" \
  --milestone "Sprint 4: Validation & Polish" \
  --body "$(cat <<'EOF'
## Authorization Context
- References: drift-mitigation-design.md Section 2.1
- Extends coding prompt
- Depends on architecture files

## Description
Update coding agent prompt to require verification against locked architecture before implementation.

## Implementation Steps
- [ ] Add architecture verification to Step 1 of coding evaluation:
  - Read contracts.yaml and quote relevant section
  - Read schemas.yaml and quote relevant section
  - Read decisions.yaml and quote relevant constraints
- [ ] Add "Architecture Deviation Check" to Step 3:
  - State if implementation requires changing locked invariant
  - If yes, document why and STOP
- [ ] Add conditional logic for projects without architecture/
- [ ] Test with sample project

## Validation
- [ ] Agent quotes architecture files in output
- [ ] Deviation detection works
- [ ] Graceful fallback when architecture/ missing

## Acceptance Criteria
- [ ] Coding prompt requires architecture verification
- [ ] Explicit quotes from lock files in output
- [ ] Deviation handling documented
- [ ] Backwards compatible with non-locked projects

## Dependencies
- Issue 3.2: Architecture Lock Phase

## Files to Modify
- `src/claude_agent/prompts/coding.md`
EOF
)"
```

### Phase 4 Issues

```bash
# Issue 4.1: Validator Agent Forced Evaluation Sequence
gh issue create \
  --title "[Phase 4] Implement forced evaluation sequence in Validator Agent prompt" \
  --label "phase:4-validation,priority:high,type:feature,component:prompts,status:ready" \
  --milestone "Sprint 2: Integration & Init Quality" \
  --body "$(cat <<'EOF'
## Authorization Context
- References: drift-mitigation-design.md Section 1.3
- Similar pattern to Issues 1.1 and 2.1
- Improves verdict reliability

## Description
Add mandatory evaluation sequence to validator prompt for evidence-based verdicts.

## Implementation Steps
- [ ] Read current `prompts/validator.md`
- [ ] Add "MANDATORY VALIDATION SEQUENCE" section with:
  - Step 1: Spec Alignment Check (explicit output required)
  - Step 2: Test Execution with evidence (explicit output required)
  - Step 3: Aggregate Verdict with reasoning (explicit output required)
- [ ] Require screenshot evidence reference for each test
- [ ] Require specific failure reasons for REJECTED verdict
- [ ] Add CRITICAL warning about verdicts without evidence
- [ ] Test with sample validation run

## Validation
- [ ] Agent output includes spec alignment section
- [ ] Test execution includes evidence for each feature
- [ ] Aggregate verdict includes reasoning

## Acceptance Criteria
- [ ] Validator prompt includes 3-step mandatory sequence
- [ ] Each tested feature has explicit pass/fail evidence
- [ ] Verdicts require reasoning
- [ ] CRITICAL warning about untrusted verdicts

## Dependencies
None (can run parallel to Phase 3)

## Files to Modify
- `src/claude_agent/prompts/validator.md`
EOF
)"

# Issue 4.2: Evaluation Validation Hook
gh issue create \
  --title "[Phase 4] Implement evaluation validation hook in security.py" \
  --label "phase:4-validation,priority:medium,type:feature,component:security,status:blocked" \
  --milestone "Sprint 4: Validation & Polish" \
  --body "$(cat <<'EOF'
## Authorization Context
- References: drift-mitigation-design.md Section 7
- Enforces evaluation compliance
- Can trigger retry

## Description
Implement a validation hook that verifies agent output contains required evaluation sections.

## Implementation Steps
- [ ] Define `ValidationResult` dataclass:
  - valid: bool
  - error: str (optional)
  - action: str (retry_with_emphasis, continue, fail)
  - evaluation_data: dict (optional)
- [ ] Implement `evaluation_validation_hook()`:
  - Define required sections per phase
  - Parse agent output for section presence
  - Return ValidationResult
- [ ] Implement `extract_evaluation_sections()`:
  - Parse markdown output
  - Extract structured data from evaluation sections
- [ ] Integrate hook into agent session flow
- [ ] Add retry logic with emphasis on missing sections
- [ ] Add unit tests

## Validation
- [ ] Hook detects missing sections
- [ ] Retry with emphasis works
- [ ] Extraction produces valid data
- [ ] Hook doesn't block valid output

## Acceptance Criteria
- [ ] Hook validates presence of required sections
- [ ] Missing sections trigger retry with emphasis
- [ ] Evaluation data extracted for handoff enrichment
- [ ] All three agent phases supported

## Dependencies
- Issue 1.1: Coding Agent Forced Eval
- Issue 2.1: Initializer Agent Forced Eval
- Issue 4.1: Validator Agent Forced Eval

## Files to Modify
- `src/claude_agent/security.py`
- `src/claude_agent/agent.py`
- `tests/test_security.py`
EOF
)"

# Issue 4.3: Drift Detection Dashboard CLI
gh issue create \
  --title "[Phase 4] Implement drift detection dashboard in CLI" \
  --label "phase:4-validation,priority:low,type:feature,component:agent,status:blocked" \
  --milestone "Sprint 4: Validation & Polish" \
  --body "$(cat <<'EOF'
## Authorization Context
- References: drift-mitigation-design.md Section 6
- Depends on metrics tracking (Issue 1.3)
- CLI-only output

## Description
Add a dashboard view to the CLI that displays drift detection metrics and trends.

## Implementation Steps
- [ ] Add `claude-agent drift` command
- [ ] Implement dashboard display:
  - Session count and date range
  - Regression rate trend (last 5 sessions)
  - Session velocity trend
  - Validator rejection rate
  - Architecture deviation count
- [ ] Add color coding for concerning trends (red/yellow/green)
- [ ] Add `--json` flag for machine-readable output
- [ ] Add sparkline graphs for trends (optional)
- [ ] Add documentation

## Validation
- [ ] Dashboard displays with sample data
- [ ] Trends calculate correctly
- [ ] JSON output is valid
- [ ] Empty metrics handled gracefully

## Acceptance Criteria
- [ ] `claude-agent drift` command shows metrics dashboard
- [ ] Trends displayed for key indicators
- [ ] Color coding for health status
- [ ] JSON output supported

## Dependencies
- Issue 1.3: Basic Metrics Tracking
- Issue 1.4: Integrate Metrics

## Files to Modify
- `src/claude_agent/cli.py`
- `src/claude_agent/metrics.py`
EOF
)"
```

### Documentation Issues

```bash
# Issue D.1: Update AGENTS.md
gh issue create \
  --title "[Docs] Update AGENTS.md with drift mitigation architecture" \
  --label "type:documentation,priority:medium" \
  --milestone "Sprint 4: Validation & Polish" \
  --body "$(cat <<'EOF'
## Description
Update the main AGENTS.md file with documentation of the drift mitigation system.

## Implementation Steps
- [ ] Add "Drift Mitigation" section
- [ ] Document four-layer architecture
- [ ] Document forced evaluation sequences
- [ ] Document architecture lock phase
- [ ] Document metrics and dashboard
- [ ] Add troubleshooting for drift issues

## Acceptance Criteria
- [ ] AGENTS.md includes drift mitigation documentation
- [ ] All new components documented
- [ ] Troubleshooting section added

## Dependencies
All Phase 1-4 issues

## Files to Modify
- `AGENTS.md`
EOF
)"

# Issue D.2: Create Migration Guide
gh issue create \
  --title "[Docs] Create migration guide for existing projects" \
  --label "type:documentation,priority:high" \
  --milestone "Sprint 4: Validation & Polish" \
  --body "$(cat <<'EOF'
## Description
Create documentation for migrating existing claude-agent projects to the new drift mitigation system.

## Implementation Steps
- [ ] Document backwards compatibility
- [ ] Document architecture lock for existing projects
- [ ] Document metrics initialization
- [ ] Provide migration commands

## Acceptance Criteria
- [ ] Clear migration path documented
- [ ] No breaking changes for existing projects
- [ ] Step-by-step migration guide

## Dependencies
All Phase 1-4 issues

## Files to Create
- `docs/MIGRATION.md` or add to README
EOF
)"
```

---

## Step 5: Create GitHub Project Board

Create a project board to track sprint progress.

### Using GitHub Web Interface

1. Navigate to the repository on GitHub
2. Go to **Projects** tab
3. Click **New project**
4. Select **Board** template
5. Name: "Drift Mitigation Sprint"
6. Create columns:
   - **Backlog** - Issues not yet started
   - **Sprint 1** - Current sprint issues
   - **Sprint 2** - Next sprint issues
   - **Sprint 3** - Future sprint issues
   - **Sprint 4** - Final sprint issues
   - **In Progress** - Active work
   - **In Review** - PRs open
   - **Done** - Completed issues

### Using GitHub CLI

```bash
# Create project (requires gh extension or API)
gh project create --title "Drift Mitigation Sprint" --owner {owner}
```

---

## Step 6: Link Issues to Project

After creating issues, add them to the project board:

```bash
# Get list of issue numbers
gh issue list --label "phase:1-foundation" --json number

# Add each issue to project (via web interface or API)
```

---

## Step 7: Set Up Branch Protection (Optional)

For quality control, consider branch protection:

```bash
# Protect main branch
gh api repos/{owner}/{repo}/branches/main/protection -X PUT \
  -f required_status_checks='{"strict":true,"contexts":["test"]}' \
  -f enforce_admins=true \
  -f required_pull_request_reviews='{"required_approving_review_count":1}'
```

---

## Step 8: Create Issue Templates

Create issue templates for consistency.

### Feature Issue Template

Create `.github/ISSUE_TEMPLATE/feature.md`:

```markdown
---
name: Feature Implementation
about: Implementation issue for drift mitigation
labels: type:feature
---

## Authorization Context
- References:
- Approved by:
- Dependencies:

## Description
[Describe the feature]

## Implementation Steps
- [ ] Step 1
- [ ] Step 2

## Validation
- [ ] Test 1
- [ ] Test 2

## Acceptance Criteria
- [ ] Criteria 1
- [ ] Criteria 2

## Dependencies
[List blocking issues]

## Files to Modify
- `path/to/file.py`
```

---

## Verification Checklist

After setup, verify:

- [ ] All 21 labels created
- [ ] 4 milestones created with due dates
- [ ] 2 epic issues created
- [ ] 13 implementation issues created
- [ ] 2 documentation issues created
- [ ] Issues assigned to correct milestones
- [ ] Dependencies noted in issue bodies
- [ ] Project board created with columns
- [ ] Issues linked to project board

---

## Quick Reference

### Issue Count by Phase

| Phase | Issues | Priority Critical | Priority High |
|-------|--------|-------------------|---------------|
| Phase 1 | 4 | 2 | 2 |
| Phase 2 | 3 | 1 | 1 |
| Phase 3 | 4 | 1 | 2 |
| Phase 4 | 3 | 0 | 1 |
| Docs | 2 | 0 | 1 |
| **Total** | **16** | **4** | **7** |

### Sprint Assignment

| Sprint | Issues |
|--------|--------|
| Sprint 1 | 1.1, 1.2, 1.3, 1.4, 2.1 |
| Sprint 2 | 2.2, 4.1 |
| Sprint 3 | 2.3, 3.1, 3.2, 3.3 |
| Sprint 4 | 3.4, 4.2, 4.3, D.1, D.2 |

---

## Support

For questions about this setup guide:
- Review `reports/drift-mitigation-design.md` for technical details
- Review `reports/drift-mitigation-github-issues-plan.md` for issue specifications
- Contact the engineering lead for clarification
