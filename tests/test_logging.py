"""
Tests for Structured Logging and Observability
==============================================

Tests for the logging module including:
- LogEntry serialization/deserialization
- AgentLogger file operations and rotation
- SessionStatsTracker statistics tracking
- LogReader querying and filtering
- CLI integration
"""

import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from claude_agent.logging import (
    LogLevel,
    EventType,
    LogEntry,
    LoggingConfig,
    AgentLogger,
    SessionStats,
    SessionStatsTracker,
    LogReader,
    parse_since_value,
    reset_session_stats,
    generate_session_id,
    truncate_string,
)


class TestLogEntry:
    """Tests for LogEntry dataclass."""

    def test_to_json_creates_valid_json(self):
        """LogEntry.to_json should create valid JSON."""
        entry = LogEntry(
            ts=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            level=LogLevel.INFO,
            event=EventType.SESSION_START,
            session_id="abc123",
            data={"model": "claude-opus", "iteration": 1},
        )
        json_str = entry.to_json()
        parsed = json.loads(json_str)
        assert parsed["level"] == "info"
        assert parsed["event"] == "session_start"
        assert parsed["session_id"] == "abc123"
        assert parsed["model"] == "claude-opus"
        assert parsed["iteration"] == 1

    def test_from_json_parses_correctly(self):
        """LogEntry.from_json should parse JSON string correctly."""
        json_str = json.dumps({
            "ts": "2024-01-15T10:30:00+00:00",
            "level": "warning",
            "event": "security_block",
            "session_id": "xyz789",
            "command": "rm -rf /",
            "reason": "not allowed",
        })
        entry = LogEntry.from_json(json_str)
        assert entry.level == LogLevel.WARNING
        assert entry.event == EventType.SECURITY_BLOCK
        assert entry.session_id == "xyz789"
        assert entry.data["command"] == "rm -rf /"
        assert entry.data["reason"] == "not allowed"

    def test_roundtrip_preserves_data(self):
        """LogEntry should roundtrip through JSON correctly."""
        original = LogEntry(
            ts=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            level=LogLevel.ERROR,
            event=EventType.ERROR,
            session_id="test123",
            data={"error_type": "ValueError", "message": "test error"},
        )
        json_str = original.to_json()
        restored = LogEntry.from_json(json_str)
        assert restored.level == original.level
        assert restored.event == original.event
        assert restored.session_id == original.session_id
        assert restored.data == original.data


class TestLoggingConfig:
    """Tests for LoggingConfig dataclass."""

    def test_default_values(self):
        """LoggingConfig should have sensible defaults."""
        config = LoggingConfig()
        assert config.enabled is True
        assert config.level == LogLevel.INFO
        assert config.include_tool_results is False
        assert config.include_allowed_commands is False
        assert config.max_summary_length == 500
        assert config.max_size_mb == 10
        assert config.max_files == 5
        assert config.retention_days == 30


class TestAgentLogger:
    """Tests for AgentLogger class."""

    def test_creates_log_directory(self, tmp_path):
        """AgentLogger should create log directory if it doesn't exist."""
        logger = AgentLogger(tmp_path, LoggingConfig())
        assert (tmp_path / ".claude-agent" / "logs").exists()

    def test_start_session_returns_session_id(self, tmp_path):
        """start_session should return a session ID."""
        logger = AgentLogger(tmp_path, LoggingConfig())
        session_id = logger.start_session(
            iteration=1,
            model="claude-opus",
            stack="python",
            agent_type="coding",
        )
        assert session_id is not None
        assert len(session_id) == 12  # hex[:12]

    def test_log_event_writes_to_file(self, tmp_path):
        """log_event should write to log file."""
        # Use DEBUG level to capture TOOL_CALL events
        config = LoggingConfig(level=LogLevel.DEBUG)
        logger = AgentLogger(tmp_path, config)
        logger.start_session(1, "claude-opus", "python", "coding")
        logger.log_event(EventType.TOOL_CALL, tool_name="Bash", input_summary="ls -la")
        logger._flush_buffer()  # Force flush

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        assert log_file.exists()
        content = log_file.read_text()
        assert "tool_call" in content
        assert "Bash" in content

    def test_log_security_block(self, tmp_path):
        """log_security_block should log with WARNING level."""
        logger = AgentLogger(tmp_path, LoggingConfig())
        logger.start_session(1, "claude-opus", "python", "coding")
        logger.log_security_block("rm -rf /", "command not allowed", "python")
        logger._flush_buffer()

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        content = log_file.read_text()
        assert "security_block" in content
        assert "rm -rf /" in content
        assert "warning" in content

    def test_end_session_flushes_buffer(self, tmp_path):
        """end_session should flush any buffered entries."""
        logger = AgentLogger(tmp_path, LoggingConfig())
        logger.start_session(1, "claude-opus", "python", "coding")
        logger.log_event(EventType.TOOL_CALL, tool_name="Read")
        # Buffer should have entry
        assert len(logger._buffer) > 0
        logger.end_session(turns_used=10, status="continue")
        # Buffer should be empty after end_session
        assert len(logger._buffer) == 0

    def test_disabled_logging(self, tmp_path):
        """Logging should not write files when disabled."""
        config = LoggingConfig(enabled=False)
        logger = AgentLogger(tmp_path, config)
        logger.start_session(1, "claude-opus", "python", "coding")
        logger.log_event(EventType.TOOL_CALL, tool_name="Bash")
        logger.end_session(turns_used=5, status="continue")

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        # File should not exist or be empty
        assert not log_file.exists() or log_file.stat().st_size == 0

    def test_log_level_filtering(self, tmp_path):
        """Events below configured level should not be logged."""
        config = LoggingConfig(level=LogLevel.WARNING)
        logger = AgentLogger(tmp_path, config)
        logger.start_session(1, "claude-opus", "python", "coding")

        # DEBUG level should be filtered out
        logger.log_event(EventType.TOOL_CALL, level=LogLevel.DEBUG, tool_name="test")
        logger._flush_buffer()

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        if log_file.exists():
            content = log_file.read_text()
            # Session start (INFO) should be filtered, tool_call (DEBUG) should be filtered
            assert "tool_call" not in content

    def test_truncates_long_strings(self, tmp_path):
        """Long string fields should be truncated."""
        config = LoggingConfig(max_summary_length=50)
        logger = AgentLogger(tmp_path, config)
        logger.start_session(1, "claude-opus", "python", "coding")

        long_string = "x" * 1000
        logger.log_event(EventType.ERROR, message=long_string)
        logger._flush_buffer()

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        content = log_file.read_text()
        # Should not contain full string
        assert "x" * 1000 not in content
        # Should contain truncated version
        assert "..." in content


