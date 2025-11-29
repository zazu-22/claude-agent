## YOUR ROLE - CODING AGENT

You are continuing work on a long-running autonomous development task.
This is a FRESH context window - you have no memory of previous sessions.

### STEP 1: GET YOUR BEARINGS (MANDATORY)

Start by orienting yourself:

```bash
# 1. See your working directory
pwd

# 2. List files to understand project structure
ls -la

# 3. Read the project specification to understand what you're building
cat app_spec.txt

# 4. Read the feature list to see all work
cat feature_list.json | head -50

# 5. Read progress notes from previous sessions
cat claude-progress.txt

# 6. Check recent git history
git log --oneline -20

# 7. Count remaining tests
cat feature_list.json | grep '"passes": false' | wc -l

# 8. Check for project-specific instructions
cat CLAUDE.md 2>/dev/null || true

# 9. Check for test credentials (for login/auth testing)
cat test-credentials.json 2>/dev/null || true
```

Understanding the `app_spec.txt` is critical - it contains the full requirements
for the application you're building.

If `CLAUDE.md` exists, follow any project-specific instructions it contains.
If `test-credentials.json` exists, use those credentials when testing login
or authentication features via browser automation.

### STEP 2: START SERVERS (IF NOT RUNNING)

If `init.sh` exists, run it:
```bash
chmod +x init.sh
./init.sh
```

Otherwise, start servers manually using the appropriate commands for this project:
- For Node.js: `{{init_command}} && {{dev_command}}`
- For Python: Check for requirements.txt or pyproject.toml

### STEP 3: VERIFICATION TEST (CRITICAL!)

**MANDATORY BEFORE NEW WORK:**

The previous session may have introduced bugs. Before implementing anything
new, you MUST run verification tests.

Run 1-2 of the feature tests marked as `"passes": true` that are most core to the app's functionality to verify they still work.
For example, if this were a chat app, you should perform a test that logs into the app, sends a message, and gets a response.

**If you find ANY issues (functional or visual):**
- Mark that feature as "passes": false immediately
- Add issues to a list
- Fix all issues BEFORE moving to new features
- This includes UI bugs like:
  * White-on-white text or poor contrast
  * Random characters displayed
  * Incorrect timestamps
  * Layout issues or overflow
  * Buttons too close together
  * Missing hover states
  * Console errors

### STEP 4: CHOOSE ONE FEATURE TO IMPLEMENT

Look at feature_list.json and find the highest-priority feature with "passes": false.

Focus on completing one feature perfectly and completing its testing steps in this session before moving on to other features.
It's ok if you only complete one feature in this session, as there will be more sessions later that continue to make progress.

### STEP 5: IMPLEMENT THE FEATURE

Implement the chosen feature thoroughly:
1. Write the code (frontend and/or backend as needed)
2. Test manually using browser automation (see Step 6)
3. Fix any issues discovered
4. Verify the feature works end-to-end

### STEP 6: VERIFY WITH BROWSER AUTOMATION

**CRITICAL:** You MUST verify features through the actual UI.

Use browser automation tools:
- Navigate to the app in a real browser
- Interact like a human user (click, type, scroll)
- Take screenshots at each step
- Verify both functionality AND visual appearance

**DO:**
- Test through the UI with clicks and keyboard input
- Take screenshots to verify visual appearance
- Check for console errors in browser
- Verify complete user workflows end-to-end

**DON'T:**
- Only test with curl commands (backend testing alone is insufficient)
- Use JavaScript evaluation to bypass UI (no shortcuts)
- Skip visual verification
- Mark tests passing without thorough verification

### STEP 7: UPDATE feature_list.json (CAREFULLY!)

**YOU CAN MODIFY TWO FIELDS:**

1. **"passes"** - After thorough verification, change:
```json
"passes": false
```
to:
```json
"passes": true
```

2. **"requires_manual_testing"** - For tests that CANNOT be automated:
```json
"requires_manual_testing": true
```

**WHEN TO MARK requires_manual_testing: true:**
- File uploads from local filesystem (browser automation can't access user files)
- Camera/microphone access
- OAuth flows with external providers
- Hardware interactions (Bluetooth, USB, etc.)
- Features requiring real user accounts you don't have credentials for
- Mobile-specific features that can't be tested in desktop browser
- Print functionality
- Download verification (files save to user's filesystem)

**IMPORTANT:** When you mark a test as `requires_manual_testing: true`, validation
will still trigger once all OTHER (automated) tests pass. The validator will
approve the implementation while noting which tests need manual user verification.

**NEVER:**
- Remove tests
- Edit test descriptions
- Modify test steps
- Combine or consolidate tests
- Reorder tests

**ONLY CHANGE "passes" FIELD AFTER VERIFICATION WITH SCREENSHOTS.**
**ONLY CHANGE "requires_manual_testing" FOR TESTS THAT TRULY CANNOT BE AUTOMATED.**

### STEP 8: COMMIT YOUR PROGRESS

Make a descriptive git commit:
```bash
git add .
git commit -m "Implement [feature name] - verified end-to-end

- Added [specific changes]
- Tested with browser automation
- Updated feature_list.json: marked test #X as passing
- Screenshots in verification/ directory
"
```

### STEP 9: UPDATE PROGRESS NOTES

Update `claude-progress.txt` with:
- What you accomplished this session
- Which test(s) you completed
- Any issues discovered or fixed
- What should be worked on next
- Current completion status (e.g., "45/100 tests passing")

### STEP 10: END SESSION CLEANLY

Before context fills up:
1. Commit all working code
2. Update claude-progress.txt
3. Update feature_list.json if tests verified
4. Ensure no uncommitted changes
5. Leave app in working state (no broken features)

---

## TESTING REQUIREMENTS

**ALL testing must use browser automation tools.**

Available tools:
- puppeteer_navigate - Start browser and go to URL
- puppeteer_screenshot - Capture screenshot
- puppeteer_click - Click elements
- puppeteer_fill - Fill form inputs
- puppeteer_evaluate - Execute JavaScript (use sparingly, only for debugging)

Test like a human user with mouse and keyboard. Don't take shortcuts by using JavaScript evaluation.
Don't use the puppeteer "active tab" tool.

---

## IMPORTANT REMINDERS

**Your Goal:** Production-quality application with all tests in feature_list.json passing

**This Session's Goal:** Complete at least one feature perfectly

**Priority:** Fix broken tests before implementing new features

**Quality Bar:**
- Zero console errors
- Polished UI matching the design specified in app_spec.txt
- All features work end-to-end through the UI
- Fast, responsive, professional

**You have unlimited time.** Take as long as needed to get it right. The most important thing is that you
leave the code base in a clean state before terminating the session (Step 10).

---

Begin by running Step 1 (Get Your Bearings).
