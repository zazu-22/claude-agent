"""
Agent Session Logic
===================

Core agent interaction functions for running autonomous coding sessions.
"""

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from claude_code_sdk import ClaudeSDKClient

from claude_agent.client import create_client
from claude_agent.config import Config
from claude_agent.detection import (
    detect_stack,
    get_stack_init_command,
    get_stack_dev_command,
)
from claude_agent.errors import ActionableError, print_error
from claude_agent.progress import (
    count_passing_tests,
    count_tests_by_type,
    find_feature_list,
    find_spec_draft,
    find_spec_for_coding,
    find_spec_validated,
    find_spec_validation_report,
    get_rejection_count,
    is_automated_work_complete,
    mark_tests_failed,
    parse_validation_verdict,
    print_session_header,
    print_progress_summary,
    print_startup_banner,
    record_spec_step,
    save_validation_attempt,
)
from claude_agent.prompts.loader import (
    get_architect_prompt,
    get_initializer_prompt,
    get_coding_prompt,
    get_review_prompt,
    get_validator_prompt,
    get_spec_create_prompt,
    get_spec_validate_prompt,
    get_spec_decompose_prompt,
    write_spec_to_project,
    render_coding_prompt,
)
from claude_agent.security import configure_security, set_security_logger
from claude_agent.logging import (
    AgentLogger,
    LoggingConfig as LoggingConfigClass,
    LogLevel,
    SessionStatsTracker,
)
from claude_agent.metrics import (
    calculate_evaluation_completeness,
    count_regressions,
    parse_evaluation_sections,
    record_session_metrics,
    record_validation_metrics,
)


def is_architecture_locked(project_dir: Path) -> bool:
    """
    Check if architecture lock phase has been completed.

    Returns True if architecture/ directory exists with all required files.
    """
    arch_dir = project_dir / "architecture"
    required_files = ["contracts.yaml", "schemas.yaml", "decisions.yaml"]

    if not arch_dir.exists():
        return False

    return all((arch_dir / f).exists() for f in required_files)


def get_next_session_id(project_dir: Path) -> int:
    """
    Determine the next session ID by reading metrics file.

    Uses drift-metrics.json as the source of truth for session IDs to avoid
    race conditions when reading progress notes (which are written by the
    agent during sessions).

    Note: This function assumes single-agent execution. If concurrent agents
    are supported in the future, a lock file or atomic ID allocation mechanism
    would be needed to prevent duplicate session IDs.
    """
    from claude_agent.metrics import load_metrics

    # Use metrics file as source of truth for session IDs
    # This avoids race conditions with progress notes parsing
    metrics = load_metrics(project_dir)
    if metrics.sessions:
        max_session = max(s.session_id for s in metrics.sessions)
        return max_session + 1

    # Fall back to progress notes for backwards compatibility
    from claude_agent.progress import parse_progress_notes

    progress_path = project_dir / "claude-progress.txt"
    if not progress_path.exists():
        return 1

    try:
        entries = parse_progress_notes(progress_path)
        if not entries:
            return 1
        max_session = max(e.session_number for e in entries)
        return max_session + 1
    except Exception:
        return 1


@dataclass
class ValidatorResult:
    """Result from validator agent session."""

    verdict: str  # "APPROVED", "REJECTED", "ERROR", "NEEDS_VERIFICATION", "CONTINUE"
    rejected_tests: list[dict]  # [{test_index: int, reason: str}, ...]
    summary: str
    manual_tests_remaining: list[dict] = None  # [{test_index: int, reason: str}, ...]
    tests_verified: int = 0  # How many tests were actually verified through UI
    error: Optional[str] = None