class TestSessionStats:
    """Tests for SessionStats dataclass."""

    def test_to_dict_serializes_all_fields(self):
        """to_dict should include all fields."""
        stats = SessionStats(
            session_id="abc123",
            start_time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            duration_seconds=1800.0,
            turns_used=50,
            tools_called={"Bash": 10, "Read": 20},
            security_blocks=2,
            features_completed=[1, 2, 3],
            features_failed=[4],
            errors_encountered=1,
            agent_type="coding",
        )
        data = stats.to_dict()
        assert data["session_id"] == "abc123"
        assert data["turns_used"] == 50
        assert data["tools_called"]["Bash"] == 10
        assert data["security_blocks"] == 2
        assert len(data["features_completed"]) == 3

    def test_from_dict_restores_stats(self):
        """from_dict should restore SessionStats correctly."""
        data = {
            "session_id": "xyz789",
            "start_time": "2024-01-15T10:00:00+00:00",
            "end_time": "2024-01-15T10:30:00+00:00",
            "duration_seconds": 1800.0,
            "turns_used": 25,
            "tools_called": {"Write": 5},
            "security_blocks": 0,
            "features_completed": [1],
            "features_failed": [],
            "errors_encountered": 0,
            "agent_type": "initializer",
        }
        stats = SessionStats.from_dict(data)
        assert stats.session_id == "xyz789"
        assert stats.turns_used == 25
        assert stats.agent_type == "initializer"


class TestSessionStatsTracker:
    """Tests for SessionStatsTracker class."""

    def test_record_tool_call(self, tmp_path):
        """record_tool_call should increment tool counts."""
        tracker = SessionStatsTracker(tmp_path, "abc123", "coding")
        tracker.record_tool_call("Bash")
        tracker.record_tool_call("Bash")
        tracker.record_tool_call("Read")
        assert tracker.stats.tools_called["Bash"] == 2
        assert tracker.stats.tools_called["Read"] == 1

    def test_record_security_block(self, tmp_path):
        """record_security_block should increment counter."""
        tracker = SessionStatsTracker(tmp_path, "abc123", "coding")
        tracker.record_security_block()
        tracker.record_security_block()
        assert tracker.stats.security_blocks == 2

    def test_record_feature_complete(self, tmp_path):
        """record_feature_complete should add to list."""
        tracker = SessionStatsTracker(tmp_path, "abc123", "coding")
        tracker.record_feature_complete(1)
        tracker.record_feature_complete(2)
        tracker.record_feature_complete(1)  # Duplicate should not be added
        assert tracker.stats.features_completed == [1, 2]

    def test_save_creates_sessions_json(self, tmp_path):
        """save should create sessions.json file."""
        # Ensure log directory exists
        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        tracker = SessionStatsTracker(tmp_path, "abc123", "coding")
        tracker.record_tool_call("Bash")
        tracker.set_turns_used(10)
        tracker.save()

        stats_file = log_dir / "sessions.json"
        assert stats_file.exists()
        data = json.loads(stats_file.read_text())
        assert len(data["sessions"]) == 1
        assert data["aggregate"]["total_sessions"] == 1

    def test_save_appends_to_existing(self, tmp_path):
        """save should append to existing sessions."""
        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        # First session
        tracker1 = SessionStatsTracker(tmp_path, "abc123", "coding")
        tracker1.set_turns_used(10)
        tracker1.save()

        # Second session
        tracker2 = SessionStatsTracker(tmp_path, "xyz789", "coding")
        tracker2.set_turns_used(20)
        tracker2.save()

        stats_file = log_dir / "sessions.json"
        data = json.loads(stats_file.read_text())
        assert len(data["sessions"]) == 2
        assert data["aggregate"]["total_sessions"] == 2
        assert data["aggregate"]["total_turns"] == 30


class TestLogReader:
    """Tests for LogReader class."""

    def test_read_entries_empty_directory(self, tmp_path):
        """read_entries should return empty list if no logs."""
        reader = LogReader(tmp_path)
        entries = reader.read_entries()
        assert entries == []

    def test_read_entries_filters_by_session(self, tmp_path):
        """read_entries should filter by session_id."""
        # Create log file with entries from different sessions
        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        entries = [
            {"ts": "2024-01-15T10:00:00+00:00", "level": "info", "event": "session_start", "session_id": "abc123"},
            {"ts": "2024-01-15T10:01:00+00:00", "level": "info", "event": "tool_call", "session_id": "abc123"},
            {"ts": "2024-01-15T10:02:00+00:00", "level": "info", "event": "session_start", "session_id": "xyz789"},
        ]
        log_file = log_dir / "agent.log"
        log_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        reader = LogReader(tmp_path)
        filtered = reader.read_entries(session_id="abc123")
        assert len(filtered) == 2
        assert all(e.session_id == "abc123" for e in filtered)

    def test_read_entries_filters_by_event_type(self, tmp_path):
        """read_entries should filter by event types."""
        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        entries = [
            {"ts": "2024-01-15T10:00:00+00:00", "level": "info", "event": "session_start", "session_id": "abc"},
            {"ts": "2024-01-15T10:01:00+00:00", "level": "warning", "event": "security_block", "session_id": "abc"},
            {"ts": "2024-01-15T10:02:00+00:00", "level": "debug", "event": "tool_call", "session_id": "abc"},
        ]
        log_file = log_dir / "agent.log"
        log_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        reader = LogReader(tmp_path)
        filtered = reader.read_entries(event_types=[EventType.SECURITY_BLOCK])
        assert len(filtered) == 1
        assert filtered[0].event == EventType.SECURITY_BLOCK

    def test_read_entries_filters_by_since(self, tmp_path):
        """read_entries should filter by since datetime."""
        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        entries = [
            {"ts": "2024-01-15T10:00:00+00:00", "level": "info", "event": "session_start", "session_id": "abc"},
            {"ts": "2024-01-15T12:00:00+00:00", "level": "info", "event": "session_end", "session_id": "abc"},
        ]
        log_file = log_dir / "agent.log"
        log_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        reader = LogReader(tmp_path)
        since = datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc)
        filtered = reader.read_entries(since=since)
        assert len(filtered) == 1
        assert filtered[0].event == EventType.SESSION_END

    def test_read_entries_respects_limit(self, tmp_path):
        """read_entries should respect the limit parameter."""
        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        entries = [
            {"ts": f"2024-01-15T10:{i:02d}:00+00:00", "level": "info", "event": "tool_call", "session_id": "abc"}
            for i in range(20)
        ]
        log_file = log_dir / "agent.log"
        log_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        reader = LogReader(tmp_path)
        filtered = reader.read_entries(limit=5)
        assert len(filtered) == 5

    def test_get_sessions_stats(self, tmp_path):
        """get_sessions_stats should return session statistics."""
        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        stats = {
            "sessions": [{"session_id": "abc", "turns_used": 10}],
            "aggregate": {"total_sessions": 1, "total_turns": 10},
        }
        stats_file = log_dir / "sessions.json"
        stats_file.write_text(json.dumps(stats))

        reader = LogReader(tmp_path)
        data = reader.get_sessions_stats()
        assert data["aggregate"]["total_sessions"] == 1
        assert data["aggregate"]["total_turns"] == 10


