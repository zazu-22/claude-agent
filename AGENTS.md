# AGENTS.md
This file provides guidance to AI coding assistants working in this repository.

**Note:** CLAUDE.md, .clinerules, .cursorrules, .windsurfrules, .replit.md, GEMINI.md, .github/copilot-instructions.md, and .idx/airules.md are symlinks to AGENTS.md in this project.

# Claude Agent

Autonomous coding agent CLI powered by Claude. Enables long-running coding sessions with persistent progress tracking across multiple context windows using the Claude Code SDK.

## Project Overview

This is a Python CLI tool that orchestrates autonomous coding sessions using a two-agent pattern:

1. **Initializer Agent**: Reads a spec, generates a detailed `feature_list.json` with test cases
2. **Coding Agent**: Implements features one by one, marks tests as passing
3. **Validator Agent**: Reviews completed work through UI testing before approval

Key files:
- `src/claude_agent/cli.py` - Click-based CLI entry point
- `src/claude_agent/agent.py` - Core agent session logic
- `src/claude_agent/config.py` - Configuration loading and merging
- `src/claude_agent/security.py` - Command allowlist security hooks
- `src/claude_agent/progress.py` - Progress tracking utilities
- `src/claude_agent/prompts/*.md` - Agent prompt templates

## Build & Commands

### Environment Setup (uv)

