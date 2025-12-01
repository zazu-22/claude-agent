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
- `spec-review.md` - Optional spec review output

## Directory Structure

```
claude-agent/
├── src/claude_agent/      # Main package
│   ├── __init__.py        # Version and exports
│   ├── __main__.py        # Entry point
│   ├── cli.py             # Click CLI commands
│   ├── agent.py           # Agent session logic
│   ├── client.py          # Claude SDK client creation
│   ├── config.py          # Configuration loading
│   ├── detection.py       # Tech stack detection
│   ├── progress.py        # Progress tracking
│   ├── security.py        # Security hooks
│   ├── wizard.py          # Interactive spec wizard
│   └── prompts/           # Agent prompts
│       ├── __init__.py
│       ├── loader.py      # Prompt loading utilities
│       ├── coding.md      # Coding agent prompt
│       ├── initializer.md # Initializer agent prompt
│       ├── review.md      # Spec review prompt
│       └── validator.md   # Validator agent prompt
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

### Two-Agent Pattern
The agent uses distinct personas for different phases:

1. **Initializer Agent** (`prompts/initializer.md`)
   - Reads spec, creates `feature_list.json`
   - Sets up project structure
   - Runs once at project start

2. **Coding Agent** (`prompts/coding.md`)
   - Implements features from feature list
   - Tests through browser automation
   - Commits progress, updates notes
   - Runs repeatedly until all features pass

3. **Validator Agent** (`prompts/validator.md`)
   - Reviews completed implementation
   - Tests through actual UI
   - Issues APPROVED/REJECTED/CONTINUE/NEEDS_VERIFICATION verdict
   - Runs when all automated tests pass

### Session Flow
```
Start → Is feature_list.json present?
  No  → Run Initializer Agent → Create feature list
  Yes → Check test status
        All automated pass? → Run Validator
        Otherwise → Run Coding Agent → Implement features
```

### Configuration Priority
1. CLI arguments (highest)
2. Config file (`.claude-agent.yaml`)
3. Defaults (lowest)

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

## Debugging Tips

### Common Issues
- **"Command not allowed"**: Add to allowlist in `detection.py` or config
- **"No spec provided"**: Use `--spec` or `--goal` flags
- **Validator fails to parse**: Check JSON format in validator response
- **Session hangs**: First session can take 10-20+ minutes

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
