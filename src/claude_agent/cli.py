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
@click.option(
    "--project-dir", "-p",
    type=click.Path(path_type=Path),
    default=".",
    help="Project directory (default: current directory)",
)
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
@click.option(
    "--reset",
    is_flag=True,
    help="Clear previous agent files and start fresh (will prompt for confirmation)",
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
    reset: bool,
):
    """
    Claude Agent - Autonomous coding agent powered by Claude.

    Run long-running autonomous coding sessions with persistent progress
    tracking across multiple context windows.

    \b
    Examples:
      claude-agent -p ./my-project --spec ./SPEC.md
      claude-agent -p ./my-project --goal "Build a REST API"
      claude-agent -p ./my-project --review --spec ./SPEC.md
      claude-agent  # Uses current directory + wizard if no spec
    """
    # If a subcommand was invoked, don't run the main agent
    if ctx.invoked_subcommand is not None:
        return

    # Note: claude-code-sdk uses Claude Code CLI's OAuth authentication
    # (your Max subscription), so ANTHROPIC_API_KEY is not required.
    # The SDK will use your existing Claude Code authentication.

    # Resolve project directory
    project_dir = project_dir.resolve()

    # Handle --reset flag
    if reset:
        agent_files = [
            "feature_list.json",
            "app_spec.txt",
            "spec-review.md",
            "claude-progress.txt",
            "validation-history.json",
            "validation-progress.txt",
        ]
        existing = [f for f in agent_files if (project_dir / f).exists()]

        if not existing:
            click.echo("No agent files to reset.")
        else:
            click.echo(f"Will delete from {project_dir}:")
            for f in existing:
                click.echo(f"  - {f}")

            if click.confirm("\nProceed with reset?"):
                for f in existing:
                    (project_dir / f).unlink()
                click.echo("Reset complete.")
                click.echo("Run 'claude-agent' again to start fresh.")
                sys.exit(0)
            else:
                click.echo("Reset cancelled.")
                sys.exit(0)

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

    # Check if we have a spec - if not, check for existing or run wizard
    if not merged_config.spec_content:
        feature_list = project_dir / "feature_list.json"
        existing_spec = project_dir / "app_spec.txt"

        if feature_list.exists():
            # Continuing existing project - no spec needed
            pass
        elif existing_spec.exists():
            # Found existing spec (e.g., from aborted review)
            click.echo(f"Found existing spec: {existing_spec}")
            merged_config.goal = existing_spec.read_text()
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
    """Initialize a new project with a config file template.

    PROJECT_DIR is the directory to initialize (default: current directory).
    """
    project_dir = Path(project_dir).resolve()
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
    """Show project status and progress.

    PROJECT_DIR is the project to check (default: current directory).
    """
    from claude_agent.progress import count_tests_by_type

    project_dir = Path(project_dir).resolve()

    click.echo(f"\nProject: {project_dir}")

    # Detect stack
    stack = detect_stack(project_dir)
    click.echo(f"Stack:   {stack}")

    # Get session state with descriptive output
    state = get_session_state(project_dir)
    counts = count_tests_by_type(project_dir)

    if state == "pending_validation":
        click.echo(f"State:   {state} (all automated tests pass, {counts['manual_total']} manual remaining)")
        click.echo("         -> Running claude-agent will trigger validation")
    elif state == "validating":
        click.echo(f"State:   {state} (all tests pass, awaiting validator approval)")
    elif state == "in_progress":
        click.echo(f"State:   {state} ({counts['automated_passing']}/{counts['automated_total']} automated tests passing)")
    else:
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


# =============================================================================
# Spec Command Group
# =============================================================================


@main.group()
def spec():
    """Spec creation and validation commands."""
    pass


@spec.command("create")
@click.option("-g", "--goal", type=str, help="What to build")
@click.option("--from-file", type=click.Path(exists=True), help="Read goal from file")
@click.option("-i", "--interactive", is_flag=True, help="Interactive mode")
@click.option("-p", "--project-dir", type=click.Path(path_type=Path), default=".")
def spec_create(goal, from_file, interactive, project_dir):
    """Create a project specification from a goal or rough idea."""
    project_dir = Path(project_dir).resolve()

    # Get goal from file if specified
    if from_file:
        goal = Path(from_file).read_text()

    # Interactive mode
    context = ""
    if interactive:
        from claude_agent.spec_wizard import interactive_spec_create
        goal, context = interactive_spec_create(project_dir)
        if not goal:
            click.echo("Cancelled.")
            sys.exit(0)

    if not goal:
        click.echo("Error: --goal or --from-file required (or use -i for interactive)")
        sys.exit(1)

    click.echo(f"Creating specification for: {goal[:100]}...")
    click.echo("Note: Full spec creation requires running the agent session.")
    click.echo("Use 'claude-agent spec auto -g \"goal\"' for full workflow.")


