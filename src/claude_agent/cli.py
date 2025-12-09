"""
Claude Agent CLI
================

Command-line interface for the autonomous coding agent.
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional

import click

from claude_agent import __version__
from claude_agent.agent import run_autonomous_agent
from claude_agent.config import (
    generate_config_template,
    merge_config,
)
from claude_agent.detection import detect_stack, get_available_stacks
from claude_agent.errors import ActionableError, ConfigParseError, print_error
from claude_agent.progress import (
    bulk_unblock_features,
    find_feature_list,
    find_spec_for_coding,
    find_spec_validation_report,
    get_blocked_features,
    get_session_state,
    print_progress_summary,
    unblock_feature,
)


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis if it exceeds max_len."""
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


@click.group(invoke_without_command=True)
@click.option(
    "--project-dir",
    "-p",
    type=click.Path(path_type=Path),
    default=".",
    help="Project directory (default: current directory)",
)
@click.option(
    "--spec",
    "-s",
    type=click.Path(exists=True, path_type=Path),
    help="Path to specification file",
)
@click.option(
    "--goal",
    "-g",
    type=str,
    help="Short goal description (alternative to --spec)",
)
@click.option(
    "--features",
    "-f",
    type=int,
    help="Number of features to generate (default: 50)",
)
@click.option(
    "--stack",
    type=click.Choice(get_available_stacks()),
    help="Tech stack (auto-detected if not specified)",
)
@click.option(
    "--model",
    "-m",
    type=str,
    help="Claude model to use",
)
@click.option(
    "--max-iterations",
    "-n",
    type=int,
    help="Maximum agent iterations",
)
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config file",
)
@click.option(
    "--review",
    "-r",
    is_flag=True,
    help="Review spec before generating features (recommended for new specs)",
)
@click.option(
    "--reset",
    is_flag=True,
    help="Clear previous agent files and start fresh (will prompt for confirmation)",
)
@click.option(
    "--auto-spec",
    is_flag=True,
    help="Run spec workflow before coding (create -> validate -> decompose)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable real-time structured log output to stderr",
)
@click.option(
    "--skip-architecture",
    is_flag=True,
    default=False,
    help="Skip architecture lock phase (not recommended)",
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
    auto_spec: bool,
    verbose: bool,
    skip_architecture: bool,
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
        # Files that can exist in both root and specs/ subdirectory
        agent_files = [
            "feature_list.json",
            "app_spec.txt",
            "spec-review.md",
            "claude-progress.txt",
            "validation-history.json",
            "validation-progress.txt",
        ]
        # Files that only exist in specs/ subdirectory (spec workflow files)
        specs_only_files = [
            "spec-draft.md",
            "spec-validated.md",
            "spec-validation.md",
        ]
        # Check both project root and specs/ subdirectory
        existing: list[Path] = []
        for f in agent_files:
            root_path = project_dir / f
            specs_path = project_dir / "specs" / f
            if root_path.exists():
                existing.append(root_path)
            if specs_path.exists():
                existing.append(specs_path)
        # Check specs/-only files
        for f in specs_only_files:
            specs_path = project_dir / "specs" / f
            if specs_path.exists():
                existing.append(specs_path)
        # Also check for spec-workflow.json in root
        workflow_file = project_dir / "spec-workflow.json"
        if workflow_file.exists():
            existing.append(workflow_file)

        if not existing:
            click.echo("No agent files to reset.")
        else:
            # Use consistent warning format for destructive operation
            click.echo(click.style("Warning:", fg="yellow", bold=True) + " This will delete agent state files")
            click.echo("")
            click.echo(f"  Files to be deleted from {project_dir}:")
            for f in existing:
                rel_path = f.relative_to(project_dir)
                click.echo(f"    - {rel_path}")
            click.echo("")
            click.echo("  This action cannot be undone. You will need to re-run the spec workflow.")

            if click.confirm("\nProceed with reset?"):
                for f in existing:
                    f.unlink()
                click.echo("")
                click.echo(click.style("Reset complete.", fg="green", bold=True))
                click.echo("Run 'claude-agent' again to start fresh.")
                sys.exit(0)
            else:
                click.echo("Reset cancelled.")
                sys.exit(0)

    # Merge configuration from all sources
    try:
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
            cli_verbose=verbose,
            cli_skip_architecture=skip_architecture,
        )
    except ConfigParseError as e:
        print_error(e.get_actionable_error())
        sys.exit(1)

    # Handle --auto-spec flag
    if auto_spec:
        if not goal:
            print_error(ActionableError(
                message="--auto-spec requires --goal",
                context="The auto-spec workflow needs a goal to generate a specification from.",
                example='claude-agent --auto-spec --goal "Build a REST API for user management"',
                help_command="claude-agent --help",
            ))
            sys.exit(1)

        from claude_agent.agent import run_spec_workflow

        success = asyncio.run(run_spec_workflow(merged_config, goal))
        if not success:
            click.echo("\nSpec workflow failed. Fix issues and try again.")
            sys.exit(1)

        # After spec workflow, feature_list.json now exists
        # Continue with normal agent (coding agent)
        click.echo("\nSpec workflow complete. Starting coding agent...")

    # Check if we have a spec - if not, check for existing or run wizard
    if not merged_config.spec_content:
        feature_list = find_feature_list(project_dir)
        existing_spec = find_spec_for_coding(project_dir)

        if feature_list:
            # Continuing existing project - no spec needed
            pass
        elif existing_spec:
            # Found existing spec (e.g., from aborted review or spec workflow)
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
        print_error(ActionableError(
            message=f"Unexpected error: {type(e).__name__}",
            context=str(e),
            example="claude-agent logs --errors",
            help_command="claude-agent --help",
        ))
        click.echo("\n  If this persists, check the logs and consider filing a bug report.")
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
@click.argument(
    "project_dir", type=click.Path(exists=True, path_type=Path), default="."
)
@click.option("--metrics", is_flag=True, help="Show drift metrics summary")
def status(project_dir: Path, metrics: bool):
    """Show project status and progress.

    PROJECT_DIR is the project to check (default: current directory).
    """
    from claude_agent.progress import count_tests_by_type, get_latest_session_entry

    project_dir = Path(project_dir).resolve()

    click.echo(f"\nProject: {project_dir}")

    # Detect stack
    stack = detect_stack(project_dir)
    click.echo(f"Stack:   {stack}")

    # Get session state with descriptive output
    state = get_session_state(project_dir)
    counts = count_tests_by_type(project_dir)

    if state == "pending_validation":
        click.echo(
            f"State:   {state} (all automated tests pass, {counts['manual_total']} manual remaining)"
        )
        click.echo("         -> Running claude-agent will trigger validation")
    elif state == "validating":
        click.echo(f"State:   {state} (all tests pass, awaiting validator approval)")
    elif state == "in_progress":
        click.echo(
            f"State:   {state} ({counts['automated_passing']}/{counts['automated_total']} automated tests passing)"
        )
    else:
        click.echo(f"State:   {state}")

    # Show progress
    print_progress_summary(project_dir)

    # Show structured progress summary from progress notes
    latest_entry = get_latest_session_entry(project_dir)
    if latest_entry:
        click.echo("\nLast Session:")
        click.echo(f"  Session:   {latest_entry.session_number}")
        click.echo(f"  Timestamp: {latest_entry.timestamp}")
        click.echo(
            f"  Status:    {latest_entry.status.passing}/{latest_entry.status.total} "
            f"features passing ({latest_entry.status.percentage:.1f}%)"
        )
        if latest_entry.completed_features:
            click.echo(f"  Completed: {len(latest_entry.completed_features)} feature(s)")
        if latest_entry.issues_found:
            click.echo(f"  Issues:    {len(latest_entry.issues_found)} found")
        if latest_entry.git_commits:
            click.echo(f"  Commits:   {', '.join(latest_entry.git_commits)}")

    # Show recent progress notes if available (fallback for legacy format)
    progress_file = project_dir / "claude-progress.txt"
    if progress_file.exists() and not latest_entry:
        click.echo("\nRecent progress notes:")
        content = progress_file.read_text()
        # Show last 20 lines
        lines = content.strip().split("\n")
        for line in lines[-20:]:
            click.echo(f"  {line}")

    # Show drift metrics if requested
    if metrics:
        from claude_agent.metrics import load_metrics, calculate_drift_indicators

        drift_metrics = load_metrics(project_dir)
        indicators = calculate_drift_indicators(drift_metrics)

        click.echo("\n--- Drift Metrics ---")
        click.echo(f"Total Sessions: {drift_metrics.total_sessions}")
        click.echo(f"Regression Rate: {indicators['regression_rate']:.1f}%")
        click.echo(f"Velocity Trend: {indicators['velocity_trend']}")
        click.echo(f"Rejection Rate: {indicators['rejection_rate']:.1f}%")
        click.echo(f"Multi-Feature Rate: {indicators['multi_feature_rate']:.1f}%")
        click.echo(f"Incomplete Evaluation Rate: {indicators['incomplete_evaluation_rate']:.1f}%")

        if drift_metrics.total_regressions_caught > 0:
            click.echo(
                f"Total Regressions Caught: {drift_metrics.total_regressions_caught}"
            )

        if drift_metrics.sessions:
            click.echo("\nRecent Sessions:")
            for session in drift_metrics.sessions[-3:]:
                flags = []
                if session.is_multi_feature:
                    flags.append("multi-feature")
                if session.evaluation_completeness_score < 1.0:
                    flags.append(f"eval:{session.evaluation_completeness_score:.0%}")
                flag_str = f" [{', '.join(flags)}]" if flags else ""
                click.echo(
                    f"  Session {session.session_id}: "
                    f"{session.features_completed} completed, "
                    f"{session.regressions_caught} regressions{flag_str}"
                )


