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
from claude_agent.progress import (
    count_passing_tests,
    count_tests_by_type,
    find_spec_draft,
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
    get_initializer_prompt,
    get_coding_prompt,
    get_review_prompt,
    get_validator_prompt,
    get_spec_create_prompt,
    get_spec_validate_prompt,
    get_spec_decompose_prompt,
    write_spec_to_project,
)
from claude_agent.security import configure_security


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
) -> bool:
    """
    Run a spec review session before generating features.

    Args:
        config: Configuration object
        stack: Detected tech stack
        spec_content: The specification content to review

    Returns:
        True if user wants to proceed, False to abort
    """
    project_dir = config.project_dir

    print("\n" + "=" * 70)
    print("  SPEC REVIEW MODE")
    print("=" * 70)
    print("\nThe agent will analyze your spec and create a review document.")
    print("You can then decide whether to proceed or refine the spec first.\n")

    # Write spec to project for the agent
    write_spec_to_project(project_dir, spec_content)

    # Create client for review session
    client = create_client(
        project_dir=project_dir,
        model=config.agent.model,
        max_turns=config.agent.max_turns,
        stack=stack,
    )

    # Run review session
    prompt = get_review_prompt(spec_content)

    async with client:
        status, response = await run_agent_session(client, prompt, project_dir)

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
) -> tuple[str, str]:
    """
    Run a single agent session using Claude Agent SDK.

    Args:
        client: Claude SDK client
        message: The prompt to send
        project_dir: Project directory path

    Returns:
        (status, response_text) where status is:
        - "continue" if agent should continue working
        - "error" if an error occurred
    """
    print("Sending prompt to Claude Agent SDK...\n")

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
                        print(f"\n[Tool: {block.name}]", flush=True)
                        if hasattr(block, "input"):
                            input_str = str(block.input)
                            if len(input_str) > 200:
                                print(f"   Input: {input_str[:200]}...", flush=True)
                            else:
                                print(f"   Input: {input_str}", flush=True)

            # Handle UserMessage (tool results)
            elif msg_type == "UserMessage" and hasattr(msg, "content"):
                for block in msg.content:
                    block_type = type(block).__name__

                    if block_type == "ToolResultBlock":
                        result_content = getattr(block, "content", "")
                        is_error = getattr(block, "is_error", False)

                        if "blocked" in str(result_content).lower():
                            print(f"   [BLOCKED] {result_content}", flush=True)
                        elif is_error:
                            error_str = str(result_content)[:500]
                            print(f"   [Error] {error_str}", flush=True)
                        else:
                            print("   [Done]", flush=True)

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

        print("\n" + "-" * 70 + "\n")
        return "continue", response_text

    except Exception as e:
        print(f"Error during agent session: {e}")
        return "error", str(e)


async def run_validator_session(
    config: Config,
    stack: str,
    project_dir: Path,
    init_command: str,
    dev_command: str,
) -> ValidatorResult:
    """
    Run validator agent session and parse results.

    Args:
        config: Configuration object
        stack: Detected tech stack
        project_dir: Project directory path
        init_command: Command to install dependencies
        dev_command: Command to start development server

    Returns:
        ValidatorResult with verdict and any rejected tests
    """
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

    # Run session
    async with client:
        status, response = await run_agent_session(client, prompt, project_dir)

    # Parse response
    result = parse_validator_response(response)

    return result


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
    tests_file = project_dir / "feature_list.json"
    is_first_run = not tests_file.exists()

    if is_first_run:
        # Validate we have spec content
        spec_content = config.spec_content

        # Check for existing app_spec.txt (e.g., from aborted review)
        if not spec_content:
            existing_spec = project_dir / "app_spec.txt"
            if existing_spec.exists():
                print(f"Found existing spec: {existing_spec}")
                spec_content = existing_spec.read_text()
            else:
                print("Error: No spec file or goal provided.")
                print(
                    "Use --spec PATH or --goal 'description' to specify what to build."
                )
                return

        # Run review session if requested
        if config.review:
            proceed = await run_review_session(config, stack, spec_content)
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
                prompt = get_coding_prompt(
                    init_command=init_command,
                    dev_command=dev_command,
                )

            # Run session
            async with client:
                status, response = await run_agent_session(client, prompt, project_dir)

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

    # Run session
    async with client:
        status, _ = await run_agent_session(client, prompt, project_dir)

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
        print("\nError: spec-draft.md was not created")
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
        status, response = await run_agent_session(client, prompt, project_dir)

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
        status, _ = await run_agent_session(client, prompt, project_dir)

    feature_list_path = project_dir / "feature_list.json"

    record_spec_step(
        project_dir,
        "decompose",
        {
            "status": "complete" if feature_list_path.exists() else "error",
            "output_file": "feature_list.json",
            "feature_count": feature_count,
        },
    )

    if feature_list_path.exists():
        print(f"\nCreated: {feature_list_path}")
    else:
        print("\nError: feature_list.json was not created")

    return status, feature_list_path


async def run_spec_workflow(config: Config, goal: str) -> bool:
    """
    Run full spec workflow (auto mode).

    This orchestrates the complete spec workflow:
    1. Create: Generate detailed spec from goal
    2. Validate: Check spec for completeness
    3. Decompose: Break into feature list

    Args:
        config: Configuration object
        goal: The user's goal or rough idea

    Returns:
        True if workflow completed successfully
    """
    print("\n" + "=" * 70)
    print("  SPEC WORKFLOW - AUTO MODE")
    print("=" * 70)
    print(f"\nGoal: {goal[:100]}{'...' if len(goal) > 100 else ''}")
    print("-" * 70)

    project_dir = config.project_dir

    # Step 1: Create
    print("\nStep 1/3: Creating specification...")
    status, spec_path = await run_spec_create_session(config, goal)

    if not spec_path.exists():
        print("\nError: Spec creation failed - spec-draft.md not created")
        return False

    # Step 2: Validate
    print("\nStep 2/3: Validating specification...")
    status, passed = await run_spec_validate_session(config, spec_path)

    if not passed:
        print("\nValidation failed - blocking issues found")
        print("Review spec-validation.md and fix issues before continuing")
        return False

    # Find the validated spec (may be in root or specs/)
    validated_path = find_spec_validated(project_dir)
    if validated_path is None:
        print("\nError: spec-validated.md not found after validation passed")
        return False

    # Step 3: Decompose
    print("\nStep 3/3: Decomposing into features...")
    status, feature_path = await run_spec_decompose_session(
        config, validated_path, config.features
    )

    if not feature_path.exists():
        print("\nError: Decomposition failed - feature_list.json not created")
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