class TestParseSinceValue:
    """Tests for parse_since_value function."""

    def test_parses_hours(self):
        """Should parse hour values like '2h'."""
        result = parse_since_value("2h")
        expected = datetime.now(timezone.utc) - timedelta(hours=2)
        # Allow some tolerance
        assert abs((result - expected).total_seconds()) < 2

    def test_parses_days(self):
        """Should parse day values like '3d'."""
        result = parse_since_value("3d")
        expected = datetime.now(timezone.utc) - timedelta(days=3)
        assert abs((result - expected).total_seconds()) < 2

    def test_parses_minutes(self):
        """Should parse minute values like '30m'."""
        result = parse_since_value("30m")
        expected = datetime.now(timezone.utc) - timedelta(minutes=30)
        assert abs((result - expected).total_seconds()) < 2

    def test_parses_iso_date(self):
        """Should parse ISO date format."""
        result = parse_since_value("2024-01-15")
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parses_iso_datetime(self):
        """Should parse ISO datetime format."""
        result = parse_since_value("2024-01-15T10:30:00")
        assert result.year == 2024
        assert result.hour == 10
        assert result.minute == 30

    def test_raises_on_invalid(self):
        """Should raise ValueError for invalid format."""
        with pytest.raises(ValueError):
            parse_since_value("invalid")