@main.command()
@click.argument("feature_index", type=int, required=False)
@click.option("-p", "--project-dir", type=click.Path(path_type=Path), default=".")
@click.option("--list", "list_blocked", is_flag=True, help="List all blocked features")
@click.option("--all", "unblock_all", is_flag=True, help="Unblock all blocked features")
def unblock(feature_index: Optional[int], project_dir: Path, list_blocked: bool, unblock_all: bool):
    """Unblock a feature that was blocked due to architecture deviation.

    \b
    When a feature is blocked due to an architecture conflict, you can:
    1. Update the architecture files to resolve the conflict
    2. Run this command to unblock the feature

    \b
    Examples:
      claude-agent unblock 5              # Unblock feature #5
      claude-agent unblock --list         # List all blocked features
      claude-agent unblock --all          # Unblock all blocked features

    \b
    Manual alternative:
      Edit feature_list.json and remove "blocked" and "blocked_reason" fields
    """
    project_dir = Path(project_dir).resolve()

    # List blocked features
    if list_blocked or (feature_index is None and not unblock_all):
        blocked = get_blocked_features(project_dir)

        if not blocked:
            click.echo("No blocked features found.")
            return

        click.echo(f"\nBlocked features in {project_dir.name}:")
        click.echo("-" * 70)
        for item in blocked:
            desc = _truncate(item['description'], 50)
            reason = _truncate(item['blocked_reason'], 60)
            click.echo(f"  #{item['index']}: {desc}")
            click.echo(f"       Reason: {reason}")
        click.echo("-" * 70)
        click.echo("\nTo unblock: claude-agent unblock <index>")
        click.echo("To unblock all: claude-agent unblock --all")
        return

    # Unblock all blocked features (using bulk operation for efficiency)
    if unblock_all:
        blocked = get_blocked_features(project_dir)

        if not blocked:
            click.echo("No blocked features to unblock.")
            return

        click.echo(f"Unblocking {len(blocked)} feature(s)...")

        # Use bulk unblock for efficiency (single file read/write)
        indices = [item["index"] for item in blocked]
        success_count, errors = bulk_unblock_features(project_dir, indices)

        # Report successes
        for item in blocked:
            idx = item["index"]
            if not any(str(idx) in err for err in errors):
                desc = _truncate(item["description"], 40)
                click.echo(f"  ✓ Unblocked feature #{idx}: {desc}")

        # Report errors
        for err in errors:
            click.echo(f"  ✗ {err}", err=True)

        click.echo(f"\nUnblocked {success_count}/{len(blocked)} features.")
        return

    # Unblock specific feature
    if feature_index is not None:
        success, message = unblock_feature(project_dir, feature_index)

        if success:
            click.echo(click.style("✓ ", fg="green") + message)
            click.echo("\nThe feature is now available for implementation.")
            click.echo("Run 'claude-agent' to continue coding.")
        else:
            click.echo(click.style("✗ ", fg="red") + message, err=True)
            sys.exit(1)


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
    from claude_agent.agent import run_spec_create_session

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
        print_error(ActionableError(
            message="--goal or --from-file required",
            context="A goal is needed to generate a specification. Provide what you want to build.",
            example='claude-agent spec create --goal "Build a REST API for user management"',
            help_command="claude-agent spec create --help",
        ))
        click.echo("\n  Tip: Use -i for interactive mode to be guided through spec creation.")
        sys.exit(1)

    try:
        config = merge_config(project_dir=project_dir)
    except ConfigParseError as e:
        print_error(e.get_actionable_error())
        sys.exit(1)
    asyncio.run(run_spec_create_session(config, goal, context))


