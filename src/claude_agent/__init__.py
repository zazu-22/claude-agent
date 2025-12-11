"""
Claude Agent - Autonomous coding agent CLI powered by Claude.

A tool for running long-running autonomous coding sessions with
persistent progress tracking across multiple context windows.
"""

__version__ = "0.7.1"

# Structured error handling exports (F1)
from claude_agent.structured_errors import (
    StructuredError,
    ErrorType,
    ErrorCategory,
)

# State management exports (F3)
from claude_agent.state import (
    WorkflowState,
    get_state_dir,
    get_workflow_dir,
    load_workflow_state,
    save_workflow_state,
)

__all__ = [
    "__version__",
    # Structured errors
    "StructuredError",
    "ErrorType",
    "ErrorCategory",
    # State management
    "WorkflowState",
    "get_state_dir",
    "get_workflow_dir",
    "load_workflow_state",
    "save_workflow_state",
]
