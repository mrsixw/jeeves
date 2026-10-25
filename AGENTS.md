# Agent Instructions

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
- `tests/` — pytest suite mirroring src modules (mocked; never hits the network)
- `tests/e2e/` — behaviour-driven end-to-end suite: Gherkin scenarios driving
  the built zipapp as a subprocess. See `docs/design/testing.md`
- `pyproject.toml` — project metadata, dependencies, tool config
- `VERSION` — static file containing the current version string
- `Makefile` — build, test, lint, format targets
- `utils/` — helper scripts for release management and CI guards

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

### Lockable Resources plugin
Not base Jenkins — the `lockable-resources` plugin, handled in `src/jeeves/lockable.py`.
Everything hangs off the `/lockable-resources/` root action. Every mutator is `@RequirePOST`,
takes a **single** resource (the parameter is `resource`, no list support), and answers by
forwarding to the previous page — so the status code is the only meaningful part of the reply.
- `GET /lockable-resources/api/json` — the whole register (`resources[]`)
- `POST /lockable-resources/reserve` — form `resource`, optional `reason`; perm RESERVE
- `POST /lockable-resources/unreserve` — form `resource`; perm RESERVE, and the caller must hold it or be an administrator
- `POST /lockable-resources/unlock`, `/reset` — form `resource`; perm UNLOCK
- `POST /lockable-resources/createResource` — form `name`, `description`, `labels` (space-separated); perm CONFIGURE; 409 if it exists
- `POST /lockable-resources/deleteResource` — form `resource`; perm CONFIGURE; 423 if the resource is not free
- **A 404 is ambiguous on every mutator.** With the plugin absent there is no
  `/lockable-resources/reserve` either, so Jenkins answers exactly as it does for a resource that
  is not on the register. Probe `GET /lockable-resources/api/json` to settle it: a 404 there means
  the plugin is missing; otherwise a 404 from `reserve`/`unreserve`/`unlock`/`reset` means the
  resource is unknown, while a 404 from `createResource`/`deleteResource` means the plugin is too
  old — those two are `@Restricted(NoExternalUse.class)` upstream and absent from older releases.
- `unreserve`, `unlock` and `reset` **read the resource before posting**, because the plugin
  answers **200 whether or not there was anything to do** — so a blind POST would have us claim
  work we did not perform. Reading first also means an absent resource is reported as unknown
  rather than as one already in good order.
- Test `reservedBy`, not `free`, when deciding whether there is a reservation to release: a
  resource locked by a build is not free yet carries no reservation.
- A **403** from `unreserve` is kept as a race guard only — the reservation being dropped between
  our read and our POST. Earlier notes here claimed the plugin 403s when nobody holds the
  resource; it does not, on 1576.v217259b_f9976. The end-to-end suite caught jeeves reporting a
  release it had not performed, which is the kind of wire assumption only a real plugin settles.
- Out of scope: `/lockable-resources/remote/v1/`, a heartbeat-driven lock-holding REST protocol
  for long-lived external clients.

### JUnit plugin
Not base Jenkins — `junit`, handled in `src/jeeves/junit.py`.
- `GET /job/x/N/testReport/api/json` — `TestResult`: `passCount`, `failCount`, `skipCount`,
  `duration` (seconds, float), `suites[name,cases[className,name,status,duration,age,errorDetails]]`.
  **Always pass a `tree`**: cases export `stdout`/`stderr`, which can be megabytes each.
- Case `status` is the plugin's enum: `PASSED`, `SKIPPED`, `FAILED`, `FIXED`, `REGRESSION`. The
  failing ones are `FAILED` and `REGRESSION`; `age` is builds failing in a row.
- Multi-configuration builds expose an `AggregatedTestResultAction` at the same URL instead:
  `childReports[child[fullDisplayName,url],result[…same fields…]]`. Ask for both in one `tree`.
- **A 404 on `testReport` is ambiguous**: no results published, or plugin absent. Only
  `GET /pluginManager/api/json?tree=plugins[shortName,active]` settles it, and that needs
  Overall/SystemRead — so ask it on the error path only, and report "undetermined" on a 403.

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
- `make test` — run the mocked suites (`uv run pytest -v`); excludes e2e
- `make bats` — run the shell script tests (`npx --yes bats tests/bats`)
- `make e2e` — build the zipapp, then run the end-to-end suite against it
- `make e2e-offline` — the e2e scenarios that need no container
- `make lint` — check linting and formatting (includes `shellcheck` and `spell`)
- `make shellcheck` — static analysis for every shell source, the same pinned
  `shellcheck` version CI runs
- `make spell` — spell check, the same `typos` version CI runs
- `make format` — auto-fix lint and formatting
- `make build` — build a shiv executable

## Testing expectations
**Every change to behaviour ships with tests in both layers.** They are doing
different jobs:

- **Unit tests carry the coverage.** `tests/` is where breadth lives — every
  branch, every flag permutation, every error path, the output shapes.
  Fixtures are free and no process is spawned, so this is the cheap place to
  be exhaustive.
- **End-to-end scenarios do the validation.** `tests/e2e/features/` proves the
  thing actually works: the real binary, real exit codes, the real stdout and
  stderr file descriptors, and a wire format Jenkins genuinely accepts. A new
  command wants at least one scenario walking its happy path, plus one for any
  contract a unit test cannot see — an exit code, a stream split, something
  touching disk, a guard firing before any network call.