@spec.command("validate")
@click.argument("spec_file", type=click.Path(exists=True), required=False)
@click.option("-i", "--interactive", is_flag=True, help="Interactive mode")
@click.option("-p", "--project-dir", type=click.Path(path_type=Path), default=".")
def spec_validate(spec_file, interactive, project_dir):
    """Validate a specification for completeness and clarity."""
    from claude_agent.agent import run_spec_validate_session
    from claude_agent.progress import find_spec_draft

    project_dir = Path(project_dir).resolve()

    if spec_file:
        spec_path = Path(spec_file)
    else:
        # Check both project root and specs/ subdirectory
        spec_path = find_spec_draft(project_dir)
        if spec_path is None:
            print_error(ActionableError(
                message="spec-draft.md not found",
                context="Validation requires a draft specification to validate.",
                example='claude-agent spec create --goal "Build a REST API"',
                help_command="claude-agent spec create --help",
            ))
            click.echo("\n  Or specify a spec file: claude-agent spec validate path/to/spec.md")
            sys.exit(1)

    if not spec_path.exists():
        print_error(ActionableError(
            message=f"{spec_path} not found",
            context="The specified spec file does not exist.",
            example='claude-agent spec create --goal "Build a REST API"',
            help_command="claude-agent spec validate --help",
        ))
        click.echo("\n  Check the file path and try again.")
        sys.exit(1)

    try:
        config = merge_config(project_dir=project_dir)
    except ConfigParseError as e:
        print_error(e.get_actionable_error())
        sys.exit(1)
    status, passed = asyncio.run(run_spec_validate_session(config, spec_path))

    sys.exit(0 if passed else 1)


