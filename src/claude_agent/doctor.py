"""
Doctor Command Module
=====================

Health check logic for the claude-agent doctor command.
Validates environment, tools, and configuration before running coding sessions.
"""

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import click

from claude_agent.config import find_config_file, load_config_file
from claude_agent.detection import detect_stack
from claude_agent.errors import ConfigParseError


# =============================================================================
# Constants
# =============================================================================

# Subprocess timeout in seconds (spec requirement)
SUBPROCESS_TIMEOUT = 3

# Known configuration keys for unknown key detection
KNOWN_CONFIG_KEYS = {
    "spec_file",
    "goal",
    "features",
    "stack",
    "agent",
    "security",
    "validator",
    "workflow",
    "logging",
    "evaluation",
    "architecture",
}

# Minimum recommended versions (advisory warnings only)
MIN_NODE_VERSION = 18
MIN_PYTHON_VERSION = (3, 10)
MIN_NPM_VERSION = 8


# =============================================================================
# Enums and Data Classes
# =============================================================================


class CheckStatus(Enum):
    """Status of a single health check."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


@dataclass
class CheckResult:
    """Result of a single health check."""

    name: str
    category: str  # authentication, tools, project
    status: CheckStatus
    message: str
    fix_command: Optional[str] = None
    version: Optional[str] = None
    details: Optional[str] = None


@dataclass
class DoctorReport:
    """Complete doctor check report."""

    checks: list[CheckResult]
    project_dir: Optional[str] = None
    stack: Optional[str] = None

    @property
    def error_count(self) -> int:
        """Count of failed checks."""
        return sum(1 for c in self.checks if c.status == CheckStatus.FAIL)

    @property
    def warning_count(self) -> int:
        """Count of warning checks."""
        return sum(1 for c in self.checks if c.status == CheckStatus.WARN)

    @property
    def pass_count(self) -> int:
        """Count of passed checks."""
        return sum(1 for c in self.checks if c.status == CheckStatus.PASS)

    @property
    def is_healthy(self) -> bool:
        """True if no errors (warnings allowed)."""
        return self.error_count == 0


@dataclass
class FixResult:
    """Result of an auto-fix attempt."""

    name: str
    success: bool
    message: str
    fix_type: str  # fixed, manual, failed, suggestion


# =============================================================================
# Helper Functions
# =============================================================================


def _run_command(
    cmd: list[str], timeout: int = SUBPROCESS_TIMEOUT
) -> tuple[bool, str, str]:
    """Run a command and return (success, stdout, stderr).

    Args:
        cmd: Command and arguments as list
        timeout: Timeout in seconds

    Returns:
        Tuple of (success, stdout, stderr)
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out after {timeout} seconds"
    except FileNotFoundError:
        return False, "", f"Command not found: {cmd[0]}"
    except Exception as e:
        return False, "", str(e)


def _parse_version(output: str) -> Optional[str]:
    """Extract version number from command output.

    Handles various version output formats:
    - "v1.2.3"
    - "git version 2.39.0"
    - "Python 3.12.0"
    - "1.2.3"
    """
    import re

    # Remove leading 'v' if present
    output = output.strip()

    # Try to find version pattern
    patterns = [
        r"v?(\d+\.\d+\.\d+)",  # Standard semver
        r"v?(\d+\.\d+)",  # Major.minor only
    ]

    for pattern in patterns:
        match = re.search(pattern, output)
        if match:
            return match.group(1)

    return None


def _parse_major_version(version_str: Optional[str]) -> Optional[int]:
    """Extract major version number from version string."""
    if not version_str:
        return None
    try:
        return int(version_str.split(".")[0])
    except (ValueError, IndexError):
        return None