This project uses [uv](https://github.com/astral-sh/uv) for Python environment management.

```bash
# Create virtual environment and install dependencies
uv sync

# Install with dev dependencies
uv sync --extra dev

# Reinstall/refresh all dependencies
uv sync --reinstall

# Add a new dependency
uv add <package>

# Add a dev dependency
uv add --dev <package>

# Update dependencies
uv lock --upgrade
uv sync
```

### Running

```bash
# Main CLI command (via uv)
uv run claude-agent [OPTIONS]

# With a spec file
uv run claude-agent -p ./my-project --spec ./SPEC.md

# With a goal description
uv run claude-agent -p ./my-project --goal "Build a REST API"

# Review spec before generating features
uv run claude-agent -p ./my-project --spec ./SPEC.md --review

# Initialize config file
uv run claude-agent init [DIR]

# Check project status
uv run claude-agent status [DIR]

# Reset agent files
uv run claude-agent --reset
```

### Testing

```bash
# Run tests with pytest
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/test_security.py

# Run with asyncio support
uv run pytest --asyncio-mode=auto
```

### Type Checking & Linting

This project does not currently have explicit type checking or linting configured. Consider using:

```bash
# Type checking (if adding)
uv run mypy src/

# Linting (if adding)
uv run ruff check src/
uv run ruff format src/
```

## Code Style

### Python Version
- Requires Python 3.10+
- Uses modern Python features (dataclasses, type hints, walrus operator)

### Imports
- Standard library imports first
- Third-party imports second (click, yaml, claude_code_sdk)
- Local imports last (from claude_agent.*)
- Absolute imports preferred

### Formatting
- 4-space indentation
- Double quotes for strings
- Line length: follow PEP 8 (~88-100 chars reasonable)
- Docstrings: Google-style with module-level docstrings using `===` underlines

### Naming Conventions
- `snake_case` for functions and variables
- `PascalCase` for classes and dataclasses
- `SCREAMING_SNAKE_CASE` for constants
- Private functions prefixed with `_`

### Type Hints
- Use type hints for function signatures
- Use `Optional[T]` for nullable types
- Use `list[T]`, `dict[K, V]` (Python 3.10+ syntax)
- Dataclasses with type annotations for configuration

### Error Handling
- Use specific exceptions
- Fail fast with clear error messages
- Use `click.echo()` for CLI output
- Return tuples like `(success, errors)` for multi-error scenarios

### Async Patterns
- Use `asyncio.run()` at entry points
- Use `async with` for client context managers
- Stream responses with `async for`

## Testing

### Framework
- pytest with pytest-asyncio for async tests

### Testing Philosophy
**When tests fail, fix the code, not the test.**

Key principles:
- Tests should be meaningful - Avoid tests that always pass
- Test actual functionality - Call the functions being tested
- Failing tests are valuable - They reveal bugs
- Fix the root cause - Don't hide failing tests

### Test Patterns
- Unit tests in `tests/` directory (when created)
- Test files named `test_*.py`
- Test functions named `test_*`
- Use fixtures for common setup

## Security

### Defense-in-Depth Model
1. **OS-level sandbox**: Bash commands run in isolated environment
2. **Filesystem restrictions**: Operations limited to project directory
3. **Command allowlist**: Only explicitly permitted commands execute

### Command Allowlist
The security module (`security.py`) enforces an allowlist approach:

**Base commands (all stacks):**
- `ls`, `cat`, `head`, `tail`, `wc`, `grep`
- `cp`, `mkdir`, `chmod`, `pwd`
- `git`, `ps`, `lsof`, `sleep`, `pkill`
- `init.sh`

**Node.js stack adds:**
- `npm`, `npx`, `node`, `yarn`, `pnpm`

**Python stack adds:**
- `python`, `python3`, `pip`, `pip3`, `uv`, `poetry`, `pytest`, `ruff`

### Security Hooks
- `bash_security_hook()` - Validates all bash commands before execution
- `validate_pkill_command()` - Only allows killing dev processes
- `validate_chmod_command()` - Only allows `+x` mode
- `validator_stop_hook()` - Enforces verdict output before session ends

### Configuration
Extra commands can be allowed via `.claude-agent.yaml`:
```yaml
security:
  extra_commands:
    - docker
    - make
```

## Configuration

### Config File
Create `.claude-agent.yaml` in project root:

```yaml
# Specification
spec_file: ./docs/SPEC.md
# goal: "Build a REST API"

# Feature generation
features: 50

# Tech stack (auto-detected if not specified)
# stack: python

# Agent settings
agent:
  model: claude-opus-4-5-20251101
  # max_iterations: 10
  # auto_continue_delay: 3

# Security
security:
  extra_commands: []

# Validator settings
validator:
  model: claude-opus-4-5-20251101
  enabled: true
  max_rejections: 3
  max_turns: 75
```

### Environment
- Uses Claude Code CLI OAuth authentication (Max subscription)
- No separate `ANTHROPIC_API_KEY` required
- Project directory resolved to absolute path

### Generated Files
The agent creates these files in the project directory:
- `feature_list.json` - Source of truth for all features and status
- `app_spec.txt` - Copy of the specification
- `claude-progress.txt` - Session notes and handoff info
- `validation-history.json` - Validation attempt records
- `drift-metrics.json` - Drift detection metrics tracking
- `spec-review.md` - Optional spec review output
- `architecture/` - Architecture lock files (created by Architect Agent):
  - `contracts.yaml` - API endpoint definitions
  - `schemas.yaml` - Data model definitions
  - `decisions.yaml` - Architectural decision records

## Directory Structure

```
claude-agent/
├── src/claude_agent/      # Main package
│   ├── __init__.py        # Version and exports
│   ├── __main__.py        # Entry point
│   ├── cli.py             # Click CLI commands
│   ├── agent.py           # Agent session logic
│   ├── architecture.py    # Architecture lock file validation
│   ├── client.py          # Claude SDK client creation
│   ├── config.py          # Configuration loading
│   ├── decisions.py       # Architectural decision records
│   ├── detection.py       # Tech stack detection
│   ├── metrics.py         # Drift detection metrics tracking
│   ├── progress.py        # Progress tracking
│   ├── security.py        # Security hooks
│   ├── wizard.py          # Interactive spec wizard
│   └── prompts/           # Agent prompts
│       ├── __init__.py
│       ├── loader.py      # Prompt loading utilities
│       ├── architect.md   # Architecture lock agent prompt
│       ├── coding.md      # Coding agent prompt
│       ├── initializer.md # Initializer agent prompt
│       ├── review.md      # Spec review prompt
│       └── validator.md   # Validator agent prompt
├── scripts/               # Automation scripts
│   ├── github_api.py      # GitHub API wrapper (code-first pattern)
│   └── github_tasks/      # Task YAML definitions
├── .github/workflows/     # GitHub Actions
│   ├── github-setup.yml   # GitHub setup automation
│   └── CLAUDE.md          # Workflow documentation
├── tests/                 # Test directory (create as needed)
├── pyproject.toml         # Project configuration
├── README.md              # User documentation
└── .claude-agent.yaml     # Optional config template
```

### Reports Directory
ALL project reports and documentation should be saved to the `reports/` directory:

```
claude-agent/
├── reports/              # All project reports and documentation
│   └── *.md             # Various report types
├── temp/                # Temporary files and debugging
└── [other directories]
```

### Temporary Files & Debugging
All temporary files, debugging scripts, and test artifacts should be in `/temp`:

**Guidelines:**
- Never commit files from `/temp` directory
- Use `/temp` for all debugging scripts
- Clean up `/temp` regularly

## Architecture

### Four-Agent Pattern
The agent uses distinct personas for different phases:

1. **Initializer Agent** (`prompts/initializer.md`)
   - Reads spec, creates `feature_list.json`
   - Sets up project structure
   - Runs once at project start
   - Must complete forced evaluation sequence before generating features

2. **Architect Agent** (`prompts/architect.md`)
   - Establishes architectural constraints before coding begins
   - Creates lock files: `contracts.yaml`, `schemas.yaml`, `decisions.yaml`
   - Runs once after initialization, before first coding session
   - Prevents architectural drift across sessions

3. **Coding Agent** (`prompts/coding.md`)
   - Implements features from feature list
   - Tests through browser automation
   - Commits progress, updates notes
   - Must verify architecture constraints before implementation
   - Runs repeatedly until all features pass

4. **Validator Agent** (`prompts/validator.md`)
   - Reviews completed implementation
   - Tests through actual UI
   - Issues APPROVED/REJECTED/CONTINUE/NEEDS_VERIFICATION verdict
   - Must provide evidence for each verdict
   - Runs when all automated tests pass

### Session Flow
```
Start → Is feature_list.json present?
  No  → Run Initializer Agent → Create feature list
  Yes → Is architecture/ locked?
        No  → Run Architect Agent → Create lock files
        Yes → Check test status
              All automated pass? → Run Validator
              Otherwise → Run Coding Agent → Implement features
```

### Configuration Priority
1. CLI arguments (highest)
2. Config file (`.claude-agent.yaml`)
3. Defaults (lowest)

## Drift Mitigation

The agent implements a comprehensive drift mitigation system to prevent quality degradation in long-running coding sessions.

### Problem Overview

Long-running agentic workflows face three distinct failure modes that compound across sessions:

| Failure Mode | Description | Manifestation |
|--------------|-------------|---------------|
| **Lossy Handoff Divergence** | Context passes between stateless sessions via artifacts; implicit intent is lost | Session N+1 interprets artifacts differently than Session N intended |
| **Stochastic Cascade Drift** | LLM outputs are probabilistic samples; variance at step N compounds at step N+1 | "Refinement" passes branch into new trajectories |
| **Passive Instruction Decay** | LLMs reason about what they should do, acknowledge instructions, then fail to execute | Agent identifies it should verify previous work, then skips to implementation |

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

### Architecture Lock Phase

The Architecture Lock Phase runs between Initialization and first Coding session to establish hard constraints.

**Purpose:** Lock architectural invariants before allowing generative implementation.

**Lock Files Created in `architecture/` Directory:**

| File | Purpose | Contents |
|------|---------|----------|
| `contracts.yaml` | API surface definitions | Endpoints, methods, request/response shapes |
| `schemas.yaml` | Data model definitions | Entities, fields, types, constraints |
| `decisions.yaml` | Architectural decisions | Technology choices, rationale, constraints |

**Example `contracts.yaml`:**
```yaml
version: 1
locked_at: "2024-01-15T10:00:00Z"
contracts:
  - name: "user_auth"
    endpoints:
      - path: "/api/auth/login"
        method: "POST"
        request_shape:
          email: string
          password: string
        response_shape:
          token: string
          user: object
```

**Example `decisions.yaml`:**
```yaml
version: 1
decisions:
  - id: DR-001
    topic: "Authentication strategy"
    choice: "JWT with refresh tokens"
    alternatives_considered:
      - "Session cookies - rejected due to mobile app requirements"
    rationale: "Spec requires stateless API for mobile clients"
    constraints_created:
      - "All auth must use JWT middleware"
      - "Token refresh endpoint required"
    affects_features: [3, 5, 12]
```

**Architect Agent Evaluation Sequence:**
1. **Step 1 - Identify API Boundaries**: List each endpoint with path, method, shapes
2. **Step 2 - Identify Data Models**: List each entity with fields, relationships
3. **Step 3 - Identify Architectural Decisions**: Document technology choices with rationale
4. **Step 4 - Generate Lock Files**: Write validated YAML files

### Forced Evaluation Sequences

Each agent must complete mandatory evaluation checkpoints with explicit output before proceeding.

#### Coding Agent Evaluation Sequence

Before implementing ANY feature, the coding agent MUST complete:

**Step A - Context Verification** (explicit output required):
- [ ] Quote specific feature from `feature_list.json` (index and full text)
- [ ] Quote last session's status from `claude-progress.txt`
- [ ] Identify architectural constraints from previous sessions
- [ ] **If `architecture/` exists**: Verify relevant contracts, schemas, decisions
- [ ] Answer: "Does this feature require changing a locked invariant? YES/NO"

**Step B - Regression Verification** (explicit output required):
- Test previously passing features
- Report PASS/FAIL with evidence for each
- Confirm no regressions introduced

**Step C - Implementation Plan** (explicit output required):
- State what will be built
- List files to modify
- Quote relevant architecture constraints that must be honored

**CRITICAL:** Steps A-C are WORTHLESS unless actually performed. Skipping to implementation without evidence above is a FAILURE MODE that causes drift.

#### Initializer Agent Evaluation Sequence

Before generating `feature_list.json`, MUST complete:

**Step 1 - Spec Decomposition**:
- For each spec section: list requirements and ambiguities

**Step 2 - Feature Mapping**:
- For EACH feature: state spec section it traces to with quote
- Justify feature granularity

**Step 3 - Coverage Check**:
- Count spec requirements covered vs total
- Identify any uncovered requirements
- Add features if needed

**CRITICAL:** Features without spec traceability are DRIFT RISKS.

#### Validator Agent Evaluation Sequence

Before issuing ANY verdict, MUST complete:

**Step A - Spec Alignment Check**:
- For each feature tested: quote spec requirement
- Define what "working" means
- State verification method

**Step B - Test Execution with Evidence**:
- Document actual steps performed
- State expected vs actual results
- Provide screenshot evidence
- Assign PASS/FAIL verdict per feature

**Step C - Aggregate Verdict with Reasoning**:
- Summarize: features tested, passed, failed
- List failed features with specific reasons
- State reasoning BEFORE JSON verdict

**CRITICAL:** A verdict without Step B evidence is NOT TRUSTWORTHY.

### Decision Record Protocol

The Decision Record Protocol captures WHY decisions were made, not just WHAT was done.

**When to Create Decision Records:**
- Choosing between multiple valid implementation approaches
- Adding a new dependency
- Establishing a pattern that future features should follow
- Deviating from an existing pattern (with justification)

**Decision Record Fields:**
| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Format: "DR-YYYYMMDD-UUID" |
| `topic` | Yes | What was being decided |
| `choice` | Yes | What was chosen |
| `timestamp` | No | ISO format datetime |
| `session` | No | Session number that made decision |
| `rationale` | No | Why this choice was made |
| `alternatives_considered` | No | Other options evaluated |
| `constraints_created` | No | What future sessions must honor |
| `affects_features` | No | Feature indices affected |

**Implementation:** Decision records are append-only. Use `decisions.py` functions:
- `load_decisions()` - Load all decisions
- `append_decision()` - Add new decision (never modifies existing)
- `get_relevant_decisions(feature_index)` - Get decisions affecting a feature
- `get_all_constraints()` - Get flat list of all constraints

### Metrics Tracking

Drift metrics are automatically tracked in `drift-metrics.json` and provide visibility into drift patterns.

#### Session Metrics (per coding session)
| Metric | Description |
|--------|-------------|
| `features_attempted` | Features agent tried to implement |
| `features_completed` | Net change in passing features (can be negative) |
| `features_regressed` | Features that went from pass to fail |
| `regressions_caught` | Regressions detected by agent during verification |
| `assumptions_stated` | Number of explicit assumptions documented |
| `assumptions_violated` | Assumptions that proved incorrect |
| `architecture_deviations` | Locked constraints violated |
| `evaluation_sections_present` | Which eval sections appeared (context, regression, plan) |
| `evaluation_completeness_score` | 0.0-1.0 score of evaluation quality |
| `is_multi_feature` | Whether session worked on multiple features |

#### Validation Metrics (per validation attempt)
| Metric | Description |
|--------|-------------|
| `verdict` | "approved" or "rejected" |
| `features_tested` | Number of features tested |
| `features_failed` | Number of features that failed |
| `failure_reasons` | List of failure descriptions |

#### Drift Indicators (calculated aggregates)
| Indicator | Calculation | Drift Signal |
|-----------|-------------|--------------|
| `regression_rate` | % sessions with regressions | High = drift occurring |
| `velocity_trend` | Comparing avg features/session over time | "decreasing" = complexity/drift |
| `rejection_rate` | % validation attempts rejected | Increasing = drift accumulating |
| `multi_feature_rate` | % sessions with multi-feature work | High = deviation from architecture |
| `incomplete_evaluation_rate` | % sessions with incomplete evals | High = skipped safeguards |

**Velocity Trend Thresholds:**
- Requires minimum 6 sessions for trend calculation
- 10% change threshold to trigger "increasing"/"decreasing"
- 0.5 feature/session minimum absolute change

View metrics with: `claude-agent status --metrics`

### Troubleshooting Drift Issues

#### Common Drift Symptoms

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| Increasing validator rejections | Features diverging from spec | Review `decisions.yaml` for constraint violations |
| Regressions detected each session | Interdependent features not tested together | Add regression verification to affected features |
| Velocity decreasing over sessions | Accumulated technical debt or drift | Reset architecture lock, review feature dependencies |
| Evaluation sections missing | Passive instruction decay | Agent may need prompt refresh or session restart |
| Multi-feature sessions increasing | Scope creep or unclear feature boundaries | Re-evaluate feature granularity in `feature_list.json` |

#### Diagnostic Commands

```bash
# View current drift metrics
claude-agent status ./my-project --metrics

# Check architecture lock status
ls -la ./my-project/architecture/

# View decision history
cat ./my-project/architecture/decisions.yaml

# Check validation history
cat ./my-project/validation-history.json

# Review regression patterns in progress notes
grep -n "FAIL" ./my-project/claude-progress.txt
```

#### Recovery Actions

**High Regression Rate:**
1. Review recent decision records for constraint violations
2. Check if architecture lock files are being honored
3. Consider resetting specific features to "not_started"

**Increasing Rejection Rate:**
1. Compare rejected features against spec requirements
2. Review validator evidence for patterns
3. Check if spec has ambiguities causing interpretation drift

**Decreasing Velocity:**
1. Review session metrics for incomplete evaluations
2. Check for multi-feature sessions (scope creep)
3. Consider architecture review if constraints are blocking progress

**Architecture Deviation Detected:**
1. STOP implementation immediately
2. Document why deviation is needed in `decisions.yaml`
3. Update lock files if deviation is justified
4. Propagate changes to affected features

## Agent Delegation & Tool Execution

### Parallel Execution
When performing multiple operations, send all tool calls in a single message:

```python
# Good - parallel execution
await asyncio.gather(
    search_files("*.py"),
    read_config(),
    check_status()
)
```

### Available Agents (if using Claude Code)
When working on this codebase with Claude Code, consider using specialized agents:
- `code-review-expert` - After significant changes
- `testing-expert` - For test reliability issues
- `refactoring-expert` - For code quality improvements

## Common Tasks

### Adding a New Tech Stack
1. Add entry to `STACK_SIGNATURES` in `detection.py`
2. Include markers, commands, pkill_targets, init/dev commands
3. Update README documentation

### Modifying Security Hooks
1. Edit `security.py`
2. Add new validation functions as needed
3. Register in `bash_security_hook()`

### Changing Agent Prompts
1. Edit markdown files in `prompts/`
2. Use `{{variable}}` syntax for template substitution
3. Test with a sample project

### Adding CLI Options
1. Add Click decorator in `cli.py`
2. Pass through `merge_config()` in `config.py`
3. Update help text and README

## GitHub Automation

This repository includes a reusable GitHub API automation system for bulk operations (labels, milestones, issues) without MCP context overhead. Uses a "code-first" pattern with YAML task definitions.

**Key files:**
- `scripts/github_api.py` - API wrapper script
- `scripts/github_tasks/*.yaml` - Task definitions
- `.github/workflows/github-setup.yml` - GitHub Actions workflow

**See:** `.github/workflows/CLAUDE.md` for detailed usage instructions.

## Debugging Tips

### Common Issues
- **"Command not allowed"**: Add to allowlist in `detection.py` or config
- **"No spec provided"**: Use `--spec` or `--goal` flags
- **Validator fails to parse**: Check JSON format in validator response
- **Session hangs**: First session can take 10-20+ minutes
- **Architecture lock fails**: Check YAML syntax in `architecture/*.yaml` files
- **High regression rate**: Review drift metrics and decision records

### Drift-Related Debugging
- **Missing evaluation sections**: Agent skipped forced evaluation; check metrics for `incomplete_evaluation_rate`
- **Architecture deviations**: Coding agent violated constraints; review `decisions.yaml` for conflicts
- **Validator rejection loop**: Features may be drifting from spec; check `validation-history.json`
- **Velocity declining**: Technical debt accumulating; review session metrics

### Useful Commands
```bash
# Check project status
claude-agent status ./my-project

# View progress
cat ./my-project/claude-progress.txt

# Check feature list
cat ./my-project/feature_list.json | head -50

# Reset and start fresh
claude-agent --reset -p ./my-project

# View drift metrics
claude-agent status ./my-project --metrics

# Check architecture lock files
ls -la ./my-project/architecture/
cat ./my-project/architecture/decisions.yaml

# Review validation history
cat ./my-project/validation-history.json
```

## Contributing

### Before Committing
1. Run tests: `uv run pytest`
2. Check types (if configured): `uv run mypy src/`
3. Format code: `uv run ruff format src/`
4. Lint: `uv run ruff check src/`

### Commit Messages
Follow conventional commits:
- `feat:` New features
- `fix:` Bug fixes
- `docs:` Documentation
- `refactor:` Code restructuring
- `test:` Test additions/changes

### Version Control
- Commit frequently
- One logical change per commit
- Never skip pre-commit hooks

### Versioning
Version numbers are maintained in two places that must be kept in sync:
- `pyproject.toml` - The canonical version for the package
- `src/claude_agent/__init__.py` - Runtime-accessible version (`__version__`)

When bumping versions:
1. Update both files to the same version
2. Use semantic versioning (MAJOR.MINOR.PATCH)
3. Include version bump in the commit with the relevant changes
