"""
Structured Logging and Observability
====================================

Comprehensive structured logging system for claude-agent that enables:
- Post-mortem debugging of agent sessions
- Tracking of security decisions and blocks
- Session statistics and performance metrics
- Real-time verbose output during execution
- Historical log viewing and filtering
"""

import json
import os
import platform
import sys
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, Any

from claude_agent.progress import atomic_write
from claude_agent import __version__ as SDK_VERSION


class LogLevel(str, Enum):
    """Log levels for event filtering.

    Level hierarchy: DEBUG < INFO < GATE < WARNING < ERROR

    GATE is a new level for phase transition events (DR-015).
    It's more significant than INFO but not a problem like WARNING.
    """

    DEBUG = "debug"
    INFO = "info"
    GATE = "gate"  # Phase transition events (DR-015)
    WARNING = "warning"
    ERROR = "error"


# Log level hierarchy for filtering (DR-015: DEBUG < INFO < GATE < WARNING < ERROR)
LOG_LEVEL_ORDER = [LogLevel.DEBUG, LogLevel.INFO, LogLevel.GATE, LogLevel.WARNING, LogLevel.ERROR]


class EventType(str, Enum):
    """Types of events that can be logged.

    New event types added for Milestone 5 (F5.1):
    - PHASE_ENTER: Agent enters new phase (GATE level)
    - PHASE_EXIT: Agent exits phase (GATE level)
    - ERROR_CLASSIFIED: Structured error logged (ERROR level)
    - HOOK_FIRED: Hook executed (INFO level)
    """

    SESSION_START = "session_start"
    SESSION_END = "session_end"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SECURITY_BLOCK = "security_block"
    SECURITY_ALLOW = "security_allow"
    FEATURE_COMPLETE = "feature_complete"
    FEATURE_FAILED = "feature_failed"
    VALIDATION_START = "validation_start"
    VALIDATION_RESULT = "validation_result"
    ERROR = "error"
    LOG_MESSAGE = "log_message"
    # New event types for phase tracking and hooks (F5.1)
    PHASE_ENTER = "phase_enter"
    PHASE_EXIT = "phase_exit"
    ERROR_CLASSIFIED = "error_classified"
    HOOK_FIRED = "hook_fired"


# Map event types to their default log levels
EVENT_LEVELS: dict[EventType, LogLevel] = {
    EventType.SESSION_START: LogLevel.INFO,
    EventType.SESSION_END: LogLevel.INFO,
    EventType.TOOL_CALL: LogLevel.DEBUG,
    EventType.TOOL_RESULT: LogLevel.DEBUG,
    EventType.SECURITY_BLOCK: LogLevel.WARNING,
    EventType.SECURITY_ALLOW: LogLevel.DEBUG,
    EventType.FEATURE_COMPLETE: LogLevel.INFO,
    EventType.FEATURE_FAILED: LogLevel.WARNING,
    EventType.VALIDATION_START: LogLevel.INFO,
    EventType.VALIDATION_RESULT: LogLevel.INFO,
    EventType.ERROR: LogLevel.ERROR,
    EventType.LOG_MESSAGE: LogLevel.INFO,
    # New event types with levels per DR-015
    EventType.PHASE_ENTER: LogLevel.GATE,
    EventType.PHASE_EXIT: LogLevel.GATE,
    EventType.ERROR_CLASSIFIED: LogLevel.ERROR,
    EventType.HOOK_FIRED: LogLevel.INFO,
}