def _parse_python_version(version_str: Optional[str]) -> Optional[tuple[int, int]]:
    """Extract (major, minor) version from Python version string."""
    if not version_str:
        return None
    try:
        parts = version_str.split(".")
        return (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return None


# =============================================================================
# Individual Check Functions
# =============================================================================


def check_claude_cli(verbose: bool = False) -> CheckResult:
    """Verify Claude Code CLI installation and responsiveness.

    Returns CheckResult with:
    - PASS if installed and responds to --version
    - FAIL if not installed or times out
    """
    name = "Claude Code CLI"
    category = "authentication"

    # First check if command exists in PATH
    claude_path = shutil.which("claude")
    if not claude_path:
        return CheckResult(
            name=name,
            category=category,
            status=CheckStatus.FAIL,
            message="Claude Code CLI not installed",
            fix_command="Install Claude Code CLI from https://claude.ai/code",
            details=f"PATH: {os.environ.get('PATH', '')}" if verbose else None,
        )

    # Run claude --version
    details_parts = []
    if verbose:
        details_parts.append(f"Running: claude --version")
        details_parts.append(f"Path: {claude_path}")

    success, stdout, stderr = _run_command(["claude", "--version"])

    if not success:
        if "timed out" in stderr:
            return CheckResult(
                name=name,
                category=category,
                status=CheckStatus.FAIL,
                message="Claude Code CLI not responding (timeout)",
                fix_command="Run 'claude login' to authenticate",
                details="\n".join(details_parts) if details_parts else None,
            )
        return CheckResult(
            name=name,
            category=category,
            status=CheckStatus.FAIL,
            message=f"Claude Code CLI error: {stderr[:100]}",
            fix_command="Run 'claude login' to authenticate",
            details=stderr if verbose else None,
        )

    version = _parse_version(stdout)
    if verbose:
        details_parts.append(f"Output: {stdout.strip()}")

    return CheckResult(
        name=name,
        category=category,
        status=CheckStatus.PASS,
        message="Claude Code CLI installed",
        version=version,
        details="\n".join(details_parts) if details_parts else None,
    )


def check_git(verbose: bool = False) -> CheckResult:
    """Verify git is installed and accessible.

    Returns CheckResult with:
    - PASS if installed with version
    - FAIL if not installed
    """
    name = "Git"
    category = "tools"

    # Check if command exists
    git_path = shutil.which("git")
    if not git_path:
        return CheckResult(
            name=name,
            category=category,
            status=CheckStatus.FAIL,
            message="Git not installed",
            fix_command="Install Git: https://git-scm.com/downloads",
            details=f"PATH: {os.environ.get('PATH', '')}" if verbose else None,
        )

    # Run git --version
    details_parts = []
    if verbose:
        details_parts.append(f"Running: git --version")
        details_parts.append(f"Path: {git_path}")

    success, stdout, stderr = _run_command(["git", "--version"])

    if not success:
        return CheckResult(
            name=name,
            category=category,
            status=CheckStatus.FAIL,
            message=f"Git error: {stderr[:100]}",
            fix_command="Reinstall Git: https://git-scm.com/downloads",
            details=stderr if verbose else None,
        )

    version = _parse_version(stdout)
    if verbose:
        details_parts.append(f"Output: {stdout.strip()}")

    return CheckResult(
        name=name,
        category=category,
        status=CheckStatus.PASS,
        message="Git available",
        version=version,
        details="\n".join(details_parts) if details_parts else None,
    )


def check_stack_tools(stack: str, verbose: bool = False) -> list[CheckResult]:
    """Verify tools required for the detected tech stack.

    Args:
        stack: Stack name ('node' or 'python')
        verbose: Include detailed diagnostics

    Returns:
        List of CheckResult for each stack-specific tool
    """
    if stack == "node":
        return _check_node_tools(verbose)
    elif stack == "python":
        return _check_python_tools(verbose)
    else:
        # Unknown stack - return empty list
        return []


def _check_node_tools(verbose: bool = False) -> list[CheckResult]:
    """Check Node.js stack tools."""
    results = []
    category = "tools"

    # Check Node.js
    node_path = shutil.which("node")
    if not node_path:
        results.append(
            CheckResult(
                name="Node.js",
                category=category,
                status=CheckStatus.FAIL,
                message="Node.js not installed",
                fix_command="Install Node.js: https://nodejs.org/",
            )
        )
    else:
        details_parts = []
        if verbose:
            details_parts.append(f"Running: node --version")
            details_parts.append(f"Path: {node_path}")

        success, stdout, stderr = _run_command(["node", "--version"])
        version = _parse_version(stdout) if success else None

        if verbose and success:
            details_parts.append(f"Output: {stdout.strip()}")

        # Check version for advisory warning
        major = _parse_major_version(version)
        if success and major is not None and major < MIN_NODE_VERSION:
            results.append(
                CheckResult(
                    name="Node.js",
                    category=category,
                    status=CheckStatus.WARN,
                    message=f"Node.js version {version} is below recommended minimum ({MIN_NODE_VERSION}.x)",
                    version=version,
                    details="\n".join(details_parts) if details_parts else None,
                )
            )
        elif success:
            results.append(
                CheckResult(
                    name="Node.js",
                    category=category,
                    status=CheckStatus.PASS,
                    message="Node.js available",
                    version=version,
                    details="\n".join(details_parts) if details_parts else None,
                )
            )
        else:
            results.append(
                CheckResult(
                    name="Node.js",
                    category=category,
                    status=CheckStatus.FAIL,
                    message=f"Node.js error: {stderr[:100]}",
                    fix_command="Reinstall Node.js: https://nodejs.org/",
                    details=stderr if verbose else None,
                )
            )

    # Check npm
    npm_path = shutil.which("npm")
    if not npm_path:
        results.append(
            CheckResult(
                name="npm",
                category=category,
                status=CheckStatus.FAIL,
                message="npm not installed",
                fix_command="Install Node.js (includes npm): https://nodejs.org/",
            )
        )
    else:
        details_parts = []
        if verbose:
            details_parts.append(f"Running: npm --version")
            details_parts.append(f"Path: {npm_path}")

        success, stdout, stderr = _run_command(["npm", "--version"])
        version = _parse_version(stdout) if success else None

        if verbose and success:
            details_parts.append(f"Output: {stdout.strip()}")

        # Check version for advisory warning
        major = _parse_major_version(version)
        if success and major is not None and major < MIN_NPM_VERSION:
            results.append(
                CheckResult(
                    name="npm",
                    category=category,
                    status=CheckStatus.WARN,
                    message=f"npm version {version} is below recommended minimum ({MIN_NPM_VERSION}.x)",
                    version=version,
                    details="\n".join(details_parts) if details_parts else None,
                )
            )
        elif success:
            results.append(
                CheckResult(
                    name="npm",
                    category=category,
                    status=CheckStatus.PASS,
                    message="npm available",
                    version=version,
                    details="\n".join(details_parts) if details_parts else None,
                )
            )
        else:
            results.append(
                CheckResult(
                    name="npm",
                    category=category,
                    status=CheckStatus.FAIL,
                    message=f"npm error: {stderr[:100]}",
                    fix_command="Reinstall Node.js (includes npm): https://nodejs.org/",
                    details=stderr if verbose else None,
                )
            )

    return results


def _check_python_tools(verbose: bool = False) -> list[CheckResult]:
    """Check Python stack tools."""
    results = []
    category = "tools"

    # Check Python 3
    python_path = shutil.which("python3")
    if not python_path:
        results.append(
            CheckResult(
                name="Python",
                category=category,
                status=CheckStatus.FAIL,
                message="Python 3 not installed",
                fix_command="Install Python: https://www.python.org/downloads/",
            )
        )
    else:
        details_parts = []
        if verbose:
            details_parts.append(f"Running: python3 --version")
            details_parts.append(f"Path: {python_path}")

        success, stdout, stderr = _run_command(["python3", "--version"])
        version = _parse_version(stdout) if success else None

        if verbose and success:
            details_parts.append(f"Output: {stdout.strip()}")

        # Check version for advisory warning
        py_version = _parse_python_version(version)
        if success and py_version is not None and py_version < MIN_PYTHON_VERSION:
            results.append(
                CheckResult(
                    name="Python",
                    category=category,
                    status=CheckStatus.WARN,
                    message=f"Python version {version} is below recommended minimum ({MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]})",
                    version=version,
                    details="\n".join(details_parts) if details_parts else None,
                )
            )
        elif success:
            results.append(
                CheckResult(
                    name="Python",
                    category=category,
                    status=CheckStatus.PASS,
                    message="Python available",
                    version=version,
                    details="\n".join(details_parts) if details_parts else None,
                )
            )
        else:
            results.append(
                CheckResult(
                    name="Python",
                    category=category,
                    status=CheckStatus.FAIL,
                    message=f"Python error: {stderr[:100]}",
                    fix_command="Reinstall Python: https://www.python.org/downloads/",
                    details=stderr if verbose else None,
                )
            )

    # Check pip3 or uv (either is acceptable)
    pip_path = shutil.which("pip3")
    uv_path = shutil.which("uv")

    if not pip_path and not uv_path:
        results.append(
            CheckResult(
                name="pip/uv",
                category=category,
                status=CheckStatus.FAIL,
                message="Neither pip3 nor uv installed",
                fix_command="Install pip or uv: pip comes with Python, or install uv from https://github.com/astral-sh/uv",
            )
        )
    elif uv_path:
        # Prefer uv if available
        details_parts = []
        if verbose:
            details_parts.append(f"Running: uv --version")
            details_parts.append(f"Path: {uv_path}")

        success, stdout, stderr = _run_command(["uv", "--version"])
        version = _parse_version(stdout) if success else None

        if verbose and success:
            details_parts.append(f"Output: {stdout.strip()}")

        if success:
            results.append(
                CheckResult(
                    name="uv",
                    category=category,
                    status=CheckStatus.PASS,
                    message="uv available",
                    version=version,
                    details="\n".join(details_parts) if details_parts else None,
                )
            )
        else:
            # Fall back to pip3
            if pip_path:
                success, stdout, stderr = _run_command(["pip3", "--version"])
                version = _parse_version(stdout) if success else None
                results.append(
                    CheckResult(
                        name="pip",
                        category=category,
                        status=CheckStatus.PASS if success else CheckStatus.FAIL,
                        message="pip available" if success else f"pip error: {stderr[:100]}",
                        version=version,
                    )
                )
            else:
                results.append(
                    CheckResult(
                        name="uv",
                        category=category,
                        status=CheckStatus.FAIL,
                        message=f"uv error: {stderr[:100]}",
                        fix_command="Reinstall uv: https://github.com/astral-sh/uv",
                        details=stderr if verbose else None,
                    )
                )
    else:
        # Use pip3
        details_parts = []
        if verbose:
            details_parts.append(f"Running: pip3 --version")
            details_parts.append(f"Path: {pip_path}")

        success, stdout, stderr = _run_command(["pip3", "--version"])
        version = _parse_version(stdout) if success else None

        if verbose and success:
            details_parts.append(f"Output: {stdout.strip()}")

        if success:
            results.append(
                CheckResult(
                    name="pip",
                    category=category,
                    status=CheckStatus.PASS,
                    message="pip available",
                    version=version,
                    details="\n".join(details_parts) if details_parts else None,
                )
            )
        else:
            results.append(
                CheckResult(
                    name="pip",
                    category=category,
                    status=CheckStatus.FAIL,
                    message=f"pip error: {stderr[:100]}",
                    fix_command="Reinstall Python (includes pip): https://www.python.org/downloads/",
                    details=stderr if verbose else None,
                )
            )

    return results


def check_puppeteer(verbose: bool = False, npm_available: bool = True) -> CheckResult:
    """Verify puppeteer-mcp-server is available.

    Args:
        verbose: Include detailed diagnostics
        npm_available: Whether npm check passed (skip if False)

    Returns:
        CheckResult with PASS, FAIL, or SKIP status
    """
    name = "puppeteer-mcp-server"
    category = "tools"

    # Skip if npm is not available
    if not npm_available:
        return CheckResult(
            name=name,
            category=category,
            status=CheckStatus.SKIP,
            message="Skipped (requires npm)",
            details="npm check failed, puppeteer-mcp-server check skipped" if verbose else None,
        )

    details_parts = []

    # Try npm list -g first (faster, doesn't execute code)
    if verbose:
        details_parts.append("Running: npm list -g puppeteer-mcp-server")

    success, stdout, stderr = _run_command(
        ["npm", "list", "-g", "puppeteer-mcp-server", "--depth=0"],
        timeout=5,  # npm list can be slow
    )

    if success and "puppeteer-mcp-server" in stdout:
        # Parse version from npm list output
        version = _parse_version(stdout)
        if verbose:
            details_parts.append(f"Output: {stdout.strip()}")

        return CheckResult(
            name=name,
            category=category,
            status=CheckStatus.PASS,
            message="puppeteer-mcp-server available",
            version=version,
            details="\n".join(details_parts) if details_parts else None,
        )

    # Not found globally
    if verbose:
        details_parts.append(f"Result: Not found in global packages")

    return CheckResult(
        name=name,
        category=category,
        status=CheckStatus.FAIL,
        message="puppeteer-mcp-server not found",
        fix_command="npm install -g puppeteer-mcp-server",
        details="\n".join(details_parts) if details_parts else None,
    )


def check_project_dir(path: Path, verbose: bool = False) -> CheckResult:
    """Verify project directory exists and is writable.

    Args:
        path: Project directory path
        verbose: Include detailed diagnostics

    Returns:
        CheckResult with PASS or FAIL status
    """
    name = "Project Directory"
    category = "project"
    path_str = str(path)

    details_parts = []
    if verbose:
        details_parts.append(f"Checking: {path_str}")

    # Check if directory exists
    if not path.exists():
        return CheckResult(
            name=name,
            category=category,
            status=CheckStatus.FAIL,
            message=f"Directory does not exist: {path_str}",
            fix_command=f"mkdir -p {path_str}",
            details="\n".join(details_parts) if details_parts else None,
        )

    # Check if it's a directory (not a file)
    if not path.is_dir():
        return CheckResult(
            name=name,
            category=category,
            status=CheckStatus.FAIL,
            message=f"Path exists but is not a directory: {path_str}",
            details="\n".join(details_parts) if details_parts else None,
        )

    # Check write permissions by creating a temp file
    try:
        with tempfile.NamedTemporaryFile(dir=path, delete=True) as tmp:
            if verbose:
                details_parts.append(f"Write test: Created temp file {tmp.name}")
    except PermissionError:
        return CheckResult(
            name=name,
            category=category,
            status=CheckStatus.FAIL,
            message=f"Permission denied: cannot write to {path_str}",
            fix_command=f"Check directory permissions: ls -la {path_str}",
            details="\n".join(details_parts) if details_parts else None,
        )
    except Exception as e:
        return CheckResult(
            name=name,
            category=category,
            status=CheckStatus.FAIL,
            message=f"Cannot access directory: {str(e)[:100]}",
            details="\n".join(details_parts) if details_parts else None,
        )

    if verbose:
        details_parts.append("Result: Directory exists and is writable")

    return CheckResult(
        name=name,
        category=category,
        status=CheckStatus.PASS,
        message="Directory exists and writable",
        details="\n".join(details_parts) if details_parts else None,
    )


def check_config(project_dir: Path, verbose: bool = False) -> list[CheckResult]:
    """Validate .claude-agent.yaml if present.

    Args:
        project_dir: Directory to search for config file
        verbose: Include detailed diagnostics

    Returns:
        List of CheckResult (may include warning for unknown keys)
    """
    results = []
    name = "Configuration File"
    category = "project"

    details_parts = []
    if verbose:
        details_parts.append(f"Searching for config in: {project_dir}")

    # Find config file
    config_path = find_config_file(project_dir)

    if config_path is None:
        if verbose:
            details_parts.append("Result: No config file found (optional)")

        # Config is optional - not an error, just a note
        results.append(
            CheckResult(
                name=name,
                category=category,
                status=CheckStatus.PASS,
                message=".claude-agent.yaml not found (optional)",
                fix_command="claude-agent init",
                details="\n".join(details_parts) if details_parts else None,
            )
        )
        return results

    if verbose:
        details_parts.append(f"Found: {config_path}")

    # Try to load and validate
    try:
        config_data = load_config_file(config_path)

        if verbose:
            details_parts.append(f"Parsed successfully with {len(config_data)} keys")

        # Check for unknown keys
        unknown_keys = set(config_data.keys()) - KNOWN_CONFIG_KEYS
        if unknown_keys:
            if verbose:
                details_parts.append(f"Unknown keys found: {unknown_keys}")

            results.append(
                CheckResult(
                    name=name,
                    category=category,
                    status=CheckStatus.WARN,
                    message=f"Unknown configuration keys: {', '.join(sorted(unknown_keys))}",
                    details="\n".join(details_parts) if details_parts else None,
                )
            )
        else:
            results.append(
                CheckResult(
                    name=name,
                    category=category,
                    status=CheckStatus.PASS,
                    message=".claude-agent.yaml found and valid",
                    details="\n".join(details_parts) if details_parts else None,
                )
            )

    except ConfigParseError as e:
        if verbose:
            details_parts.append(f"Parse error: {e.original_error}")

        location = f" at line {e.line_number}" if e.line_number else ""
        results.append(
            CheckResult(
                name=name,
                category=category,
                status=CheckStatus.FAIL,
                message=f"YAML syntax error{location}: {e.original_error}",
                fix_command="Check YAML syntax and fix errors",
                details="\n".join(details_parts) if details_parts else None,
            )
        )

    return results


# =============================================================================
# Main Orchestration Functions
# =============================================================================


def run_doctor_checks(
    project_dir: Path,
    stack: Optional[str] = None,
    verbose: bool = False,
) -> DoctorReport:
    """Run all health checks and return a DoctorReport.

    Args:
        project_dir: Project directory to check
        stack: Tech stack name (auto-detected if not provided)
        verbose: Include detailed diagnostics

    Returns:
        DoctorReport with all check results
    """
    checks: list[CheckResult] = []

    # Auto-detect stack if not provided
    if stack is None:
        stack = detect_stack(project_dir)

    # Run checks in order with dependency handling
    # 1. Authentication
    checks.append(check_claude_cli(verbose=verbose))

    # 2. Required tools
    checks.append(check_git(verbose=verbose))

    # 3. Stack-specific tools
    stack_results = check_stack_tools(stack, verbose=verbose)
    checks.extend(stack_results)

    # 4. Puppeteer (depends on npm for node stack)
    npm_available = True
    if stack == "node":
        # Check if npm passed
        npm_checks = [r for r in stack_results if r.name == "npm"]
        npm_available = any(r.status == CheckStatus.PASS for r in npm_checks)

    checks.append(check_puppeteer(verbose=verbose, npm_available=npm_available))

    # 5. Project directory
    checks.append(check_project_dir(project_dir, verbose=verbose))

    # 6. Configuration
    config_results = check_config(project_dir, verbose=verbose)
    checks.extend(config_results)

    return DoctorReport(
        checks=checks,
        project_dir=str(project_dir),
        stack=stack,
    )


def attempt_fixes(
    report: DoctorReport,
    project_dir: Path,
) -> list[FixResult]:
    """Attempt automatic remediation of detected issues.

    Args:
        report: Doctor report with failed checks
        project_dir: Project directory for fixes

    Returns:
        List of FixResult describing what was attempted
    """
    results: list[FixResult] = []

    for check in report.checks:
        if check.status != CheckStatus.FAIL:
            continue

        # Handle specific fix cases
        if check.name == "Project Directory":
            # Create missing directory
            try:
                Path(project_dir).mkdir(parents=True, exist_ok=True)
                results.append(
                    FixResult(
                        name="Project Directory",
                        success=True,
                        message=f"Created directory: {project_dir}",
                        fix_type="fixed",
                    )
                )
            except Exception as e:
                results.append(
                    FixResult(
                        name="Project Directory",
                        success=False,
                        message=f"Failed to create directory: {e}",
                        fix_type="failed",
                    )
                )

        elif check.name == "puppeteer-mcp-server":
            # Install with user confirmation
            if click.confirm("Install puppeteer-mcp-server globally?"):
                success, stdout, stderr = _run_command(
                    ["npm", "install", "-g", "puppeteer-mcp-server"],
                    timeout=120,  # npm install can be slow
                )
                if success:
                    results.append(
                        FixResult(
                            name="puppeteer-mcp-server",
                            success=True,
                            message="Installed puppeteer-mcp-server",
                            fix_type="fixed",
                        )
                    )
                else:
                    results.append(
                        FixResult(
                            name="puppeteer-mcp-server",
                            success=False,
                            message=f"Install failed: {stderr[:100]}",
                            fix_type="failed",
                        )
                    )
            else:
                results.append(
                    FixResult(
                        name="puppeteer-mcp-server",
                        success=False,
                        message="User declined installation",
                        fix_type="manual",
                    )
                )

        elif check.name == "Configuration File" and "not found" in check.message.lower():
            # Suggest init, don't auto-create
            results.append(
                FixResult(
                    name="Configuration File",
                    success=False,
                    message="Run 'claude-agent init' to create config file",
                    fix_type="suggestion",
                )
            )

        elif check.name == "Configuration File":
            # Config exists but has errors - don't modify
            results.append(
                FixResult(
                    name="Configuration File",
                    success=False,
                    message="Manual fix required for config file errors",
                    fix_type="manual",
                )
            )

        elif check.name in ("Claude Code CLI", "Git", "Node.js", "npm", "Python", "pip", "uv"):
            # System tools - can't auto-fix
            results.append(
                FixResult(
                    name=check.name,
                    success=False,
                    message=f"Manual installation required: {check.fix_command or 'see documentation'}",
                    fix_type="manual",
                )
            )

    return results


# =============================================================================
# Output Formatting Functions
# =============================================================================


def format_report(
    report: DoctorReport,
    verbose: bool = False,
) -> str:
    """Format DoctorReport for console output.

    Args:
        report: The doctor report to format
        verbose: Include additional diagnostic info

    Returns:
        Formatted string for console output
    """
    lines = []

    # Check NO_COLOR
    use_color = os.environ.get("NO_COLOR") is None

    # Status symbols
    symbols = {
        CheckStatus.PASS: "[✓]",
        CheckStatus.FAIL: "[✗]",
        CheckStatus.WARN: "[!]",
        CheckStatus.SKIP: "[-]",
    }

    # Color styling function
    def style_status(text: str, status: CheckStatus) -> str:
        if not use_color:
            return text
        colors = {
            CheckStatus.PASS: "green",
            CheckStatus.FAIL: "red",
            CheckStatus.WARN: "yellow",
            CheckStatus.SKIP: "white",
        }
        return click.style(text, fg=colors.get(status))

    # Header
    if use_color:
        lines.append(click.style("Claude Agent Environment Check", bold=True))
    else:
        lines.append("Claude Agent Environment Check")
    lines.append("=" * 30)
    lines.append("")

    # Show PATH in verbose mode
    if verbose:
        path_val = os.environ.get("PATH", "")
        if len(path_val) > 100:
            path_val = path_val[:97] + "..."
        lines.append(f"PATH: {path_val}")
        lines.append("")

    # Group checks by category
    categories = {
        "authentication": "Authentication",
        "tools": "Required Tools",
        "project": f"Project ({report.project_dir})" if report.project_dir else "Project",
    }

    for cat_key, cat_name in categories.items():
        cat_checks = [c for c in report.checks if c.category == cat_key]
        if not cat_checks:
            continue

        # Category header
        if use_color:
            lines.append(click.style(f"{cat_name}:", bold=True))
        else:
            lines.append(f"{cat_name}:")

        for check in cat_checks:
            symbol = symbols[check.status]
            styled_symbol = style_status(symbol, check.status)

            # Format check line
            version_str = f" ({check.version})" if check.version else ""
            lines.append(f"  {styled_symbol} {check.message}{version_str}")

            # Show fix command for failed checks
            if check.status == CheckStatus.FAIL and check.fix_command:
                lines.append(f"      Run: {check.fix_command}")

            # Show details in verbose mode
            if verbose and check.details:
                for detail_line in check.details.split("\n"):
                    if len(detail_line) > 500:
                        detail_line = detail_line[:497] + "..."
                    lines.append(f"      {detail_line}")

        lines.append("")

    # Stack info
    if report.stack:
        lines.append(f"Stack detected: {report.stack}")
        lines.append("")

    # Summary
    if report.is_healthy:
        if report.warning_count > 0:
            summary = f"Summary: All checks passed with {report.warning_count} warning(s)"
            if use_color:
                summary = click.style(summary, fg="yellow")
        else:
            summary = "Summary: All checks passed!"
            if use_color:
                summary = click.style(summary, fg="green")
        lines.append(summary)
        lines.append("Run 'claude-agent' to start your coding session.")
    else:
        summary = f"Summary: {report.error_count} error(s), {report.warning_count} warning(s)"
        if use_color:
            summary = click.style(summary, fg="red")
        lines.append(summary)
        lines.append("Run 'claude-agent doctor --fix' to attempt automatic fixes.")

    return "\n".join(lines)


def format_report_json(report: DoctorReport) -> dict:
    """Format DoctorReport as JSON-serializable dict.

    Args:
        report: The doctor report to format

    Returns:
        Dictionary ready for JSON serialization
    """
    checks_output = []
    for check in report.checks:
        check_dict = {
            "name": check.name,
            "category": check.category,
            "status": check.status.value,
            "message": check.message,
        }
        if check.version is not None:
            check_dict["version"] = check.version
        if check.fix_command is not None:
            check_dict["fix_command"] = check.fix_command
        checks_output.append(check_dict)

    return {
        "project_dir": report.project_dir,
        "stack": report.stack,
        "summary": {
            "errors": report.error_count,
            "warnings": report.warning_count,
            "passed": report.pass_count,
        },
        "is_healthy": report.is_healthy,
        "checks": checks_output,
    }


def format_fix_results(results: list[FixResult]) -> str:
    """Format fix results for console output.

    Args:
        results: List of fix results

    Returns:
        Formatted string for console output
    """
    if not results:
        return "No fixes attempted."

    lines = []

    # Check NO_COLOR
    use_color = os.environ.get("NO_COLOR") is None

    lines.append("")
    if use_color:
        lines.append(click.style("Fix Results:", bold=True))
    else:
        lines.append("Fix Results:")

    symbols = {
        "fixed": "[✓]",
        "manual": "[!]",
        "failed": "[✗]",
        "suggestion": "[→]",
    }

    colors = {
        "fixed": "green",
        "manual": "yellow",
        "failed": "red",
        "suggestion": "cyan",
    }

    for result in results:
        symbol = symbols.get(result.fix_type, "[-]")
        label = result.fix_type.capitalize()

        if use_color:
            symbol = click.style(symbol, fg=colors.get(result.fix_type, "white"))
            label = click.style(label, fg=colors.get(result.fix_type, "white"))

        lines.append(f"  {symbol} {label}: {result.message}")

    return "\n".join(lines)
