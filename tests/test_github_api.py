"""
Tests for GitHub API automation script.
"""

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Mock requests before importing github_api
sys.modules["requests"] = MagicMock()
sys.modules["yaml"] = MagicMock()

# Import from scripts directory
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from github_api import Config, TaskRunner, GitHubAPI


class TestConfig:
    """Tests for Config dataclass validation."""

    def test_valid_repo_format(self):
        """Valid owner/repo format should work."""
        config = Config(token="test-token", repo="owner/repo")
        assert config.owner == "owner"
        assert config.repo_name == "repo"

    def test_invalid_repo_format_no_slash(self):
        """Repo without slash should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Config(token="test-token", repo="invalid-format")
        assert "Invalid repo format" in str(exc_info.value)
        assert "Expected 'owner/repo'" in str(exc_info.value)

    def test_invalid_repo_format_empty_owner(self):
        """Repo with empty owner should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Config(token="test-token", repo="/repo")
        assert "Invalid repo format" in str(exc_info.value)

    def test_invalid_repo_format_empty_repo(self):
        """Repo with empty repo name should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Config(token="test-token", repo="owner/")
        assert "Invalid repo format" in str(exc_info.value)

    def test_invalid_repo_format_too_many_slashes(self):
        """Repo with multiple slashes should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Config(token="test-token", repo="owner/repo/extra")
        assert "Invalid repo format" in str(exc_info.value)

    def test_headers_include_authorization(self):
        """Headers should include Bearer token."""
        config = Config(token="my-secret-token", repo="owner/repo")
        assert config.headers["Authorization"] == "Bearer my-secret-token"
        assert "application/vnd.github+json" in config.headers["Accept"]


class TestTaskRunnerParseRelativeDate:
    """Tests for TaskRunner._parse_relative_date method."""

    @pytest.fixture
    def runner(self):
        """Create a TaskRunner with mocked dependencies."""
        config = Config(token="test", repo="owner/repo", dry_run=True)
        api = MagicMock(spec=GitHubAPI)
        return TaskRunner(api, config)

    def test_parse_days(self, runner):
        """Parse '+5 days' correctly."""
        result = runner._parse_relative_date("+5 days")
        # Result should be ISO format
        assert result.endswith("Z")
        # Parse and verify it's roughly 5 days from now
        parsed = datetime.strptime(result, "%Y-%m-%dT%H:%M:%SZ")
        expected = datetime.now(timezone.utc) + timedelta(days=5)
        # Allow 1 minute tolerance for test execution time
        assert abs((parsed.replace(tzinfo=timezone.utc) - expected).total_seconds()) < 60

    def test_parse_weeks(self, runner):
        """Parse '+2 weeks' correctly."""
        result = runner._parse_relative_date("+2 weeks")
        assert result.endswith("Z")
        parsed = datetime.strptime(result, "%Y-%m-%dT%H:%M:%SZ")
        expected = datetime.now(timezone.utc) + timedelta(weeks=2)
        assert abs((parsed.replace(tzinfo=timezone.utc) - expected).total_seconds()) < 60

    def test_parse_months(self, runner):
        """Parse '+1 month' correctly (approximated as 30 days)."""
        result = runner._parse_relative_date("+1 month")
        assert result.endswith("Z")
        parsed = datetime.strptime(result, "%Y-%m-%dT%H:%M:%SZ")
        expected = datetime.now(timezone.utc) + timedelta(days=30)
        assert abs((parsed.replace(tzinfo=timezone.utc) - expected).total_seconds()) < 60

    def test_parse_singular_unit(self, runner):
        """Parse '+1 day' (singular) correctly."""
        result = runner._parse_relative_date("+1 day")
        assert result.endswith("Z")

    def test_invalid_format_returns_original(self, runner):
        """Invalid format should return original string."""
        result = runner._parse_relative_date("invalid")
        assert result == "invalid"

    def test_unknown_unit_returns_original(self, runner):
        """Unknown time unit should return original string."""
        result = runner._parse_relative_date("+5 years")
        assert result == "+5 years"


class TestTaskRunnerResolveBody:
    """Tests for TaskRunner._resolve_body method."""

    @pytest.fixture
    def runner(self):
        """Create a TaskRunner with mocked dependencies."""
        config = Config(token="test", repo="owner/repo", dry_run=True)
        api = MagicMock(spec=GitHubAPI)
        return TaskRunner(api, config)

    def test_inline_body(self, runner):
        """Inline body should be returned directly."""
        issue = {"title": "Test", "body": "This is the body"}
        result = runner._resolve_body(issue)
        assert result == "This is the body"

    def test_body_file_exists(self, runner):
        """Body from file should be read correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Body from file\n\nContent here.")
            temp_path = f.name

        try:
            issue = {"title": "Test", "body_file": temp_path}
            result = runner._resolve_body(issue)
            assert "Body from file" in result
            assert "Content here" in result
        finally:
            Path(temp_path).unlink()

    def test_body_file_not_found(self, runner):
        """Missing body file should raise FileNotFoundError."""
        issue = {"title": "Test", "body_file": "/nonexistent/path/body.md"}
        with pytest.raises(FileNotFoundError) as exc_info:
            runner._resolve_body(issue)
        assert "Issue body file not found" in str(exc_info.value)

    def test_no_body_returns_empty(self, runner):
        """Issue with no body or body_file should return empty string."""
        issue = {"title": "Test"}
        result = runner._resolve_body(issue)
        assert result == ""

    def test_inline_body_takes_precedence(self, runner):
        """If both body and body_file exist, body takes precedence."""
        issue = {
            "title": "Test",
            "body": "Inline content",
            "body_file": "/some/path.md"
        }
        result = runner._resolve_body(issue)
        assert result == "Inline content"
