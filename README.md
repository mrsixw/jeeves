# 🎩 jeeves

[![CI](https://github.com/mrsixw/jeeves/actions/workflows/ci.yml/badge.svg)](https://github.com/mrsixw/jeeves/actions/workflows/ci.yml)

**Your Jenkins CI/CD butler.** Jeeves handles your Jenkins affairs with the bearing and discretion of P.G. Wodehouse's most celebrated manservant.

> *"Jeeves," I said, "it just occurred to me — is the nightly build passing?"*
> *"Certainly, sir. Jenkins is in fine form. All pipelines are green."*

## Commands

| Command | Description |
| ------- | ----------- |
| `jeeves status` | Check Jenkins server health |
| `jeeves jobs [--folder NAME]` | List all jobs and their status |
| `jeeves build JOB [--param K=V]` | Trigger a build |
| `jeeves log JOB [--build N]` | Show build console output |
| `jeeves queue` | Show the build queue |
| `jeeves cancel JOB --build N` | Cancel a running build |
| `jeeves nodes` | List build nodes (agents) |

## Installation

```bash
curl -sSL https://raw.githubusercontent.com/mrsixw/jeeves/main/install.sh | bash
```

## Quick start

```bash
jeeves --help
jeeves --theme rainbow
jeeves --name Alice
jeeves --init-config
jeeves --show-config
eval "$(jeeves --completion bash)"
```

## Using this template

See the **[Getting Started guide](docs/manual/getting-started.md)** for the full
walkthrough. In brief:

1. Click **Use this template** on GitHub
2. Clone your new repo and run `uv sync --extra dev`
3. Run `uv run python utils/rename.py` to rename the package in one pass
4. Replace the `greet` business logic in `src/<pkg>/cli.py` with your own
5. Add a `GH_TOKEN` secret to your repo (required for the release CI job)
6. Run `make format && make lint && make test` to verify everything works

## Development

```bash
uv sync --extra dev
make format && make lint && make test
```

## Documentation

- [Getting started](docs/manual/getting-started.md)
- [Options reference](docs/manual/options.md)
- [Usage guide](docs/manual/usage.md)
- [Troubleshooting](docs/manual/troubleshooting.md)
- [Contributing](CONTRIBUTING.md)
