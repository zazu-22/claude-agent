# GitHub Workflows Guide for Claude

This document provides guidance for AI assistants working with GitHub Actions workflows in this repository.

## Available Workflows

### `github-setup.yml` - GitHub Setup Tasks

A reusable workflow for automating GitHub repository setup tasks (labels, milestones, issues).

**Purpose:** Execute bulk GitHub operations without loading heavy MCP tool schemas into context. This follows the "code-first" pattern from Anthropic's engineering guidance.

**When to use:**
- Setting up a new feature sprint with labels, milestones, and issues
- Bulk creating or updating repository labels
- Automating repetitive GitHub setup tasks

**How it works:**
1. Task definitions live in `scripts/github_tasks/*.yaml`
2. The workflow runs `scripts/github_api.py` with the specified task file
3. The script makes GitHub API calls using a stored token

**Triggering the workflow:**
- Navigate to Actions > "GitHub Setup Tasks" in the GitHub UI
- Click "Run workflow"
- Select the task file and options
- The workflow requires the `GITHUB_SETUP_TOKEN` secret to be configured

**Creating new task files:**
1. Create a YAML file in `scripts/github_tasks/`
2. Follow the schema documented in `scripts/github_tasks/README.md`
3. Test with `dry_run: true` first

**Example task file structure:**
```yaml
name: "My Sprint Setup"
repo: "owner/repo"

labels:
  - name: "priority:high"
    color: "D93F0B"
    description: "High priority item"

milestones:
  - title: "Sprint 1"
    description: "First sprint"
    due_on: "+2 weeks"

issues:
  - title: "Implement feature X"
    labels: ["priority:high"]
    milestone: "Sprint 1"
    body: |
      ## Description
      Implement feature X...
```

## Security Notes

- **GITHUB_SETUP_TOKEN**: Store as a repository secret with `repo` scope
- Never commit tokens to the repository
- Use `dry_run: true` to preview changes before executing
- The token is only accessible within GitHub Actions, not in code

## Extending the System

To add new GitHub operations:

1. Add the function to `scripts/github_api.py`
2. Update the `TaskRunner` class to handle the new operation type
3. Document the YAML schema in `scripts/github_tasks/README.md`
4. The workflow itself rarely needs modification

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Task file not found" | Check the filename matches exactly (case-sensitive) |
| "GITHUB_TOKEN not set" | Add `GITHUB_SETUP_TOKEN` to repository secrets |
| "401 Unauthorized" | Token expired or lacks required scopes |
| "422 Validation Failed" | Resource may already exist (check logs) |
| Labels created but issues fail | Ensure milestone titles match exactly |

## Related Files

- `scripts/github_api.py` - The API wrapper script
- `scripts/github_tasks/` - Task definition files
- `scripts/github_tasks/README.md` - Task file schema documentation
