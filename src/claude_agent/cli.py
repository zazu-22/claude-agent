"""
Claude Agent CLI
================

Command-line interface for the autonomous coding agent.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

import click

from claude_agent import __version__
from claude_agent.agent import run_autonomous_agent
from claude_agent.config import (
    Config,
    generate_config_template,
    merge_config,
)
from claude_agent.detection import detect_stack, get_available_stacks
from claude_agent.progress import (
    count_passing_tests,
    get_session_state,
    print_progress_summary,
)


@click.group(invoke_without_command=True)
@click.argument("project_dir", type=click.Path(path_type=Path), default=".")
@click.option(
    "--spec", "-s",
    type=click.Path(exists=True, path_type=Path),
    help="Path to specification file",
)
@click.option(
    "--goal", "-g",
    type=str,
    help="Short goal description (alternative to --spec)",
)
@click.option(
    "--features", "-f",
    type=int,
    help="Number of features to generate (default: 50)",
)
@click.option(
    "--stack",
    type=click.Choice(get_available_stacks()),
    help="Tech stack (auto-detected if not specified)",
)
@click.option(
    "--model", "-m",
    type=str,
    help="Claude model to use",
)
@click.option(
    "--max-iterations", "-n",
    type=int,
    help="Maximum agent iterations",
)
@click.option(
    "--config", "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config file",
)
@click.option(
    "--review", "-r",
    is_flag=True,
    help="Review spec before generating features (recommended for new specs)",
)
@click.version_option(version=__version__)
@click.pass_context
def main(
    ctx,
    project_dir: Path,
    spec: Optional[Path],
    goal: Optional[str],
    features: Optional[int],
    stack: Optional[str],
    model: Optional[str],
    max_iterations: Optional[int],
    config: Optional[Path],
    review: bool,
):
    """
    Claude Agent - Autonomous coding agent powered by Claude.

    Run long-running autonomous coding sessions with persistent progress
    tracking across multiple context windows.

    \b
    Examples:
      claude-agent ./my-project --spec ./SPEC.md
      claude-agent ./my-project --goal "Build a REST API"
      claude-agent ./my-project  # Uses wizard if no spec
    """
    # If a subcommand was invoked, don't run the main agent
    if ctx.invoked_subcommand is not None:
        return

    # Note: claude-code-sdk uses Claude Code CLI's OAuth authentication
    # (your Max subscription), so ANTHROPIC_API_KEY is not required.
    # The SDK will use your existing Claude Code authentication.

    # Resolve project directory
    project_dir = project_dir.resolve()

    # Merge configuration from all sources
    merged_config = merge_config(
        project_dir=project_dir,
        cli_spec=spec,
        cli_goal=goal,
        cli_features=features,
        cli_stack=stack,
        cli_model=model,
        cli_max_iterations=max_iterations,
        cli_config_path=config,
        cli_review=review,
    )

    # Check if we have a spec - if not, run the wizard
    if not merged_config.spec_content:
        # Check if this is a continuation (feature_list.json exists)
        feature_list = project_dir / "feature_list.json"
        if feature_list.exists():
            # Continuing existing project - no spec needed
            pass
        else:
            # New project with no spec - run wizard
            from claude_agent.wizard import run_wizard
            spec_content = run_wizard(project_dir)
            if spec_content:
                merged_config.goal = spec_content
            else:
                click.echo("No specification provided. Exiting.")
                sys.exit(1)

    # Run the agent
    try:
        asyncio.run(run_autonomous_agent(merged_config))
    except KeyboardInterrupt:
        click.echo("\n\nInterrupted by user")
        click.echo("To resume, run the same command again")
    except Exception as e:
        click.echo(f"\nFatal error: {e}")
        raise


@main.command()
@click.argument("project_dir", type=click.Path(path_type=Path), default=".")
def init(project_dir: Path):
    """Initialize a new project with a config file template."""
    project_dir = project_dir.resolve()
    project_dir.mkdir(parents=True, exist_ok=True)

    config_path = project_dir / ".claude-agent.yaml"
    if config_path.exists():
        click.echo(f"Config file already exists: {config_path}")
        if not click.confirm("Overwrite?"):
            return

    config_content = generate_config_template()
    config_path.write_text(config_content)
    click.echo(f"Created config file: {config_path}")
    click.echo("\nEdit this file to configure your project, then run:")
    click.echo(f"  claude-agent {project_dir}")


@main.command()
@click.argument("project_dir", type=click.Path(exists=True, path_type=Path), default=".")
def status(project_dir: Path):
    """Show project status and progress."""
    project_dir = project_dir.resolve()

    click.echo(f"\nProject: {project_dir}")

    # Detect stack
    stack = detect_stack(project_dir)
    click.echo(f"Stack:   {stack}")

    # Get session state
    state = get_session_state(project_dir)
    click.echo(f"State:   {state}")

    # Show progress
    print_progress_summary(project_dir)

    # Show recent progress notes if available
    progress_file = project_dir / "claude-progress.txt"
    if progress_file.exists():
        click.echo("\nRecent progress notes:")
        content = progress_file.read_text()
        # Show last 20 lines
        lines = content.strip().split("\n")
        for line in lines[-20:]:
            click.echo(f"  {line}")


if __name__ == "__main__":
    main()
