# Browser Testing Skill

## Purpose

This skill provides patterns for UI testing through browser automation. All feature
verification must be performed through actual UI interaction, not just API testing
or JavaScript evaluation shortcuts.

## When to Use

Use this skill when:
- Verifying feature implementation through the UI
- Testing user flows end-to-end
- Capturing screenshot evidence for feature completion
- Debugging visual or interaction issues
- Validating responsive behavior

## Pattern

### Test Execution Workflow

#### Step 1: Navigate and Wait

Always wait for the page to be fully loaded:

```
1. Navigate to the target URL
2. Wait for key elements to be visible
3. Take initial screenshot to verify state
```

**Wait Strategies:**
- Wait for specific element to appear (preferred)
- Wait for network requests to complete
- Never use fixed time delays unless absolutely necessary

#### Step 2: Interact Like a User

Test through actual UI interactions:

**DO:**
- Click buttons with visible text
- Fill form fields using input selectors
- Scroll to elements before interacting
- Use keyboard navigation where appropriate
- Wait after actions that trigger async operations

**DON'T:**
- Use JavaScript to set values directly
- Bypass form validation with code
- Click hidden elements
- Shortcut multi-step flows

#### Step 3: Verify Results

After each significant action:

1. Wait for expected state change
2. Verify visible indicators of success/failure
3. Check for error messages
4. Take screenshot for evidence
5. Check browser console for errors

### Selector Best Practices

**Priority order for selectors:**

1. **Test IDs** (best): `[data-testid="submit-btn"]`
2. **ARIA labels**: `[aria-label="Submit form"]`
3. **Form attributes**: `input[name="email"]`
4. **Semantic HTML**: `button[type="submit"]`
5. **Text content**: Contains "Submit"
6. **CSS classes** (avoid if possible): `.btn-primary`

**Avoid:**
- Complex XPath expressions
- Index-based selectors (`li:nth-child(3)`)
- Dynamically generated class names
- Selectors that depend on layout

### Screenshot Evidence Protocol

Take screenshots at key moments:

```markdown
## Screenshot Checklist

- [ ] Initial state (before interaction)
- [ ] After form fill (before submit)
- [ ] Success state (after completion)
- [ ] Error state (when testing failure cases)
- [ ] Mobile viewport (if responsive)
```

**Screenshot naming convention:**
```
feature_X_step_description.png
Examples:
- feature_5_login_form_filled.png
- feature_5_login_success.png
- feature_5_login_error_invalid.png
```

### Common Testing Patterns

#### Login Flow Testing

```
1. Navigate to /login
2. Wait for email input to be visible
3. Fill email field with test credentials
4. Fill password field
5. Screenshot: form filled state
6. Click login button
7. Wait for redirect OR error message
8. Screenshot: result state
9. Verify expected outcome (dashboard OR error)
```

#### Form Validation Testing

```
1. Navigate to form page
2. Leave required fields empty
3. Click submit
4. Verify validation messages appear
5. Screenshot: validation errors
6. Fill fields with valid data
7. Click submit
8. Verify success
9. Screenshot: success state
```

#### List/Table Data Testing

```
1. Navigate to list page
2. Wait for data to load (spinner disappears)
3. Verify expected items are visible
4. Screenshot: list with data
5. Test sorting (if applicable)
6. Test filtering (if applicable)
7. Test pagination (if applicable)
```

### Handling Async Operations

**For operations that take time:**

1. Look for loading indicators
2. Wait for loading indicator to disappear
3. OR wait for success element to appear
4. Set reasonable timeout (5-10 seconds max)
5. If timeout, check console for errors

**For real-time updates:**

1. Perform action in one tab/session
2. Verify update appears in another (if needed)
3. Check WebSocket/SSE connections if updates missing

### Visual Verification Checklist

Beyond functionality, verify visual quality:

- [ ] Text is readable (contrast, size)
- [ ] No overlapping elements
- [ ] Buttons are clickable (not covered)
- [ ] Forms align properly
- [ ] Responsive at different widths
- [ ] No console errors
- [ ] No broken images
- [ ] Loading states show correctly
- [ ] Error states are visible and clear

## Escalation

**When to escalate to human intervention:**
- Element is present but not interactable
- Consistent timeout waiting for elements
- Visual bugs that can't be fixed in code
- Mobile-specific issues requiring device testing
- Features requiring file upload from filesystem
- OAuth flows with external providers

**Escalation format:**
```markdown
## BROWSER TESTING BLOCKED

**Feature:** #X - [description]
**Blocker:** [what's preventing testing]

**What Was Tried:**
1. [attempt and result]
2. [attempt and result]

**Screenshots:**
- [path to relevant screenshots]

**Console Errors:**
```
[any relevant console output]
```

**Recommendation:**
[suggest manual testing steps for human]
```

## Examples

### Good Browser Test Documentation

```markdown
## Browser Test: Feature #12 - User Registration

### Setup
- URL: http://localhost:3000/register
- Test credentials: test+new@example.com / TestPass123!

### Test Steps
1. Navigate to /register
   - Screenshot: registration_form_initial.png
   - All fields visible: name, email, password, confirm

2. Fill form
   - Name: "Test User"
   - Email: test+new@example.com
   - Password: TestPass123!
   - Confirm: TestPass123!
   - Screenshot: registration_form_filled.png

3. Submit form
   - Clicked "Create Account" button
   - Waited for redirect
   - Screenshot: registration_success.png

4. Verification
   - Redirected to /dashboard
   - User name visible in header
   - Console: No errors

### Result: PASS
Feature #12 verified through browser automation.
```

### Bad Browser Test Documentation (Avoid)

```markdown
## Test Feature #12

Tested registration. It works.

### Result: PASS
```

The bad example lacks evidence, specific steps, and screenshots, making it
impossible to verify the test was actually performed correctly.
