# Claude Agent

Autonomous coding agent CLI powered by Claude. Run long-running coding sessions with persistent progress tracking across multiple context windows.

## Installation

```bash
pip install -e .
```

## Quick Start

```bash
# Uses your existing Claude Code authentication (Max subscription)
# No separate API key needed!

# Run with a spec file
claude-agent -p ./my-project --spec ./SPEC.md

# Run with a goal description
claude-agent -p ./my-project --goal "Build a REST API with user authentication"

# Review spec before generating features (recommended)
claude-agent -p ./my-project --spec ./SPEC.md --review

# Run interactive wizard (when no spec provided)
claude-agent -p ./my-project

# Generate spec from a goal using the spec workflow
claude-agent spec create --goal "Build a task management API"

# Validate an existing spec before implementation
claude-agent spec validate ./SPEC.md

# Decompose a validated spec into features
claude-agent spec decompose ./spec-validated.md --features 50
```

## How It Works

Claude Agent uses a **two-agent pattern** for long-running autonomous coding:

1. **Initializer Agent (Session 1)**: Reads your spec, creates a detailed `feature_list.json` with test cases, and sets up the project structure.

2. **Coding Agents (Sessions 2+)**: Each session gets a fresh context window, reads the feature list, implements features one by one, and marks tests as passing.

Progress persists through:
- `feature_list.json` - Source of truth for all features and their status
- `claude-progress.txt` - Session notes and handoff information
- `drift-metrics.json` - Drift detection metrics tracking
- Git commits - Records implementation history

### Drift Metrics

Use `claude-agent status --metrics` to view drift detection indicators:

- **Total Sessions**: Number of coding sessions run
- **Regression Rate**: Percentage of sessions that caught regressions
- **Velocity Trend**: Whether feature completion rate is increasing, stable, or decreasing
- **Rejection Rate**: Percentage of validation attempts that were rejected

The agent automatically tracks these metrics to detect when implementation is drifting from the spec.

## Spec Workflow

The spec workflow helps you go from idea to implementation-ready specification:

```
Goal → Create → Validate → Decompose → Implement
```

### 1. Create (`spec create`)

Generate a detailed specification from a brief goal:

```bash
claude-agent spec create --goal "Build a REST API with authentication"
```

Creates `spec-draft.md` with:
- Project overview and success criteria
- Functional requirements with priorities
- Technical requirements and architecture
- Non-functional requirements
- Out of scope items
- Open questions and assumptions

### 2. Validate (`spec validate`)

Check a specification for completeness and issues:

```bash
claude-agent spec validate ./spec-draft.md
```

Produces:
- `spec-validation.md` - Issues categorized as BLOCKING, WARNING, or SUGGESTION
- `spec-validated.md` - Cleaned spec with minor issues resolved (if passed)
- Verdict: PASS or FAIL

### 3. Decompose (`spec decompose`)

Break a validated spec into implementable features:

```bash
claude-agent spec decompose ./spec-validated.md --features 50
```

Creates:
- `feature_list.json` - Test cases ready for the coding agent
- `app_spec.txt` - Spec copy for agent reference

### Full Workflow

Run all steps automatically:

```bash
claude-agent spec auto --goal "Build a task management API"
```

Or use the `--auto-spec` flag with the main command:

```bash
claude-agent -p ./my-project --goal "Build a REST API" --auto-spec
```

## CLI Reference

```bash
# Main command
claude-agent [OPTIONS]

# Options
-p, --project-dir PATH   # Project directory (default: current directory)
-s, --spec PATH          # Path to specification file
-g, --goal TEXT          # Short goal description (alternative to --spec)
-f, --features INT       # Number of features to generate (default: 50)
--stack TEXT             # Tech stack: node, python (auto-detected)
-m, --model TEXT         # Claude model (default: claude-opus-4-5-20251101)
-n, --max-iterations INT # Limit iterations
-c, --config PATH        # Path to config file
-r, --review             # Review spec before generating features

# Subcommands
claude-agent init [DIR]    # Create .claude-agent.yaml template
claude-agent status [DIR]  # Show project progress
claude-agent status [DIR] --metrics  # Show drift metrics
claude-agent doctor        # Check environment health

# Spec workflow commands
claude-agent spec create   # Generate spec from goal
claude-agent spec validate # Validate spec for completeness
claude-agent spec decompose # Break spec into features
claude-agent spec auto     # Run full workflow (create → validate → decompose)
claude-agent spec status   # Show spec workflow status
```

