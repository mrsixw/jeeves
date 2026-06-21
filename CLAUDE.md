# Claude Instructions

## Project Overview
- **five-clis** is a batteries-included Python CLI template (named after Five Guys: burgers, shakes & fries → five CLI essentials).
- Built with Python and Click. Full infrastructure: themes, seasonal colours, caching, config files, XDG dirs, shell completions, auto-update checks, CI, release pipeline.
- Package structure: code in `src/fiveclis/`, tests in `tests/`.
- Use this as a GitHub template to scaffold new CLI apps.

## Project Structure
- `src/fiveclis/` — package source code
  - `cli.py` — Click entrypoint (replace greet logic with your own)
  - `ui.py` — Terminal themes, seasonal colour system (SEASONAL_PALETTES, PRIDE_RAINBOW, HOLI_RAINBOW, THEMES registry)
  - `config.py` — TOML configuration loader
  - `cache.py` — Generic TTL disk cache
  - `updater.py` — GitHub release update checker
  - `logger.py` — File logging setup
  - `xdg.py` — XDG base directory support
- `tests/` — pytest suite mirroring src modules
- `pyproject.toml` — project metadata, dependencies, tool config
- `VERSION` — static file containing the current version string
- `Makefile` — build, test, lint, format targets
- `utils/` — helper scripts for release management

## Environment
- Python >= 3.11
- Package manager: **uv** (not pip). Use `uv sync`, `uv run`, etc.

## Common Commands
- `make test` — run tests (`uv run pytest -v`)
- `make lint` — check linting and formatting
- `make format` — auto-fix lint and formatting
- `make build` — build a shiv executable

## Commit Messages
- Use Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`, `ci:`).

## Code Quality
- **Before every commit:** `make format && make lint && make test`
- stdout for data; stderr for progress/warnings/errors
- No bare `except Exception` — catch specific types
