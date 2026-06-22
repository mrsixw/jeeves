# Agent Instructions

## Project Overview
- **jeeves** is a Jenkins CI/CD butler CLI tool with a P.G. Wodehouse theme.
- Built with Python and Click. Infrastructure: themes, seasonal colours, caching, config files, XDG dirs, shell completions, auto-update checks, CI, release pipeline.
- Package: `src/jeeves/`. Tests: `tests/`. Package manager: **uv**.

## Common Commands
- `make test` — run tests
- `make lint` — check linting and formatting
- `make format` — auto-fix lint and formatting

## Tone and Personality
This project is inspired by P.G. Wodehouse's Jeeves — efficient, unflappable, and faintly wry — but kept light on the formality. Use the butler voice throughout, but avoid addressing the user as "sir" in every routine message; reserve it for error messages where the apologetic tone is most natural.

### Butler Voice
**Success / info messages** — always include an emoji:
- Status OK: `"✅ Certainly. {desc} is in fine form."`
- Jobs list: `"📋 Allow me to present the staff roster."`
- Build triggered: `"🚀 I shall dispatch '{job}' at once. Very good."`
- Build cancelled: `"🛑 Consider build #{n} of '{job}' dismissed."`
- Queue header: `"⏳ The pending requests."`
- Nodes header: `"🏠 The household staff."`
- Whoami: `"👤 Authenticated as: {id} ({fullName})"`

**Empty results** — whimsical, never just "none found":
- No jobs: `"The staff roster appears entirely bare. Jenkins would seem to have no positions filled at present."`
- Empty queue: `"The queue stands quite empty. Jenkins is evidently at leisure — a rare and precious state of affairs."`
- No nodes: `"The household staff appears to have entirely absented themselves. One trusts they haven't all handed in their notice."`

**Errors** — route through `_butler_error(msg, colour)`, prefixed with `🎩`, sent to stderr. Errors retain "sir" for the apologetic butler tone:
- Connection failure: `"I'm afraid the Jenkins estate at {url} appears to be quite unreachable, sir. The line seems entirely dead."`
- 403 Forbidden: `"Jenkins has turned us away at the door, sir. A 403 — most irregular. One suspects our credentials may not be in order."`
- 404 Not Found: `"I searched the premises most thoroughly, sir, but the requested resource could not be found. A 404. It has vanished like Bertie's good intentions."`
- Other HTTP error: `"Jenkins appears to be in a considerable state of disarray, sir. A {code}. Perhaps a restorative cup of tea is called for."`
- Generic fallback: `"I'm afraid there's been a spot of bother, sir: {msg}"`

## Automated Workflows
This repository provides standardized automated workflows for managing issues. All agents must refer to and execute these exact steps:
- **Start work on an issue:** Follow the steps defined in [.agents/skills/start-issue/SKILL.md](.agents/skills/start-issue/SKILL.md).
- **Finish work on an issue:** Follow the steps defined in [.agents/skills/finish-issue/SKILL.md](.agents/skills/finish-issue/SKILL.md).
- **Raise a Pull Request:** Follow the steps defined in [.agents/skills/raise-pr/SKILL.md](.agents/skills/raise-pr/SKILL.md).
- **Monitor Pull Request CI:** Follow the steps defined in [.agents/skills/monitor-pr/SKILL.md](.agents/skills/monitor-pr/SKILL.md).
- **Raise a new issue:** Follow the steps defined in [.agents/skills/raise-issue/SKILL.md](.agents/skills/raise-issue/SKILL.md).

## Commit Messages
- Use Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`, `ci:`).

## Code Quality
- **Before every commit:** `make format && make lint && make test`
- stdout for data; stderr for progress/warnings/errors
- No bare `except Exception`
