# 🎩 jeeves

[![CI](https://github.com/mrsixw/jeeves/actions/workflows/ci.yml/badge.svg)](https://github.com/mrsixw/jeeves/actions/workflows/ci.yml)

**Your Jenkins CI/CD butler.** Inspired by P.G. Wodehouse's Jeeves — efficient, unflappable, and faintly wry — but kept light on the formality.

> *"Jeeves — is the nightly build passing?"*
> *"Certainly. Jenkins is in fine form. All pipelines are green."*

## Commands

Commands are grouped to mirror Jenkins' own hierarchy: server-level commands at the top, then `job`, `build`, and `node` groups.

| Command | Description |
| ------- | ----------- |
| `jeeves status` | Check Jenkins server health |
| `jeeves queue` | Show the build queue |
| `jeeves whoami` | Show the authenticated Jenkins user |
| `jeeves job list [--folder NAME]` | List all jobs and their status |
| `jeeves job params JOB` | Show a job's build parameters |
| `jeeves job trigger JOB [--param K=V]` | Trigger a build |
| `jeeves build summary JOB` | Show last / successful / failed builds |
| `jeeves build list JOB [--limit N] [--result X] [--param K=V]` | Show recent build history, optionally filtered by parameter |
| `jeeves build show JOB [BUILD]` | Show a single build, including its parameters and causes |
| `jeeves build blame JOB [BUILD]` | Show who changed what in a build (culprits and SCM changes) |
| `jeeves build log JOB [BUILD]` | Show build console output |
| `jeeves build cancel JOB BUILD` | Cancel a running build |
| `jeeves build rebuild JOB [--param K=V]` | Re-run a build with its previous parameters |
| `jeeves node list [--stats]` | List build nodes (agents); `--stats` adds health metrics |

### Deprecated spellings

The pre-0.18 flat commands (`jobs`, `build JOB`, `builds …`, `params`, `log`, `cancel`, `rebuild`, `nodes`) still work for one more release. They are hidden from `--help` and print a gentle notice pointing at the new spelling. One caveat: a job literally named after a `build` subcommand (`list`, `summary`, `show`, `log`, `cancel`, `rebuild`) cannot be triggered via the legacy `jeeves build NAME` form — use `jeeves job trigger NAME`.

## Installation

```bash
curl -sSL https://raw.githubusercontent.com/mrsixw/jeeves/main/install.sh | bash
```

Or build and install from source:

```bash
git clone https://github.com/mrsixw/jeeves.git
cd jeeves
make build
sudo make install
```

*(Note: This compiles and installs the butler locally from your source checkout. If you want to download and install a pre-compiled binary instantly instead, use the `install.sh` script above).*

By default, this installs the executable to `/usr/local/bin`. You can customize the installation prefix using the `PREFIX` variable:

```bash
make install PREFIX=$HOME/.local
```

To uninstall:

```bash
sudo make uninstall
```

If installed with a custom `PREFIX`:

```bash
make uninstall PREFIX=$HOME/.local
```

## Quick start

```bash
jeeves --init-config                       # write a starter config
jeeves status                              # check the Jenkins server
jeeves job list                            # list jobs and their status
jeeves --profile staging job list          # target a named [profiles.*] server
jeeves --format json job list | jq        # structured output for scripting
eval "$(jeeves --completion bash)"         # shell completions
```

## Development

```bash
uv sync --extra dev
make format && make lint && make test
```

## Documentation

- [Options reference](docs/manual/options.md)
- [Usage guide](docs/manual/usage.md)
- [Troubleshooting](docs/manual/troubleshooting.md)
- [Contributing](CONTRIBUTING.md)

---

Made with ❤️ in the UK using the [five-clis](https://github.com/mrsixw/five-clis) framework.
