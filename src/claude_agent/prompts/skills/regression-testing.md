# Regression Testing Skill

## Purpose

This skill provides patterns for testing previously implemented features to ensure
they still work correctly after new changes. Regression testing is critical to
prevent quality drift in long-running development sessions.

## When to Use

Use this skill when:
- Starting a new coding session after context window reset
- After implementing any new feature
- Before marking a feature as complete
- When the validator has reported regressions
- After refactoring code that affects multiple features

## Pattern

### Pre-Implementation Verification

Before implementing any new feature, verify that existing features still work:

1. **Identify Critical Path Features**
   - List features that the current work depends on
   - List features that share code with the current work
   - Prioritize testing the most interconnected features

2. **Execute Verification Tests**
   For each critical feature:
   ```
   a. Read the feature's test steps from feature_list.json
   b. Navigate to the relevant part of the application
   c. Execute the documented test steps
   d. Take a screenshot for evidence
   e. Record: PASS or FAIL with specific observations
   ```

3. **Document Results**
   ```markdown
   ## Regression Check - Session N

   | Feature # | Description | Status | Evidence |
   |-----------|-------------|--------|----------|
   | 5 | User login | PASS | Screenshot: login works |
   | 12 | Form validation | FAIL | Error messages not showing |
   ```

### Post-Implementation Verification

After implementing a feature:

1. **Test the New Feature**
   - Execute all test steps for the feature you just implemented
   - Verify edge cases mentioned in the feature description
   - Check for console errors or warnings

2. **Test Related Features**
   - Identify features that share components or state
   - Execute quick smoke tests on each
   - Document any issues found

3. **Fix Before Moving On**
   If regressions are found:
   ```
   1. Stop implementing new features
   2. Mark the regressed feature as "passes": false
   3. Fix the regression
   4. Re-test to confirm the fix
   5. Re-test the new feature
   6. Only then proceed to the next feature
   ```

### Visual Regression Patterns

Common visual issues to check:
- Text color and contrast
- Element alignment and spacing
- Responsive behavior
- Hover and focus states
- Loading states and transitions
- Error state displays

## Escalation

**When to escalate to human intervention:**
- Multiple features fail that were previously passing
- Root cause is unclear after 2-3 investigation cycles
- Fix for one regression causes another regression
- Feature requires changes to architecture lock files

**Escalation format:**
```markdown
## REGRESSION REQUIRES ATTENTION

**Affected Features:** #X, #Y, #Z
**Symptoms:** [specific behavior observed]
**Attempted Fixes:** [what was tried]
**Suspected Cause:** [best hypothesis]
**Recommended Action:** [suggestion for human]
```

## Examples

### Good Regression Test Documentation

```markdown
=== Regression Check Before Feature #15 ===

Testing Feature #3 (User login):
1. Navigated to /login
2. Entered test credentials
3. Clicked Login button
4. Verified redirect to dashboard
5. Screenshot captured: user_avatar_visible
Result: PASS

Testing Feature #8 (Dashboard charts):
1. Navigated to /dashboard
2. Waited for charts to load
3. Verified data displayed correctly
4. Screenshot captured: charts_rendered
Result: PASS

Regression check complete. Safe to proceed with Feature #15.
```

### Bad Regression Test Documentation (Avoid)

```markdown
Checked login - works
Checked dashboard - works
```

The bad example lacks evidence and specific observations, making it impossible
to trace issues later.
