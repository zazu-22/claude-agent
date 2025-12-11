# Error Recovery Skill

## Purpose

This skill provides patterns for handling errors intelligently during autonomous
coding sessions. Different error types require different recovery strategies, and
understanding these patterns prevents wasted time and context.

## When to Use

Use this skill when:
- A command or operation fails unexpectedly
- Tests are failing and the cause is unclear
- The application is in a broken state
- Network or API errors occur
- Security blocks prevent an operation

## Pattern

### Error Classification

First, classify the error by type to determine the correct recovery strategy:

| Error Type | Indicator | Recovery Strategy |
|------------|-----------|-------------------|
| **RETRY** | Transient failures (network timeout, rate limit) | Wait and retry up to 3 times |
| **MANUAL** | Needs human input (security block, unclear requirement) | Pause and request guidance |
| **FATAL** | Cannot proceed (missing critical dependency) | Abort with clear message |
| **TIMEOUT** | Operation took too long | Log and escalate |

### Error Categories and Recovery Steps

#### NETWORK Errors
*Examples: API failures, connection refused, DNS resolution*

Recovery steps:
1. Check if the service is running (use `ps` or similar)
2. Verify network connectivity
3. Wait 5 seconds and retry (up to 3 times)
4. If persists, check service logs
5. Escalate if external service is down

#### AUTH Errors
*Examples: Permission denied, token expired, invalid credentials*

Recovery steps:
1. Check if authentication is configured correctly
2. Verify credentials haven't expired
3. Re-read .env or config files
4. Check if OAuth tokens need refresh
5. Escalate if credentials need regeneration

#### LOGIC Errors
*Examples: Lint failures, type errors, test failures*

Recovery steps:
1. Read the full error message carefully
2. Locate the exact file and line number
3. Review the code change that caused the error
4. Fix the code issue (not the test)
5. Re-run the failed check
6. If unclear, add logging to understand the flow

#### CONFIG Errors
*Examples: Invalid configuration values, missing env vars*

Recovery steps:
1. Check .env file exists and is readable
2. Verify required environment variables are set
3. Check config file syntax (YAML, JSON parsing)
4. Compare against documentation or examples
5. Reset to known-good configuration if needed

#### RESOURCE Errors
*Examples: Missing files, branches, dependencies*

Recovery steps:
1. Verify the path is correct (absolute vs relative)
2. Check if file/directory exists
3. Check git status for untracked or modified files
4. Reinstall dependencies if package-related
5. Check for git branch issues

#### SECURITY Errors
*Examples: Command blocked by allowlist, permission denied*

Recovery steps:
1. Read the security error message for the blocked command
2. Check if there's an equivalent allowed command
3. Review .claude-agent.yaml for extra_commands config
4. Do NOT try to bypass security - escalate instead
5. Document the command needed for human review

#### VALIDATION Errors
*Examples: Feature test failures, UI doesn't match spec*

Recovery steps:
1. Re-read the feature requirements in feature_list.json
2. Compare expected vs actual behavior
3. Take screenshots to document the discrepancy
4. Check for recent code changes that might have caused it
5. Fix the implementation, not the test requirements

### Recovery Attempt Tracking

When attempting recovery, track your attempts:

```markdown
## Error Recovery Log

Error: [error message]
Category: [LOGIC|NETWORK|etc.]
Type: [RETRY|MANUAL|FATAL|TIMEOUT]

Attempt 1: [what you tried]
Result: [outcome]

Attempt 2: [what you tried]
Result: [outcome]

Attempt 3: [what you tried]
Result: [outcome]

Final Status: [RESOLVED|ESCALATED|FAILED]
```

### When NOT to Retry

Do not retry when:
- The error message indicates a permanent condition
- You've already tried 3 times with the same approach
- The error is related to security or permissions
- The error indicates missing credentials or tokens
- The root cause is clearly code logic (fix first, then retry)

## Escalation

**When to escalate to human intervention:**
- After 3 failed recovery attempts
- When the error message is unclear or ambiguous
- When security modifications are needed
- When external service credentials are required
- When the error affects locked architecture components

**Escalation format:**
```markdown
## ERROR REQUIRES HUMAN INTERVENTION

**Error Type:** [RETRY|MANUAL|FATAL|TIMEOUT]
**Category:** [NETWORK|AUTH|LOGIC|etc.]
**Message:** [full error message]

**Recovery Attempts:**
1. [attempt and result]
2. [attempt and result]
3. [attempt and result]

**Suspected Cause:** [best hypothesis]
**Recommended Action:** [specific ask for human]
```

## Examples

### Good Error Recovery

```markdown
Error: npm install failed with EACCES

Classification: RESOURCE (file permission issue)
Type: MANUAL (needs elevated permission or directory change)

Attempt 1: Check npm cache permissions
Result: Cache directory owned by root

Attempt 2: Suggest using --prefix flag
Result: Works with different install location

Resolution: Added note to use npm --prefix ./node_modules install
```

### Avoid This Pattern

```markdown
Error: Something broke
Fix: Deleted and recreated everything

# Why this is bad:
# - No error classification
# - No understanding of root cause
# - Destructive action without analysis
# - Will likely happen again
```