## Health Check

Before starting a coding session, verify your environment is properly configured:

```bash
claude-agent doctor
```

### Flags

| Flag | Description |
|------|-------------|
| `-p, --project-dir PATH` | Project directory to check (default: current directory) |
| `--json` | Output machine-readable JSON |
| `-v, --verbose` | Show detailed diagnostic information |
| `--fix` | Attempt automatic remediation of detected issues |

### Example Output

**Healthy environment:**

```
Claude Agent Environment Check
==============================

Authentication:
  [✓] Claude Code CLI installed (2.0.62)

Required Tools:
  [✓] Git available (2.52.0)
  [✓] Python available (3.13.6)
  [✓] uv available (0.8.8)
  [✓] puppeteer-mcp-server available (22.18.0)

Project (/path/to/project):
  [✓] Directory exists and writable
  [✓] .claude-agent.yaml found and valid

Stack detected: python

Summary: All checks passed!
Run 'claude-agent' to start your coding session.
```

**Environment with issues:**

```
Claude Agent Environment Check
==============================

Authentication:
  [✗] Claude Code CLI not installed
      Run: Install Claude Code CLI from https://claude.ai/code

Required Tools:
  [✓] Git available (2.52.0)
  [✓] Node.js available (20.10.0)
  [✓] npm available (10.2.3)
  [✗] puppeteer-mcp-server not found
      Run: npm install -g puppeteer-mcp-server

Project (/path/to/project):
  [✓] Directory exists and writable
  [!] Unknown configuration keys: typo_key

Summary: 2 error(s), 1 warning(s)
Run 'claude-agent doctor --fix' to attempt automatic fixes.
```

### JSON Output

Use `--json` for machine-readable output:

```bash
claude-agent doctor --json
```

```json
{
  "project_dir": "/path/to/project",
  "stack": "python",
  "summary": {
    "errors": 0,
    "warnings": 0,
    "passed": 7
  },
  "is_healthy": true,
  "checks": [
    {
      "name": "Claude Code CLI",
      "category": "authentication",
      "status": "pass",
      "message": "Claude Code CLI installed",
      "version": "2.0.62"
    }
  ]
}
```

### Auto-Fix

Use `--fix` to automatically remediate certain issues:

```bash
claude-agent doctor --fix
```

The auto-fix feature can:
- Create missing project directories
- Install puppeteer-mcp-server (with user confirmation)

It cannot automatically install system tools like Claude Code CLI, Git, Node.js, or Python.

## Configuration File

Create `.claude-agent.yaml` in your project for persistent settings:

```yaml
spec_file: ./docs/SPEC.md
features: 75
stack: python

agent:
  model: claude-opus-4-5-20251101
  max_iterations: 10

security:
  extra_commands:
    - docker
    - make
```

### Feature List Evaluation

The agent can evaluate feature list quality for Best-of-N sampling:

```yaml
evaluation:
  coverage_weight: 0.4      # How well features cover spec requirements
  testability_weight: 0.3   # Whether features have concrete test steps
  granularity_weight: 0.2   # Whether features are right-sized
  independence_weight: 0.1  # Whether features can be implemented independently
  min_acceptable_score: 0.6 # Threshold for acceptable feature lists
```

Weights must sum to 1.0. The evaluation scores each feature list on four criteria and produces a weighted aggregate score from 0.0 to 1.0.

## Tech Stack Support

Auto-detected from project files:

| Stack | Markers | Commands |
|-------|---------|----------|
| Node.js | package.json, tsconfig.json | npm, npx, node, yarn |
| Python | pyproject.toml, requirements.txt | python, pip, uv, pytest |

## Security

Defense-in-depth security model:

1. **OS-level sandbox**: Bash commands run in isolated environment
2. **Filesystem restrictions**: File operations limited to project directory
3. **Command allowlist**: Only whitelisted commands can execute

## Timing Expectations

- **First session**: 10-20+ minutes (generating feature list)
- **Each coding session**: 5-15 minutes per feature
- **Full project**: Hours across many sessions (depends on feature count)

Use `--features 20` for faster demos.

## License

MIT
