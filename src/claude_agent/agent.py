"""
Agent Session Logic
===================

Core agent interaction functions for running autonomous coding sessions.
"""

import asyncio
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
    print_session_header,
    print_progress_summary,
    print_startup_banner,
)
from claude_agent.prompts.loader import (
    get_initializer_prompt,
    get_coding_prompt,
    get_review_prompt,
    write_spec_to_project,
)
from claude_agent.security import configure_security


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

        print("\n" + "-" * 70 + "\n")
        return "continue", response_text

    except Exception as e:
        print(f"Error during agent session: {e}")
        return "error", str(e)


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
                print("Use --spec PATH or --goal 'description' to specify what to build.")
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
        print(f"  NOTE: First session may take 10-20+ minutes!")
        print(f"  The agent is generating {config.features} detailed test cases.")
        print("  This may appear to hang - it's working. Watch for [Tool: ...] output.")
        print("=" * 70)
        print()

        # Write spec to project directory for agent reference
        write_spec_to_project(project_dir, spec_content)
    else:
        print("Continuing existing project")
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

        # Print session header
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

        # Check for completion
        passing, total = count_passing_tests(project_dir)
        if total > 0 and passing == total:
            print("\n" + "=" * 70)
            print("  ALL FEATURES COMPLETE!")
            print("=" * 70)
            print(f"\n{passing}/{total} features passing - project is done!")
            break

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