def parse_validator_response(response: str) -> ValidatorResult:
    """
    Parse validator response to extract structured verdict.

    Attempts multiple parsing strategies with fallback to NEEDS_VERIFICATION.
    """
    # Strategy 1: Look for JSON in code block
    json_match = re.search(r"```json\s*\n(.*?)\n```", response, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            return ValidatorResult(
                verdict=data.get("verdict", "REJECTED"),
                rejected_tests=data.get("rejected_tests", []),
                summary=data.get("summary", ""),
                manual_tests_remaining=data.get("manual_tests_remaining", []),
                tests_verified=data.get("tests_verified", 0),
            )
        except json.JSONDecodeError:
            pass

    # Strategy 2: Look for plain JSON object with verdict key
    try:
        json_match = re.search(
            r'\{\s*"verdict"\s*:\s*"[^"]+"\s*,.*?\}',
            response,
            re.DOTALL,
        )
        if json_match:
            data = json.loads(json_match.group(0))
            return ValidatorResult(
                verdict=data.get("verdict", "REJECTED"),
                rejected_tests=data.get("rejected_tests", []),
                summary=data.get("summary", ""),
                manual_tests_remaining=data.get("manual_tests_remaining", []),
                tests_verified=data.get("tests_verified", 0),
            )
    except json.JSONDecodeError:
        pass

    # Strategy 3: Look for APPROVED keyword (only if REJECTED not present)
    upper_response = response.upper()
    if "APPROVED" in upper_response and "REJECTED" not in upper_response:
        return ValidatorResult(
            verdict="APPROVED",
            rejected_tests=[],
            summary="Approval inferred from response keywords",
        )

    # Default: Treat as NEEDS_VERIFICATION - validator couldn't properly verify
    # This is safer than assuming rejection or approval
    return ValidatorResult(
        verdict="NEEDS_VERIFICATION",
        rejected_tests=[],
        summary="",
        error="Could not parse structured output from validator - manual verification required",
    )


def print_validation_header(attempt: int) -> None:
    """Print formatted validation phase header."""
    print("\n" + "=" * 70)
    print(f"  VALIDATION PHASE (Attempt {attempt})")
    print("  Reviewing implementation against specification...")
    print("=" * 70 + "\n")


async def run_review_session(
    config: Config,
    stack: str,
    spec_content: str,
    logger: Optional[AgentLogger] = None,
) -> bool:
    """
    Run a spec review session before generating features.

    Args:
        config: Configuration object
        stack: Detected tech stack
        spec_content: The specification content to review
        logger: Optional AgentLogger for structured logging

    Returns:
        True if user wants to proceed, False to abort
    """
    project_dir = config.project_dir

    print("\n" + "=" * 70)
    print("  SPEC REVIEW MODE")
    print("=" * 70)
    print("\nThe agent will analyze your spec and create a review document.")
    print("You can then decide whether to proceed or refine the spec first.\n")

    # Start logging session for review
    session_id = None
    stats_tracker = None
    if logger:
        session_id = logger.start_session(
            iteration=0,
            model=config.agent.model,
            stack=stack,
            agent_type="review",
        )
        stats_tracker = SessionStatsTracker(
            project_dir=project_dir,
            session_id=session_id,
            agent_type="review",
        )

    # Write spec to project for the agent
    write_spec_to_project(project_dir, spec_content)

    # Create client for review session
    client = create_client(
        project_dir=project_dir,
        model=config.agent.model,
        max_turns=config.agent.max_turns,
        stack=stack,
    )

    # Run review session with logging
    prompt = get_review_prompt(spec_content)

    async with client:
        status, response = await run_agent_session(
            client, prompt, project_dir, logger, stats_tracker
        )

    # End logging session
    if logger:
        logger.end_session(
            turns_used=stats_tracker.stats.turns_used if stats_tracker else 0,
            status=status,
        )
        if stats_tracker:
            stats_tracker.save()

    # Check if review file was created
    review_file = project_dir / "spec-review.md"
    if review_file.exists():
        print("\n" + "=" * 70)
        print("  REVIEW COMPLETE")
        print("=" * 70)
        print(f"\nReview saved to: {review_file}")
        print("\nPlease review the analysis above and the spec-review.md file.")
        print("\nOptions:")
        print("  [Enter] Proceed with feature generation")
        print("  [n]     Abort - refine spec and run again")
        print("  [v]     View spec-review.md contents")

        while True:
            response = input("\nProceed? [Y/n/v]: ").strip().lower()
            if response in ("", "y", "yes"):
                return True
            elif response in ("n", "no"):
                print("\nAborting. Refine your spec and run again.")
                print(f"Review file preserved at: {review_file}")
                return False
            elif response == "v":
                print("\n" + "-" * 70)
                print(review_file.read_text())
                print("-" * 70)
            else:
                print("Please enter 'y' to proceed, 'n' to abort, or 'v' to view.")
    else:
        print("\nWarning: Review file was not created.")
        response = input("Proceed anyway? [y/N]: ").strip().lower()
        return response in ("y", "yes")


async def run_agent_session(
    client: ClaudeSDKClient,
    message: str,
    project_dir: Path,
    logger: Optional[AgentLogger] = None,
    stats_tracker: Optional[SessionStatsTracker] = None,
) -> tuple[str, str]:
    """
    Run a single agent session using Claude Agent SDK.

    Args:
        client: Claude SDK client
        message: The prompt to send
        project_dir: Project directory path
        logger: Optional AgentLogger for structured logging
        stats_tracker: Optional SessionStatsTracker for statistics

    Returns:
        (status, response_text) where status is:
        - "continue" if agent should continue working
        - "error" if an error occurred
    """
    print("Sending prompt to Claude Agent SDK...\n")

    # Track last tool name for result logging
    last_tool_name = None
    turns_used = 0

    try:
        await client.query(message)

        response_text = ""
        async for msg in client.receive_response():
            msg_type = type(msg).__name__

            # Handle AssistantMessage (text and tool use)
            if msg_type == "AssistantMessage" and hasattr(msg, "content"):
                for block in msg.content:
                    block_type = type(block).__name__

                    if block_type == "TextBlock" and hasattr(block, "text"):
                        response_text += block.text
                        print(block.text, end="", flush=True)
                    elif block_type == "ToolUseBlock" and hasattr(block, "name"):
                        tool_name = block.name
                        last_tool_name = tool_name
                        print(f"\n[Tool: {tool_name}]", flush=True)

                        tool_input = None
                        if hasattr(block, "input"):
                            tool_input = block.input
                            input_str = str(tool_input)
                            if len(input_str) > 200:
                                print(f"   Input: {input_str[:200]}...", flush=True)
                            else:
                                print(f"   Input: {input_str}", flush=True)

                        # Log tool call
                        if logger:
                            logger.log_tool_call(tool_name, tool_input)
                        if stats_tracker:
                            stats_tracker.record_tool_call(tool_name)

            # Handle UserMessage (tool results)
            elif msg_type == "UserMessage" and hasattr(msg, "content"):
                for block in msg.content:
                    block_type = type(block).__name__

                    if block_type == "ToolResultBlock":
                        result_content = getattr(block, "content", "")
                        is_error = getattr(block, "is_error", False)

                        if "blocked" in str(result_content).lower():
                            print(f"   [BLOCKED] {result_content}", flush=True)
                            # Note: security blocks are already logged by security.py
                            if stats_tracker:
                                stats_tracker.record_security_block()
                        elif is_error:
                            error_str = str(result_content)[:500]
                            print(f"   [Error] {error_str}", flush=True)
                            if stats_tracker:
                                stats_tracker.record_error()
                        else:
                            print("   [Done]", flush=True)

                        # Log tool result
                        if logger and last_tool_name:
                            logger.log_tool_result(last_tool_name, is_error, result_content)

            # Handle ResultMessage (session end - critical diagnostic info)
            elif msg_type == "ResultMessage":
                num_turns = getattr(msg, "num_turns", "?")
                is_error = getattr(msg, "is_error", False)
                subtype = getattr(msg, "subtype", "unknown")
                result = getattr(msg, "result", None)
                print(
                    f"\n[Session End] turns={num_turns}, subtype={subtype}, is_error={is_error}",
                    flush=True,
                )
                if result:
                    print(
                        f"   Result: {result[:200]}..."
                        if len(str(result)) > 200
                        else f"   Result: {result}",
                        flush=True,
                    )

                # Track turns used
                if isinstance(num_turns, int):
                    turns_used = num_turns
                    if stats_tracker:
                        stats_tracker.set_turns_used(turns_used)

        print("\n" + "-" * 70 + "\n")
        return "continue", response_text

    except Exception as e:
        print_error(ActionableError(
            message=f"Agent session failed: {type(e).__name__}",
            context=str(e),
            example="claude-agent logs --errors",
            help_command="claude-agent --help",
        ))
        # Log error
        if logger:
            import traceback
            logger.log_error(
                error_type=type(e).__name__,
                message=str(e),
                stack_trace=traceback.format_exc(),
            )
        if stats_tracker:
            stats_tracker.record_error()
        return "error", str(e)


async def run_validator_session(
    config: Config,
    stack: str,
    project_dir: Path,
    init_command: str,
    dev_command: str,
    logger: Optional[AgentLogger] = None,
) -> ValidatorResult:
    """
    Run validator agent session and parse results.

    Args:
        config: Configuration object
        stack: Detected tech stack
        project_dir: Project directory path
        init_command: Command to install dependencies
        dev_command: Command to start development server
        logger: Optional AgentLogger for structured logging

    Returns:
        ValidatorResult with verdict and any rejected tests
    """
    # Start logging session for validator
    session_id = None
    stats_tracker = None
    if logger:
        session_id = logger.start_session(
            iteration=0,  # Validators don't have iterations
            model=config.validator.model,
            stack=stack,
            agent_type="validator",
        )
        stats_tracker = SessionStatsTracker(
            project_dir=project_dir,
            session_id=session_id,
            agent_type="validator",
        )

    # Create client with validator model, lower max_turns, and stop hook
    # Stop hook enforces verdict output before session ends
    client = create_client(
        project_dir=project_dir,
        model=config.validator.model,
        max_turns=config.validator.max_turns,
        stack=stack,
        is_validator=True,
    )

    # Get validator prompt
    prompt = get_validator_prompt(
        init_command=init_command,
        dev_command=dev_command,
    )

    # Run session with logging
    async with client:
        status, response = await run_agent_session(
            client, prompt, project_dir, logger, stats_tracker
        )

    # Parse response
    result = parse_validator_response(response)

    # Log validation result and end session
    if logger:
        logger.log_validation_result(
            verdict=result.verdict,
            tests_verified=result.tests_verified,
            rejected_count=len(result.rejected_tests),
        )
        logger.end_session(
            turns_used=stats_tracker.stats.turns_used if stats_tracker else 0,
            status=status,
        )
        if stats_tracker:
            stats_tracker.save()

    return result


async def run_architect_session(
    config: Config,
    stack: str,
    project_dir: Path,
    logger: Optional[AgentLogger] = None,
    max_retries: int = 2,
) -> tuple[str, bool]:
    """
    Run the architecture lock agent session with retry support.

    If the agent creates files but they fail validation, this function will
    clean up and retry up to max_retries times before giving up.

    Args:
        config: Configuration object
        stack: Detected tech stack
        project_dir: Project directory path
        logger: Optional AgentLogger for structured logging
        max_retries: Maximum number of retry attempts (default: 2)

    Returns:
        (status, success) where success indicates if all architecture files were created
        and contain valid YAML with required fields
    """
    from claude_agent.architecture import (
        validate_architecture_files,
        cleanup_partial_architecture,
    )

    last_status = "error"
    last_validation_errors: list[str] = []

    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            print(f"\nRetrying architecture phase (attempt {attempt}/{max_retries})...")
            if logger:
                logger.info(f"Architecture retry attempt {attempt}/{max_retries}")
            # Brief delay before retry
            await asyncio.sleep(2)

        # Start logging session
        session_id = None
        stats_tracker = None
        if logger:
            session_id = logger.start_session(
                iteration=0,
                model=config.agent.model,
                stack=stack,
                agent_type="architect",
            )
            stats_tracker = SessionStatsTracker(
                project_dir=project_dir,
                session_id=session_id,
                agent_type="architect",
            )

        # Create client
        client = create_client(
            project_dir=project_dir,
            model=config.agent.model,
            max_turns=config.agent.max_turns,
            stack=stack,
        )

        # Get prompt
        prompt = get_architect_prompt()

        # Run session
        async with client:
            status, response = await run_agent_session(
                client, prompt, project_dir, logger, stats_tracker
            )

        last_status = status

        # End logging session
        if logger:
            logger.end_session(
                turns_used=stats_tracker.stats.turns_used if stats_tracker else 0,
                status=status,
            )
            if stats_tracker:
                stats_tracker.save()

        # Verify outputs - check both existence and content validity
        files_exist = is_architecture_locked(project_dir)

        if files_exist:
            # Validate YAML content and structure
            valid, validation_errors = validate_architecture_files(project_dir)
            last_validation_errors = validation_errors

            if valid:
                # Success! All files valid
                if attempt > 1 and logger:
                    logger.info(f"Architecture succeeded on attempt {attempt}")
                return status, True
            else:
                # Files exist but are invalid - log prominently and clean up
                print(f"\n{'='*60}")
                print("ARCHITECTURE VALIDATION FAILED")
                print(f"{'='*60}")
                print(f"Attempt {attempt}/{max_retries} - Found {len(validation_errors)} validation error(s):")
                for i, error in enumerate(validation_errors, 1):
                    print(f"  {i}. {error}")
                    if logger:
                        logger.warning(f"Architecture validation error [{i}]: {error}")
                print(f"{'='*60}\n")

                # Clean up invalid files before retry
                cleanup_partial_architecture(project_dir)
        else:
            # Files don't all exist - clean up any partial architecture
            print(f"\nArchitecture attempt {attempt}/{max_retries}: Required files not created")
            if logger:
                logger.warning(f"Architecture attempt {attempt}: Required files not created")
            cleaned = cleanup_partial_architecture(project_dir)
            if cleaned and logger:
                logger.warning("Cleaned up partial architecture directory")

    # All retries exhausted
    if logger:
        logger.warning(
            f"Architecture failed after {max_retries} attempts. "
            f"Last errors: {last_validation_errors}"
        )

    return last_status, False


def _create_logging_config(config: Config) -> LoggingConfigClass:
    """Create a LoggingConfigClass from the config object's logging settings."""
    level_map = {
        "debug": LogLevel.DEBUG,
        "info": LogLevel.INFO,
        "warning": LogLevel.WARNING,
        "error": LogLevel.ERROR,
    }
    return LoggingConfigClass(
        enabled=config.logging.enabled,
        level=level_map.get(config.logging.level, LogLevel.INFO),
        include_tool_results=config.logging.include_tool_results,
        include_allowed_commands=config.logging.include_allowed_commands,
        max_summary_length=config.logging.max_summary_length,
        max_size_mb=config.logging.max_size_mb,
        max_files=config.logging.max_files,
        retention_days=config.logging.retention_days,
    )


async def run_autonomous_agent(config: Config) -> None:
    """
    Run the autonomous agent loop.

    Args:
        config: Configuration object with all settings
    """
    project_dir = config.project_dir

    # Detect or use configured stack
    stack = config.stack or detect_stack(project_dir)

    # Configure security for this stack
    configure_security(
        stack=stack,
        extra_commands=config.security.extra_commands or None,
    )

    # Initialize logging
    logging_config = _create_logging_config(config)
    logger = AgentLogger(
        project_dir=project_dir,
        config=logging_config,
        verbose=config.verbose,
    )

    # Set up security logger for security decision logging
    set_security_logger(logger)

    # Print startup banner
    print_startup_banner(
        project_dir=project_dir,
        stack=stack,
        model=config.agent.model,
        max_iterations=config.agent.max_iterations,
    )

    # Create project directory
    project_dir.mkdir(parents=True, exist_ok=True)

    # Check if this is a fresh start or continuation
    tests_file = find_feature_list(project_dir)
    is_first_run = tests_file is None

    if is_first_run:
        # Validate we have spec content
        spec_content = config.spec_content

        # Check for existing spec file (e.g., from aborted review or spec workflow)
        if not spec_content:
            existing_spec = find_spec_for_coding(project_dir)
            if existing_spec:
                print(f"Found existing spec: {existing_spec}")
                spec_content = existing_spec.read_text()
            else:
                print_error(ActionableError(
                    message="No spec file or goal provided",
                    context="The agent needs to know what to build.",
                    example='claude-agent --spec PATH or --goal "description"',
                    help_command="claude-agent --help",
                ))
                print("\n  Tip: Run claude-agent with no args to use the interactive wizard.")
                return

        # Run review session if requested
        if config.review:
            proceed = await run_review_session(config, stack, spec_content, logger)
            if not proceed:
                return
            print("\n" + "=" * 70)
            print("  Proceeding with feature generation...")
            print("=" * 70 + "\n")

        print("Fresh start - will use initializer agent")
        print()
        print("=" * 70)
        print("  NOTE: First session may take 10-20+ minutes!")
        print(f"  The agent is generating {config.features} detailed test cases.")
        print("  This may appear to hang - it's working. Watch for [Tool: ...] output.")
        print("=" * 70)
        print()

        # Write spec to project directory for agent reference
        write_spec_to_project(project_dir, spec_content)
    else:
        # Show detected state
        from claude_agent.progress import get_session_state

        state = get_session_state(project_dir)
        counts = count_tests_by_type(project_dir)

        print("\n" + "-" * 70)
        print("PROJECT STATE DETECTED:")
        print(f"  State: {state}")
        print(
            f"  Automated: {counts['automated_passing']}/{counts['automated_total']} | Manual: {counts['manual_passing']}/{counts['manual_total']}"
        )
        if state == "pending_validation":
            print("  -> Will trigger VALIDATION (all automated tests pass)")
        else:
            print("  -> Will run CODING AGENT")
        print("-" * 70)
        print_progress_summary(project_dir)

    # Get stack-specific commands
    init_command = get_stack_init_command(stack)
    dev_command = get_stack_dev_command(stack)

    # Check if architecture phase needed (after initializer may have run)
    architecture_exists = is_architecture_locked(project_dir)
    should_run_architecture = (
        config.architecture.enabled
        and not config.skip_architecture
        and not architecture_exists
    )

    if should_run_architecture:
        # Only run architecture phase if feature_list.json exists (initializer completed)
        if find_feature_list(project_dir):
            print("\n" + "=" * 70)
            print("  ARCHITECTURE LOCK PHASE")
            print("  Establishing architectural invariants...")
            print("=" * 70 + "\n")

            status, success = await run_architect_session(
                config=config,
                stack=stack,
                project_dir=project_dir,
                logger=logger,
            )

            if success:
                print("\n" + "=" * 70)
                print("  ARCHITECTURE PHASE COMPLETE")
                print("  Proceeding to coding sessions...")
                print("=" * 70 + "\n")
            else:
                if config.architecture.required:
                    print_error(ActionableError(
                        message="Architecture lock phase failed",
                        context="Required architecture files were not created.",
                        example="claude-agent --skip-architecture",
                        help_command="claude-agent --help",
                    ))
                    return
                else:
                    # Prominent warning when architecture fails but isn't required
                    print("\n" + "!" * 70)
                    print("  WARNING: ARCHITECTURE LOCK PHASE FAILED")
                    print("!" * 70)
                    print()
                    print("  The architect agent did not create valid architecture files.")
                    print("  This means drift protection is REDUCED for this project.")
                    print()
                    print("  Implications:")
                    print("  - No locked API contracts to verify against")
                    print("  - No schema definitions to constrain data models")
                    print("  - No decision records to prevent conflicting choices")
                    print()
                    print("  To require architecture (fail instead of warn):")
                    print("    Set 'architecture.required: true' in .claude-agent.yaml")
                    print()
                    print("  Continuing to coding sessions without architecture lock...")
                    print("!" * 70 + "\n")

    # Main loop
    iteration = 0
    max_iterations = config.agent.max_iterations

    while True:
        iteration += 1

        # Check max iterations
        if max_iterations and iteration > max_iterations:
            print(f"\nReached max iterations ({max_iterations})")
            print("To continue, run the command again without --max-iterations")
            break

        # Check if validation should trigger BEFORE running coding session
        passing, total = count_passing_tests(project_dir)
        counts = count_tests_by_type(project_dir)
        automated_complete = is_automated_work_complete(project_dir)
        all_tests_pass = total > 0 and passing == total
        should_validate = (all_tests_pass or automated_complete) and not is_first_run

        if should_validate:
            # Show workflow decision
            print("\n" + "-" * 70)
            print("WORKFLOW CHECK:")
            print(f"  Total tests: {total} | Passing: {passing}")
            print(
                f"  Automated: {counts['automated_passing']}/{counts['automated_total']} | Manual: {counts['manual_passing']}/{counts['manual_total']}"
            )
            if all_tests_pass:
                trigger_reason = "all tests passing"
            else:
                trigger_reason = f"automated work complete ({counts['manual_total']} manual tests remaining)"
            print(f"  -> TRIGGERING VALIDATION ({trigger_reason})")
            print("-" * 70)
        else:
            # Run coding session
            print_session_header(iteration, is_first_run)

            # Track features at session start for metrics
            features_at_start, _ = count_passing_tests(project_dir)

            # Determine agent type for logging
            agent_type = "initializer" if is_first_run else "coding"

            # Start logging session
            session_id = logger.start_session(
                iteration=iteration,
                model=config.agent.model,
                stack=stack,
                agent_type=agent_type,
            )

            # Create stats tracker for this session
            stats_tracker = SessionStatsTracker(
                project_dir=project_dir,
                session_id=session_id,
                agent_type=agent_type,
            )

            # Create client (fresh context)
            client = create_client(
                project_dir=project_dir,
                model=config.agent.model,
                max_turns=config.agent.max_turns,
                stack=stack,
            )

            # Choose prompt based on session type
            if is_first_run:
                prompt = get_initializer_prompt(
                    spec_content=spec_content,
                    feature_count=config.features,
                    init_command=init_command,
                    dev_command=dev_command,
                )
                is_first_run = False  # Only use initializer once
            else:
                # Get base coding prompt and render with template variables
                raw_prompt = get_coding_prompt(
                    init_command=init_command,
                    dev_command=dev_command,
                )
                # Render {{last_passed_feature}} variable for regression testing
                prompt = render_coding_prompt(raw_prompt, project_dir)

            # Run session with logging
            async with client:
                status, response = await run_agent_session(
                    client, prompt, project_dir, logger, stats_tracker
                )

            # End logging session and save stats
            logger.end_session(
                turns_used=stats_tracker.stats.turns_used,
                status=status,
            )
            stats_tracker.save()

            # Record session metrics for drift detection
            features_at_end, _ = count_passing_tests(project_dir)
            # Calculate net change and track regressions separately
            features_delta = features_at_end - features_at_start
            # features_regressed: count of features that went from passing to failing
            features_regressed = abs(features_delta) if features_delta < 0 else 0
            # features_completed: net change (can be negative for regressions)
            features_completed = features_delta
            evaluation_sections, evaluation_complete = parse_evaluation_sections(response)
            regressions, regression_section_found = count_regressions(response)

            # The coding agent is designed to target exactly one feature per session.
            # This is a core architectural constraint for drift mitigation:
            # - Small, focused sessions reduce stochastic cascade drift
            # - Single-feature scope makes regression verification tractable
            # - Predictable session duration enables better progress tracking
            #
            # If multi-feature sessions are needed in the future, calculate
            # features_attempted dynamically by parsing the session output for
            # "implementing Feature #N" patterns or similar markers.
            features_attempted = 1

            # Detect multi-feature session (drift indicator)
            is_multi_feature = abs(features_completed) > features_attempted
            if is_multi_feature:
                logger.warning(
                    f"Multi-feature session detected: completed {features_completed} features "
                    f"vs expected {features_attempted}. This may indicate drift from "
                    "single-feature session architecture."
                )

            # Calculate evaluation completeness score
            eval_completeness = calculate_evaluation_completeness(evaluation_sections)

            # Get session ID immediately before recording to minimize race window
            # (session ID allocation and metric recording happen atomically)
            metrics_session_id = get_next_session_id(project_dir)

            record_session_metrics(
                project_dir=project_dir,
                session_id=metrics_session_id,
                features_attempted=features_attempted,
                features_completed=features_completed,
                features_regressed=features_regressed,
                regressions_caught=regressions,
                evaluation_sections_present=evaluation_sections,
                evaluation_completeness_score=eval_completeness,
                is_multi_feature=is_multi_feature,
            )

            # Re-check after coding session
            passing, total = count_passing_tests(project_dir)
            counts = count_tests_by_type(project_dir)
            automated_complete = is_automated_work_complete(project_dir)
            all_tests_pass = total > 0 and passing == total

            # Show workflow decision after coding
            print("\n" + "-" * 70)
            print("WORKFLOW CHECK:")
            print(f"  Total tests: {total} | Passing: {passing}")
            print(
                f"  Automated: {counts['automated_passing']}/{counts['automated_total']} | Manual: {counts['manual_passing']}/{counts['manual_total']}"
            )

        # Trigger validation if:
        # 1. All tests pass (including any manual tests), OR
        # 2. All automated tests pass (manual tests may remain)
        if all_tests_pass or automated_complete:
            # Show trigger reason if we came from coding (not already shown)
            if not should_validate:
                if all_tests_pass:
                    trigger_reason = "all tests passing"
                else:
                    trigger_reason = f"automated work complete ({counts['manual_total']} manual tests remaining)"
                print(f"  -> TRIGGERING VALIDATION ({trigger_reason})")
                print("-" * 70)

            # Skip validation if disabled
            if not config.validator.enabled:
                print("\n" + "=" * 70)
                if all_tests_pass:
                    print("  ALL FEATURES COMPLETE!")
                else:
                    print("  AUTOMATED WORK COMPLETE!")
                    print(
                        f"  {counts['manual_total']} test(s) require manual verification"
                    )
                print("=" * 70)
                print(f"\n{passing}/{total} features passing - {trigger_reason}")
                break

            # Check rejection limit
            rejection_count = get_rejection_count(project_dir)
            if rejection_count >= config.validator.max_rejections:
                print("\n" + "=" * 70)
                print(
                    f"  MAX VALIDATION REJECTIONS ({config.validator.max_rejections}) REACHED"
                )
                print("=" * 70)
                print("\nManual review recommended.")
                print(
                    "To continue, increase max_rejections in config or disable validation."
                )
                break

            # Run validation phase - may take multiple sessions
            validation_session = 0
            while True:
                validation_session += 1
                print_validation_header(rejection_count + 1)
                if validation_session > 1:
                    print(f"(Validation session {validation_session})")
                if counts["manual_total"] > 0:
                    print(
                        f"Note: {counts['manual_total']} test(s) marked as requiring manual verification"
                    )
                print()

                result = await run_validator_session(
                    config=config,
                    stack=stack,
                    project_dir=project_dir,
                    init_command=init_command,
                    dev_command=dev_command,
                    logger=logger,
                )

                # Save attempt to history
                save_validation_attempt(
                    project_dir=project_dir,
                    result=result.verdict.lower(),
                    rejected_indices=[
                        t.get("test_index", -1) for t in result.rejected_tests
                    ],
                    summary=result.summary,
                )

                # Record validation metrics for drift detection
                record_validation_metrics(
                    project_dir=project_dir,
                    verdict=result.verdict.lower(),
                    features_tested=result.tests_verified or total,
                    features_failed=len(result.rejected_tests),
                    failure_reasons=[
                        t.get("reason", "Unknown")
                        for t in result.rejected_tests
                        if t.get("reason")
                    ],
                )

                if result.verdict == "APPROVED":
                    print("\n" + "=" * 70)
                    print("  VALIDATION PASSED - ALL FEATURES COMPLETE!")
                    print("=" * 70)
                    print(f"\n{passing}/{total} features validated and approved!")
                    if counts["manual_total"] > 0:
                        print(
                            f"\nNote: {counts['manual_total']} test(s) require manual verification by user"
                        )
                    break  # Exit validation loop

                # Handle CONTINUE - validator needs more sessions to complete testing
                if result.verdict == "CONTINUE":
                    print(
                        f"\nValidator tested {result.tests_verified} feature(s) so far"
                    )
                    print("Continuing validation in next session...")
                    await asyncio.sleep(config.agent.auto_continue_delay)
                    continue  # Continue validation loop

                # Handle NEEDS_VERIFICATION - validator couldn't properly test
                if result.verdict == "NEEDS_VERIFICATION":
                    print("\n" + "=" * 70)
                    print("  VALIDATION INCOMPLETE - MANUAL VERIFICATION REQUIRED")
                    print("=" * 70)
                    print("\nValidator could not fully verify the implementation.")
                    if result.error:
                        print(f"Reason: {result.error}")
                    print("\nThe automated agent has completed its work.")
                    print(
                        "Please manually verify the implementation before deployment."
                    )
                    if result.tests_verified > 0:
                        print(
                            f"Tests verified by validator: {result.tests_verified}/{total}"
                        )
                    break  # Exit validation loop

                # Handle rejection or error
                if result.rejected_tests:
                    indices = [
                        t.get("test_index")
                        for t in result.rejected_tests
                        if "test_index" in t
                    ]
                    reasons = {
                        t.get("test_index"): t.get("reason", "Rejected by validator")
                        for t in result.rejected_tests
                        if "test_index" in t
                    }
                    updated, errors = mark_tests_failed(project_dir, indices, reasons)

                    if errors:
                        for err in errors:
                            print(f"Warning: {err}")

                    print(f"\nValidation rejected {len(indices)} feature(s)")
                    print(f"Marked {updated} test(s) as needing rework")

                if result.error:
                    print(f"\nValidator error: {result.error}")
                    print("Treating as rejection - will retry validation on next pass")

                break  # Exit validation loop on rejection/error

            # After validation loop, decide what to do
            if result.verdict == "APPROVED":
                break  # Exit main loop - we're done!

            if result.verdict == "NEEDS_VERIFICATION":
                break  # Exit main loop - manual review needed

            # Otherwise (REJECTED or ERROR), return to coding agent
            print("\n" + "-" * 70)
            print("WORKFLOW CHECK:")
            print(f"  Validation result: {result.verdict}")
            print("  -> RETURNING TO CODING AGENT (to address rejected features)")
            print("-" * 70)
            await asyncio.sleep(config.agent.auto_continue_delay)
            continue  # Continue main loop

        # Not ready for validation - continue coding
        remaining = counts["automated_total"] - counts["automated_passing"]
        print(f"  -> CONTINUING CODING ({remaining} automated tests remaining)")
        print("-" * 70)

        # Handle status
        if status == "continue":
            delay = config.agent.auto_continue_delay
            print(f"\nAgent will auto-continue in {delay}s...")
            print_progress_summary(project_dir)
            await asyncio.sleep(delay)

        elif status == "error":
            print("\nSession encountered an error")
            print("Will retry with a fresh session...")
            await asyncio.sleep(config.agent.auto_continue_delay)

        # Small delay between sessions
        if max_iterations is None or iteration < max_iterations:
            print("\nPreparing next session...\n")
            await asyncio.sleep(1)

    # Final summary
    print("\n" + "=" * 70)
    print("  SESSION COMPLETE")
    print("=" * 70)
    print(f"\nProject directory: {project_dir}")
    print_progress_summary(project_dir)

    print("\n" + "-" * 70)
    print("  TO RUN THE GENERATED APPLICATION:")
    print("-" * 70)
    print(f"\n  cd {project_dir.resolve()}")
    print("  ./init.sh           # Run the setup script")
    print(f"  # Or manually: {init_command} && {dev_command}")
    print("-" * 70)

    print("\nDone!")


# =============================================================================
# Spec Workflow Session Runners
# =============================================================================


async def run_spec_create_session(
    config: Config,
    goal: str,
    context: str = "",
) -> tuple[str, Path]:
    """
    Run spec creation session.

    Args:
        config: Configuration object
        goal: The user's goal or rough idea
        context: Optional additional context

    Returns:
        (status, spec_path) where status is "complete" or "error"
    """
    project_dir = config.project_dir
    stack = config.stack or detect_stack(project_dir)

    # Configure security
    configure_security(stack=stack, extra_commands=config.security.extra_commands)

    # Initialize logging
    logging_config = _create_logging_config(config)
    logger = AgentLogger(
        project_dir=project_dir,
        config=logging_config,
        verbose=config.verbose,
    )
    set_security_logger(logger)

    # Start logging session
    session_id = logger.start_session(
        iteration=0,
        model=config.agent.model,
        stack=stack,
        agent_type="spec_create",
    )
    stats_tracker = SessionStatsTracker(
        project_dir=project_dir,
        session_id=session_id,
        agent_type="spec_create",
    )

    # Print header
    print("\n" + "=" * 70)
    print("  SPEC WORKFLOW - STEP 1: CREATE")
    print("  Creating detailed specification from goal...")
    print("=" * 70 + "\n")

    # Create client
    client = create_client(
        project_dir=project_dir,
        model=config.agent.model,
        max_turns=config.agent.max_turns,
        stack=stack,
    )

    # Get prompt
    prompt = get_spec_create_prompt(goal, context)

    # Run session with logging
    async with client:
        status, _ = await run_agent_session(
            client, prompt, project_dir, logger, stats_tracker
        )

    # End logging session
    logger.end_session(
        turns_used=stats_tracker.stats.turns_used,
        status=status,
    )
    stats_tracker.save()

    # Find spec-draft.md in project root or specs/ subdirectory
    spec_path = find_spec_draft(project_dir)

    # Record step
    if spec_path is not None:
        record_spec_step(
            project_dir,
            "create",
            {
                "status": "complete",
                "output_file": str(spec_path.relative_to(project_dir)),
                "goal": goal[:200],  # Truncate for storage
            },
        )
        print(f"\nCreated: {spec_path}")
        return "complete", spec_path
    else:
        # File not found - record error with default path
        record_spec_step(
            project_dir,
            "create",
            {
                "status": "error",
                "output_file": "spec-draft.md",
                "goal": goal[:200],
            },
        )
        print_error(ActionableError(
            message="spec-draft.md was not created",
            context="The spec creation agent may have encountered issues.",
            example="claude-agent logs --errors",
            help_command="claude-agent spec create --help",
        ))
        print("\n  Try running the command again or check the logs for details.")
        return "error", project_dir / "spec-draft.md"


async def run_spec_validate_session(
    config: Config,
    spec_path: Path,
) -> tuple[str, bool]:
    """
    Run spec validation session.

    Args:
        config: Configuration object
        spec_path: Path to the specification file to validate

    Returns:
        (status, passed) where passed indicates if validation succeeded
    """
    project_dir = config.project_dir
    stack = config.stack or detect_stack(project_dir)

    configure_security(stack=stack, extra_commands=config.security.extra_commands)

    # Initialize logging
    logging_config = _create_logging_config(config)
    logger = AgentLogger(
        project_dir=project_dir,
        config=logging_config,
        verbose=config.verbose,
    )
    set_security_logger(logger)

    # Start logging session
    session_id = logger.start_session(
        iteration=0,
        model=config.agent.model,
        stack=stack,
        agent_type="spec_validate",
    )
    stats_tracker = SessionStatsTracker(
        project_dir=project_dir,
        session_id=session_id,
        agent_type="spec_validate",
    )

    print("\n" + "=" * 70)
    print("  SPEC WORKFLOW - STEP 2: VALIDATE")
    print("  Validating specification for completeness...")
    print("=" * 70 + "\n")

    # Read spec content
    spec_content = spec_path.read_text()

    client = create_client(
        project_dir=project_dir,
        model=config.agent.model,
        max_turns=config.agent.max_turns,
        stack=stack,
    )

    prompt = get_spec_validate_prompt(spec_content)

    async with client:
        status, response = await run_agent_session(
            client, prompt, project_dir, logger, stats_tracker
        )

    # End logging session
    logger.end_session(
        turns_used=stats_tracker.stats.turns_used,
        status=status,
    )
    stats_tracker.save()

    # Parse the actual verdict from the validation report
    verdict = parse_validation_verdict(project_dir)

    # Also check if spec-validated.md was created (for the output_file field)
    validated_path = find_spec_validated(project_dir)
    validation_report_path = find_spec_validation_report(project_dir)

    # Determine passed status from parsed verdict
    passed = verdict.passed

    # Record step with detailed info
    record_spec_step(
        project_dir,
        "validate",
        {
            "status": "complete",
            "passed": passed,
            "verdict": verdict.verdict,
            "blocking": verdict.blocking,
            "warnings": verdict.warnings,
            "suggestions": verdict.suggestions,
            "output_file": (
                str(validated_path.relative_to(project_dir))
                if validated_path
                else None
            ),
            "validation_report": (
                str(validation_report_path.relative_to(project_dir))
                if validation_report_path
                else None
            ),
        },
    )

    # Print results
    if passed:
        print(f"\nValidation PASSED (verdict: {verdict.verdict})")
        print(f"  Blocking: {verdict.blocking}, Warnings: {verdict.warnings}, Suggestions: {verdict.suggestions}")
        if validated_path:
            print(f"  Validated spec: {validated_path}")
        else:
            # Passed but no validated file - this is unusual
            print("  Warning: spec-validated.md not found (expected for PASS verdict)")
    else:
        print(f"\nValidation FAILED (verdict: {verdict.verdict})")
        print(f"  Blocking: {verdict.blocking}, Warnings: {verdict.warnings}, Suggestions: {verdict.suggestions}")
        if verdict.error:
            print(f"  Parse error: {verdict.error}")
        if validation_report_path:
            print(f"  Review issues in: {validation_report_path}")

    return status, passed


async def run_spec_decompose_session(
    config: Config,
    spec_path: Path,
    feature_count: int,
) -> tuple[str, Path]:
    """
    Run spec decomposition session.

    Args:
        config: Configuration object
        spec_path: Path to the validated specification file
        feature_count: Target number of features to generate

    Returns:
        (status, feature_list_path)
    """
    project_dir = config.project_dir
    stack = config.stack or detect_stack(project_dir)

    configure_security(stack=stack, extra_commands=config.security.extra_commands)

    # Initialize logging
    logging_config = _create_logging_config(config)
    logger = AgentLogger(
        project_dir=project_dir,
        config=logging_config,
        verbose=config.verbose,
    )
    set_security_logger(logger)

    # Start logging session
    session_id = logger.start_session(
        iteration=0,
        model=config.agent.model,
        stack=stack,
        agent_type="spec_decompose",
    )
    stats_tracker = SessionStatsTracker(
        project_dir=project_dir,
        session_id=session_id,
        agent_type="spec_decompose",
    )

    print("\n" + "=" * 70)
    print("  SPEC WORKFLOW - STEP 3: DECOMPOSE")
    print(f"  Decomposing specification into ~{feature_count} features...")
    print("=" * 70 + "\n")

    spec_content = spec_path.read_text()

    client = create_client(
        project_dir=project_dir,
        model=config.agent.model,
        max_turns=config.agent.max_turns,
        stack=stack,
    )

    prompt = get_spec_decompose_prompt(spec_content, feature_count)

    async with client:
        status, _ = await run_agent_session(
            client, prompt, project_dir, logger, stats_tracker
        )

    # End logging session
    logger.end_session(
        turns_used=stats_tracker.stats.turns_used,
        status=status,
    )
    stats_tracker.save()

    # Find feature_list.json (may be in specs/ or project root)
    feature_list_path = find_feature_list(project_dir)

    record_spec_step(
        project_dir,
        "decompose",
        {
            "status": "complete" if feature_list_path else "error",
            "output_file": str(feature_list_path) if feature_list_path else None,
            "feature_count": feature_count,
        },
    )

    if feature_list_path:
        print(f"\nCreated: {feature_list_path}")
    else:
        print_error(ActionableError(
            message="feature_list.json was not created",
            context="The decomposition agent may have encountered issues.",
            example="claude-agent logs --errors",
            help_command="claude-agent spec decompose --help",
        ))
        print("\n  Try running the command again or check the logs for details.")

    # Return a default path if not found (for type consistency)
    return status, feature_list_path or (project_dir / "feature_list.json")


async def run_spec_workflow(config: Config, goal: Optional[str]) -> bool:
    """
    Run full spec workflow (auto mode) with resume support.

    This orchestrates the complete spec workflow:
    1. Create: Generate detailed spec from goal
    2. Validate: Check spec for completeness
    3. Decompose: Break into feature list

    If a spec already exists, resumes from the current phase.

    Args:
        config: Configuration object
        goal: The user's goal or rough idea (optional if resuming)

    Returns:
        True if workflow completed successfully
    """
    from claude_agent.progress import get_spec_phase

    project_dir = config.project_dir

    # Check current phase to determine where to resume
    phase = get_spec_phase(project_dir)

    print("\n" + "=" * 70)
    print("  SPEC WORKFLOW - AUTO MODE")
    print("=" * 70)

    if goal:
        print(f"\nGoal: {goal[:100]}{'...' if len(goal) > 100 else ''}")
    if phase != "none":
        print(f"Resuming from phase: {phase}")
    print("-" * 70)

    # Step 1: Create (skip if already done)
    if phase == "none":
        if not goal:
            print_error(ActionableError(
                message="--goal is required when no spec exists",
                context="Starting a new spec workflow requires a goal.",
                example='claude-agent spec auto --goal "Build a REST API"',
                help_command="claude-agent spec auto --help",
            ))
            return False

        print("\nStep 1/3: Creating specification...")
        status, spec_path = await run_spec_create_session(config, goal)

        if not spec_path.exists():
            print_error(ActionableError(
                message="Spec creation failed - spec-draft.md not created",
                context="The first step of the workflow failed.",
                example="claude-agent logs --errors",
                help_command="claude-agent spec status",
            ))
            print("\n  Check the logs and retry with 'claude-agent spec auto'.")
            return False
    else:
        print("\nStep 1/3: Creating specification... [SKIPPED - already exists]")
        spec_path = find_spec_draft(project_dir)
        if spec_path is None:
            print_error(ActionableError(
                message="spec-draft.md not found but phase indicates it should exist",
                context="Workflow state is inconsistent. The file may have been deleted.",
                example="claude-agent --reset",
                help_command="claude-agent spec status",
            ))
            print("\n  Use --reset to start fresh, or check spec status for details.")
            return False

    # Step 2: Validate (skip if already done)
    if phase in ("none", "created"):
        print("\nStep 2/3: Validating specification...")
        status, passed = await run_spec_validate_session(config, spec_path)

        if not passed:
            print_error(ActionableError(
                message="Validation failed - blocking issues found",
                context="The spec has issues that must be fixed before decomposition.",
                example="cat specs/spec-validation.md",
                help_command="claude-agent spec status",
            ))
            print("\n  Review spec-validation.md and fix issues before continuing.")
            return False
    else:
        print("\nStep 2/3: Validating specification... [SKIPPED - already validated]")

    # Find the validated spec (may be in root or specs/)
    validated_path = find_spec_validated(project_dir)
    if validated_path is None:
        print_error(ActionableError(
            message="spec-validated.md not found",
            context="Validation may have failed to save the approved spec.",
            example="claude-agent spec validate",
            help_command="claude-agent spec status",
        ))
        print("\n  Run 'claude-agent spec validate' to retry validation.")
        return False

    # Step 3: Decompose (skip if already done)
    if phase in ("none", "created", "validated"):
        print("\nStep 3/3: Decomposing into features...")
        status, feature_path = await run_spec_decompose_session(
            config, validated_path, config.features
        )

        if not feature_path.exists():
            print_error(ActionableError(
                message="Decomposition failed - feature_list.json not created",
                context="The final step of the workflow failed.",
                example="claude-agent spec decompose",
                help_command="claude-agent logs --errors",
            ))
            print("\n  Run 'claude-agent spec decompose' to retry.")
            return False
    else:
        print("\nStep 3/3: Decomposing into features... [SKIPPED - already decomposed]")
        feature_path = find_feature_list(project_dir)
        if not feature_path:
            print_error(ActionableError(
                message="feature_list.json not found but phase indicates it should exist",
                context="Workflow state is inconsistent. The file may have been deleted.",
                example="claude-agent --reset",
                help_command="claude-agent spec status",
            ))
            print("\n  Use --reset to start fresh, or run 'claude-agent spec decompose'.")
            return False

    # Summary
    print("\n" + "=" * 70)
    print("  SPEC WORKFLOW COMPLETE")
    print("=" * 70)
    print("\nGenerated files:")
    print("  - spec-draft.md          (initial spec)")
    print("  - spec-validation.md     (validation report)")
    print("  - spec-validated.md      (approved spec)")
    print("  - feature_list.json      (implementation roadmap)")
    print("\nReady for coding. Run 'claude-agent' to start implementation.")

    return True