@spec.command("decompose")
@click.argument("spec_file", type=click.Path(exists=True), required=False)
@click.option("-f", "--features", type=int, default=50, help="Target feature count")
@click.option("-p", "--project-dir", type=click.Path(path_type=Path), default=".")
def spec_decompose(spec_file, features, project_dir):
    """Decompose a validated spec into a feature list."""
    from claude_agent.agent import run_spec_decompose_session
    from claude_agent.progress import find_spec_draft, find_spec_validated

    project_dir = Path(project_dir).resolve()

    if spec_file:
        spec_path = Path(spec_file)
    else:
        # Check both project root and specs/ subdirectory for validated spec
        spec_path = find_spec_validated(project_dir)

    if spec_path is None or not spec_path.exists():
        # Fall back to spec-draft.md with warning
        draft_path = find_spec_draft(project_dir)
        if draft_path is not None:
            click.echo("Warning: Using spec-draft.md (not validated)")
            click.echo("Consider running 'claude-agent spec validate' first")
            spec_path = draft_path
        else:
            print_error(ActionableError(
                message="No spec file found",
                context="Decomposition needs a validated spec to break into features.",
                example='claude-agent spec create --goal "Build a REST API"',
                help_command="claude-agent spec decompose --help",
            ))
            click.echo("\n  Workflow: spec create -> spec validate -> spec decompose")
            click.echo("  Or specify a spec file: claude-agent spec decompose path/to/spec.md")
            sys.exit(1)

    try:
        config = merge_config(project_dir=project_dir, cli_features=features)
    except ConfigParseError as e:
        print_error(e.get_actionable_error())
        sys.exit(1)
    status, feature_path = asyncio.run(
        run_spec_decompose_session(config, spec_path, features)
    )

    sys.exit(0 if feature_path.exists() else 1)


