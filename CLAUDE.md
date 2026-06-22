# Claude Instructions

## Project Overview
- **jeeves** is a Jenkins CI/CD butler CLI tool with a P.G. Wodehouse theme.
- Built with Python and Click. Full infrastructure: themes, seasonal colours, caching, config files, XDG dirs, shell completions, auto-update checks, CI, release pipeline.
- Package structure: code in `src/jeeves/`, tests in `tests/`.

## Project Structure
- `src/jeeves/` — package source code
  - `cli.py` — Click group entrypoint with `status`, `jobs`, `build`, `log`, `queue`, `cancel`, `nodes` subcommands
  - `jenkins.py` — Jenkins HTTP API client (`JenkinsClient`, `JenkinsError`)
  - `ui.py` — Terminal themes, seasonal colour system (SEASONAL_PALETTES, PRIDE_RAINBOW, HOLI_RAINBOW, THEMES registry)
  - `config.py` — TOML configuration loader; `get_jenkins_config()` extracts Jenkins connection settings
  - `cache.py` — Generic TTL disk cache
  - `updater.py` — GitHub release update checker
  - `logger.py` — File logging setup
  - `xdg.py` — XDG base directory support
- `tests/` — pytest suite mirroring src modules
- `pyproject.toml` — project metadata, dependencies, tool config
- `VERSION` — static file containing the current version string
- `Makefile` — build, test, lint, format targets
- `utils/` — helper scripts for release management

## Jenkins API Notes
- Jenkins HTTP API: append `/api/json` to any URL for JSON data; auth via HTTP Basic (username + API token)
- `GET /api/json` — server root (mode, nodeDescription, numExecutors, jobs)
- `GET /job/{name}/api/json` — job details
- `POST /job/{name}/build` — trigger build (no params)
- `POST /job/{name}/buildWithParameters?K=V` — trigger build with params
- `GET /job/{name}/lastBuild/consoleText` — console log (plain text, not JSON)
- `GET /queue/api/json` — build queue (items[])
- `POST /job/{name}/{build}/stop` — cancel a running build
- `GET /computer/api/json` — nodes/agents (computer[])

## Butler Voice
All output messages follow the Jeeves voice:
- Success: "Certainly, sir." / "Very good, sir."
- Error: "I'm afraid there's been a spot of bother, sir: {error}"
- Empty list: "The {thing} appears to be unoccupied at present, sir."
- Build triggered: "I shall dispatch '{job}' at once, sir."
- Build cancelled: "Consider build #{n} dismissed, sir."

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
