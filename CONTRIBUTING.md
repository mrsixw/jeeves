# Contributing to five-clis

## Development setup

```bash
git clone https://github.com/mrsixw/five-clis
cd five-clis
uv sync --extra dev
```

## Before every commit

Run all three in order — no exceptions:

```bash
make format   # auto-fix formatting
make lint     # must exit clean
make test     # all tests must pass
```

## Conventional commits

Use `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`, `ci:` prefixes.

## Workflow

- Every branch must reference a GitHub issue
- Branch format: `issue-<N>_short_description`
- One issue = one branch = one PR
- PRs must include `Closes #N` in the body

## Code style

- `ruff` for linting and import sorting
- `black` for formatting (88-char line length)
- No bare `except Exception` — catch specific exception types
- stdout for data output; stderr for progress/warnings/errors