Shell scripts have their own suite, `tests/bats/`, and the same expectation
applies: touch a script, cover the change, and run `make bats`.

Some overlap between the layers is expected and fine; the same behaviour being
covered in unit and validated end to end is the point, not waste. What does not
belong end to end is *breadth* — a scenario per flag permutation buys little
and costs a process spawn, or a container boot, on every run.

Not every scenario needs Jenkins. `tests/e2e/features/cli_contract.feature`
runs container-free (`make e2e-offline`) and is the right home for anything
provable without a server — guards that fire before any network call,
packaging, completions, config handling. Reach for the container only when the
assertion is about what Jenkins itself accepts or returns.

A pure refactor with no user-visible change may leave the scenarios alone. If
you add a user-facing behaviour and no scenario, say in the PR description why.

### Which layer am I writing?
**If it fakes any part of the system under test, it is a unit test** — it
belongs in `tests/`, not `tests/e2e/`. Faking means `monkeypatch`, but equally
`requests-mock` or `CliRunner`. `tests/e2e/` drives the built binary as a real
subprocess, which is the only layer that sees true process exit codes, the real
stdout and stderr file descriptors, and the zipapp's own packaging.

### Testing the shell scripts
- `tests/bats/` covers `install.sh` and everything in `utils/`. Each test runs
  the real script as a subprocess with `gh`, `git`, `curl`, `tar`, `install`
  and `python3` stubbed on `PATH`, and `HOME` redirected into a temporary
  directory. Offline, and safe to run anywhere.
- Those stubs are faking, by the rule above, which is why this suite lives
  under `tests/` and not `tests/e2e/`.
- The helper reads the binary name from `[project.scripts]` in
  `pyproject.toml`; nothing hardcodes it.
- Stubs record their arguments: assert *what the script asked for*, not only
  what it printed. `assert_called_arg` matches a whole argument, so a quoting
  bug cannot hide behind a flattened command line.
- Run `make bats` whenever you touch a shell script.

### Install the Jenkins plugins the scenarios need
Anything beyond base Jenkins — lockable resources, matrix auth, a plugin's
build step — can only be covered end to end if the plugin is baked into the
fixture image. Install it; do not drop the layer because the plugin is absent.

1. Add it to the **direct** block at the top of
   `tests/e2e/docker/plugins.txt`, with its version pinned.
2. **Regenerate the whole file**: `cd tests/e2e/docker`, build the image, then
   read the installed versions back out of it with the command in the file's
   own header, and replace the transitive block with what it prints.
   `jenkins-plugin-cli` resolves transitive dependencies to
   latest-compatible, so one new direct plugin moves transitive versions too.
   The file holds the entire resolved closure, every entry pinned, because
   silent version drift is the class of bug this suite exists to catch.
3. Configure the instance in `tests/e2e/docker/casc.yaml` only *after* the
   plugin is installed. JCasC validates the whole document at boot and rejects
   a section whose plugin is absent, so Jenkins fails to start rather than
   warning — `globalMatrix` without `matrix-auth` broke the fixture exactly
   this way. If a boot fails after a casc edit, read the container logs before
   anything else.
4. Add any seed job as `tests/e2e/docker/jobs/*.xml`, wired into the
   `jenkins_container` fixture so its name is asserted by the fixture
   inventory scenario.
5. Expect the first run after a plugin change to rebuild the image, which is
   the slow part; it is then cached for the session.

Full rationale, the environment traps, and the pytest pin: `docs/design/testing.md`.

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

## Agent Instruction Files
`AGENTS.md` is the single source of truth. `CLAUDE.md`, `GEMINI.md` and
`.github/copilot-instructions.md` are symlinks to it, so there is one file to
edit and drift between them is impossible.

- `AGENTS.md` — canonical. Read natively by Codex and most other agents
- `CLAUDE.md` → symlink — Claude Code
- `GEMINI.md` → symlink — Gemini
- `.github/copilot-instructions.md` → symlink — GitHub Copilot

`AGENTS.md` is the canonical file because Codex, Copilot and others read that
name natively, and it is the emerging cross-tool convention. The three tools
that insist on their own filename get a symlink instead of a copy.

On Windows, git checks symlinks out as plain text files containing the target
path unless `core.symlinks=true` and Developer Mode are both enabled.

## Commit Messages
- Use Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`, `ci:`).
- **A `!` after the type, or `BREAKING CHANGE` anywhere in the body, releases a
  new MAJOR version.** `feat!: drop the old flag` is what took the sibling
  breakfast repo from 0.107.1 to 1.0.0. These are the *only* things that cause a
  major bump, so neither is a decoration for "this is important" — use one when
  you mean to change the first number, and say so in the PR description when you
  do.
- The version a merge will release is computed from these messages by
  `git mkver`, not chosen by hand. The `version` CI job prints it on every pull
  request, so check it before merging rather than discovering it afterwards.
- **Mentioning either marker in a commit body counts as using it.** mkver scans
  every line of every commit message since the last tag for the marker as a
  substring, so a body explaining that a commit "was marked `feat!:`" reads to
  mkver exactly like a declaration, and releases a major version. When you need
  to write about them, break the string: `feat!` without the colon, or spell the
  footer with a hyphen.
- `git mkver patch` does not mean "bump the patch number" — it writes whatever
  version mkver computed into `VERSION`. Never run it on a feature branch.

## Code Quality
- **Before every commit:** `make format && make lint && make test`
- stdout for data; stderr for progress/warnings/errors
- No bare `except Exception` — catch specific types
