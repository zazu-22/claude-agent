#!/usr/bin/env bash
#
# Claude Agent - Development Environment Setup
# =============================================
#
# This script sets up and runs the development environment for claude-agent.
# It installs dependencies using uv and provides helpful information.
#
# Usage:
#   ./init.sh          # Full setup and information
#   ./init.sh --quick  # Quick dependency install only
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "======================================================================"
echo "  CLAUDE AGENT - Development Environment Setup"
echo "======================================================================"
echo ""

# Check for uv
if ! command -v uv &> /dev/null; then
    echo -e "${RED}Error: 'uv' is not installed.${NC}"
    echo ""
    echo "Please install uv first:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo ""
    echo "Or via pip:"
    echo "  pip install uv"
    echo ""
    exit 1
fi

echo -e "${GREEN}[OK]${NC} uv found: $(uv --version)"

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
REQUIRED_VERSION="3.10"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo -e "${RED}Error: Python $REQUIRED_VERSION+ is required, found Python $PYTHON_VERSION${NC}"
    exit 1
fi

echo -e "${GREEN}[OK]${NC} Python version: $PYTHON_VERSION"
echo ""

# Install dependencies
echo "Installing dependencies..."
echo "----------------------------------------------------------------------"

if [ "$1" == "--quick" ]; then
    uv sync
else
    uv sync --extra dev
fi

echo ""
echo -e "${GREEN}[OK]${NC} Dependencies installed successfully"
echo ""

# Quick mode exits here
if [ "$1" == "--quick" ]; then
    echo "Quick setup complete. Run './init.sh' for full setup information."
    exit 0
fi

# Verify installation
echo "Verifying installation..."
echo "----------------------------------------------------------------------"

if uv run claude-agent --version &> /dev/null; then
    VERSION=$(uv run claude-agent --version)
    echo -e "${GREEN}[OK]${NC} claude-agent installed: $VERSION"
else
    echo -e "${RED}[FAIL]${NC} claude-agent installation failed"
    exit 1
fi

echo ""

# Run tests to verify setup
echo "Running tests to verify setup..."
echo "----------------------------------------------------------------------"

if uv run pytest -q --tb=no 2>/dev/null; then
    echo -e "${GREEN}[OK]${NC} All tests pass"
else
    echo -e "${YELLOW}[WARN]${NC} Some tests may have failed - check output above"
fi

echo ""
echo "======================================================================"
echo "  SETUP COMPLETE"
echo "======================================================================"
echo ""
echo -e "${BLUE}Available Commands:${NC}"
echo ""
echo "  Main CLI:"
echo "    uv run claude-agent --help              # Show help"
echo "    uv run claude-agent status .            # Check project status"
echo "    uv run claude-agent init .              # Initialize config file"
echo ""
echo "  Spec Workflow (new):"
echo "    uv run claude-agent spec create -g \"your goal\"  # Create specification"
echo "    uv run claude-agent spec validate               # Validate spec"
echo "    uv run claude-agent spec decompose              # Generate features"
echo "    uv run claude-agent spec auto -g \"your goal\"    # Full workflow"
echo "    uv run claude-agent spec status                 # Check workflow status"
echo ""
echo "  Development:"
echo "    uv run pytest -v                        # Run tests"
echo "    uv run ruff check src/                  # Lint code"
echo "    uv run ruff format src/                 # Format code"
echo ""
echo -e "${BLUE}Quick Start Example:${NC}"
echo ""
echo "  # Create a new project with spec workflow"
echo "  mkdir my-project && cd my-project"
echo "  uv run claude-agent spec auto -g \"Build a todo app with React\""
echo "  uv run claude-agent  # Start coding agent"
echo ""
echo "----------------------------------------------------------------------"