@spec.command("auto")
@click.option("-g", "--goal", type=str, help="What to build (required for new specs)")
@click.option("-p", "--project-dir", type=click.Path(path_type=Path), default=".")
def spec_auto(goal, project_dir):
    """Run full spec workflow (create -> validate -> decompose).

    If a spec already exists, resumes from the current phase.
    The --goal option is only required when starting a new spec.
    """
    from claude_agent.agent import run_spec_workflow
    from claude_agent.progress import get_spec_phase

    project_dir = Path(project_dir).resolve()

    # Check current phase to determine if we can resume
    phase = get_spec_phase(project_dir)

    if phase == "none" and not goal:
        # No spec exists and no goal provided
        print_error(ActionableError(
            message="--goal is required when no spec exists",
            context="The spec auto command creates a new specification from a goal.",
            example='claude-agent spec auto --goal "Build a REST API for user management"',
            help_command="claude-agent spec auto --help",
        ))
        click.echo("\n  Note: --goal is optional when resuming an existing workflow.")
        sys.exit(1)

    if phase != "none" and not goal:
        # Resuming - show current state
        click.echo(f"Resuming spec workflow from phase: {phase}")

    try:
        config = merge_config(project_dir=project_dir)
    except ConfigParseError as e:
        print_error(e.get_actionable_error())
        sys.exit(1)

    success = asyncio.run(run_spec_workflow(config, goal))
    sys.exit(0 if success else 1)


@spec.command("status")
@click.option("-p", "--project-dir", type=click.Path(path_type=Path), default=".")
def spec_status(project_dir):
    """Show spec workflow progress and status."""
    from claude_agent.progress import (
        find_spec_draft,
        find_spec_validated,
        get_spec_phase,
        get_spec_workflow_state,
    )

    project_dir = Path(project_dir).resolve()

    click.echo(f"\nProject: {project_dir}")

    # Get phase from files
    phase = get_spec_phase(project_dir)
    click.echo(f"Phase: {phase}")

    # Show files present (check both project root and specs/ subdirectory)
    click.echo("\nFiles:")

    # Check spec-draft.md in both locations
    draft_path = find_spec_draft(project_dir)
    if draft_path:
        rel_path = draft_path.relative_to(project_dir)
        click.echo(f"  + {rel_path}: present")
    else:
        click.echo("  - spec-draft.md: missing")

    # Check spec-validated.md in both locations
    validated_path = find_spec_validated(project_dir)
    if validated_path:
        rel_path = validated_path.relative_to(project_dir)
        click.echo(f"  + {rel_path}: present")
    else:
        click.echo("  - spec-validated.md: missing")

    # Check spec-validation.md
    validation_path = find_spec_validation_report(project_dir)
    if validation_path:
        rel_path = validation_path.relative_to(project_dir)
        click.echo(f"  + spec-validation.md: {rel_path}")
    else:
        click.echo("  - spec-validation.md: missing")

    # Check feature_list.json
    feature_path = find_feature_list(project_dir)
    if feature_path:
        rel_path = feature_path.relative_to(project_dir)
        click.echo(f"  + feature_list.json: {rel_path}")
    else:
        click.echo("  - feature_list.json: missing")

    # Show workflow state if exists
    state = get_spec_workflow_state(project_dir)
    if state["history"]:
        click.echo("\nHistory:")
        for entry in state["history"]:
            step = entry.get("step", "unknown")
            timestamp = entry.get("timestamp", "unknown")
            status = entry.get("status", "unknown")
            click.echo(f"  - {step}: {status} ({timestamp})")


# =============================================================================
# Logging Command Group
# =============================================================================