@spec.command("validate")
@click.argument("spec_file", type=click.Path(exists=True), required=False)
@click.option("-i", "--interactive", is_flag=True, help="Interactive mode")
@click.option("-p", "--project-dir", type=click.Path(path_type=Path), default=".")
def spec_validate(spec_file, interactive, project_dir):
    """Validate a specification for completeness and clarity."""
    project_dir = Path(project_dir).resolve()
    spec_path = Path(spec_file) if spec_file else project_dir / "spec-draft.md"

    if not spec_path.exists():
        click.echo(f"Error: {spec_path} not found")
        click.echo("Run 'claude-agent spec create' first or specify a spec file")
        sys.exit(1)

    click.echo(f"Validating: {spec_path}")
    click.echo("Note: Full validation requires running the agent session.")


@spec.command("decompose")
@click.argument("spec_file", type=click.Path(exists=True), required=False)
@click.option("-f", "--features", type=int, default=50, help="Target feature count")
@click.option("-p", "--project-dir", type=click.Path(path_type=Path), default=".")
def spec_decompose(spec_file, features, project_dir):
    """Decompose a validated spec into a feature list."""
    project_dir = Path(project_dir).resolve()
    spec_path = Path(spec_file) if spec_file else project_dir / "spec-validated.md"

    if not spec_path.exists():
        # Fall back to spec-draft.md with warning
        draft_path = project_dir / "spec-draft.md"
        if draft_path.exists():
            click.echo("Warning: Using spec-draft.md (not validated)")
            click.echo("Consider running 'claude-agent spec validate' first")
            spec_path = draft_path
        else:
            click.echo(f"Error: {spec_path} not found")
            click.echo("Run 'claude-agent spec validate' first or specify a spec file")
            sys.exit(1)

    click.echo(f"Decomposing: {spec_path}")
    click.echo(f"Target features: {features}")
    click.echo("Note: Full decomposition requires running the agent session.")


@spec.command("auto")
@click.option("-g", "--goal", type=str, required=True, help="What to build")
@click.option("-p", "--project-dir", type=click.Path(path_type=Path), default=".")
def spec_auto(goal, project_dir):
    """Run full spec workflow (create -> validate -> decompose)."""
    project_dir = Path(project_dir).resolve()

    click.echo(f"Running full spec workflow for: {goal[:100]}...")
    click.echo("Note: Full workflow requires running agent sessions.")
    click.echo("This is a placeholder - full implementation coming soon.")


@spec.command("status")
@click.option("-p", "--project-dir", type=click.Path(path_type=Path), default=".")
def spec_status(project_dir):
    """Show spec workflow progress and status."""
    from claude_agent.progress import get_spec_phase, get_spec_workflow_state

    project_dir = Path(project_dir).resolve()

    click.echo(f"\nProject: {project_dir}")

    # Get phase from files
    phase = get_spec_phase(project_dir)
    click.echo(f"Phase: {phase}")

    # Show files present
    files = {
        "spec-draft.md": "Draft specification",
        "spec-validated.md": "Validated specification",
        "spec-validation.md": "Validation report",
        "feature_list.json": "Feature list",
    }

    click.echo("\nFiles:")
    for filename, description in files.items():
        path = project_dir / filename
        status = "present" if path.exists() else "missing"
        symbol = "+" if path.exists() else "-"
        click.echo(f"  {symbol} {filename}: {status}")

    # Show workflow state if exists
    state = get_spec_workflow_state(project_dir)
    if state["history"]:
        click.echo("\nHistory:")
        for entry in state["history"]:
            step = entry.get("step", "unknown")
            timestamp = entry.get("timestamp", "unknown")
            status = entry.get("status", "unknown")
            click.echo(f"  - {step}: {status} ({timestamp})")


if __name__ == "__main__":
    main()
