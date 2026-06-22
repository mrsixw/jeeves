---
name: raise-pr
description: Generate a detailed pull request body and create/update a PR on GitHub. Gathers workspace changes, updates the PR body dynamically, and posts update comments to capture a historical paper trail.
---

# Raise PR Skill

Standardized procedure to generate, submit, and dynamically update a detailed pull request on GitHub for this project.

## When to use this skill
- Use this skill when you have completed work or made additional updates on an issue branch, run all verification checks, and are ready to create or update a GitHub Pull Request for the active branch.

## How to use it

### Steps for Creating a Pull Request

1. **Analyze workspace changes:**
   Review your local git changes, commit history, and test outcomes to collect all context:
   - Identify which files were created, modified, or deleted.
   - Collect the exact names of any new unit tests added (e.g., in `tests/test_*.py`).
   - Identify the linked GitHub issue number from your branch name (`issue-<N>_...`).

2. **Generate a detailed PR body:**
   Construct a pull request body using the standard template below. Be specific — avoid generic one-sentence summaries.

   #### Template Format:
   ```markdown
   ## Summary

   - **[Brief feature description]**: [Explain the high-level intent].
   - **Key Changes**:
     - Detail the specific classes, functions, or files modified (e.g., in `src/jeeves/`).
     - List any new CLI subcommands, config keys, or API methods introduced.
     - List new files or directories added.

   ## Test plan

   - [x] `make format && make lint && make test` passes.
   - [x] **[Specific unit tests added]**:
     - `test_func_a` — verifies [intent].
     - `test_func_b` — verifies [intent].
   - [x] **Manual Verification**:
     - Verify CLI execution (e.g., `uv run jeeves --version` runs cleanly).

   Closes #<issue-number>

   🤖 Generated with [Claude Code](https://claude.com/claude-code)
   ```

3. **Verify the PR title format:**
   `#<issue-number>: <description>`
   Example: `#4: Add whoami command for auth/connectivity debugging`

4. **Create the PR using the GitHub CLI:**
   ```bash
   gh pr create --title "#<issue-number>: <description>" --body "<body>"
   ```

5. **Confirm to the user:** Report the PR URL and a summary of what was submitted.

---

### Steps for Updating a Pull Request

If a PR is already open for the current branch:

1. **Regenerate the PR body** covering all changes across the full branch, then update it:
   ```bash
   gh pr edit --body "<regenerated-body>"
   ```

2. **Post an update comment** summarising what changed in this push:
   ```bash
   gh pr comment --body "### Update: [Brief Description]

   - **What's New**: [Detail the latest additions/fixes].
   - **Verification**: [Tests run or added in this update]."
   ```
