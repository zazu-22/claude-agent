# Architecture Verification Skill

## Purpose

This skill provides patterns for verifying that implementation plans and code changes
comply with locked architecture constraints. Architecture lock files prevent drift
by establishing invariants that must not be violated without explicit approval.

## When to Use

Use this skill when:
- Starting implementation of a new feature
- Making changes that affect API contracts
- Modifying data models or schemas
- Adding new dependencies or patterns
- After receiving architecture deviation warnings

## Pattern

### Pre-Implementation Verification

Before writing any implementation code, verify your plan against architecture lock files:

#### Step 1: Identify Relevant Constraints

Read the architecture files and identify which constraints apply:

```bash
# Check if architecture files exist
ls specs/architecture/

# Read relevant files
cat specs/architecture/contracts.yaml
cat specs/architecture/schemas.yaml
cat specs/architecture/decisions.yaml
```

#### Step 2: Contracts Verification

For each endpoint or API your feature will use or implement:

```markdown
## Contracts Check

Feature: #X - [description]

Relevant contracts from contracts.yaml:
- Contract: [name]
  Endpoint: [path and method]
  My plan: [how I'll use/implement it]
  Status: COMPATIBLE / DEVIATION REQUIRED

Deviation details (if any):
- [specific change needed]
- [why existing contract is insufficient]
```

**Contract Violation Indicators:**
- Changing an existing endpoint's path or method
- Removing required request fields
- Changing response field types
- Adding breaking changes to existing contracts

**Not Violations (Compatible Evolution):**
- Adding new optional request fields
- Adding new response fields
- Adding new endpoints to existing contracts

#### Step 3: Schemas Verification

For each data model your feature will create or modify:

```markdown
## Schemas Check

Feature: #X - [description]

Relevant schemas from schemas.yaml:
- Schema: [name]
  Fields used: [list fields]
  My plan: [how I'll use/modify it]
  Status: COMPATIBLE / DEVIATION REQUIRED

Deviation details (if any):
- [specific change needed]
- [why existing schema is insufficient]
```

**Schema Violation Indicators:**
- Changing field types
- Removing required fields
- Changing validation constraints
- Renaming fields

**Not Violations (Compatible Evolution):**
- Adding new optional fields
- Adding new schemas
- Using existing schemas as documented

#### Step 4: Decisions Verification

For each architectural decision that might constrain your implementation:

```markdown
## Decisions Check

Feature: #X - [description]

Relevant decisions from decisions.yaml:
- Decision: DR-XXX
  Topic: [topic]
  Constraints: [list constraints_created]
  My plan: [how I'll honor the constraints]
  Status: COMPLIANT / NEEDS DEVIATION

Violation details (if any):
- Constraint: [the constraint]
- My need: [why I can't comply]
```

### Handling Deviations

When your implementation requires changing locked architecture:

1. **STOP** - Do not proceed with implementation
2. **Document** the deviation in claude-progress.txt:
   ```markdown
   ARCHITECTURE DEVIATION DETECTED:
   - Feature: #X
   - Deviation type: [contract/schema/decision]
   - Specific conflict: [details]
   - Reasoning: [why change is needed]
   ```
3. **Mark Feature as Blocked** in feature_list.json:
   ```json
   {
     "blocked": true,
     "blocked_reason": "Requires changing DR-XXX constraint"
   }
   ```
4. **Move to Next Feature** - Do not attempt to implement blocked features

### Decision Record Protocol

When making NEW architectural decisions during implementation (not deviations):

```markdown
## New Architectural Decision

Decision ID: DR-YYYYMMDD-XXX
Topic: [what was being decided]
Choice: [what was chosen]
Alternatives Considered:
- [option A] - [why rejected]
- [option B] - [why rejected]
Rationale: [why this choice was made]
Constraints Created:
- [constraint 1]
- [constraint 2]
Affects Features: [list of feature indices]
```

Append this to specs/architecture/decisions.yaml.

## Escalation

**When to escalate to human intervention:**
- Implementation requires modifying locked contracts
- Implementation requires changing schema field types
- Implementation conflicts with explicit decision constraints
- Multiple features are blocked by the same constraint

**Escalation format:**
```markdown
## ARCHITECTURE DEVIATION REQUIRES APPROVAL

**Feature:** #X - [description]
**Deviation Type:** [Contract/Schema/Decision]
**Current Lock:**
[quote the exact constraint from lock files]

**Required Change:**
[describe what needs to change]

**Impact Assessment:**
- Affected features: [list]
- Affected contracts/schemas: [list]
- Breaking changes: [yes/no, details]

**Recommendation:**
[suggest how to resolve - update lock files, redesign feature, etc.]
```

## Examples

### Good Architecture Verification

```markdown
## Architecture Verification - Feature #15

### Contracts Check
Contract: user_auth
- POST /api/auth/login - Using as documented - COMPATIBLE
- POST /api/auth/register - Need to add optional 'phone' field - COMPATIBLE (additive)

### Schemas Check
Schema: User
- Adding 'phone' field (optional) - COMPATIBLE
- email, password unchanged - COMPATIBLE

### Decisions Check
DR-001: JWT authentication required
- My implementation uses JWT as specified - COMPLIANT
DR-003: All validation via Zod
- Using Zod for phone number validation - COMPLIANT

**Result:** Proceeding with implementation. No deviations detected.
```

### Architecture Deviation Example

```markdown
## Architecture Verification - Feature #23

### Contracts Check
Contract: payment_api
- PUT /api/payments/{id} - DEVIATION REQUIRED
  Current: Request requires 'amount' field
  Needed: Want to allow omitting 'amount' for partial updates

### Resolution
Marking Feature #23 as BLOCKED.
Reason: Requires changing required field to optional in contracts.yaml

Adding to blocked features and moving to Feature #24.
```