class TestResetSessionStats:
    """Tests for reset_session_stats function."""

    def test_removes_sessions_file(self, tmp_path):
        """reset_session_stats should remove sessions.json."""
        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stats_file = log_dir / "sessions.json"
        stats_file.write_text('{"sessions": []}')

        result = reset_session_stats(tmp_path)
        assert result is True
        assert not stats_file.exists()

    def test_returns_true_if_no_file(self, tmp_path):
        """reset_session_stats should return True if file doesn't exist."""
        result = reset_session_stats(tmp_path)
        assert result is True


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_generate_session_id_is_unique(self):
        """generate_session_id should produce unique IDs."""
        ids = [generate_session_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_generate_session_id_length(self):
        """generate_session_id should produce 12-character IDs."""
        session_id = generate_session_id()
        assert len(session_id) == 12

    def test_truncate_string_short(self):
        """truncate_string should return short strings unchanged."""
        result = truncate_string("hello", 100)
        assert result == "hello"

    def test_truncate_string_long(self):
        """truncate_string should truncate long strings."""
        result = truncate_string("hello world", 8)
        assert len(result) == 8
        assert result.endswith("...")

    def test_truncate_string_exact_length(self):
        """truncate_string should handle exact length."""
        result = truncate_string("hello", 5)
        assert result == "hello"


class TestRetentionDaysCleanup:
    """Tests for retention_days log file cleanup (Feature 45)."""

    def test_cleanup_old_files_deletes_expired_files(self, tmp_path):
        """_cleanup_old_files should delete files older than retention_days."""
        import os
        import time

        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        # Create a rotated log file
        old_log = log_dir / "agent.log.1"
        old_log.write_text('{"test": "old data"}\n')

        # Set modification time to be older than retention period (2 days ago)
        old_time = time.time() - (3 * 86400)  # 3 days ago
        os.utime(old_log, (old_time, old_time))

        # Create logger with 1 day retention
        config = LoggingConfig(retention_days=1)
        logger = AgentLogger(tmp_path, config=config)

        # Manually call cleanup
        logger._cleanup_old_files()

        # File should be deleted
        assert not old_log.exists()

    def test_cleanup_old_files_keeps_recent_files(self, tmp_path):
        """_cleanup_old_files should keep files within retention period."""
        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        # Create a recent rotated log file (mtime is now)
        recent_log = log_dir / "agent.log.1"
        recent_log.write_text('{"test": "recent data"}\n')

        # Create logger with 30 day retention
        config = LoggingConfig(retention_days=30)
        logger = AgentLogger(tmp_path, config=config)

        # Manually call cleanup
        logger._cleanup_old_files()

        # File should still exist
        assert recent_log.exists()

    def test_cleanup_disabled_when_retention_zero(self, tmp_path):
        """_cleanup_old_files should do nothing when retention_days is 0."""
        import os
        import time

        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        # Create an old file
        old_log = log_dir / "agent.log.1"
        old_log.write_text('{"test": "data"}\n')
        old_time = time.time() - (365 * 86400)  # 1 year ago
        os.utime(old_log, (old_time, old_time))

        # Create logger with 0 retention (disabled)
        config = LoggingConfig(retention_days=0)
        logger = AgentLogger(tmp_path, config=config)

        # Manually call cleanup
        logger._cleanup_old_files()

        # File should still exist (cleanup disabled)
        assert old_log.exists()


class TestRecentEventsContext:
    """Tests for recent_events context in error logs (Feature 53)."""

    def test_error_includes_recent_events(self, tmp_path):
        """log_error should include recent_events context."""
        config = LoggingConfig(level=LogLevel.DEBUG)
        logger = AgentLogger(tmp_path, config=config)
        logger.session_id = "test123"

        # Generate some events
        logger.log_tool_call("Bash", "ls -la")
        logger.log_tool_result("Bash", is_error=False, result="file.txt")
        logger.log_tool_call("Read", "/path/to/file")

        # Log an error
        logger.log_error("TestError", "Something went wrong")

        # Flush and check log
        logger._flush_buffer()

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        entries = [json.loads(line) for line in log_file.read_text().strip().split("\n")]

        # Find the error entry
        error_entry = next(e for e in entries if e["event"] == "error")

        # Should have recent_events field
        assert "recent_events" in error_entry
        assert isinstance(error_entry["recent_events"], list)
        assert len(error_entry["recent_events"]) > 0

    def test_recent_events_limited_to_5(self, tmp_path):
        """recent_events should be limited to 5 entries."""
        config = LoggingConfig(level=LogLevel.DEBUG)
        logger = AgentLogger(tmp_path, config=config)
        logger.session_id = "test123"

        # Generate more than 5 events
        for i in range(10):
            logger.log_tool_call(f"Tool{i}", f"command {i}")

        # Log an error
        logger.log_error("TestError", "Something went wrong")

        # Flush and check log
        logger._flush_buffer()

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        entries = [json.loads(line) for line in log_file.read_text().strip().split("\n")]

        # Find the error entry
        error_entry = next(e for e in entries if e["event"] == "error")

        # Should have exactly 5 recent events
        assert len(error_entry["recent_events"]) == 5

    def test_recent_events_excludes_errors(self, tmp_path):
        """recent_events should not include error events themselves."""
        config = LoggingConfig(level=LogLevel.DEBUG)
        logger = AgentLogger(tmp_path, config=config)
        logger.session_id = "test123"

        # Log an error, then another event, then another error
        logger.log_error("FirstError", "First problem")
        logger.log_tool_call("Bash", "command")
        logger.log_error("SecondError", "Second problem")

        # Flush and check log
        logger._flush_buffer()

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        entries = [json.loads(line) for line in log_file.read_text().strip().split("\n")]

        # Find the second error entry
        error_entries = [e for e in entries if e["event"] == "error"]
        second_error = error_entries[1]

        # recent_events should contain the tool_call, but not the first error
        assert any("tool_call" in ev for ev in second_error["recent_events"])


class TestEnvironmentInfo:
    """Tests for environment info in session logs (Feature 54)."""

    def test_session_start_includes_environment(self, tmp_path):
        """session_start event should include environment info."""
        logger = AgentLogger(tmp_path)
        session_id = logger.start_session(
            iteration=1,
            model="claude-opus",
            stack="python",
            agent_type="coding",
        )

        # Flush buffer
        logger._flush_buffer()

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        entries = [json.loads(line) for line in log_file.read_text().strip().split("\n")]

        # Find session_start entry
        start_entry = next(e for e in entries if e["event"] == "session_start")

        # Should have environment field
        assert "environment" in start_entry
        env = start_entry["environment"]

        # Check required fields
        assert "python_version" in env
        assert "sdk_version" in env
        assert "os" in env

        # Values should be non-empty strings
        assert isinstance(env["python_version"], str) and len(env["python_version"]) > 0
        assert isinstance(env["sdk_version"], str) and len(env["sdk_version"]) > 0
        assert isinstance(env["os"], str) and len(env["os"]) > 0

    def test_get_environment_info_returns_correct_structure(self):
        """get_environment_info should return dict with required fields."""
        from claude_agent.logging import get_environment_info
        import platform

        env = get_environment_info()

        assert "python_version" in env
        assert "sdk_version" in env
        assert "os" in env

        # Verify Python version matches actual version
        assert env["python_version"] == platform.python_version()

        # Verify OS is lowercase
        assert env["os"] == platform.system().lower()


# ==============================================================================
# MILESTONE 5: ENHANCED LOGGING TESTS
# ==============================================================================


class TestGateLogLevel:
    """Tests for GATE log level in level hierarchy (Feature #112, DR-015)."""

    def test_gate_exists_in_log_level_enum(self):
        """GATE should exist as a LogLevel enum value."""
        assert hasattr(LogLevel, "GATE")
        assert LogLevel.GATE.value == "gate"

    def test_gate_is_between_info_and_warning(self):
        """GATE should be positioned between INFO and WARNING in hierarchy."""
        from claude_agent.logging import LOG_LEVEL_ORDER

        info_idx = LOG_LEVEL_ORDER.index(LogLevel.INFO)
        gate_idx = LOG_LEVEL_ORDER.index(LogLevel.GATE)
        warning_idx = LOG_LEVEL_ORDER.index(LogLevel.WARNING)

        # DR-015: Level hierarchy: DEBUG < INFO < GATE < WARNING < ERROR
        assert info_idx < gate_idx < warning_idx

    def test_log_level_order_is_complete(self):
        """LOG_LEVEL_ORDER should include all 5 levels in correct order."""
        from claude_agent.logging import LOG_LEVEL_ORDER

        assert len(LOG_LEVEL_ORDER) == 5
        assert LOG_LEVEL_ORDER == [
            LogLevel.DEBUG,
            LogLevel.INFO,
            LogLevel.GATE,
            LogLevel.WARNING,
            LogLevel.ERROR,
        ]

    def test_gate_level_filtering(self, tmp_path):
        """Events below GATE level should be filtered when config.level=GATE."""
        config = LoggingConfig(level=LogLevel.GATE)
        logger = AgentLogger(tmp_path, config=config)
        logger.session_id = "test123"

        # INFO level should be filtered out
        logger.log_event(EventType.LOG_MESSAGE, level=LogLevel.INFO, message="info msg")
        # GATE level should be included
        logger.log_event(EventType.PHASE_ENTER, phase="coding")
        # WARNING level should be included
        logger.log_event(EventType.LOG_MESSAGE, level=LogLevel.WARNING, message="warn msg")

        logger._flush_buffer()

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        content = log_file.read_text()

        # INFO should be filtered out
        assert "info msg" not in content
        # GATE and above should be included
        assert "phase_enter" in content
        assert "warn msg" in content

    def test_gate_serializes_to_json(self):
        """GATE level should serialize correctly to JSON."""
        entry = LogEntry(
            ts=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            level=LogLevel.GATE,
            event=EventType.PHASE_ENTER,
            session_id="abc123",
            data={"phase": "coding"},
        )
        json_str = entry.to_json()
        parsed = json.loads(json_str)
        assert parsed["level"] == "gate"

    def test_gate_deserializes_from_json(self):
        """GATE level should deserialize correctly from JSON."""
        json_str = json.dumps({
            "ts": "2024-01-15T10:30:00+00:00",
            "level": "gate",
            "event": "phase_enter",
            "session_id": "abc123",
            "phase": "coding",
        })
        entry = LogEntry.from_json(json_str)
        assert entry.level == LogLevel.GATE


class TestNewEventTypes:
    """Tests for new event types PHASE_ENTER, PHASE_EXIT, ERROR_CLASSIFIED, HOOK_FIRED (Feature #113)."""

    def test_phase_enter_exists(self):
        """PHASE_ENTER should exist as EventType enum value."""
        assert hasattr(EventType, "PHASE_ENTER")
        assert EventType.PHASE_ENTER.value == "phase_enter"

    def test_phase_exit_exists(self):
        """PHASE_EXIT should exist as EventType enum value."""
        assert hasattr(EventType, "PHASE_EXIT")
        assert EventType.PHASE_EXIT.value == "phase_exit"

    def test_error_classified_exists(self):
        """ERROR_CLASSIFIED should exist as EventType enum value."""
        assert hasattr(EventType, "ERROR_CLASSIFIED")
        assert EventType.ERROR_CLASSIFIED.value == "error_classified"

    def test_hook_fired_exists(self):
        """HOOK_FIRED should exist as EventType enum value."""
        assert hasattr(EventType, "HOOK_FIRED")
        assert EventType.HOOK_FIRED.value == "hook_fired"

    def test_phase_enter_serializes_to_json(self):
        """PHASE_ENTER event should serialize correctly."""
        entry = LogEntry(
            ts=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            level=LogLevel.GATE,
            event=EventType.PHASE_ENTER,
            session_id="abc123",
            data={"phase": "validating"},
        )
        json_str = entry.to_json()
        parsed = json.loads(json_str)
        assert parsed["event"] == "phase_enter"

    def test_phase_exit_serializes_to_json(self):
        """PHASE_EXIT event should serialize correctly."""
        entry = LogEntry(
            ts=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            level=LogLevel.GATE,
            event=EventType.PHASE_EXIT,
            session_id="abc123",
            data={"phase": "coding", "duration_seconds": 120.5},
        )
        json_str = entry.to_json()
        parsed = json.loads(json_str)
        assert parsed["event"] == "phase_exit"
        assert parsed["duration_seconds"] == 120.5

    def test_error_classified_serializes_to_json(self):
        """ERROR_CLASSIFIED event should serialize correctly."""
        entry = LogEntry(
            ts=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            level=LogLevel.ERROR,
            event=EventType.ERROR_CLASSIFIED,
            session_id="abc123",
            data={"error_type": "manual", "error_category": "security"},
        )
        json_str = entry.to_json()
        parsed = json.loads(json_str)
        assert parsed["event"] == "error_classified"
        assert parsed["error_type"] == "manual"

    def test_hook_fired_serializes_to_json(self):
        """HOOK_FIRED event should serialize correctly."""
        entry = LogEntry(
            ts=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            level=LogLevel.INFO,
            event=EventType.HOOK_FIRED,
            session_id="abc123",
            data={"hook_name": "session-start", "result": "success"},
        )
        json_str = entry.to_json()
        parsed = json.loads(json_str)
        assert parsed["event"] == "hook_fired"
        assert parsed["hook_name"] == "session-start"

    def test_new_events_deserialize_from_json(self):
        """All new event types should deserialize correctly from JSON."""
        events = [
            ("phase_enter", EventType.PHASE_ENTER),
            ("phase_exit", EventType.PHASE_EXIT),
            ("error_classified", EventType.ERROR_CLASSIFIED),
            ("hook_fired", EventType.HOOK_FIRED),
        ]
        for event_str, expected_type in events:
            json_str = json.dumps({
                "ts": "2024-01-15T10:30:00+00:00",
                "level": "info",
                "event": event_str,
                "session_id": "abc123",
            })
            entry = LogEntry.from_json(json_str)
            assert entry.event == expected_type, f"Failed for {event_str}"

    def test_default_log_levels_for_new_events(self):
        """New events should have correct default log levels (DR-015)."""
        from claude_agent.logging import EVENT_LEVELS

        # PHASE_ENTER and PHASE_EXIT use GATE level
        assert EVENT_LEVELS[EventType.PHASE_ENTER] == LogLevel.GATE
        assert EVENT_LEVELS[EventType.PHASE_EXIT] == LogLevel.GATE
        # ERROR_CLASSIFIED uses ERROR level
        assert EVENT_LEVELS[EventType.ERROR_CLASSIFIED] == LogLevel.ERROR
        # HOOK_FIRED uses INFO level
        assert EVENT_LEVELS[EventType.HOOK_FIRED] == LogLevel.INFO


class TestPhaseEnterExitMethods:
    """Tests for phase_enter and phase_exit methods (Feature #114, DR-016)."""

    def test_phase_enter_logs_phase_enter_event(self, tmp_path):
        """phase_enter should log a PHASE_ENTER event."""
        config = LoggingConfig(level=LogLevel.DEBUG)
        logger = AgentLogger(tmp_path, config=config)
        logger.session_id = "test123"

        logger.phase_enter("coding")
        logger._flush_buffer()

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        entries = [json.loads(line) for line in log_file.read_text().strip().split("\n")]

        phase_entry = next((e for e in entries if e["event"] == "phase_enter"), None)
        assert phase_entry is not None
        assert phase_entry["phase"] == "coding"
        assert phase_entry["level"] == "gate"

    def test_phase_enter_sets_current_phase(self, tmp_path):
        """phase_enter should set current_phase instance variable."""
        logger = AgentLogger(tmp_path)
        logger.session_id = "test123"

        assert logger.current_phase == ""
        logger.phase_enter("validating")
        assert logger.current_phase == "validating"

    def test_phase_exit_logs_phase_exit_event(self, tmp_path):
        """phase_exit should log a PHASE_EXIT event."""
        config = LoggingConfig(level=LogLevel.DEBUG)
        logger = AgentLogger(tmp_path, config=config)
        logger.session_id = "test123"

        logger.phase_enter("coding")
        logger.phase_exit("coding")
        logger._flush_buffer()

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        entries = [json.loads(line) for line in log_file.read_text().strip().split("\n")]

        exit_entry = next((e for e in entries if e["event"] == "phase_exit"), None)
        assert exit_entry is not None
        assert exit_entry["phase"] == "coding"
        assert exit_entry["level"] == "gate"

    def test_phase_exit_calculates_duration(self, tmp_path):
        """phase_exit should calculate duration if entry time available."""
        import time

        config = LoggingConfig(level=LogLevel.DEBUG)
        logger = AgentLogger(tmp_path, config=config)
        logger.session_id = "test123"

        logger.phase_enter("coding")
        time.sleep(0.1)  # Small delay
        logger.phase_exit("coding")
        logger._flush_buffer()

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        entries = [json.loads(line) for line in log_file.read_text().strip().split("\n")]

        exit_entry = next((e for e in entries if e["event"] == "phase_exit"), None)
        assert exit_entry is not None
        assert "duration_seconds" in exit_entry
        assert exit_entry["duration_seconds"] >= 0.1

    def test_phase_exit_clears_current_phase(self, tmp_path):
        """phase_exit should clear current_phase after logging."""
        logger = AgentLogger(tmp_path)
        logger.session_id = "test123"

        logger.phase_enter("coding")
        assert logger.current_phase == "coding"
        logger.phase_exit("coding")
        assert logger.current_phase == ""

    def test_phase_enter_includes_context_kwargs(self, tmp_path):
        """phase_enter should include context kwargs in event data."""
        config = LoggingConfig(level=LogLevel.DEBUG)
        logger = AgentLogger(tmp_path, config=config)
        logger.session_id = "test123"

        logger.phase_enter("coding", iteration=5, model="claude-opus")
        logger._flush_buffer()

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        entries = [json.loads(line) for line in log_file.read_text().strip().split("\n")]

        phase_entry = next((e for e in entries if e["event"] == "phase_enter"), None)
        assert phase_entry is not None
        assert phase_entry["iteration"] == 5
        assert phase_entry["model"] == "claude-opus"

    def test_phase_exit_includes_context_kwargs(self, tmp_path):
        """phase_exit should include context kwargs in event data."""
        config = LoggingConfig(level=LogLevel.DEBUG)
        logger = AgentLogger(tmp_path, config=config)
        logger.session_id = "test123"

        logger.phase_enter("validating")
        logger.phase_exit("validating", verdict="approved", features_tested=10)
        logger._flush_buffer()

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        entries = [json.loads(line) for line in log_file.read_text().strip().split("\n")]

        exit_entry = next((e for e in entries if e["event"] == "phase_exit"), None)
        assert exit_entry is not None
        assert exit_entry["verdict"] == "approved"
        assert exit_entry["features_tested"] == 10


class TestLogErrorClassified:
    """Tests for log_error_classified method (Feature #115)."""

    def test_logs_error_classified_event(self, tmp_path):
        """log_error_classified should log ERROR_CLASSIFIED event."""
        config = LoggingConfig(level=LogLevel.DEBUG)
        logger = AgentLogger(tmp_path, config=config)
        logger.session_id = "test123"

        # Create a mock StructuredError-like object
        class MockError:
            type = type("MockType", (), {"value": "manual"})()
            category = type("MockCategory", (), {"value": "security"})()
            message = "Command blocked"
            recovery_hint = "Add to allowlist"
            context = {"command": "rm -rf /"}

        logger.log_error_classified(MockError())
        logger._flush_buffer()

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        entries = [json.loads(line) for line in log_file.read_text().strip().split("\n")]

        error_entry = next((e for e in entries if e["event"] == "error_classified"), None)
        assert error_entry is not None
        assert error_entry["level"] == "error"

    def test_includes_error_type_and_category(self, tmp_path):
        """log_error_classified should include error type and category."""
        config = LoggingConfig(level=LogLevel.DEBUG)
        logger = AgentLogger(tmp_path, config=config)
        logger.session_id = "test123"

        class MockError:
            type = type("MockType", (), {"value": "retry"})()
            category = type("MockCategory", (), {"value": "network"})()
            message = "Connection failed"
            recovery_hint = "Check internet"
            context = {}

        logger.log_error_classified(MockError())
        logger._flush_buffer()

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        entries = [json.loads(line) for line in log_file.read_text().strip().split("\n")]

        error_entry = next((e for e in entries if e["event"] == "error_classified"), None)
        assert error_entry is not None
        assert error_entry["error_type"] == "retry"
        assert error_entry["error_category"] == "network"

    def test_includes_recovery_hint(self, tmp_path):
        """log_error_classified should include recovery_hint."""
        config = LoggingConfig(level=LogLevel.DEBUG)
        logger = AgentLogger(tmp_path, config=config)
        logger.session_id = "test123"

        class MockError:
            type = type("MockType", (), {"value": "manual"})()
            category = type("MockCategory", (), {"value": "config"})()
            message = "Invalid config"
            recovery_hint = "Check .claude-agent.yaml"
            context = {}

        logger.log_error_classified(MockError())
        logger._flush_buffer()

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        entries = [json.loads(line) for line in log_file.read_text().strip().split("\n")]

        error_entry = next((e for e in entries if e["event"] == "error_classified"), None)
        assert error_entry is not None
        assert error_entry["recovery_hint"] == "Check .claude-agent.yaml"


class TestLogHookFired:
    """Tests for log_hook_fired method (Feature #116)."""

    def test_logs_hook_fired_event(self, tmp_path):
        """log_hook_fired should log HOOK_FIRED event."""
        config = LoggingConfig(level=LogLevel.DEBUG)
        logger = AgentLogger(tmp_path, config=config)
        logger.session_id = "test123"

        logger.log_hook_fired("session-start", "success")
        logger._flush_buffer()

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        entries = [json.loads(line) for line in log_file.read_text().strip().split("\n")]

        hook_entry = next((e for e in entries if e["event"] == "hook_fired"), None)
        assert hook_entry is not None
        assert hook_entry["level"] == "info"

    def test_includes_hook_name(self, tmp_path):
        """log_hook_fired should include hook name."""
        config = LoggingConfig(level=LogLevel.DEBUG)
        logger = AgentLogger(tmp_path, config=config)
        logger.session_id = "test123"

        logger.log_hook_fired("session-stop", "{}")
        logger._flush_buffer()

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        entries = [json.loads(line) for line in log_file.read_text().strip().split("\n")]

        hook_entry = next((e for e in entries if e["event"] == "hook_fired"), None)
        assert hook_entry is not None
        assert hook_entry["hook_name"] == "session-stop"

    def test_includes_result(self, tmp_path):
        """log_hook_fired should include result."""
        config = LoggingConfig(level=LogLevel.DEBUG)
        logger = AgentLogger(tmp_path, config=config)
        logger.session_id = "test123"

        logger.log_hook_fired("session-start", '{"additionalContext": "test"}')
        logger._flush_buffer()

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        entries = [json.loads(line) for line in log_file.read_text().strip().split("\n")]

        hook_entry = next((e for e in entries if e["event"] == "hook_fired"), None)
        assert hook_entry is not None
        assert "additionalContext" in hook_entry["result"]


class TestPhaseFieldInLogEntry:
    """Tests for phase field in LogEntry (Feature #117, DR-016)."""

    def test_phase_field_serializes_to_json(self):
        """LogEntry phase field should serialize to JSON."""
        entry = LogEntry(
            ts=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            level=LogLevel.INFO,
            event=EventType.TOOL_CALL,
            session_id="abc123",
            data={"tool_name": "Bash"},
            phase="coding",
        )
        json_str = entry.to_json()
        parsed = json.loads(json_str)
        assert parsed["phase"] == "coding"

    def test_phase_field_deserializes_from_json(self):
        """LogEntry should deserialize phase field from JSON."""
        json_str = json.dumps({
            "ts": "2024-01-15T10:30:00+00:00",
            "level": "info",
            "event": "tool_call",
            "session_id": "abc123",
            "phase": "validating",
        })
        entry = LogEntry.from_json(json_str)
        assert entry.phase == "validating"

    def test_phase_field_defaults_to_empty_string(self):
        """LogEntry phase field should default to empty string (DR-016)."""
        entry = LogEntry(
            ts=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            level=LogLevel.INFO,
            event=EventType.TOOL_CALL,
            session_id="abc123",
        )
        assert entry.phase == ""

    def test_phase_field_backward_compatible(self):
        """LogEntry should handle missing phase in old logs (DR-019)."""
        # Old log format without phase field
        json_str = json.dumps({
            "ts": "2024-01-15T10:30:00+00:00",
            "level": "info",
            "event": "session_start",
            "session_id": "abc123",
            "model": "claude-opus",
        })
        entry = LogEntry.from_json(json_str)
        assert entry.phase == ""  # Should default to empty string

    def test_log_event_includes_current_phase(self, tmp_path):
        """log_event should include current_phase in entries."""
        config = LoggingConfig(level=LogLevel.DEBUG)
        logger = AgentLogger(tmp_path, config=config)
        logger.session_id = "test123"

        # Set current phase
        logger.current_phase = "coding"
        logger.log_event(EventType.TOOL_CALL, tool_name="Bash")
        logger._flush_buffer()

        log_file = tmp_path / ".claude-agent" / "logs" / "agent.log"
        entries = [json.loads(line) for line in log_file.read_text().strip().split("\n")]

        tool_entry = next((e for e in entries if e["event"] == "tool_call"), None)
        assert tool_entry is not None
        assert tool_entry["phase"] == "coding"


class TestPhaseFilterInLogReader:
    """Tests for phase filter in LogReader.read_entries() (Feature #118, DR-017)."""

    def test_filtering_returns_only_matching_phase_entries(self, tmp_path):
        """Phase filter should return only entries with matching phase."""
        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        entries = [
            {"ts": "2024-01-15T10:00:00+00:00", "level": "info", "event": "tool_call", "session_id": "abc", "phase": "coding"},
            {"ts": "2024-01-15T10:01:00+00:00", "level": "info", "event": "tool_call", "session_id": "abc", "phase": "validating"},
            {"ts": "2024-01-15T10:02:00+00:00", "level": "info", "event": "tool_call", "session_id": "abc", "phase": "coding"},
        ]
        log_file = log_dir / "agent.log"
        log_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        reader = LogReader(tmp_path)
        filtered = reader.read_entries(phase="coding")

        assert len(filtered) == 2
        assert all(e.phase == "coding" for e in filtered)

    def test_none_phase_returns_all_entries(self, tmp_path):
        """None phase should return all entries."""
        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        entries = [
            {"ts": "2024-01-15T10:00:00+00:00", "level": "info", "event": "tool_call", "session_id": "abc", "phase": "coding"},
            {"ts": "2024-01-15T10:01:00+00:00", "level": "info", "event": "tool_call", "session_id": "abc", "phase": "validating"},
            {"ts": "2024-01-15T10:02:00+00:00", "level": "info", "event": "tool_call", "session_id": "abc", "phase": ""},
        ]
        log_file = log_dir / "agent.log"
        log_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        reader = LogReader(tmp_path)
        filtered = reader.read_entries(phase=None, limit=100)

        assert len(filtered) == 3

    def test_phase_filter_combines_with_other_filters(self, tmp_path):
        """Phase filter should combine with other filters (DR-017 AND logic)."""
        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        entries = [
            {"ts": "2024-01-15T10:00:00+00:00", "level": "warning", "event": "security_block", "session_id": "abc", "phase": "coding"},
            {"ts": "2024-01-15T10:01:00+00:00", "level": "info", "event": "tool_call", "session_id": "abc", "phase": "coding"},
            {"ts": "2024-01-15T10:02:00+00:00", "level": "warning", "event": "security_block", "session_id": "xyz", "phase": "coding"},
        ]
        log_file = log_dir / "agent.log"
        log_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        reader = LogReader(tmp_path)
        # Filter by phase AND session_id
        filtered = reader.read_entries(phase="coding", session_id="abc")

        assert len(filtered) == 2
        assert all(e.phase == "coding" and e.session_id == "abc" for e in filtered)


class TestErrorsOnlyFilterInLogReader:
    """Tests for errors_only filter in LogReader.read_entries() (Feature #119)."""

    def test_true_returns_only_error_events(self, tmp_path):
        """errors_only=True should return only ERROR and ERROR_CLASSIFIED events."""
        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        entries = [
            {"ts": "2024-01-15T10:00:00+00:00", "level": "error", "event": "error", "session_id": "abc", "phase": ""},
            {"ts": "2024-01-15T10:01:00+00:00", "level": "info", "event": "tool_call", "session_id": "abc", "phase": ""},
            {"ts": "2024-01-15T10:02:00+00:00", "level": "error", "event": "error_classified", "session_id": "abc", "phase": ""},
            {"ts": "2024-01-15T10:03:00+00:00", "level": "warning", "event": "security_block", "session_id": "abc", "phase": ""},
        ]
        log_file = log_dir / "agent.log"
        log_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        reader = LogReader(tmp_path)
        filtered = reader.read_entries(errors_only=True)

        assert len(filtered) == 2
        assert all(e.level == LogLevel.ERROR or e.event == EventType.ERROR_CLASSIFIED for e in filtered)

    def test_false_returns_all_events(self, tmp_path):
        """errors_only=False should return all events."""
        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        entries = [
            {"ts": "2024-01-15T10:00:00+00:00", "level": "error", "event": "error", "session_id": "abc", "phase": ""},
            {"ts": "2024-01-15T10:01:00+00:00", "level": "info", "event": "tool_call", "session_id": "abc", "phase": ""},
        ]
        log_file = log_dir / "agent.log"
        log_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        reader = LogReader(tmp_path)
        filtered = reader.read_entries(errors_only=False)

        assert len(filtered) == 2

    def test_errors_only_combines_with_other_filters(self, tmp_path):
        """errors_only should combine with other filters (DR-017 AND logic)."""
        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        entries = [
            {"ts": "2024-01-15T10:00:00+00:00", "level": "error", "event": "error", "session_id": "abc", "phase": "coding"},
            {"ts": "2024-01-15T10:01:00+00:00", "level": "error", "event": "error", "session_id": "abc", "phase": "validating"},
            {"ts": "2024-01-15T10:02:00+00:00", "level": "info", "event": "tool_call", "session_id": "abc", "phase": "coding"},
        ]
        log_file = log_dir / "agent.log"
        log_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        reader = LogReader(tmp_path)
        # Filter by errors_only AND phase
        filtered = reader.read_entries(errors_only=True, phase="coding")

        assert len(filtered) == 1
        assert filtered[0].phase == "coding"
        assert filtered[0].level == LogLevel.ERROR


class TestWorkflowIdFilter:
    """Tests for workflow_id filter in LogReader.read_entries()."""

    def test_workflow_id_filters_by_session(self, tmp_path):
        """workflow_id should filter by session_id (alias)."""
        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        entries = [
            {"ts": "2024-01-15T10:00:00+00:00", "level": "info", "event": "tool_call", "session_id": "workflow-abc", "phase": ""},
            {"ts": "2024-01-15T10:01:00+00:00", "level": "info", "event": "tool_call", "session_id": "workflow-xyz", "phase": ""},
        ]
        log_file = log_dir / "agent.log"
        log_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        reader = LogReader(tmp_path)
        filtered = reader.read_entries(workflow_id="workflow-abc")

        assert len(filtered) == 1
        assert filtered[0].session_id == "workflow-abc"


class TestCLILogOptionsIntegration:
    """Integration tests for new CLI log options (Feature #120)."""

    def test_phase_option_filters_correctly(self, tmp_path):
        """--phase option should filter log entries by phase."""
        from click.testing import CliRunner
        from claude_agent.cli import logs

        # Create log file with entries
        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        entries = [
            {"ts": "2024-01-15T10:00:00+00:00", "level": "info", "event": "tool_call", "session_id": "abc", "phase": "coding"},
            {"ts": "2024-01-15T10:01:00+00:00", "level": "info", "event": "tool_call", "session_id": "abc", "phase": "validating"},
        ]
        log_file = log_dir / "agent.log"
        log_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        runner = CliRunner()
        result = runner.invoke(logs, [str(tmp_path), "--phase", "coding", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output) == 1
        assert output[0]["phase"] == "coding"

    def test_level_gate_works(self, tmp_path):
        """--level gate option should filter to GATE level and above."""
        from click.testing import CliRunner
        from claude_agent.cli import logs

        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        entries = [
            {"ts": "2024-01-15T10:00:00+00:00", "level": "info", "event": "session_start", "session_id": "abc", "phase": ""},
            {"ts": "2024-01-15T10:01:00+00:00", "level": "gate", "event": "phase_enter", "session_id": "abc", "phase": "coding"},
            {"ts": "2024-01-15T10:02:00+00:00", "level": "warning", "event": "security_block", "session_id": "abc", "phase": ""},
        ]
        log_file = log_dir / "agent.log"
        log_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        runner = CliRunner()
        result = runner.invoke(logs, [str(tmp_path), "--level", "gate", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        # Should include GATE and WARNING, exclude INFO
        assert len(output) == 2
        assert all(e["level"] in ["gate", "warning", "error"] for e in output)

    def test_errors_shorthand_works(self, tmp_path):
        """--errors shorthand should filter to error events."""
        from click.testing import CliRunner
        from claude_agent.cli import logs

        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        entries = [
            {"ts": "2024-01-15T10:00:00+00:00", "level": "error", "event": "error", "session_id": "abc", "phase": ""},
            {"ts": "2024-01-15T10:01:00+00:00", "level": "info", "event": "tool_call", "session_id": "abc", "phase": ""},
            {"ts": "2024-01-15T10:02:00+00:00", "level": "error", "event": "error_classified", "session_id": "abc", "phase": ""},
        ]
        log_file = log_dir / "agent.log"
        log_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        runner = CliRunner()
        result = runner.invoke(logs, [str(tmp_path), "--errors", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output) == 2
        assert all(e["event"] in ["error", "error_classified"] for e in output)

    def test_workflow_option_filters_correctly(self, tmp_path):
        """--workflow option should filter by workflow/session ID."""
        from click.testing import CliRunner
        from claude_agent.cli import logs

        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        entries = [
            {"ts": "2024-01-15T10:00:00+00:00", "level": "info", "event": "tool_call", "session_id": "workflow-123", "phase": ""},
            {"ts": "2024-01-15T10:01:00+00:00", "level": "info", "event": "tool_call", "session_id": "workflow-456", "phase": ""},
        ]
        log_file = log_dir / "agent.log"
        log_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        runner = CliRunner()
        result = runner.invoke(logs, [str(tmp_path), "--workflow", "workflow-123", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output) == 1
        assert output[0]["session_id"] == "workflow-123"

    def test_combined_filters_work(self, tmp_path):
        """Multiple filter options should combine with AND logic (DR-017)."""
        from click.testing import CliRunner
        from claude_agent.cli import logs

        log_dir = tmp_path / ".claude-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        entries = [
            {"ts": "2024-01-15T10:00:00+00:00", "level": "error", "event": "error", "session_id": "abc", "phase": "coding"},
            {"ts": "2024-01-15T10:01:00+00:00", "level": "error", "event": "error", "session_id": "abc", "phase": "validating"},
            {"ts": "2024-01-15T10:02:00+00:00", "level": "info", "event": "tool_call", "session_id": "abc", "phase": "coding"},
            {"ts": "2024-01-15T10:03:00+00:00", "level": "error", "event": "error", "session_id": "xyz", "phase": "coding"},
        ]
        log_file = log_dir / "agent.log"
        log_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        runner = CliRunner()
        # Combine --errors AND --phase AND --workflow (session)
        result = runner.invoke(logs, [str(tmp_path), "--errors", "--phase", "coding", "--session", "abc", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        # Should only match the one entry that satisfies all conditions
        assert len(output) == 1
        assert output[0]["phase"] == "coding"
        assert output[0]["session_id"] == "abc"
        assert output[0]["event"] == "error"
