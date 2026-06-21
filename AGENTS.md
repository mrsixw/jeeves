# Agent Instructions

## Project Overview
- **five-clis** is a batteries-included Python CLI template.
- Built with Python and Click. Infrastructure: themes, seasonal colours, caching, config files, XDG dirs, shell completions, auto-update checks, CI, release pipeline.
- Package: `src/fiveclis/`. Tests: `tests/`. Package manager: **uv**.

## Common Commands
- `make test` — run tests
- `make lint` — check linting and formatting
- `make format` — auto-fix lint and formatting

## Commit Messages
- Use Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`, `ci:`).

## Code Quality
- **Before every commit:** `make format && make lint && make test`
- stdout for data; stderr for progress/warnings/errors
- No bare `except Exception`
