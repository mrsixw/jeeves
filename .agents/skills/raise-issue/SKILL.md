---
name: raise-issue
description: Raise a detailed, structured issue on GitHub. Gathers context, builds reproduction steps, expected outcomes, and acceptance criteria.
---

# Raise Issue Skill

Standardized procedure to generate and raise a high-quality issue on GitHub for this project.

## When to use this skill
- Use this skill when you identify a bug, a required enhancement, or a new feature that does not have an active GitHub issue yet.
- **A GitHub issue MUST exist before any coding work begins.** Always use this skill first.

## How to use it

### Steps

1. **Analyze the problem or requirement:**
   - For bugs: exact error tracebacks, terminal output, reproduction commands, and conditions.
   - For features: proposed goals, user benefit, CLI flags or API methods, and expected output.

2. **Generate a structured description:**

   #### Bug Issues:
   ```markdown
   ## Problem
   [What is failing and why it is wrong. Include tracebacks.]

   ## Steps to reproduce
   \`\`\`bash
   [Exact command to trigger the bug]
   \`\`\`

   ## Expected behaviour
   [What should happen.]

   ## Actual behaviour
   [What is currently happening.]

   ## Suspected Cause (optional)
   [Specific file, function, or commit suspected.]
   ```

   #### Feature / Enhancement Issues:
   ```markdown
   ## Summary
   [High-level explanation of the feature and what user problem it solves.]

   ## Proposed Solution
   [How it should be implemented — CLI subcommands, API methods, config keys.]

   ## Examples
   \`\`\`bash
   jeeves whoami
   👤 Authenticated as: alice (Alice Smith)
   \`\`\`

   ## Acceptance Criteria
   - [ ] [Behaviour under condition A]
   - [ ] [Error handling for condition B]
   - [ ] [Tests added]
   - [ ] [make format && make lint && make test all pass]
   ```

3. **Verify the title:**
   - Keep it imperative and natural. No conventional commit prefixes (`feat:`, `fix:`).
   - Example: "Add whoami command for auth/connectivity debugging"

4. **Create the issue:**
   ```bash
   gh issue create --repo mrsixw/jeeves --title "<title>" --body "<body>"
   ```

5. **Confirm to the user:** Report the issue URL and number.
