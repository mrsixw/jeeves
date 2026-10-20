# Testing Strategy

How jeeves is tested, and — more usefully — which layer a new test belongs in.

## The layers

| Layer | Location | Runs the binary? | Needs a server? | Command |
| --- | --- | --- | --- | --- |
| Unit | `tests/test_*.py` | no | no | `make test` |
| CLI | `tests/test_cli.py` | no (in-process `CliRunner`) | no (mocked) | `make test` |
| End-to-end | `tests/e2e/` | **yes**, the shiv zipapp as a subprocess | not yet — see below | `make e2e` |

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
- Genuinely separate **stdout and stderr**. `CliRunner` merges them, so the
  project's stream discipline — "stdout for data, stderr for everything else" —
  is otherwise unenforceable. A butler error landing on stdout would corrupt
  `--format json` for anything piping us, and no mocked test would notice.
- The **shiv zipapp itself**: packaging, the `utils/preamble.py` Python-version
  guard, the console entry point, and the version it reports.
- Real **files on disk** — the config `--init-config` writes, the cache, the log.
- **Cross-process behaviour**: one run writes the cache, the next reads it.

## Running them

```bash
make test   # unit + CLI. Offline, fast. e2e is excluded by default.
make e2e    # builds the zipapp, then runs everything in tests/e2e
make e2e-ci # CI variant: uses an already-built binary, fails instead of skipping

uv run pytest -v -m e2e tests/e2e   # if the binary is already built
```

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
| `JEEVES_E2E_TIMEOUT` | Per-invocation subprocess timeout in seconds (default 90) |

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

Ask what a unit test **structurally cannot see**. If the answer is "nothing",
the test belongs in `tests/test_cli.py`.

Worth a scenario:

- A new or changed **exit code**, or a new user-facing error path.
- Anything about **stdout versus stderr**.
- A new **subcommand**, or a change to how the artifact is packaged or invoked.
- Anything touching **disk** — the cache, config generation, the log.
- **Ordering** properties, such as a guard firing before any network call.
- A new **output format**, or a change to an existing one's shape.

Not worth one: flag permutations, formatting details, branch coverage. Those
belong in the unit layer, where fixtures are free and no process is spawned.

A scenario that merely repeats what `tests/test_cli.py` already proves is worse
than no scenario — it costs time on every run and implies coverage it does not
add.

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

## Not yet: a real Jenkins in a container

The scenarios here need no server. The next slice of
[#137](https://github.com/mrsixw/jeeves/issues/137) stands up a real Jenkins in
Docker — digest-pinned, plugin versions pinned, configured by
Configuration-as-Code — so the commands that actually talk to Jenkins can be
exercised against it, including the mutating ones.

When it lands, container scenarios get a `@docker` tag and a
`JEEVES_E2E_REQUIRE_DOCKER` gate alongside the existing one, and the table at
the top of this document grows a "yes" in its last column.
