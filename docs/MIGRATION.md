# Migration Guide: Drift Mitigation System

This guide helps you transition existing claude-agent projects to use the new drift mitigation system. The migration is designed to be **fully backwards compatible** with no breaking changes.

## Overview

The drift mitigation system adds three key capabilities:

1. **Metrics Tracking** - Automatic tracking of session quality and drift indicators
2. **Architecture Lock** - Locked contracts, schemas, and decisions to prevent architectural drift
3. **Forced Evaluation** - Mandatory evaluation sequences before implementation

## Quick Start

For most existing projects, migration requires **no action**. Simply upgrade to the latest version and continue running:

```bash
# Update claude-agent
uv sync

# Resume your project - drift mitigation activates automatically
uv run claude-agent -p ./your-project
```

## Backwards Compatibility

The drift mitigation system is designed with full backwards compatibility:

| Feature | Existing Projects | Notes |
|---------|------------------|-------|
| Metrics file | Auto-created on first session | Old sessions won't have full metrics data |
| Architecture lock | Optional (enabled by default) | Use `--skip-architecture` to defer |
| Evaluation sequences | Automatic in new sessions | Tracked in metrics |
| Feature list | Unchanged format | No modifications required |
| Progress notes | Compatible | New structured entries supported |
| Config file | New optional fields | Existing configs remain valid |

### Legacy Data Handling

When loading existing `drift-metrics.json` files, the system automatically provides sensible defaults for any new fields that were added in later versions. This ensures:

- Old metrics files load without errors
- Missing fields receive safe default values (e.g., zero for counts, 1.0 for completeness scores)
- Old sessions are treated as having complete evaluation until new sessions provide actual data

This approach means you never need to manually update or migrate your metrics files.

## Step-by-Step Migration

### Step 1: Check Current Project Status

First, verify your project state:

```bash
# Check project status
uv run claude-agent status ./your-project

# Check for existing metrics (may not exist yet)
uv run claude-agent status ./your-project --metrics
```

Expected output for a pre-migration project:
```
Project: /path/to/your-project
Stack:   node
State:   in_progress (15/50 automated tests passing)

--- Drift Metrics ---
Total Sessions: 0
Regression Rate: 0.0%
Velocity Trend: insufficient_data
```

### Step 2: Initialize Metrics Tracking

Metrics are automatically initialized on the first session after upgrade. No action required - just run the agent:

```bash
uv run claude-agent -p ./your-project
```

After the first session, you'll see metrics populated:

```bash
uv run claude-agent status ./your-project --metrics

# Output:
# Total Sessions: 1
# Regression Rate: 0.0%
# Velocity Trend: insufficient_data
# Multi-Feature Rate: 0.0%
# Incomplete Evaluation Rate: 0.0%
```

The `drift-metrics.json` file is created automatically:

```json
{
  "sessions": [{
    "session_id": 1,
    "timestamp": "2025-12-09T10:30:00Z",
    "features_attempted": 3,
    "features_completed": 2,
    "features_regressed": 0,
    "regressions_caught": 0,
    "evaluation_sections_present": ["context", "regression", "plan"],
    "evaluation_completeness_score": 1.0,
    "is_multi_feature": false
  }],
  "validation_attempts": [],
  "total_sessions": 1,
  "total_regressions_caught": 0,
  "average_features_per_session": 2.0,
  "rejection_count": 0,
  "multi_feature_session_count": 0,
  "incomplete_evaluation_count": 0
}
```

### Step 3: Configure Architecture Lock (Recommended)

Architecture lock creates contracts, schemas, and decision records to prevent architectural drift. For existing projects with established patterns, you have three options:

#### Option A: Enable Architecture Lock (Recommended)

Run the architecture phase to lock your existing patterns:

```bash
uv run claude-agent -p ./your-project
```