@dataclass
class LogEntry:
    """A single log entry.

    Extended with phase field for phase tracking (DR-016).
    """

    ts: datetime
    level: LogLevel
    event: EventType
    session_id: str
    data: dict[str, Any] = field(default_factory=dict)
    phase: str = ""  # Current phase when entry was logged (DR-016)

    def to_json(self) -> str:
        """Serialize to JSON string for JSONL format."""
        return json.dumps(
            {
                "ts": self.ts.isoformat(),
                "level": self.level.value,
                "event": self.event.value,
                "session_id": self.session_id,
                "phase": self.phase,  # Include phase in output (DR-016)
                **self.data,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, json_str: str) -> "LogEntry":
        """Deserialize from JSON string.

        Backward compatible with existing logs (DR-019).
        """
        data = json.loads(json_str)
        ts = datetime.fromisoformat(data.pop("ts"))
        level_str = data.pop("level")
        # Handle new GATE level and backward compatibility
        try:
            level = LogLevel(level_str)
        except ValueError:
            # Fall back to INFO for unknown levels (backward compatibility)
            level = LogLevel.INFO
        event_str = data.pop("event")
        try:
            event = EventType(event_str)
        except ValueError:
            # Fall back to LOG_MESSAGE for unknown event types
            event = EventType.LOG_MESSAGE
        session_id = data.pop("session_id")
        # Handle missing phase field for old logs (DR-016, DR-019)
        phase = data.pop("phase", "")
        return cls(ts=ts, level=level, event=event, session_id=session_id, data=data, phase=phase)


@dataclass
class SessionStats:
    """Statistics for a single agent session."""

    session_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    turns_used: int = 0
    tools_called: dict[str, int] = field(default_factory=dict)
    security_blocks: int = 0
    features_completed: list[int] = field(default_factory=list)
    features_failed: list[int] = field(default_factory=list)
    errors_encountered: int = 0
    agent_type: str = "coding"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "turns_used": self.turns_used,
            "tools_called": self.tools_called,
            "security_blocks": self.security_blocks,
            "features_completed": self.features_completed,
            "features_failed": self.features_failed,
            "errors_encountered": self.errors_encountered,
            "agent_type": self.agent_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionStats":
        """Create from dictionary."""
        return cls(
            session_id=data["session_id"],
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=(
                datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None
            ),
            duration_seconds=data.get("duration_seconds"),
            turns_used=data.get("turns_used", 0),
            tools_called=data.get("tools_called", {}),
            security_blocks=data.get("security_blocks", 0),
            features_completed=data.get("features_completed", []),
            features_failed=data.get("features_failed", []),
            errors_encountered=data.get("errors_encountered", 0),
            agent_type=data.get("agent_type", "coding"),
        )


@dataclass
class LoggingConfig:
    """Configuration for the logging system."""

    enabled: bool = True
    level: LogLevel = LogLevel.INFO
    include_tool_results: bool = False
    include_allowed_commands: bool = False
    max_summary_length: int = 500
    # Rotation settings
    max_size_mb: int = 10
    max_files: int = 5
    retention_days: int = 30


def generate_session_id() -> str:
    """Generate a short unique session ID."""
    return uuid.uuid4().hex[:12]


def truncate_string(s: str, max_length: int) -> str:
    """Truncate a string to max_length, adding ellipsis if truncated."""
    if len(s) <= max_length:
        return s
    return s[: max_length - 3] + "..."


def get_environment_info() -> dict[str, str]:
    """Get environment information for logging.

    Returns:
        Dict with python_version, sdk_version, and os fields.
    """
    return {
        "python_version": platform.python_version(),
        "sdk_version": SDK_VERSION,
        "os": platform.system().lower(),
    }


class AgentLogger:
    """
    Main logger for agent sessions.

    Handles JSONL log file writing with rotation and buffering.

    Extended for Milestone 5 with:
    - Phase tracking (current_phase instance variable) per DR-016
    - phase_enter() and phase_exit() methods
    - log_error_classified() for StructuredError integration
    - log_hook_fired() for hook execution tracking
    """

    def __init__(
        self,
        project_dir: Path,
        config: Optional[LoggingConfig] = None,
        verbose: bool = False,
    ):
        """
        Initialize the logger.

        Args:
            project_dir: Project directory (logs go to .claude-agent/logs/ or XDG)
            config: Logging configuration
            verbose: Enable real-time stderr output
        """
        self.project_dir = project_dir
        self.config = config or LoggingConfig()
        self.verbose = verbose
        self.session_id: Optional[str] = None
        self._disabled = False
        self._buffer: list[str] = []
        self._buffer_size = 10
        self._last_flush = datetime.now(timezone.utc)

        # Phase tracking (DR-016)
        self.current_phase: str = ""
        self._phase_start_time: Optional[datetime] = None

        # Circular buffer for recent events (for error context)
        # Uses deque with maxlen for efficient O(1) operations
        self._recent_events: deque[str] = deque(maxlen=5)

        # Log directory and file paths (DR-020: XDG support)
        if self.config.use_xdg_logs:
            # Use XDG state directory for logs
            from claude_agent.state import get_logs_dir, get_project_hash
            self._log_dir = get_logs_dir()
            # Include project hash in filename for isolation
            project_hash = get_project_hash(project_dir)
            self._log_file = self._log_dir / f"agent-{project_hash}.log"
            self._stats_file = self._log_dir / f"sessions-{project_hash}.json"
        else:
            # Fall back to project-local logs
            self._log_dir = project_dir / ".claude-agent" / "logs"
            self._log_file = self._log_dir / "agent.log"
            self._stats_file = self._log_dir / "sessions.json"

        # Try to create log directory
        if self.config.enabled:
            try:
                self._log_dir.mkdir(parents=True, exist_ok=True)
                # Set file permissions on Unix
                if hasattr(os, "chmod"):
                    try:
                        os.chmod(self._log_dir, 0o700)
                    except OSError:
                        pass
            except OSError as e:
                # Directory creation failed - disable logging silently
                self._disabled = True
                print(
                    f"Warning: Could not create log directory {self._log_dir}: {e}",
                    file=sys.stderr,
                )

    def start_session(
        self,
        iteration: int,
        model: str,
        stack: str,
        agent_type: str,
    ) -> str:
        """
        Start a new logging session.

        Args:
            iteration: Session iteration number
            model: Claude model being used
            stack: Tech stack (node, python, etc.)
            agent_type: Type of agent (initializer, coding, validator)

        Returns:
            The generated session ID
        """
        self.session_id = generate_session_id()

        # Get environment info for this session
        env_info = get_environment_info()

        self.log_event(
            EventType.SESSION_START,
            iteration=iteration,
            model=model,
            stack=stack,
            agent_type=agent_type,
            environment=env_info,
        )

        return self.session_id

    def end_session(
        self,
        turns_used: int,
        status: str,
    ) -> None:
        """
        End the current logging session.

        Args:
            turns_used: Number of turns used in the session
            status: Final status (continue, error, etc.)
        """
        if not self.session_id:
            return

        start_entry = self._find_session_start()
        duration_seconds = None
        if start_entry:
            duration_seconds = (
                datetime.now(timezone.utc) - start_entry.ts
            ).total_seconds()

        self.log_event(
            EventType.SESSION_END,
            turns_used=turns_used,
            duration_seconds=duration_seconds,
            status=status,
        )

        # Flush any remaining buffered entries
        self._flush_buffer()

        self.session_id = None

    def log_event(
        self,
        event_type: EventType,
        level: Optional[LogLevel] = None,
        **data: Any,
    ) -> None:
        """
        Log an event.

        Args:
            event_type: Type of event
            level: Log level (defaults based on event type)
            **data: Event-specific data fields
        """
        if self._disabled or not self.config.enabled:
            return

        # Use default level for event type if not specified
        if level is None:
            level = EVENT_LEVELS.get(event_type, LogLevel.INFO)

        # Skip if below configured level (using updated LOG_LEVEL_ORDER with GATE)
        if LOG_LEVEL_ORDER.index(level) < LOG_LEVEL_ORDER.index(self.config.level):
            return

        # Truncate long string fields
        truncated_data = {}
        for key, value in data.items():
            if isinstance(value, str) and len(value) > self.config.max_summary_length:
                truncated_data[key] = truncate_string(
                    value, self.config.max_summary_length
                )
            else:
                truncated_data[key] = value

        entry = LogEntry(
            ts=datetime.now(timezone.utc),
            level=level,
            event=event_type,
            session_id=self.session_id or "unknown",
            data=truncated_data,
            phase=self.current_phase,  # Include current phase (DR-016)
        )

        # Add to buffer
        self._buffer.append(entry.to_json())

        # Track recent events for error context (exclude errors themselves)
        # Format: "event_type:tool_name" for debugging context
        if event_type != EventType.ERROR:
            event_summary = f"{event_type.value}:{truncated_data.get('tool_name', '')}"
            self._recent_events.append(event_summary)  # deque auto-maintains maxlen

        # Verbose output to stderr
        if self.verbose:
            self._print_verbose(entry)

        # Flush if buffer is full or time elapsed
        if len(self._buffer) >= self._buffer_size:
            self._flush_buffer()
        elif (datetime.now(timezone.utc) - self._last_flush).total_seconds() >= 1:
            self._flush_buffer()

    def log_tool_call(self, tool_name: str, input_data: Any) -> None:
        """Log a tool call."""
        input_summary = str(input_data)
        self.log_event(
            EventType.TOOL_CALL,
            tool_name=tool_name,
            input_summary=truncate_string(input_summary, self.config.max_summary_length),
        )

    def log_tool_result(
        self, tool_name: str, is_error: bool, result: Any = None
    ) -> None:
        """Log a tool result."""
        if not self.config.include_tool_results and result is not None:
            result_summary = "[result truncated]"
        else:
            result_summary = truncate_string(
                str(result) if result else "", self.config.max_summary_length
            )

        self.log_event(
            EventType.TOOL_RESULT,
            tool_name=tool_name,
            is_error=is_error,
            result_summary=result_summary,
        )

    def log_security_block(
        self,
        command: str,
        reason: str,
        stack: str,
        error_type: Optional[str] = None,
        error_category: Optional[str] = None,
    ) -> None:
        """Log a security block event.

        Args:
            command: The command that was blocked
            reason: Why it was blocked
            stack: Tech stack (for allowlist context)
            error_type: StructuredError type (e.g., "manual") - optional for backward compatibility
            error_category: StructuredError category (e.g., "security") - optional for backward compatibility
        """
        data = {
            "command": truncate_string(command, self.config.max_summary_length),
            "reason": reason,
            "stack": stack,
        }
        # Include structured error info if provided (DR-018)
        if error_type:
            data["error_type"] = error_type
        if error_category:
            data["error_category"] = error_category

        self.log_event(EventType.SECURITY_BLOCK, **data)

    def log_security_allow(self, command: str, stack: str) -> None:
        """Log a security allow event (verbose mode only)."""
        if self.config.include_allowed_commands or self.verbose:
            self.log_event(
                EventType.SECURITY_ALLOW,
                command=truncate_string(command, self.config.max_summary_length),
                stack=stack,
            )

    def log_feature_complete(self, index: int, description: str) -> None:
        """Log a feature completion event."""
        self.log_event(
            EventType.FEATURE_COMPLETE,
            index=index,
            description=truncate_string(description, self.config.max_summary_length),
        )

    def log_feature_failed(
        self, index: int, description: str, reason: str
    ) -> None:
        """Log a feature failure event."""
        self.log_event(
            EventType.FEATURE_FAILED,
            index=index,
            description=truncate_string(description, self.config.max_summary_length),
            reason=reason,
        )

    def log_validation_start(self, attempt: int) -> None:
        """Log validation start event."""
        self.log_event(
            EventType.VALIDATION_START,
            attempt=attempt,
        )

    def log_validation_result(
        self, verdict: str, tests_verified: int, rejected_count: int
    ) -> None:
        """Log validation result event."""
        self.log_event(
            EventType.VALIDATION_RESULT,
            verdict=verdict,
            tests_verified=tests_verified,
            rejected_count=rejected_count,
        )

    def log_error(
        self,
        error_type: str,
        message: str,
        context: Optional[dict[str, Any]] = None,
        stack_trace: Optional[str] = None,
    ) -> None:
        """Log an error event."""
        self.log_event(
            EventType.ERROR,
            error_type=error_type,
            message=truncate_string(message, self.config.max_summary_length),
            context=context or {},
            stack_trace=stack_trace,
            recent_events=list(self._recent_events),  # Include recent event context
        )

    def debug(self, message: str) -> None:
        """Log a debug message."""
        self.log_event(
            EventType.LOG_MESSAGE,
            level=LogLevel.DEBUG,
            message=truncate_string(message, self.config.max_summary_length),
        )

    def info(self, message: str) -> None:
        """Log an info message."""
        self.log_event(
            EventType.LOG_MESSAGE,
            level=LogLevel.INFO,
            message=truncate_string(message, self.config.max_summary_length),
        )

    def warning(self, message: str) -> None:
        """Log a warning message."""
        self.log_event(
            EventType.LOG_MESSAGE,
            level=LogLevel.WARNING,
            message=truncate_string(message, self.config.max_summary_length),
        )

    def error(self, message: str) -> None:
        """Log an error message (simple version without context)."""
        self.log_event(
            EventType.LOG_MESSAGE,
            level=LogLevel.ERROR,
            message=truncate_string(message, self.config.max_summary_length),
        )

    # ==========================================================================
    # Phase Tracking Methods (F5.1, DR-015, DR-016)
    # ==========================================================================

    def phase_enter(self, phase: str, **context: Any) -> None:
        """
        Log phase entry event and set current phase.

        Args:
            phase: Phase name (e.g., "initializing", "coding", "validating")
            **context: Additional context to log with the event
        """
        self.current_phase = phase
        self._phase_start_time = datetime.now(timezone.utc)

        self.log_event(
            EventType.PHASE_ENTER,
            phase=phase,
            **context,
        )

    def phase_exit(self, phase: str, **context: Any) -> None:
        """
        Log phase exit event with duration and clear current phase.

        Args:
            phase: Phase name being exited
            **context: Additional context to log with the event
        """
        # Calculate duration if we have a start time
        duration_seconds = None
        if self._phase_start_time:
            duration_seconds = (
                datetime.now(timezone.utc) - self._phase_start_time
            ).total_seconds()

        self.log_event(
            EventType.PHASE_EXIT,
            phase=phase,
            duration_seconds=duration_seconds,
            **context,
        )

        # Clear phase tracking
        self.current_phase = ""
        self._phase_start_time = None

    def log_error_classified(self, error: Any) -> None:
        """
        Log a classified/structured error.

        Args:
            error: A StructuredError instance (imported dynamically to avoid circular import)

        Note:
            This method expects an object with type, category, message, and recovery_hint
            attributes. It's designed to work with StructuredError from structured_errors.py.
        """
        # Extract error attributes (duck-typed to avoid circular import)
        error_type = getattr(error, "type", None)
        error_category = getattr(error, "category", None)
        message = getattr(error, "message", str(error))
        recovery_hint = getattr(error, "recovery_hint", None)
        error_context = getattr(error, "context", {})

        self.log_event(
            EventType.ERROR_CLASSIFIED,
            error_type=error_type.value if hasattr(error_type, "value") else str(error_type),
            error_category=error_category.value if hasattr(error_category, "value") else str(error_category),
            message=truncate_string(message, self.config.max_summary_length),
            recovery_hint=recovery_hint,
            error_context=error_context,
        )

    def log_hook_fired(self, hook_name: str, result: str) -> None:
        """
        Log a hook execution event.

        Args:
            hook_name: Name of the hook (e.g., "session-start", "session-stop")
            result: Result of the hook execution (e.g., "success", "error", "{}")
        """
        self.log_event(
            EventType.HOOK_FIRED,
            hook_name=hook_name,
            result=truncate_string(result, self.config.max_summary_length),
        )

    def _print_verbose(self, entry: LogEntry) -> None:
        """Print formatted log entry to stderr for verbose mode."""
        # Check NO_COLOR environment variable
        use_color = os.environ.get("NO_COLOR") is None

        timestamp = entry.ts.strftime("%H:%M:%S")
        event_name = entry.event.value.upper()

        # Color codes (DR-015: GATE level added with cyan color)
        colors = {
            LogLevel.DEBUG: "\033[90m",  # Gray
            LogLevel.INFO: "\033[0m",  # Default
            LogLevel.GATE: "\033[36m",  # Cyan for phase transitions
            LogLevel.WARNING: "\033[33m",  # Yellow
            LogLevel.ERROR: "\033[31m",  # Red
        }
        reset = "\033[0m"

        color = colors.get(entry.level, "") if use_color else ""
        end_color = reset if use_color else ""

        # Format based on event type
        if entry.event == EventType.SESSION_START:
            details = f"iter={entry.data.get('iteration')} model={entry.data.get('model')} agent={entry.data.get('agent_type')}"
        elif entry.event == EventType.TOOL_CALL:
            details = f"{entry.data.get('tool_name')}: {entry.data.get('input_summary', '')[:50]}"
        elif entry.event == EventType.TOOL_RESULT:
            status = "error" if entry.data.get("is_error") else "success"
            details = f"{entry.data.get('tool_name')}: [{status}]"
        elif entry.event == EventType.SECURITY_BLOCK:
            details = f"{entry.data.get('command', '')[:50]} -> \"{entry.data.get('reason', '')[:50]}\""
        elif entry.event == EventType.SECURITY_ALLOW:
            details = entry.data.get("command", "")[:50]
        elif entry.event == EventType.FEATURE_COMPLETE:
            details = f"#{entry.data.get('index')}: {entry.data.get('description', '')[:40]}"
        elif entry.event == EventType.FEATURE_FAILED:
            details = f"#{entry.data.get('index')}: {entry.data.get('reason', '')[:40]}"
        elif entry.event == EventType.SESSION_END:
            details = f"turns={entry.data.get('turns_used')} status={entry.data.get('status')}"
        elif entry.event == EventType.LOG_MESSAGE:
            details = entry.data.get("message", "")[:60]
        # New event types for Milestone 5 (F5.1)
        elif entry.event == EventType.PHASE_ENTER:
            details = f"-> {entry.data.get('phase', '')}"
        elif entry.event == EventType.PHASE_EXIT:
            duration = entry.data.get('duration_seconds')
            duration_str = f" ({duration:.1f}s)" if duration else ""
            details = f"<- {entry.data.get('phase', '')}{duration_str}"
        elif entry.event == EventType.ERROR_CLASSIFIED:
            details = f"[{entry.data.get('error_type', '')}:{entry.data.get('error_category', '')}] {entry.data.get('message', '')[:40]}"
        elif entry.event == EventType.HOOK_FIRED:
            details = f"{entry.data.get('hook_name', '')}: {entry.data.get('result', '')[:30]}"
        else:
            details = str(entry.data)[:60]

        print(
            f"{color}[{timestamp}] {event_name:<16} {details}{end_color}",
            file=sys.stderr,
        )

    def _flush_buffer(self) -> None:
        """Flush buffered log entries to disk."""
        if not self._buffer or self._disabled:
            return

        try:
            # Check if rotation needed before writing
            self._maybe_rotate()

            # Append to log file
            with open(self._log_file, "a", encoding="utf-8") as f:
                for entry in self._buffer:
                    f.write(entry + "\n")

            self._buffer.clear()
            self._last_flush = datetime.now(timezone.utc)

        except OSError as e:
            # Log write failed - disable logging
            self._disabled = True
            print(f"Warning: Log write failed: {e}", file=sys.stderr)
            self._buffer.clear()

    def _maybe_rotate(self) -> None:
        """Rotate log file if it exceeds max size."""
        if not self._log_file.exists():
            return

        try:
            size_mb = self._log_file.stat().st_size / (1024 * 1024)
            if size_mb < self.config.max_size_mb:
                # Even if no rotation needed, clean up old files by retention
                self._cleanup_old_files()
                return

            # Rotate files
            for i in range(self.config.max_files - 1, 0, -1):
                old_path = self._log_dir / f"agent.log.{i}"
                new_path = self._log_dir / f"agent.log.{i + 1}"
                if old_path.exists():
                    if i + 1 >= self.config.max_files:
                        old_path.unlink()  # Delete oldest
                    else:
                        old_path.rename(new_path)

            # Rename current log
            rotated_path = self._log_dir / "agent.log.1"
            self._log_file.rename(rotated_path)

            # Clean up files older than retention_days
            self._cleanup_old_files()

        except OSError:
            pass  # Rotation failed - continue with current file

    def _cleanup_old_files(self) -> None:
        """Delete rotated log files older than retention_days."""
        if self.config.retention_days <= 0:
            return

        try:
            now = datetime.now(timezone.utc)
            cutoff_seconds = self.config.retention_days * 86400

            # Check all rotated files
            for i in range(1, self.config.max_files + 1):
                log_path = self._log_dir / f"agent.log.{i}"
                if not log_path.exists():
                    continue

                try:
                    mtime = datetime.fromtimestamp(
                        log_path.stat().st_mtime, tz=timezone.utc
                    )
                    age_seconds = (now - mtime).total_seconds()
                    if age_seconds > cutoff_seconds:
                        log_path.unlink()
                except OSError:
                    continue
        except OSError:
            pass  # Cleanup failed - not critical

    def _find_session_start(self) -> Optional[LogEntry]:
        """Find the session start entry for the current session."""
        if not self.session_id or not self._log_file.exists():
            return None

        try:
            with open(self._log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = LogEntry.from_json(line.strip())
                        if (
                            entry.session_id == self.session_id
                            and entry.event == EventType.SESSION_START
                        ):
                            return entry
                    except (json.JSONDecodeError, ValueError, KeyError):
                        continue
        except OSError:
            pass

        return None


class SessionStatsTracker:
    """
    Tracks statistics for a single session and persists to sessions.json.
    """

    def __init__(self, project_dir: Path, session_id: str, agent_type: str):
        """
        Initialize stats tracker for a session.

        Args:
            project_dir: Project directory
            session_id: Session ID to track
            agent_type: Type of agent (initializer, coding, validator)
        """
        self.project_dir = project_dir
        self._stats_file = project_dir / ".claude-agent" / "logs" / "sessions.json"
        self.stats = SessionStats(
            session_id=session_id,
            start_time=datetime.now(timezone.utc),
            agent_type=agent_type,
        )

    def record_tool_call(self, tool_name: str) -> None:
        """Record a tool call."""
        self.stats.tools_called[tool_name] = (
            self.stats.tools_called.get(tool_name, 0) + 1
        )

    def record_security_block(self) -> None:
        """Record a security block."""
        self.stats.security_blocks += 1

    def record_feature_complete(self, index: int) -> None:
        """Record a completed feature."""
        if index not in self.stats.features_completed:
            self.stats.features_completed.append(index)

    def record_feature_failed(self, index: int) -> None:
        """Record a failed feature."""
        if index not in self.stats.features_failed:
            self.stats.features_failed.append(index)

    def record_error(self) -> None:
        """Record an error."""
        self.stats.errors_encountered += 1

    def set_turns_used(self, turns: int) -> None:
        """Set the number of turns used."""
        self.stats.turns_used = turns

    def save(self) -> None:
        """Save session statistics to sessions.json."""
        self.stats.end_time = datetime.now(timezone.utc)
        if self.stats.start_time:
            self.stats.duration_seconds = (
                self.stats.end_time - self.stats.start_time
            ).total_seconds()

        # Load existing stats
        sessions_data = {"sessions": [], "aggregate": {}}
        if self._stats_file.exists():
            try:
                with open(self._stats_file, "r", encoding="utf-8") as f:
                    sessions_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        # Add new session
        sessions_data["sessions"].append(self.stats.to_dict())

        # Update aggregates
        total_sessions = len(sessions_data["sessions"])
        total_turns = sum(s.get("turns_used", 0) for s in sessions_data["sessions"])
        total_duration = sum(
            s.get("duration_seconds", 0) or 0 for s in sessions_data["sessions"]
        )
        total_features = sum(
            len(s.get("features_completed", [])) for s in sessions_data["sessions"]
        )
        total_blocks = sum(
            s.get("security_blocks", 0) for s in sessions_data["sessions"]
        )

        sessions_data["aggregate"] = {
            "total_sessions": total_sessions,
            "total_turns": total_turns,
            "total_duration_seconds": total_duration,
            "total_features_completed": total_features,
            "total_security_blocks": total_blocks,
        }

        # Ensure directory exists
        self._stats_file.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write
        content = json.dumps(sessions_data, indent=2, ensure_ascii=False)
        atomic_write(self._stats_file, content)


class LogReader:
    """
    Reads and queries log entries from log files.
    """

    def __init__(self, project_dir: Path):
        """
        Initialize log reader.

        Args:
            project_dir: Project directory containing .claude-agent/logs/
        """
        self.project_dir = project_dir
        self._log_dir = project_dir / ".claude-agent" / "logs"
        self._log_file = self._log_dir / "agent.log"

    def read_entries(
        self,
        session_id: Optional[str] = None,
        event_types: Optional[list[EventType]] = None,
        levels: Optional[list[LogLevel]] = None,
        since: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
        phase: Optional[str] = None,
        errors_only: bool = False,
        workflow_id: Optional[str] = None,
    ) -> list[LogEntry]:
        """
        Read and filter log entries.

        Args:
            session_id: Filter by session ID
            event_types: Filter by event types
            levels: Filter by log levels
            since: Only entries after this time
            limit: Maximum entries to return
            offset: Number of entries to skip
            phase: Filter by phase name (F5.4, DR-017)
            errors_only: When True, filter to ERROR and ERROR_CLASSIFIED events only (F5.4)
            workflow_id: Filter by workflow/session ID (alias for session_id)

        Returns:
            List of matching LogEntry objects

        Note:
            All filters combine with AND logic (DR-017). Each filter narrows the result set.
        """
        entries: list[LogEntry] = []

        # workflow_id is an alias for session_id
        effective_session_id = workflow_id or session_id

        # Read from all log files (current + rotated)
        log_files = self._get_log_files()

        for log_file in log_files:
            if not log_file.exists():
                continue

            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            entry = LogEntry.from_json(line.strip())

                            # Apply filters (AND logic per DR-017)
                            if effective_session_id and entry.session_id != effective_session_id:
                                continue
                            if event_types and entry.event not in event_types:
                                continue
                            if levels and entry.level not in levels:
                                continue
                            if since and entry.ts < since:
                                continue
                            # Phase filter (F5.4)
                            if phase and entry.phase != phase:
                                continue
                            # Errors only filter (F5.4)
                            if errors_only:
                                if entry.level != LogLevel.ERROR and entry.event != EventType.ERROR_CLASSIFIED:
                                    continue

                            entries.append(entry)
                        except (json.JSONDecodeError, ValueError, KeyError):
                            continue
            except OSError:
                continue

        # Sort by timestamp (newest first for display)
        entries.sort(key=lambda e: e.ts, reverse=True)

        # Apply offset and limit
        return entries[offset : offset + limit]

    def _get_log_files(self) -> list[Path]:
        """Get all log files in order (newest first)."""
        files = [self._log_file]

        # Add rotated files
        for i in range(1, 10):  # Check up to 10 rotated files
            rotated = self._log_dir / f"agent.log.{i}"
            if rotated.exists():
                files.append(rotated)
            else:
                break

        return files

    def is_session_active(self) -> bool:
        """Check if there's an active session (session started but not ended)."""
        if not self._log_file.exists():
            return False

        try:
            # Read last few entries to check for active session
            with open(self._log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Check recent entries for session_start without matching session_end
            active_sessions: set[str] = set()
            for line in lines[-1000:]:  # Check last 1000 lines
                try:
                    entry = LogEntry.from_json(line.strip())
                    if entry.event == EventType.SESSION_START:
                        active_sessions.add(entry.session_id)
                    elif entry.event == EventType.SESSION_END:
                        active_sessions.discard(entry.session_id)
                except (json.JSONDecodeError, ValueError, KeyError):
                    continue

            return len(active_sessions) > 0
        except OSError:
            return False

    def get_sessions_stats(self) -> dict[str, Any]:
        """Load session statistics from sessions.json."""
        stats_file = self._log_dir / "sessions.json"
        if not stats_file.exists():
            return {"sessions": [], "aggregate": {}}

        try:
            with open(stats_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"sessions": [], "aggregate": {}}


def parse_since_value(since_str: str) -> datetime:
    """
    Parse a --since value to a datetime.

    Supports:
    - Relative: "1h", "2d", "30m"
    - Absolute: "2024-01-15", "2024-01-15T10:30:00"
    """
    # Try relative format first
    if since_str[-1] in "hdmw":
        unit = since_str[-1]
        try:
            value = int(since_str[:-1])
        except ValueError:
            raise ValueError(f"Invalid relative time: {since_str}")

        now = datetime.now(timezone.utc)
        if unit == "m":
            delta = value * 60
        elif unit == "h":
            delta = value * 3600
        elif unit == "d":
            delta = value * 86400
        elif unit == "w":
            delta = value * 604800
        else:
            raise ValueError(f"Unknown time unit: {unit}")

        return now.replace(microsecond=0) - __import__("datetime").timedelta(
            seconds=delta
        )

    # Try absolute format
    try:
        # Try datetime first
        return datetime.fromisoformat(since_str).replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    try:
        # Try date only
        from datetime import date

        d = date.fromisoformat(since_str)
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    except ValueError:
        raise ValueError(f"Could not parse time: {since_str}")


def reset_session_stats(project_dir: Path) -> bool:
    """
    Reset accumulated session statistics.

    Args:
        project_dir: Project directory

    Returns:
        True if reset was successful
    """
    stats_file = project_dir / ".claude-agent" / "logs" / "sessions.json"
    if stats_file.exists():
        try:
            stats_file.unlink()
            return True
        except OSError:
            return False
    return True
