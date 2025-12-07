#!/usr/bin/env python3
"""
GitHub API Script
=================

A lightweight, reusable GitHub API wrapper for automating repository setup tasks.
This script follows the "code-first" pattern - generating targeted API calls on demand
rather than loading heavy MCP tool schemas into context.

Usage:
    python scripts/github_api.py --task scripts/github_tasks/my-task.yaml
    python scripts/github_api.py --task scripts/github_tasks/my-task.yaml --dry-run

Environment:
    GITHUB_TOKEN: Personal Access Token with appropriate scopes (repo, project)

Task File Format:
    See scripts/github_tasks/README.md for YAML schema documentation.
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests
import yaml


# =============================================================================
# Configuration
# =============================================================================

GITHUB_API_BASE = "https://api.github.com"


@dataclass
class Config:
    """Runtime configuration."""

    token: str
    repo: str
    dry_run: bool = False
    verbose: bool = False

    @property
    def owner(self) -> str:
        return self.repo.split("/")[0]

    @property
    def repo_name(self) -> str:
        return self.repo.split("/")[1]

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }


# =============================================================================
# API Client
# =============================================================================


class GitHubAPI:
    """Lightweight GitHub API client."""

    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(config.headers)

    def _request(
        self,
        method: str,
        endpoint: str,
        data: dict | None = None,
        params: dict | None = None,
    ) -> dict | list | None:
        """Make an API request with error handling."""
        url = f"{GITHUB_API_BASE}{endpoint}"

        if self.config.dry_run:
            print(f"  [DRY-RUN] {method} {url}")
            if data:
                print(f"            Data: {json.dumps(data, indent=2)[:200]}...")
            return {"dry_run": True}

        if self.config.verbose:
            print(f"  [API] {method} {url}")

        response = self.session.request(method, url, json=data, params=params)

        if response.status_code == 422:
            # Often means resource already exists
            error_data = response.json()
            if "already_exists" in str(error_data):
                print(f"  [SKIP] Already exists")
                return {"skipped": True, "reason": "already_exists"}
            raise GitHubAPIError(response)
        elif response.status_code >= 400:
            raise GitHubAPIError(response)

        if response.status_code == 204:
            return None
        return response.json()

    def get(self, endpoint: str, params: dict | None = None) -> dict | list | None:
        return self._request("GET", endpoint, params=params)

    def post(self, endpoint: str, data: dict) -> dict | None:
        return self._request("POST", endpoint, data=data)

    def patch(self, endpoint: str, data: dict) -> dict | None:
        return self._request("PATCH", endpoint, data=data)

    def delete(self, endpoint: str) -> None:
        self._request("DELETE", endpoint)


class GitHubAPIError(Exception):
    """GitHub API error with response details."""

    def __init__(self, response: requests.Response):
        self.status_code = response.status_code
        self.response = response
        try:
            self.data = response.json()
        except Exception:
            self.data = {"message": response.text}

        message = self.data.get("message", "Unknown error")
        errors = self.data.get("errors", [])
        error_details = "; ".join(
            e.get("message", str(e)) for e in errors
        ) if errors else ""

        super().__init__(
            f"GitHub API Error {self.status_code}: {message}"
            + (f" ({error_details})" if error_details else "")
        )


# =============================================================================
# Task Operations
# =============================================================================


@dataclass
class TaskResult:
    """Result of a task operation."""

    operation: str
    success: bool
    item: str
    details: dict = field(default_factory=dict)
    error: str | None = None


class TaskRunner:
    """Executes tasks defined in YAML files."""

    def __init__(self, api: GitHubAPI, config: Config):
        self.api = api
        self.config = config
        self.results: list[TaskResult] = []
        self.created_milestones: dict[str, int] = {}  # title -> number mapping

    def run_task(self, task_file: Path) -> list[TaskResult]:
        """Run all operations defined in a task file."""
        print(f"\n{'=' * 60}")
        print(f"Running task: {task_file.name}")
        print(f"Repository: {self.config.repo}")
        print(f"Dry run: {self.config.dry_run}")
        print(f"{'=' * 60}\n")

        with open(task_file) as f:
            task_data = yaml.safe_load(f)

        # Override repo if specified in task file
        if "repo" in task_data:
            self.config.repo = task_data["repo"]

        # Run each section in order
        if "labels" in task_data:
            self._create_labels(task_data["labels"])

        if "milestones" in task_data:
            self._create_milestones(task_data["milestones"])

        if "issues" in task_data:
            self._create_issues(task_data["issues"])

        self._print_summary()
        return self.results

    def _create_labels(self, labels: list[dict]) -> None:
        """Create repository labels."""
        print(f"\n--- Creating Labels ({len(labels)}) ---\n")
        endpoint = f"/repos/{self.config.repo}/labels"

        for label in labels:
            name = label["name"]
            print(f"Creating label: {name}")

            try:
                result = self.api.post(endpoint, {
                    "name": name,
                    "color": label.get("color", "ededed").lstrip("#"),
                    "description": label.get("description", ""),
                })

                self.results.append(TaskResult(
                    operation="create_label",
                    success=True,
                    item=name,
                    details={"skipped": result.get("skipped", False)} if result else {},
                ))

            except GitHubAPIError as e:
                if "already_exists" in str(e):
                    print(f"  [SKIP] Label '{name}' already exists")
                    self.results.append(TaskResult(
                        operation="create_label",
                        success=True,
                        item=name,
                        details={"skipped": True},
                    ))
                else:
                    print(f"  [ERROR] {e}")
                    self.results.append(TaskResult(
                        operation="create_label",
                        success=False,
                        item=name,
                        error=str(e),
                    ))

    def _create_milestones(self, milestones: list[dict]) -> None:
        """Create repository milestones."""
        print(f"\n--- Creating Milestones ({len(milestones)}) ---\n")
        endpoint = f"/repos/{self.config.repo}/milestones"

        # First, get existing milestones to avoid duplicates and capture IDs
        existing = self.api.get(endpoint, params={"state": "all"}) or []
        existing_titles = {}
        for m in existing:
            existing_titles[m["title"]] = m["number"]

        for milestone in milestones:
            title = milestone["title"]
            print(f"Creating milestone: {title}")

            if title in existing_titles:
                print(f"  [SKIP] Milestone '{title}' already exists")
                self.created_milestones[title] = existing_titles[title]
                self.results.append(TaskResult(
                    operation="create_milestone",
                    success=True,
                    item=title,
                    details={"skipped": True, "number": existing_titles[title]},
                ))
                continue

            try:
                data = {
                    "title": title,
                    "description": milestone.get("description", ""),
                }

                # Handle relative due dates like "+2 weeks"
                if "due_on" in milestone:
                    due = milestone["due_on"]
                    if due.startswith("+"):
                        data["due_on"] = self._parse_relative_date(due)
                    else:
                        data["due_on"] = due

                result = self.api.post(endpoint, data)

                if result and "number" in result:
                    self.created_milestones[title] = result["number"]

                self.results.append(TaskResult(
                    operation="create_milestone",
                    success=True,
                    item=title,
                    details={"number": result.get("number") if result else None},
                ))

            except GitHubAPIError as e:
                print(f"  [ERROR] {e}")
                self.results.append(TaskResult(
                    operation="create_milestone",
                    success=False,
                    item=title,
                    error=str(e),
                ))

    def _create_issues(self, issues: list[dict]) -> None:
        """Create repository issues."""
        print(f"\n--- Creating Issues ({len(issues)}) ---\n")
        endpoint = f"/repos/{self.config.repo}/issues"

        for issue in issues:
            title = issue["title"]
            print(f"Creating issue: {title[:60]}...")

            try:
                data: dict[str, Any] = {
                    "title": title,
                    "body": self._resolve_body(issue),
                }

                if "labels" in issue:
                    data["labels"] = issue["labels"]

                if "assignees" in issue:
                    data["assignees"] = issue["assignees"]

                # Resolve milestone title to number
                if "milestone" in issue:
                    milestone_title = issue["milestone"]
                    if milestone_title in self.created_milestones:
                        data["milestone"] = self.created_milestones[milestone_title]
                    else:
                        print(f"  [WARN] Milestone '{milestone_title}' not found")

                result = self.api.post(endpoint, data)

                self.results.append(TaskResult(
                    operation="create_issue",
                    success=True,
                    item=title,
                    details={"number": result.get("number") if result else None},
                ))

            except GitHubAPIError as e:
                print(f"  [ERROR] {e}")
                self.results.append(TaskResult(
                    operation="create_issue",
                    success=False,
                    item=title,
                    error=str(e),
                ))

    def _resolve_body(self, issue: dict) -> str:
        """Resolve issue body from inline or file reference."""
        if "body" in issue:
            return issue["body"]
        elif "body_file" in issue:
            body_path = Path(issue["body_file"])
            if body_path.exists():
                return body_path.read_text()
            else:
                return f"(Body file not found: {issue['body_file']})"
        return ""

    def _parse_relative_date(self, relative: str) -> str:
        """Parse relative date like '+2 weeks' into ISO format."""
        parts = relative.strip("+").split()
        if len(parts) != 2:
            return relative

        amount = int(parts[0])
        unit = parts[1].rstrip("s")  # "weeks" -> "week"

        if unit == "day":
            delta = timedelta(days=amount)
        elif unit == "week":
            delta = timedelta(weeks=amount)
        elif unit == "month":
            delta = timedelta(days=amount * 30)
        else:
            return relative

        due_date = datetime.utcnow() + delta
        return due_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _print_summary(self) -> None:
        """Print execution summary."""
        print(f"\n{'=' * 60}")
        print("SUMMARY")
        print(f"{'=' * 60}\n")

        operations = {}
        for r in self.results:
            if r.operation not in operations:
                operations[r.operation] = {"success": 0, "skipped": 0, "failed": 0}

            if not r.success:
                operations[r.operation]["failed"] += 1
            elif r.details.get("skipped"):
                operations[r.operation]["skipped"] += 1
            else:
                operations[r.operation]["success"] += 1

        for op, counts in operations.items():
            print(f"{op}:")
            print(f"  Created: {counts['success']}")
            print(f"  Skipped: {counts['skipped']}")
            print(f"  Failed:  {counts['failed']}")
            print()

        # List any failures
        failures = [r for r in self.results if not r.success]
        if failures:
            print("FAILURES:")
            for f in failures:
                print(f"  - {f.operation}: {f.item}")
                print(f"    Error: {f.error}")


# =============================================================================
# CLI
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="GitHub API automation script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--task",
        required=True,
        type=Path,
        help="Path to task YAML file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print operations without executing",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--repo",
        help="Override repository (owner/repo)",
    )

    args = parser.parse_args()

    # Validate task file
    if not args.task.exists():
        print(f"Error: Task file not found: {args.task}")
        sys.exit(1)

    # Get token from environment
    token = os.environ.get("GITHUB_TOKEN")
    if not token and not args.dry_run:
        print("Error: GITHUB_TOKEN environment variable not set")
        print("Create a token at: https://github.com/settings/tokens/new")
        print("Required scopes: repo")
        sys.exit(1)

    # Load task to get repo
    with open(args.task) as f:
        task_data = yaml.safe_load(f)

    repo = args.repo or task_data.get("repo")
    if not repo:
        print("Error: Repository not specified in task file or --repo argument")
        sys.exit(1)

    # Create config and run
    config = Config(
        token=token or "dry-run-token",
        repo=repo,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    api = GitHubAPI(config)
    runner = TaskRunner(api, config)

    try:
        results = runner.run_task(args.task)
        failures = [r for r in results if not r.success]
        sys.exit(1 if failures else 0)
    except Exception as e:
        print(f"\nFatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
