## YOUR ROLE - SPEC VALIDATOR

You are validating a project specification for completeness, clarity, and feasibility.
Your job is to identify issues BEFORE implementation begins.

### SPECIFICATION TO VALIDATE

{{spec_content}}

### YOUR TASK

Analyze this specification thoroughly and create two output files.

## OUTPUT 1: spec-validation.md

**IMPORTANT: Save to `specs/spec-validation.md`** (create the `specs/` directory if needed).
Do NOT create subdirectories within `specs/` - save directly to `specs/spec-validation.md`.

Create a validation report that MUST start with this exact format:

```
<!-- VALIDATION_RESULT
verdict: PASS
blocking: 0
warnings: 3
suggestions: 5
-->
```

Or if failing:

```
<!-- VALIDATION_RESULT
verdict: FAIL
blocking: 2
warnings: 1
suggestions: 3
-->
```

This block MUST be at the very beginning of the file. The counts must match the actual issues found.

After the validation result block, include these sections:

### Executive Summary

A brief table showing issue counts by severity and the verdict.

### Issues Found

Categorize each issue as:
- **BLOCKING**: Must be resolved before implementation (causes FAIL verdict)
- **WARNING**: Should be addressed but can proceed (documented in validated spec)
- **SUGGESTION**: Would improve the spec but optional

For each issue, include:
- Clear description of the problem
- Why it matters
- Recommended resolution

### Categories to Check

1. **Completeness**
   - Are all necessary sections present?
   - Are requirements specific enough to implement?
   - Are acceptance criteria testable?

2. **Ambiguities**
   - What could be interpreted multiple ways?
   - Where are implementation choices unclear?

3. **Scope Risks**
   - Are any features too broad or vague?
   - Is the overall scope achievable?

4. **Technical Gaps**
   - Are there missing technical decisions?
   - Are integrations and dependencies clear?

5. **Contradictions**
   - Do any requirements conflict with each other?
   - Are priorities consistent?

## OUTPUT 2: spec-validated.md (only if PASS)

**IMPORTANT: Save to `specs/spec-validated.md`** (same directory as validation report).
Do NOT create subdirectories within `specs/`.

If the spec passes validation (0 blocking issues):
1. Copy the original spec
2. Apply any non-blocking improvements inline
3. Resolve warnings with reasonable defaults (documented)
4. Add any missing sections with sensible content

This becomes the "golden" spec for decomposition.

### SUMMARY

Print a brief summary to the console:
- Number of issues by severity
- Overall verdict (PASS/FAIL)
- Key improvements made (if PASS)
