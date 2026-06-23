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
