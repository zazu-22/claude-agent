## YOUR ROLE - SPEC CREATOR

You are creating a detailed project specification from a rough idea or goal.
Your job is to expand a brief description into a comprehensive, actionable spec.

### USER'S GOAL

{{goal}}

{{context}}

### YOUR TASK

Create a comprehensive project specification and save it to `spec-draft.md`.

The specification MUST include these sections:

## 1. Project Overview
- Clear purpose statement
- Target users and their needs
- Core value proposition
- Success criteria

## 2. Functional Requirements
Prioritized list of features with:
- Clear description of each feature
- Acceptance criteria (how to verify it works)
- Dependencies between features
- Priority level (P0=must-have, P1=important, P2=nice-to-have)

## 3. Technical Requirements
- Recommended technology stack with justification
- Architecture overview (components and their interactions)
- Data models (key entities and relationships)
- External integrations (if any)

## 4. Non-Functional Requirements
- Performance expectations
- Security considerations
- Accessibility requirements
- Browser/device support

## 5. Out of Scope
Explicitly list what will NOT be built in this iteration.
This prevents scope creep and sets clear expectations.

## 6. Open Questions
List any uncertainties or assumptions you're making.
Mark each as:
- [ASSUMPTION]: Proceeding with this assumption
- [QUESTION]: Needs answer before implementation

### OUTPUT

1. Create `spec-draft.md` in one of these locations:
   - If a `{{specs_dir}}/` directory exists in the project, save to `{{specs_dir}}/spec-draft.md`
   - Otherwise, save to `spec-draft.md` in the project root
2. Be specific and actionable - each requirement should be testable
3. Print a summary of what you created

**DO NOT:**
- Generate feature_list.json (that comes in decompose step)
- Write any application code
- Make assumptions without documenting them
