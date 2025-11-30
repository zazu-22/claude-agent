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
- Git commits - Records implementation history

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

# Spec workflow commands
claude-agent spec create   # Generate spec from goal
claude-agent spec validate # Validate spec for completeness
claude-agent spec decompose # Break spec into features
claude-agent spec auto     # Run full workflow (create → validate → decompose)
claude-agent spec status   # Show spec workflow status
```

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