@main.command()
@click.option("-p", "--project-dir", type=click.Path(path_type=Path), default=".")
@click.option("--session", "-s", type=str, help="Filter by session ID")
@click.option("--security", is_flag=True, help="Show only security events")
@click.option("--errors", is_flag=True, help="Show only error events")
@click.option("--features", is_flag=True, help="Show only feature events")
@click.option("--tools", is_flag=True, help="Show only tool events")
@click.option("--limit", "-n", type=int, default=50, help="Number of entries to show")
@click.option("--since", type=str, help="Show entries since (e.g., '1h', '2d', '2024-01-15')")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON")
@click.option("--compact", is_flag=True, help="One-line per event summary")
def logs(
    project_dir: Path,
    session: Optional[str],
    security: bool,
    errors: bool,
    features: bool,
    tools: bool,
    limit: int,
    since: Optional[str],
    output_json: bool,
    compact: bool,
):
    """View and filter log history.

    \b
    Examples:
      claude-agent logs                  # Recent 50 entries
      claude-agent logs --security       # Security events only
      claude-agent logs --errors         # Error events only
      claude-agent logs --since 1h       # Last hour
      claude-agent logs --session abc123 # Specific session
      claude-agent logs --json           # Raw JSON output
    """
    import json
    import os

    from claude_agent.logging import (
        EventType,
        LogLevel,
        LogReader,
        parse_since_value,
    )

    project_dir = Path(project_dir).resolve()
    reader = LogReader(project_dir)

    # Build event type filter
    event_types = None
    if security or errors or features or tools:
        event_types = []
        if security:
            event_types.extend([EventType.SECURITY_BLOCK, EventType.SECURITY_ALLOW])
        if errors:
            event_types.append(EventType.ERROR)
        if features:
            event_types.extend([EventType.FEATURE_COMPLETE, EventType.FEATURE_FAILED])
        if tools:
            event_types.extend([EventType.TOOL_CALL, EventType.TOOL_RESULT])

    # Parse since value
    since_dt = None
    if since:
        try:
            since_dt = parse_since_value(since)
        except ValueError as e:
            print_error(ActionableError(
                message=f"Invalid time format: {since}",
                context=str(e),
                example="Valid formats: '1h', '2d', '30m', or '2024-01-15'",
                help_command="claude-agent logs --help",
            ))
            return

    # Read entries
    entries = reader.read_entries(
        session_id=session,
        event_types=event_types,
        since=since_dt,
        limit=limit,
    )

    if not entries:
        click.echo("No log entries found.")
        if not (project_dir / ".claude-agent" / "logs" / "agent.log").exists():
            click.echo("(Log file does not exist yet - run an agent session first)")
        return

    # Check if session is active
    is_active = reader.is_session_active()

    # Output format
    if output_json:
        # Raw JSON array
        output = [
            {
                "ts": e.ts.isoformat(),
                "level": e.level.value,
                "event": e.event.value,
                "session_id": e.session_id,
                **e.data,
            }
            for e in entries
        ]
        click.echo(json.dumps(output, indent=2))
    else:
        # Check NO_COLOR
        use_color = os.environ.get("NO_COLOR") is None

        # Header
        click.echo(f"\nRecent Agent Activity (last {len(entries)} events):")
        if is_active:
            click.echo("(session in progress - log may be incomplete)")
        click.echo("-" * 70)

        # Color codes
        colors = {
            LogLevel.DEBUG: "\033[90m" if use_color else "",
            LogLevel.INFO: "" if use_color else "",
            LogLevel.WARNING: "\033[33m" if use_color else "",
            LogLevel.ERROR: "\033[31m" if use_color else "",
        }
        reset = "\033[0m" if use_color else ""

        # Reverse to show oldest first (chronological order)
        for entry in reversed(entries):
            timestamp = entry.ts.strftime("%H:%M:%S")
            event_name = entry.event.value.upper().replace("_", " ")
            color = colors.get(entry.level, "")

            if compact:
                # One-line format
                click.echo(f"{color}{timestamp} {event_name:<16} {entry.session_id[:8]}{reset}")
            else:
                # Detailed format
                if entry.event == EventType.SESSION_START:
                    details = f"iter={entry.data.get('iteration')} model={entry.data.get('model')} agent={entry.data.get('agent_type')}"
                elif entry.event == EventType.SESSION_END:
                    details = f"turns={entry.data.get('turns_used')} status={entry.data.get('status')}"
                elif entry.event == EventType.TOOL_CALL:
                    details = f"{entry.data.get('tool_name')}: {entry.data.get('input_summary', '')[:50]}"
                elif entry.event == EventType.TOOL_RESULT:
                    status = "error" if entry.data.get("is_error") else "success"
                    details = f"{entry.data.get('tool_name')}: [{status}]"
                elif entry.event == EventType.SECURITY_BLOCK:
                    details = f"{entry.data.get('command', '')[:40]} -> \"{entry.data.get('reason', '')[:30]}\""
                elif entry.event == EventType.SECURITY_ALLOW:
                    details = entry.data.get("command", "")[:50]
                elif entry.event == EventType.FEATURE_COMPLETE:
                    details = f"#{entry.data.get('index')}: {entry.data.get('description', '')[:40]}"
                elif entry.event == EventType.FEATURE_FAILED:
                    details = f"#{entry.data.get('index')}: {entry.data.get('reason', '')[:40]}"
                elif entry.event == EventType.ERROR:
                    details = f"{entry.data.get('error_type')}: {entry.data.get('message', '')[:40]}"
                else:
                    details = str(entry.data)[:60]

                click.echo(f"{color}{timestamp} {event_name:<16} {details}{reset}")

        click.echo("-" * 70)


