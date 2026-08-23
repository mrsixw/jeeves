# Claude Instructions

## Project Overview
- **jeeves** is a Jenkins CI/CD butler CLI tool with a P.G. Wodehouse theme.
- Built with Python and Click. Full infrastructure: themes, seasonal colours, caching, config files, XDG dirs, shell completions, auto-update checks, CI, release pipeline.
- Package structure: code in `src/jeeves/`, tests in `tests/`.

## Project Structure
- `src/jeeves/` — package source code
  - `cli.py` — Click group entrypoint with `status`, `queue`, `whoami`, `swatch` commands and `job`, `build`, `node` noun groups mirroring the Jenkins hierarchy (hidden deprecated aliases keep the old flat commands working for one release)
  - `jenkins.py` — Jenkins HTTP API client (`JenkinsClient`, `JenkinsError`, `normalize_jenkins_path`)
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
- `POST /job/{name}/buildWithParameters` — trigger build with params (send as form body, not query string)
- `GET /job/{name}/lastBuild/consoleText` — console log (plain text, not JSON)
- `GET /queue/api/json` — build queue (items[])
- `POST /job/{name}/{build}/stop` — cancel a running build
- `GET /job/{name}/{build}/api/json` — build detail; includes `culprits[]` and SCM changes (`changeSets[]` on pipeline builds, single `changeSet` on freestyle)
- `GET /computer/api/json` — nodes/agents (computer[])
- `GET /me/api/json` — currently authenticated user (id, fullName)
- `GET /crumbIssuer/api/json` — CSRF crumb; fetch before first POST, silently skip if unavailable
- Nested jobs: encode `folder/job` as `job/folder/job/job` in URL paths (use `normalize_jenkins_path`)

## Tone and Personality
This project is inspired by P.G. Wodehouse's Jeeves — efficient, unflappable, and faintly wry — but kept light on the formality. Use the butler voice throughout. Two hard rules:
- **Every** Jeeves-voiced message — success, info, empty state, and error — leads with a single emoji followed by **one** space (never a double space).
- Avoid addressing the user as "sir" in routine (success/info/empty) messages; reserve it for errors, and use it **at most once** per message.

### Butler Voice
**Success / info messages** — always include an emoji:
- Status OK: `"✅ Certainly. {desc} is in fine form."`
- Jobs list: `"📋 Allow me to present the staff roster."`
- Build triggered: `"🚀 I shall dispatch '{job}' at once. Very good."`
- Build cancelled: `"🛑 Consider build #{n} of '{job}' dismissed."`
- Queue header: `"⏳ The pending requests."`
- Nodes header: `"🏠 The household staff."`
- Whoami: `"👤 Authenticated as: {id} ({fullName})"`

**Empty results** — whimsical, never just "none found"; always lead with an emoji:
- No jobs: `"🗒️ The staff roster appears entirely bare. Jenkins would seem to have no positions filled at present."`
- Empty queue: `"😴 The queue stands quite empty. Jenkins is evidently at leisure — a rare and precious state of affairs."`
- No nodes: `"🚪 The household staff appears to have entirely absented themselves. One trusts they haven't all handed in their notice."`

**Errors** — route through `butler_error(msg, colour)`, prefixed with `🎩`, sent to stderr. Errors retain "sir" for the apologetic butler tone:
- Connection failure: `"I'm afraid the Jenkins estate at {url} appears to be quite unreachable, sir. The line seems entirely dead."`
- 403 Forbidden: `"Jenkins has turned us away at the door, sir. A 403 — most irregular. One suspects our credentials may not be in order."`
- 404 Not Found: `"I searched the premises most thoroughly, sir, but the requested resource could not be found. A 404. It has vanished like Bertie's good intentions."`
- Other HTTP error: `"Jenkins appears to be in a considerable state of disarray, sir. A {code}. Perhaps a restorative cup of tea is called for."`
- Generic fallback: `"I'm afraid there's been a spot of bother, sir: {msg}"`

## Work Items
- **A GitHub issue MUST exist before any work begins.** If the user requests a change and no issue exists yet, create one (or ask the user to create one) before starting implementation. Every branch, commit, and PR must reference an issue number. *Exception*: refinements, feedback iterations, or trivial tweaks on in-flight/undelivered feature branches do not require raising new issues; make changes directly on the active branch. If unsure whether to raise a new issue or continue on the current branch, always pause and ask the user first.
- Use the `raise-issue` skill to create a properly structured issue, and `start-issue` to branch off it.

## Automated Workflows
This repository provides standardized automated workflows for managing issues. All agents must refer to and execute these exact steps:
- **Start work on an issue:** Follow the steps defined in [.agents/skills/start-issue/SKILL.md](.agents/skills/start-issue/SKILL.md).
- **Finish work on an issue:** Follow the steps defined in [.agents/skills/finish-issue/SKILL.md](.agents/skills/finish-issue/SKILL.md).
- **Raise a Pull Request:** Follow the steps defined in [.agents/skills/raise-pr/SKILL.md](.agents/skills/raise-pr/SKILL.md).
- **Monitor Pull Request CI:** Follow the steps defined in [.agents/skills/monitor-pr/SKILL.md](.agents/skills/monitor-pr/SKILL.md).
- **Raise a new issue:** Follow the steps defined in [.agents/skills/raise-issue/SKILL.md](.agents/skills/raise-issue/SKILL.md).

## Environment
- Python >= 3.11
- Package manager: **uv** (not pip). Use `uv sync`, `uv run`, etc.

## Common Commands
- `make test` — run tests (`uv run pytest -v`)
- `make lint` — check linting and formatting
- `make format` — auto-fix lint and formatting
- `make build` — build a shiv executable

## Module API contract
- A leading `_` means "internal to this module". Anything a sibling module
  imports must not have one, and must appear in that module's `__all__`.
- Every module in `src/jeeves/` declares `__all__`. Add new public names to it.
- Reach other modules through their public names only. If you need something a
  module keeps private, widen that module's API deliberately — rename it and add
  it to `__all__` — rather than reaching past the underscore. A private name you
  had to import was never really private.
- The same applies to third-party libraries: depend on their documented API, not
  on internals that can change in a patch release.
- `tests/test_public_api.py` enforces the first two. Tests may still reach into
  the internals of the module they test — that boundary is not policed.

## Commit Messages
- Use Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`, `ci:`).

## Code Quality
- **Before every commit:** `make format && make lint && make test`
- stdout for data; stderr for progress/warnings/errors
- No bare `except Exception` — catch specific types
