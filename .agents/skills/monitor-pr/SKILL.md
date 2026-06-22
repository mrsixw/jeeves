---
name: monitor-pr
description: Monitor the CI checks status of a Pull Request on GitHub, parse logs on failure, and address any non-passing checks.
---

# Monitor PR Skill

Standardized procedure to track pull request CI checks on GitHub and address any test or linting failures.

## When to use this skill
- Use this skill after raising a pull request (e.g., using `raise-pr`), or when the user requests to check, monitor, or track the CI/test status of an active PR.

## How to use it

### Steps

1. **Check CI checks status:**
   ```bash
   gh pr checks
   ```

2. **Wait for completion (if pending):**
   If any checks are marked as `pending`:
   - Set a one-shot wakeup timer using the `schedule` tool (e.g., 120 seconds).
   - Stop calling tools and yield back control while the timer is running.
   - Do NOT run a shell `sleep` loop or poll continuously.

3. **Handle successful runs:**
   If all checks pass, confirm to the user that CI is green and the PR is ready for review.

4. **Diagnose and fix failures:**
   If any check fails:
   - **View failing logs:**
     ```bash
     gh run list --branch <current-branch> --limit 1
     gh run view <run-id> --log-failed
     ```
   - **Reproduce locally:**
     - Test failures: `make test` (or `uv run pytest -k <failing_test>`)
     - Lint/format: `make lint` or `make format`
   - **Fix the issue**, then run the full gate: `make format && make lint && make test`
   - **Push the fix:**
     ```bash
     git add <files>
     git commit -m "fix: address failing CI check"
     git push
     ```
   - **Resume monitoring:** Go back to Step 1.
