# 🎩 jeeves

[![CI](https://github.com/mrsixw/jeeves/actions/workflows/ci.yml/badge.svg)](https://github.com/mrsixw/jeeves/actions/workflows/ci.yml)

**Your Jenkins CI/CD butler.** Inspired by P.G. Wodehouse's Jeeves — efficient, unflappable, and faintly wry — but kept light on the formality.

> *"Jeeves — is the nightly build passing?"*
> *"Certainly. Jenkins is in fine form. All pipelines are green."*

## Commands

| Command | Description |
| ------- | ----------- |
| `jeeves status` | Check Jenkins server health |
| `jeeves jobs [--folder NAME]` | List all jobs and their status |
| `jeeves build JOB [--param K=V]` | Trigger a build |
| `jeeves builds summary JOB` | Show last / successful / failed builds |
| `jeeves builds list JOB [--limit N] [--result X] [--param K=V]` | Show recent build history, optionally filtered by parameter |
| `jeeves builds show JOB [N]` | Show a single build, including its parameters and causes |
| `jeeves rebuild JOB [--param K=V]` | Re-run a build with its previous parameters |
| `jeeves params JOB` | Show a job's build parameters |
| `jeeves log JOB [--build N]` | Show build console output |
| `jeeves queue` | Show the build queue |
| `jeeves cancel JOB --build N` | Cancel a running build |
| `jeeves nodes` | List build nodes (agents) |

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
jeeves jobs                                # list jobs and their status
jeeves --format json jobs | jq            # structured output for scripting
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
