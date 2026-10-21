# Contributing to jeeves

## Development setup

```bash
git clone https://github.com/mrsixw/jeeves
cd jeeves
uv sync --extra dev
```

## Before every commit

Run all three in order — no exceptions:

```bash
make format   # auto-fix formatting
make lint     # must exit clean (ruff, black, markdownlint, shellcheck, typos)
make test     # all tests must pass
```

If you touched a shell script, run `make bats` too.

`make test` runs the mocked suites and is offline and fast. The end-to-end
suite is separate, because it builds the zipapp and drives it as a real
subprocess:

```bash
make e2e      # builds, then runs tests/e2e
```

CI runs it on every push, and `release` is gated behind it.

**Expect to write both layers.** Coverage belongs in the unit tests — every
branch and flag permutation, where fixtures are free. The end-to-end suite
does the validation: a change to behaviour wants at least one scenario
proving the shipped binary really does it. Some overlap between the two is
expected. If a scenario needs Jenkins surface the fixture lacks, add the
plugin to `tests/e2e/docker/plugins.txt` rather than skipping the layer.
Where the boundary falls, and why it is worth keeping, is set out in
[docs/design/testing.md](docs/design/testing.md). The short version: **if it
fakes any part of the system under test, it is a unit test.**

## Testing the shell scripts

`install.sh` is the published `curl | bash` install path — including the Python
3.11 runtime guard — and `utils/` holds the scripts that cut releases. They are
covered by a [bats](https://github.com/bats-core/bats-core) suite in
`tests/bats/`:

```bash
make bats        # the shell test suite
make shellcheck  # static analysis over every shell source
make spell       # the same spell check CI runs
```

Each test runs the **real script as a subprocess** with its collaborators —
`gh`, `git`, `curl`, `tar`, `install`, `python3` — replaced by stubs on `PATH`,
and with `HOME` redirected into the test's temporary directory. Nothing reaches
the network, and an installer test cannot scribble on the machine running it.
Those stubs are faking, by the rule above, so the suite belongs under `tests/`.

`bats` and `shellcheck` are fetched on demand with `npx`, and `typos` with
`uvx` — nothing to install by hand beyond `node`.

## Conventional commits

Use `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`, `ci:` prefixes.

### Breaking changes bump the major version

Two things, and only these two, cause a **major** release:

- a `!` after the type — `feat!: drop the old flag`
- `BREAKING CHANGE` anywhere in the commit body

`git mkver` reads them straight out of the commit messages since the last tag,
so the release that follows your merge is decided by how you word the commit.
This is how the sibling breakfast repo went from 0.107.1 to 1.0.0: a commit
removing a deprecated flag was marked breaking, which was accurate and also a
major-version instruction.

Neither marker is a way to say "this change matters". Use one when you intend to
change the first number, and call it out in the pull request when you do.

The `version` CI job prints the version your merge would release on every pull
request. Check it before merging; `utils/report_next_version.sh` is the same
report, runnable locally.

**Careful writing about these markers.** mkver looks for them as a substring on
any line of any commit message since the last tag, so a commit body that
explains "this was committed as `feat!:`" is indistinguishable, to mkver, from
one declaring a breaking change — and releases a major version. Break the string
when you need to refer to it: `feat!` without the trailing colon, or the footer
written with a hyphen.

**`git mkver patch` does not mean "bump the patch number".** It applies the file
patches named in `mkver.conf` (here, writing `VERSION`), and what it writes is
the version mkver computed from the commit messages — which may be a major,
minor or patch increase. The release job calls it through
`utils/bump_version_if_tag_exists.sh` when the tag for the current version
already exists. Do not run it on a feature branch.

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
