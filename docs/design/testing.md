# Testing Strategy

How jeeves is tested, and — more usefully — which layer a new test belongs in.

## The layers

| Layer | Location | Runs the binary? | Needs a server? | Command |
| --- | --- | --- | --- | --- |
| Unit | `tests/test_*.py` | no | no | `make test` |
| CLI | `tests/test_cli.py` | no (in-process `CliRunner`) | no (mocked) | `make test` |
| End-to-end | `tests/e2e/` | **yes**, the shiv zipapp as a subprocess | **yes**, a real one in a container | `make e2e` |

### The rule

**If it fakes any part of the system under test, it is a unit test.** It
belongs in `tests/`, not `tests/e2e/`.

Faking means `monkeypatch`, but equally `requests-mock` or `CliRunner` — each
replaces something the end-to-end layer exists to exercise for real: the
network, the clock, the process boundary.

This is written down rather than assumed because the distinction is easy to
lose: a test that boots the real binary but points it at a mock is not an
end-to-end test, it is a slower unit test.

### Why this layer exists

jeeves had 482 passing tests and not one of them talked to Jenkins. Every HTTP
interaction was mocked at the `requests` layer, and the CLI tests drive Click's
`CliRunner` in-process. That suite pins our *intent* well. What it cannot do is
tell us whether that intent matches Jenkins, because the thing on the other end
of the socket is a fixture we wrote.

A mock will cheerfully accept a wrong URL path, a query string where Jenkins
demands a form body, an invented JSON field name, a status code Jenkins never
returns, and a crumb we never sent.

### What end-to-end buys that the other layers cannot

- Real process **exit codes**, not `Result.exit_code`.
- **The real OS file descriptors.** Click's `CliRunner` does separate
  `result.stdout` from `result.stderr` — the mocked suite uses both — but it
  only sees what passes through Click's own output functions. A subprocess sees
  everything on the actual file descriptors: the shiv preamble, a Python
  warning, a dependency printing directly to `sys.__stdout__`. Anything of
  that kind landing on stdout would corrupt `--format json` for a caller
  piping us, and no in-process test would notice.
- The **shiv zipapp itself**: packaging, the `utils/preamble.py` Python-version
  guard, the console entry point, and the version it reports.
- Real **files on disk** — the config `--init-config` writes, the cache, the log.
- **Cross-process behaviour**: one run writes the cache, the next reads it.

## Running them

```bash
make test        # unit + CLI. Offline, fast. e2e is excluded by default.
make e2e         # builds the zipapp, then runs everything in tests/e2e
make e2e-offline # only the scenarios that need no container
make e2e-ci      # CI variant: uses an already-built binary, fails instead of skipping

uv run pytest -v -m "e2e and not docker" tests/e2e   # the container-free subset
```

Scenarios split in two by tag. The `cli_contract.feature` scenarios need
nothing but the binary. Everything in `jenkins.feature` carries `@docker` and
costs one container boot per session, so `make e2e-offline` is the fast loop
while you are working on something unrelated to Jenkins.

`make test` stays fast because `addopts = "-m 'not e2e'"` in `pyproject.toml`.
A bare `uv run pytest` inherits that. `make e2e` passes `-m e2e` on the command
line, which overrides it.

### Skips versus failures

Locally, a missing zipapp **skips** with an actionable message, so running the
suite before `make build` is harmless rather than confusing. In CI,
`JEEVES_E2E_REQUIRE` turns that skip into a hard failure.

This matters more than it looks. A job that skips everything reports success,
and a green check that exercised nothing is worse than no check at all —
it implies coverage that is not there. Hence two independent guards:

1. `JEEVES_E2E_REQUIRE=1`, set by `make e2e-ci`, so an absent binary fails.
2. `utils/assert_tests_ran.py`, which reads the JUnit report and fails if zero
   tests ran or if any were skipped. That catches the case the first guard
   cannot: some *future* skip condition nobody remembered to gate.