@main.command()
@click.option("-p", "--project-dir", type=click.Path(path_type=Path), default=".")
@click.option("--session", "-s", type=str, help="Show stats for specific session")
@click.option("--last", type=int, help="Show stats for last N sessions")
@click.option("--reset", "do_reset", is_flag=True, help="Reset accumulated statistics")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON")
def stats(
    project_dir: Path,
    session: Optional[str],
    last: Optional[int],
    do_reset: bool,
    output_json: bool,
):
    """Show session statistics.

    \b
    Examples:
      claude-agent stats                 # Summary of all sessions
      claude-agent stats --last 5        # Last 5 sessions
      claude-agent stats --session abc   # Specific session
      claude-agent stats --reset         # Clear statistics
      claude-agent stats --json          # Raw JSON output
    """
    import json

    from claude_agent.logging import LogReader, reset_session_stats

    project_dir = Path(project_dir).resolve()

    if do_reset:
        if click.confirm("Reset all session statistics?"):
            if reset_session_stats(project_dir):
                click.echo("Statistics reset successfully.")
            else:
                click.echo("Failed to reset statistics.", err=True)
        return

    reader = LogReader(project_dir)
    stats_data = reader.get_sessions_stats()

    if not stats_data.get("sessions"):
        click.echo("No session statistics found.")
        if not (project_dir / ".claude-agent" / "logs" / "sessions.json").exists():
            click.echo("(Statistics file does not exist yet - run an agent session first)")
        return

    sessions = stats_data["sessions"]
    aggregate = stats_data.get("aggregate", {})

    # Filter sessions
    if session:
        sessions = [s for s in sessions if s["session_id"].startswith(session)]
        if not sessions:
            click.echo(f"No sessions found matching '{session}'")
            return
    elif last:
        sessions = sessions[-last:]

    if output_json:
        output = {"sessions": sessions, "aggregate": aggregate}
        click.echo(json.dumps(output, indent=2))
        return

    # Summary output
    click.echo(f"\nSession Statistics for {project_dir.name}")
    click.echo("=" * 70)

    # Aggregate stats
    if aggregate and not session:
        click.echo("\nAggregate:")
        click.echo(f"  Total sessions:      {aggregate.get('total_sessions', 0)}")
        click.echo(f"  Total turns:         {aggregate.get('total_turns', 0)}")
        total_duration = aggregate.get("total_duration_seconds", 0)
        if total_duration:
            hours = int(total_duration // 3600)
            minutes = int((total_duration % 3600) // 60)
            click.echo(f"  Total time:          {hours}h {minutes}m")
        click.echo(f"  Features completed:  {aggregate.get('total_features_completed', 0)}")
        click.echo(f"  Security blocks:     {aggregate.get('total_security_blocks', 0)}")

    # Individual sessions
    if sessions:
        click.echo(f"\n{'Sessions' if not session else 'Session Details'}:")
        click.echo("-" * 70)

        for s in sessions[-10:]:  # Show last 10 by default
            session_id = s["session_id"]
            agent_type = s.get("agent_type", "unknown")
            turns = s.get("turns_used", 0)
            duration = s.get("duration_seconds", 0)
            features = len(s.get("features_completed", []))
            blocks = s.get("security_blocks", 0)

            # Format duration
            if duration:
                mins = int(duration // 60)
                secs = int(duration % 60)
                dur_str = f"{mins}m {secs}s"
            else:
                dur_str = "?"

            click.echo(
                f"  {session_id}  {agent_type:<12} turns={turns:<4} time={dur_str:<8} features={features} blocks={blocks}"
            )

            # Show tool breakdown for detailed view
            if session and s.get("tools_called"):
                click.echo(f"    Tools: {s['tools_called']}")

    click.echo("-" * 70)


if __name__ == "__main__":
    main()