When the architecture phase runs (automatically triggered if `architecture/` doesn't exist), the **Architect Agent** will:
1. Analyze your existing code to identify API contracts
2. Extract data schemas from models/types
3. Document architectural decisions based on patterns found

This is fully automated - the agent creates the `architecture/` directory:

```
your-project/
├── architecture/
│   ├── contracts.yaml   # API endpoint definitions
│   ├── schemas.yaml     # Data model definitions
│   └── decisions.yaml   # Architectural decision records
```

#### Option B: Skip Architecture Lock (Temporary)

If you want to defer architecture lock:

```bash
# Skip for this session only
uv run claude-agent -p ./your-project --skip-architecture

# Or disable in config (not recommended for production)
```

Add to `.claude-agent.yaml`:

```yaml
architecture:
  enabled: false
```

#### Option C: Create Architecture Files Manually

For established projects with well-defined architecture, create the files manually:

```bash
mkdir -p ./your-project/architecture
```

**contracts.yaml** - Define your API contracts:

```yaml
contracts:
  - name: User API
    description: User management endpoints
    endpoints:
      - path: /api/users
        method: GET
      - path: /api/users/:id
        method: GET
      - path: /api/users
        method: POST
```

**schemas.yaml** - Define your data models:

```yaml
schemas:
  - name: User
    description: User account model
    fields:
      - name: id
        type: string
        constraints: [required, uuid]
      - name: email
        type: string
        constraints: [required, email]
      - name: created_at
        type: datetime
        constraints: [required]
```

**decisions.yaml** - Document architectural decisions:

```yaml
decisions:
  - id: DR-001
    topic: Authentication method
    choice: JWT tokens
    alternatives_considered:
      - Session cookies
      - OAuth2 only
    rationale: Stateless authentication for API-first design
    constraints_created:
      - All protected routes must validate JWT
    affects_features: []
```

### Step 4: Update Configuration (Optional)

Add drift mitigation settings to `.claude-agent.yaml` in your **project root directory**:

```yaml
# Architecture lock settings
architecture:
  enabled: true   # Run architecture phase (default: true)
  required: false # Fail if architecture lock fails (default: false)

# Metrics are always enabled, stored in:
metrics_file: drift-metrics.json
```

### Step 5: Verify Migration

After running a session with the new system:

```bash
# Check metrics are being recorded
uv run claude-agent status ./your-project --metrics

# Verify architecture files (if enabled)
ls -la ./your-project/architecture/

# Check for evaluation sections in logs (filter by session ID)
uv run claude-agent logs --session abc123

# View detailed session statistics (turns, duration, features completed)
uv run claude-agent stats
```

Expected healthy metrics after several sessions:

```
--- Drift Metrics ---
Total Sessions: 5
Regression Rate: 0.0%              # Low is good
Velocity Trend: stable             # stable or increasing is good
Rejection Rate: 0.0%               # Low is good
Multi-Feature Rate: 0.0%           # 0% is ideal
Incomplete Evaluation Rate: 0.0%   # 0% is ideal
```

## Migration Commands Reference

| Command | Purpose |
|---------|---------|
| `claude-agent status --metrics` | View drift metrics summary (regression rate, velocity trend, etc.) |
| `claude-agent status` | Check project state and feature progress |
| `claude-agent --skip-architecture` | Skip architecture phase for this session |
| `claude-agent init` | Create/update `.claude-agent.yaml` config template in project root |
| `claude-agent logs` | View recent activity including evaluations (last 50 entries) |
| `claude-agent logs --session ID` | Filter log entries by session ID prefix |
| `claude-agent stats` | View session statistics (turns used, duration, features completed per session) |
| `claude-agent stats --last N` | Show statistics for the last N sessions only |

## Understanding Drift Indicators

After migration, monitor these key indicators:

### Regression Rate

Percentage of sessions that caught regressions during the REGRESSION VERIFICATION step.

- **0-10%**: Healthy - few regressions occurring
- **10-30%**: Warning - some instability in codebase
- **30%+**: Critical - significant drift, review recent changes

### Velocity Trend

Tracks whether feature completion rate is changing over time (requires 6+ sessions).

- **increasing**: Agent is completing more features per session
- **stable**: Consistent completion rate
- **decreasing**: Warning - may indicate growing complexity or drift
- **insufficient_data**: Need more sessions to calculate

### Multi-Feature Rate

Percentage of sessions that worked on multiple features (violating single-feature architecture).

- **0%**: Ideal - following single-feature sessions
- **1-20%**: Warning - occasional multi-feature sessions
- **20%+**: Critical - significant scope creep

### Incomplete Evaluation Rate

Percentage of sessions missing required evaluation sections.

- **0%**: All sessions completing evaluation steps
- **1-10%**: Minor drift in evaluation discipline
- **10%+**: Evaluation steps being skipped - review prompts

## Troubleshooting

### Metrics File Not Created

If `drift-metrics.json` isn't being created:

1. Ensure you're running the latest version (`uv sync` to update)
2. Check file permissions in project directory (must be writable)
3. Run `claude-agent status --metrics` to trigger creation
4. Check for disk space issues

### Metrics File Corruption

If you see errors loading `drift-metrics.json`:

```
Error: Failed to load metrics - invalid JSON
```

Options:
1. **Backup and reset**: `mv drift-metrics.json drift-metrics.json.bak`
2. **Validate JSON**: Use `python -m json.tool drift-metrics.json` to find syntax errors
3. **Manual fix**: Edit the file to fix malformed JSON (missing commas, brackets, etc.)

The system will create a fresh metrics file on the next session if the file is missing or unreadable.

### Permission Errors

If you see permission denied errors:

```bash
# Check file ownership
ls -la drift-metrics.json architecture/

# Fix permissions if needed
chmod 644 drift-metrics.json
chmod 755 architecture/
chmod 644 architecture/*.yaml
```

### Architecture Validation Failures

If architecture phase fails:

```
Error: Architecture validation failed
```

Options:
1. Use `--skip-architecture` temporarily
2. Fix validation errors shown in output
3. Delete `architecture/` to start fresh

### Legacy Progress Notes

Old progress notes format is still supported. New sessions will append structured entries:

```
# Old format (still readable)
Session 5: Implemented feature X

# New format (added automatically)
=== SESSION 8 START ===
STATUS: 45/50 passing (90.0%)
FOCUS: Feature #46 - User notifications
```

## FAQ

### Do I need to re-run the initializer agent?

No. Existing `feature_list.json` files remain compatible. Metrics and architecture lock apply to coding sessions.

### Will my existing sessions appear in metrics?

No. Only sessions after migration are tracked. Historical data is not retroactively populated.

### Can I disable drift mitigation entirely?

Not recommended. You can disable architecture lock with `architecture.enabled: false`, but metrics tracking is always active (minimal overhead).

### What if architecture lock conflicts with my codebase?

If the auto-generated architecture files don't match your actual architecture:
1. Edit the files manually to reflect reality
2. Or delete `architecture/` and recreate with `--skip-architecture` followed by manual creation
3. Or disable architecture lock in config

### How do I reset metrics and start fresh?

```bash
# Remove metrics file (keeps feature list and progress)
rm ./your-project/drift-metrics.json

# Or full reset (removes all agent state)
uv run claude-agent --reset -p ./your-project
```

## Next Steps

After migration:

1. Run several sessions to populate metrics
2. Review drift indicators regularly with `status --metrics`
3. Address any high regression rates or velocity decreases
4. Consider enabling `architecture.required: true` once architecture is stable

For questions or issues, see the [GitHub repository](https://github.com/zazu-22/claude-agent).