| Variable | Effect |
| --- | --- |
| `JEEVES_E2E_BINARY` | Path to the zipapp under test (default `dist/jeeves`) |
| `JEEVES_E2E_REQUIRE` | Fail rather than skip when the zipapp is missing |
| `JEEVES_E2E_REQUIRE_DOCKER` | Fail rather than skip when no container runtime is usable |
| `JEEVES_E2E_TIMEOUT` | Per-invocation subprocess timeout in seconds (default 90) |
| `JEEVES_E2E_BOOT_TIMEOUT` | Seconds to wait for Jenkins to come up (default 180) |
| `JEEVES_E2E_BUILD_TIMEOUT` | Seconds to allow for the image build (default 900) |

## Why the tests are written in Gherkin

`tests/e2e/` uses [pytest-bdd](https://pytest-bdd.readthedocs.io/). The
`.feature` files describe behaviour in terms of what a user runs and what they
see, which suits a layer whose entire subject is observable CLI behaviour. It
also makes the boundary unmistakable: nothing in `tests/e2e/` looks like the
mocked suites, so the two are hard to confuse.

The layout:

```text
tests/e2e/
  conftest.py          fixtures and the collection hook, nothing else
  steps/
    steps.py           running the binary, and its streams
  features/            the .feature files
  test_e2e.py          scenarios("features") — binds all of them
```

`scenarios()` walks directories, so **one** binding module covers every feature
file; there is no reason for one per feature.

`conftest.py` is the odd name in that tree, and not one we picked — pytest
hardcodes it. It is the only filename pytest loads fixtures and hooks from
without a registered plugin, and what it defines applies to every test in its
directory and below. That is why `pytest_collection_modifyitems` lives there
specifically: hooks come from `conftest.py` and plugins, nowhere else.

`conftest.py` ends with `from .steps.steps import *`, and that star import is
**load-bearing**. `@given`/`@when`/`@then` register a step by injecting a pytest
fixture into the *defining* module's namespace under a generated name
(`pytestbdd_stepdef_*`). pytest only scans conftest and test modules for
fixtures, so a step in a plain module stays invisible until that namespace is
pulled in. Rewrite it as a named import and every scenario loses its steps.

A feature-level tag such as `@e2e` becomes a pytest marker on every scenario in
that file. As a backstop, a `pytest_collection_modifyitems` hook stamps `e2e`
on everything in the directory, so an untagged feature file can never leak into
`make test`.

> **Note on `AGENTS.md`'s "documented APIs, not internals" rule:** pytest-bdd
> reaches into `_pytest` privates. Our own code touches only its public
> `scenarios`, `given`, `when`, `then` and `parsers`. See the pin below.

### Why `pytest` is pinned below 10

`pytest_bdd/compat.py` reaches into pytest privates: on pytest 9.1+ it calls
`FixtureManager._register_fixture()` and `request._get_active_fixturedef()`,
sets `fixture_def.cached_result` directly, and imports `FixtureDef`,
`FixtureManager` and `FixtureRequest` from `_pytest.fixtures`.

pytest-bdd 9.0.0 fixed the `PytestRemovedIn10Warning` these used to raise — it
no longer passes the deprecated `nodeid` argument — but the dependency on
unguaranteed internals remains, and pytest 10 is not released, so there is no
way to test the combination yet.

If it does break, the e2e suite stops **collecting** rather than merely failing
a test, and because `release` is gated on the `e2e` job that would block
releases rather than just reporting red. Nothing else pins pytest, so `uv`
would be free to resolve 10 on any `uv sync`, and the first sign would be a red
job on an unrelated pull request. The pin makes the constraint deliberate.

**Revisit when pytest 10 ships** and the suite can actually be run against it.

## Environment isolation

The subprocess environment is an **allowlist**, not a blocklist: it starts
empty and copies only `PATH` (the zipapp shebang is `#!/usr/bin/env python3`)
and `TMPDIR`. Starting from nothing is what makes the "nothing is configured"
scenarios trustworthy — a `JEEVES_URL` in your own shell cannot leak in and
silently point the suite at a real Jenkins.

Four traps this closes, each read out of the source rather than guessed:

- **`XDG_*` must be absolute.** `xdg._xdg_override` only honours a value when
  `Path(value).is_absolute()`, otherwise falling back to `Path.home()` — which
  would write into your real cache.
- **`COLUMNS` must be pinned.** `render.py` compares table width against
  `shutil.get_terminal_size()`, which honours `COLUMNS`; unset in a pipe it
  falls back to 80 and the renderer starts *dropping columns*.
- **cwd must be a temp directory.** `xdg.get_config_paths()` includes
  `Path.cwd() / ".jeeves.toml"`, so a stray config in the repo root would
  change results.
- **`SHIV_ROOT` is session-scoped.** Otherwise, since each scenario gets a
  fresh sandboxed `HOME`, every one re-extracts the whole zipapp.

Also set: `JEEVES_NO_UPDATE_CHECK=1` (or every run hits the releases API and may
print a banner the stream-discipline scenarios would then see), `TZ=UTC` and
`LC_ALL=C.UTF-8`.

**Assert on stderr with `in`, never equality.** `apply_seasonal_colour`
decorates output on certain dates and `cli.py` carries a date-gated greeting.
Those are gated on colour, so scenarios pass `--no-colour`, but an exact-match
assertion would still be a hostage to the calendar.

### An unreachable Jenkins, deterministically

Scenarios that need a connection failure get their URL from the
`unreachable_url` fixture, which binds port 0 so the OS names a free port,
closes it, and then **verifies a connection is actually refused** before
handing the URL out.

The verification is the point. Hardcoding a port nothing *ought* to use — port
1, say — is an assumption, and a scenario resting on a wrong one would silently
talk to whatever was listening instead of exercising the failure path at all.
Checking costs one loopback connect per session and turns the assumption into
a fact.

## When to add a scenario

**The default is both layers**, because they are doing different jobs.

The unit layer carries the **coverage**. It is where breadth belongs: every
branch, every flag permutation, every error path, the exact output shapes.
Fixtures are free and nothing is spawned, so being exhaustive there is close
to free.

This layer does the **validation**. It answers a question the unit layer
cannot ask at all — does the shipped thing work? So a new command wants at
least one scenario walking its happy path through the real binary, even where
`tests/test_cli.py` already covers the same code. That overlap is expected:
one proves the logic, the other proves the artifact.

Beyond the happy path, a scenario earns its boot when it pins a contract a
unit test structurally cannot see:

- A new or changed **exit code**, or a new user-facing error path.
- Anything about **stdout versus stderr**.
- A new **subcommand**, or a change to how the artifact is packaged or invoked.
- Anything touching **disk** — the cache, config generation, the log.
- **Ordering** properties, such as a guard firing before any network call.
- A new **output format**, or a change to an existing one's shape.

What should *not* migrate up here is breadth. A scenario per flag permutation
adds a process spawn — often a container boot — to every run and tells us
little the unit layer has not already said far more cheaply. Exhaustiveness
below, validation here.

A pure refactor with no user-visible change may leave the scenarios alone. If
a user-facing behaviour arrives with none, the PR should say why.

### One portability trap already found

`jeeves completions bash` writes a warning to **stderr** on hosts with bash
older than 4.4, because Click gates bash completion on the host's own bash
version. macOS still ships 3.2. So the scenario asserting a clean stderr uses
`zsh`, and the bash scenario asserts only that the script reaches stdout. The
warning is correct behaviour — a diagnostic, on stderr — but a suite that
asserted a clean stderr for bash would pass in CI and fail on every Mac.

## CI

The `e2e` job runs `needs: [build]`, and `release` is gated behind it. It
downloads the artifact the `build` job produced rather than rebuilding, so the
bits under test are the bits that ship.

One detail that will otherwise cost an afternoon: artifacts travel as zips and
**do not preserve the executable bit**, hence the `chmod +x` step.

## The fixture Jenkins

`tests/e2e/docker/` builds it:

| File | Holds |
| --- | --- |
| `Dockerfile` | the digest-pinned base image and the plugin install |
| `plugins.txt` | every plugin, with its version pinned |
| `casc.yaml` | the Configuration-as-Code that configures the *instance* |
| `jobs/*.xml` | the `config.xml` for each seed job, created after boot |

### Pin the plugins, not just the image — and all of them

The base image is pinned by **digest**, not tag, because a tag can be
repointed and a digest cannot.

Naming three plugins with versions is still not reproducibility.
`jenkins-plugin-cli` resolves **transitive dependencies** to
latest-compatible, and the direct asks pull in ~54 more at whatever versions
are current that day. So `plugins.txt` holds the **entire resolved set**, 58
entries, every one pinned — the direct asks at the top, the transitive closure
below.

Silent version drift is the class of bug this suite exists to catch, so it
must not be in the suite itself. `plugins.txt` carries the command to
regenerate the list from a built image after changing a direct dependency.

### Instance config versus per-run state

A clean split, so there is one obvious home for each thing:

- **Configuration-as-Code configures the instance** — the local user, the
  authorisation strategy, the executor count. Baked into the image.
- **The fixture creates the jobs after boot**, with `POST /createItem` and a
  checked-in `config.xml`. Jobs are per-run state, not image state, and
  creating them the way a user would is part of what the suite is for.

Two JCasC traps, both found by booting it rather than by reading docs:

- `authorizationStrategy: globalMatrix` needs the **matrix-auth plugin**. Core's
  `loggedInUsersCanDoAnything` needs none, and no scenario asserts on
  finer-grained permissions, so that is what the fixture uses.
- **`security.csrf` is not a JCasC section.** Setting it fails the boot
  outright. CSRF is on by default anyway, which is what the suite wants —
  jeeves fetches a crumb before every POST, and disabling it would silently
  stop exercising that path.

### The seed jobs

`e2e-freestyle`, `e2e-pipeline`, `e2e-lock-holder`, and `nested` inside
`e2e-folder`. The names
are fixed and spelled literally in the feature files, because interpolating
them would need placeholder syntax that collides with Gherkin's own `<...>`
outline parameters. The **fixture inventory** scenario asserts every one of
those names in a single place, so a rename fails once and legibly instead of
scattering "job not found" across the file.

Why each exists:

- **Two job types** because freestyle builds report SCM changes under a single
  `changeSet` while pipeline builds use `changeSets[]`, and
  `JenkinsClient.changes()` asks for both. Only a real Jenkins of each type
  shows which one actually arrives.
- **A folder** because `normalize_jenkins_path` encodes `folder/job` as
  `/job/folder/job/job`, and a mock will accept whatever shape we invent.
- **A lock holder** because `locked` is not reachable any other way.
  Reserving a resource makes it `reserved`; only a build inside the
  lockable-resources `lock` step makes it `locked`, and only then do
  `lockCause` and `buildName` carry anything. Verified against the fixture:
  while held, the plugin reports `locked=true`, `reserved=false`,
  `reservedBy=null` and `buildName` set — so a locked resource has no holder,
  and the record's derived `state` has to prefer `locked` over `reserved`.
  The scenario polls for the lock rather than sleeping a guessed interval,
  because the queue has to assign an executor first and that is not instant
  on a loaded runner.

### The lockable resources

Declared in `casc.yaml`, not created by the fixture, because the plugin keeps
them in global configuration — they are image state in exactly the way the
jobs are not.

`e2e-lock-free` and `e2e-lock-spare` share the label `e2e-pool`, and only the
first also carries `linux`. Two resources rather than one is deliberate: a
`--label` filter that ORs instead of ANDs passes against a single labelled
resource. `e2e-lock-held` is separate so the lock-holding build cannot
interfere with the reservation scenarios.

Labels arrive from the plugin as **one space-separated string**, with
`labelsAsList` alongside it. jeeves prefers the list and falls back to
splitting the string; only the real plugin confirms which format is being
split.

### The credential path

Configuration-as-Code can declare a user with a password but cannot mint an API
token, and jeeves authenticates with a username and a **token**. So the fixture
uses the password exactly once, asking Jenkins for a token over the web API the
way a user would, and every jeeves invocation then uses that token — the path
the project documents.

One rake: that request needs a crumb **and the session cookie the crumb was
issued against**. Jenkins binds the crumb to the HTTP session, so fetching a
crumb and posting without carrying the cookie jar forward fails with "No valid
crumb". Using a single `requests.Session` for both is what keeps them together.

The fixture talks to Jenkins with `requests` directly rather than through
`JenkinsClient`, and builds the folder URL by hand rather than with
`normalize_jenkins_path`. Both are deliberate: those are the things under test,
and a fixture built on them would let a bug in them hide itself.

### Unreachable is not the same as broken

A container that fails to boot is a real failure and must be loud. A container
that boots fine but cannot be reached from the host is a property of the
host's networking, and should skip with that explanation rather than blame the
image.

The suite tells them apart by asking **from inside the container** whether
Jenkins is serving. If it answers there but not through the published port, the
fault is the host's routing: that raises `NotReachable`, which skips locally
and — under `JEEVES_E2E_REQUIRE_DOCKER`, as CI sets — fails like anything else.

That probe must ask for **the same endpoint, with the same credentials, that
the readiness poll requires** — authenticated `/api/json`, not the login page.
Probing something weaker would classify a broken security realm as a host
networking problem and skip locally, which would hide precisely the kind of
Configuration-as-Code bug this fixture is most prone to: both JCasC errors
above were security-realm or authorisation errors.

This is not hypothetical. Apple's `container` runtime on macOS 27 builds and
boots the image happily, and the guest has working outbound networking, but
host-to-guest traffic does not arrive: the container's IP never answers ARP on
the bridge. Without the distinction, that host produces a dozen failures and a
three-minute boot timeout instead of one clear sentence.

### Why `__all__` must not appear in the step modules

`conftest.py` pulls the steps in with `import *`, which **respects `__all__`**.
An empty one imports nothing, the generated `pytestbdd_stepdef_*` fixtures
never arrive, and every scenario fails with `StepDefinitionNotFoundError`
pointing nowhere near the cause. The project's "every module declares
`__all__`" rule covers `src/jeeves/`, not this package.

### What the container still cannot prove

- **Populated SCM change sets.** The seed jobs have no SCM, so `build blame`
  is exercised against an *empty* change set for both job types. That proves
  jeeves reads whichever shape Jenkins sends without erroring, which is the
  part that differs by job type — but not that it renders real commits. A
  populated change set needs a git server and an SCM-backed job.
- **A Jenkins without the lockable-resources plugin.** `jeeves plugin
  lockable-resources` degrades politely when the plugin is absent, and the
  fixture has it installed, so that branch is proved only in
  `tests/test_lockable.py`. Proving it here would need a second container
  without the plugin — a whole second boot to assert one error message, which
  is not worth it.
- **An older lockable-resources plugin.** `createResource` and
  `deleteResource` are `@Restricted(NoExternalUse)` and absent from older
  releases, which is why jeeves tells "plugin too old" apart from "no such
  resource". The fixture pins a current version, so the scenarios prove those
  endpoints *do* exist — the useful half. The too-old branch stays a unit
  test, since asserting it would mean pinning a second, deliberately stale
  image.
