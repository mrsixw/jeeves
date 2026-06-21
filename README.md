# 🍔 five-clis

[![CI](https://github.com/mrsixw/five-clis/actions/workflows/ci.yml/badge.svg)](https://github.com/mrsixw/five-clis/actions/workflows/ci.yml)

**A batteries-included Python CLI template.** Named after Five Guys — burgers, shakes & fries → five CLI essentials.

Click **Use this template** to scaffold a new project with everything wired up and working from day one.

## What's included

| Essential | Description |
| --------- | ----------- |
| **Click** | Fully-wired entrypoint with `--version`, `--help`, `--completion` |
| **Shell completions** | bash, zsh, fish — generated and validated in CI |
| **Config file** | TOML config with XDG paths, `--init-config`, `--show-config` |
| **Themes** | `default`, `dark`, `light`, `mono`, `rainbow` — plus the full seasonal colour system |
| **Seasonal colours** | Date-driven ANSI palettes: western, jewish, islamic, hindu, sikh, east-asian |
| **Caching** | Generic TTL disk cache with atomic writes |
| **Auto-update** | GitHub release update checker with 24h cache |
| **Logging** | File logging to XDG state dir |
| **CI** | GitHub Actions: test, lint, build, spell, docs-lint, man, completions, release |
| **Release pipeline** | `git-mkver` version bumping, shiv binary, man page, `gh release create` |
| **install.sh** | One-liner install with binary + man page + shell completions |

## Installation

```bash
curl -sSL https://raw.githubusercontent.com/mrsixw/five-clis/main/install.sh | bash
```

## Quick start

```bash
five-clis --help
five-clis --theme rainbow
five-clis --name Alice
five-clis --init-config
five-clis --show-config
eval "$(five-clis --completion bash)"
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
