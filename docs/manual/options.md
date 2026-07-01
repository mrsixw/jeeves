# Options Reference

## Display options

### `--theme`

Set the terminal colour theme. Choices: `default`, `dark`, `light`, `mono`, `rainbow`.

```bash
jeeves --theme rainbow
jeeves --theme mono      # no colour
```

Config key: `theme = "default"`

### `--seasonal-colours` / `--no-seasonal-colours`

Apply seasonal ANSI colours based on the current date (enabled by default).
The colour scheme changes automatically for holidays and cultural events.

Config key: `seasonal-colours = true`

### `--seasonal-calendar`

Choose which cultural calendar drives seasonal colours.

| Value | Calendar |
| ----- | -------- |
| `western` | Gregorian holidays (Christmas, Easter, Pride Month, Halloween) |
| `jewish` | Hanukkah, Passover, Rosh Hashanah, Sukkot |
| `islamic` | Eid al-Fitr, Eid al-Adha |
| `hindu` | Diwali, Holi |
| `sikh` | Vaisakhi, Bandi Chhor Divas |
| `east-asian` | Lunar New Year, Mid-Autumn, Songkran, Hanami |

Config key: `seasonal-calendar = "western"`

### `--no-colour`

Disable all ANSI colour output. Also honoured via `JEEVES_NO_COLOUR=1`.

### `--quiet`

Suppress all butler personality output: the bare-invocation greeting, per-command headers, empty-state messages, and update-check notices. Errors are reduced to `Error: <message>` on stderr. Data tables and command output are unaffected.

Useful for scripting when you only want the data and don't need the butler commentary.

```bash
jeeves --quiet jobs          # table only, no headers or greeting
jeeves --quiet build my-job  # exits 0 silently on success
JEEVES_QUIET=1 jeeves jobs  # same via environment variable
```

Config key: `quiet = true`

## Output formats

### `--format`

Choose how table commands (`jobs`, `nodes`, `queue`) render their results.
Decorative butler headers always go to stderr, so structured output on stdout
stays clean and pipe-friendly.

| Format | Description |
| ------ | ----------- |
| `table` | Default. Coloured, emoji-rich table with clickable hyperlinks. |
| `tree` | Hierarchical view (jobs only) — reconstructs the folder/job tree. |
| `json` | Pretty JSON array of records (stable keys, semantic values). |
| `ndjson` | One JSON object per line — ideal for streaming and `jq`. |
| `markdown` | GitHub-flavoured Markdown table for PRs, docs, and Slack. |
| `csv` / `tsv` | Delimited rows for spreadsheets and `cut`/`awk`. |
| `template` | Custom one-line-per-row output (see `--template`). |
| `plain` | Plain-text table, semantic values only — no emoji, ANSI colour, or hyperlinks. Human-readable equivalent of `csv` for terminal use. |

```bash
jeeves --format json jobs | jq '.[] | select(.status == "failed")'
jeeves --format tree jobs --expand
jeeves --format csv nodes > agents.csv
jeeves --format markdown jobs >> report.md
```

Config key: `format = "table"`

Structured formats (`json`, `ndjson`) emit semantic values, never the
decorative emoji. The JSON keys per command:

- **jobs**: `name`, `type`, `color`, `status`, `health`, `url`
- **nodes**: `name`, `status`, `executors`, `labels`, `url`
- **queue**: `name`, `reason`, `stuck`, `url`

### `--template`

Row template used with `--format template`. Fields are the JSON keys above,
referenced in `{braces}`.

```bash
jeeves --format template --template "{name}: {status} ({health})" jobs
jeeves --format template --template "{name} -> {url}" nodes
```

## Config options

### `--config PATH`

Path to a TOML config file. Overrides the XDG default search paths.

### `--show-config`

Print the resolved config and exit.

### `--init-config`

Write a default config file to `~/.config/jeeves/config.toml` and exit.

## Caching

### `--cache` / `--no-cache`

Enable disk caching of results (off by default).

Config key: `cache = false`

### `--cache-ttl`

How long to cache results. Accepts seconds (`300`), or suffixed strings (`5m`, `2h`). Default: 300s.

Config key: `cache-ttl = "300"`

## Shell completions

### `--completion [bash|zsh|fish]`

Print the shell completion script and exit. Eval in your shell config:

```bash
eval "$(jeeves --completion bash)"
```

## Other

### `--no-update-check`

Disable the automatic update check. Also honoured via `JEEVES_NO_UPDATE_CHECK=1`.

Config key: `no-update-check = false`

### `--version`

Show the installed version and exit.
