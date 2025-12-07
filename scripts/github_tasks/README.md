# GitHub Task Files

This directory contains YAML task definitions for the `github_api.py` automation script.

## Task File Schema

```yaml
# Task metadata
name: "Human-readable task name"
repo: "owner/repo"  # Target repository

# Labels to create
labels:
  - name: "label-name"
    color: "hex-color"  # Without # prefix
    description: "Label description"

# Milestones to create
milestones:
  - title: "Milestone Title"
    description: "Milestone description"
    due_on: "+2 weeks"  # Relative date or ISO 8601

# Issues to create
issues:
  - title: "Issue title"
    labels:
      - "label-1"
      - "label-2"
    milestone: "Milestone Title"  # References milestone by title
    assignees:
      - "username"
    body: |
      Inline markdown body content.
    # OR
    body_file: "path/to/body.md"  # External file reference
```

## Relative Date Formats

For milestone due dates, you can use relative formats:
- `+1 day` / `+5 days`
- `+1 week` / `+2 weeks`
- `+1 month` / `+3 months`

## Usage

### Via GitHub Actions (Recommended)

1. Add `GITHUB_SETUP_TOKEN` to repository secrets
2. Navigate to Actions > "GitHub Setup Tasks"
3. Click "Run workflow"
4. Select your task file
5. Optionally enable dry-run mode

### Via Command Line

```bash
# Dry run (no changes)
GITHUB_TOKEN=your_token python scripts/github_api.py \
  --task scripts/github_tasks/your-task.yaml \
  --dry-run

# Execute
GITHUB_TOKEN=your_token python scripts/github_api.py \
  --task scripts/github_tasks/your-task.yaml
```

## Creating New Task Files

1. Copy an existing task file as a template
2. Modify the labels, milestones, and issues sections
3. Test with `--dry-run` first
4. Add the filename to the workflow's task_file options

## Idempotency

The script is designed to be idempotent:
- Labels that already exist are skipped
- Milestones that already exist are skipped (and their IDs are reused)
- Issues are always created (no duplicate detection)

To avoid duplicate issues, only run issue creation once per task file.
