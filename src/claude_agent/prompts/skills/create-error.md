# Create Error Skill

## Purpose

This skill documents when and how to create structured errors using the
`StructuredError` system and factory functions. Proper error creation enables
intelligent recovery, accurate logging, and better debugging for autonomous
coding sessions.

## When to Use

Use this skill when:
- An error condition occurs that should be persisted to workflow state
- You need to classify an error for automatic retry or human intervention
- Security blocks occur from the command allowlist
- Feature validation fails
- Files or resources are not found
- Git operations fail
- Tests, linting, or type checking fails
- Agent sessions timeout

## Pattern

### Error Type Selection

Choose the appropriate `ErrorType` based on the expected recovery behavior:

| ErrorType | When to Use | Behavior |
|-----------|-------------|----------|
| **RETRY** | Transient errors that may succeed on retry | Auto-retry up to 3 times |
| **MANUAL** | Errors requiring human decision or input | Pause workflow, display guidance |
| **FATAL** | Unrecoverable errors that should stop execution | Abort with clear message |
| **TIMEOUT** | Operations that exceeded time limits | Log and escalate |

### Error Category Selection

Choose the category that best describes the error source:

| Category | Examples |
|----------|----------|
| **NETWORK** | API failures, connection refused, DNS errors |
| **AUTH** | Permission denied, token expired, invalid credentials |
| **LOGIC** | Lint failures, type errors, test failures |
| **CONFIG** | Invalid configuration values, missing env vars |
| **RESOURCE** | Missing files, branches, dependencies |
| **SECURITY** | Command blocked by security hook |
| **VALIDATION** | Feature validation failures |

### Factory Functions

Use the provided factory functions instead of creating `StructuredError` directly:

#### `error_security_block(command: str, reason: str)`

**When to use:** A command was blocked by the security allowlist.

```python
from claude_agent.structured_errors import error_security_block

# Command was not in the allowlist
err = error_security_block(
    command="rm -rf /",
    reason="Command 'rm' not in allowed commands list"
)
# Returns: StructuredError(type=MANUAL, category=SECURITY)
# recovery_hint includes path to .claude-agent.yaml
```

#### `error_validation_failed(feature_index: int, reason: str)`

**When to use:** A feature failed validation testing.

```python
from claude_agent.structured_errors import error_validation_failed

# Feature didn't pass validation
err = error_validation_failed(
    feature_index=5,
    reason="Login button click handler not responding"
)
# Returns: StructuredError(type=MANUAL, category=VALIDATION)
# Context includes feature_index for workflow tracking
```

#### `error_file_not_found(path: str)`

**When to use:** A required file or directory doesn't exist.

```python
from claude_agent.structured_errors import error_file_not_found

# File was expected but missing
err = error_file_not_found(path="/path/to/feature_list.json")
# Returns: StructuredError(type=MANUAL, category=RESOURCE)
# recovery_hint suggests checking the path
```

#### `error_git_operation(operation: str, details: str)`

**When to use:** A git command failed. Note: git errors are often transient.

```python
from claude_agent.structured_errors import error_git_operation

# Git push failed
err = error_git_operation(
    operation="push",
    details="rejected (non-fast-forward)"
)
# Returns: StructuredError(type=RETRY, category=RESOURCE)
# recovery_hint suggests git status check
```

#### `error_test_failure(test_type: str, details: str)`

**When to use:** Linting, type checking, or tests failed.

```python
from claude_agent.structured_errors import error_test_failure

# pytest failed
err = error_test_failure(
    test_type="pytest",
    details="3 tests failed in test_state.py"
)
# Returns: StructuredError(type=MANUAL, category=LOGIC)
# recovery_hint suggests reviewing test output
```

#### `error_agent_timeout(agent_type: str, duration_seconds: int)`

**When to use:** An agent session exceeded its time limit.

```python
from claude_agent.structured_errors import error_agent_timeout

# Coding agent timed out
err = error_agent_timeout(
    agent_type="coding",
    duration_seconds=3600
)
# Returns: StructuredError(type=TIMEOUT, category=RESOURCE)
# recovery_hint suggests increasing timeout or simplifying task
```

### Manual StructuredError Creation

For errors not covered by factory functions:

```python
from claude_agent.structured_errors import (
    StructuredError,
    ErrorType,
    ErrorCategory,
)
from datetime import datetime

err = StructuredError(
    type=ErrorType.RETRY,
    category=ErrorCategory.NETWORK,
    message="API rate limit exceeded",
    recovery_hint="Wait 60 seconds before retrying",
    timestamp=datetime.now(),
    context={
        "api_endpoint": "/api/v1/users",
        "rate_limit_remaining": 0,
        "reset_time": "2024-01-15T10:30:00Z"
    }
)
```

### Persisting Errors to Workflow State

Errors should be persisted to workflow state for recovery:

```python
from claude_agent.state import load_workflow_state, save_workflow_state

# Load current state
state = load_workflow_state(project_dir)
if state:
    # Set the error
    state.last_error = err.to_dict()
    save_workflow_state(state)
```

### Converting to ActionableError for CLI Display

When displaying to users:

```python
# Convert for human-readable CLI output
actionable = err.to_actionable_error()
# ActionableError has formatted message and context
```

### Error Checking Methods

After creating an error, use these methods to determine handling:

```python
if err.is_retryable():
    # Auto-retry up to 3 times
    retry_count += 1
    if retry_count <= 3:
        continue_operation()

if err.requires_human():
    # Pause and wait for human input
    display_guidance(err.recovery_hint)
    pause_workflow()
```

## Decision Tree

When an error occurs, follow this decision tree:

```
Error occurred
    │
    ├── Is it a security block?
    │   └── Yes → error_security_block()
    │
    ├── Is it a feature validation failure?
    │   └── Yes → error_validation_failed()
    │
    ├── Is a file/resource missing?
    │   └── Yes → error_file_not_found()
    │
    ├── Is it a git operation failure?
    │   └── Yes → error_git_operation()
    │
    ├── Is it a test/lint/type failure?
    │   └── Yes → error_test_failure()
    │
    ├── Did an agent session timeout?
    │   └── Yes → error_agent_timeout()
    │
    └── None of the above?
        └── Create StructuredError manually
            - Choose ErrorType based on recovery strategy
            - Choose ErrorCategory based on error source
            - Provide actionable recovery_hint
            - Include relevant context for debugging
```

## Escalation

**When to escalate error creation to human review:**
- The error category is unclear or could be multiple categories
- The recovery strategy is ambiguous
- The error might indicate a deeper systemic issue
- Custom factory function might be needed for recurring error pattern

**Escalation format:**
```markdown
## NEW ERROR PATTERN IDENTIFIED

**Observed Error:** [description]
**Current Classification:** [type/category if attempted]
**Uncertainty:** [why classification is unclear]
**Suggested Action:** [create factory function / clarify requirements]
```
