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
