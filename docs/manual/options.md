# Options Reference

## Connection

`--url`, `--user`, and `--token` are **global** flags — give them before the
command:

```bash
jeeves --url https://ci.example.com --user me --token *** job list
```

They override the config file, and each has an environment variable
(`JEEVES_URL`, `JEEVES_USER`, `JEEVES_TOKEN`). The config keys are flat,
top-level entries in `config.toml`:

```toml
jenkins-url = "https://ci.example.com"
jenkins-username = "me"
jenkins-token = "..."
```

### Connection profiles (`--profile`)

Define one `[profiles.NAME]` table per Jenkins server to switch between
instances without retyping credentials:

```toml
default-profile = "prod"        # optional: used when --profile is not given

[profiles.prod]
url = "https://jenkins.prod.example.com"
username = "me"
token = "..."

[profiles.staging]
url = "https://jenkins.staging.example.com"
```

```bash
jeeves --profile staging job list
JEEVES_PROFILE=staging jeeves status    # env alternative to the flag
```

Which profile is active: `--profile` beats `JEEVES_PROFILE`, which beats
`default-profile`. Without any of these, the flat `jenkins-*` keys apply
exactly as before.

When a profile is active:

- the flat `jenkins-*` keys are ignored entirely — a profile is
  self-contained;
- fields the profile omits fall back to `JEEVES_URL` / `JEEVES_USER` /
  `JEEVES_TOKEN`, then to the built-in defaults;
- `JEEVES_URL`-style environment variables **no longer override** the
  profile's own fields (they are demoted to fallbacks) — but explicit
  `--url` / `--user` / `--token` flags still win per field.

An unknown profile name is refused up front with the list of configured
profiles. Profile names needing dots or spaces must be TOML-quoted:
`[profiles."my.prod"]`.

### Managing profiles (`jeeves profile ...`)

Profiles can be maintained without hand-editing the config file:

```bash
jeeves profile list                                    # table; tokens masked
jeeves profile add prod --url https://ci.prod --username me --token - --default
jeeves profile add prod --token - --force              # rotate just the token
jeeves profile use staging                             # set default-profile
jeeves profile use --clear                             # back to the flat keys
jeeves profile remove prod                             # also clears a dangling default
```

Notes:

- `--token -` reads the token from a hidden prompt (or stdin when piped),
  keeping it out of shell history.
- `add` refuses to touch an existing profile unless `--force`, which merges
  only the fields you pass — omitted fields are kept.
- Edits go to the file `--config` names, else the first existing config
  search path, else `~/.config/jeeves/config.toml` (created with `0600`
  permissions). Writes are atomic and preserve comments.
- The `profile` commands work even when `default-profile` points at a
  missing profile, so a broken config can always be repaired.

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

Disable all ANSI colour output. Also honoured via the `JEEVES_NO_COLOUR`
environment variable, set to any non-empty value.

## Output formats

### `--format`

Choose how table commands (`job list`, `node list`, `queue`) render their results.
Decorative butler headers always go to stderr, so structured output on stdout
stays clean and pipe-friendly.

| Format | Description |
| ------ | ----------- |
| `table` | Default. Coloured, emoji-rich table with clickable hyperlinks. |
| `tree` | Hierarchical view (`job list` only) — reconstructs the folder/job tree. |
| `json` | Pretty JSON array of records (stable keys, semantic values). |
| `ndjson` | One JSON object per line — ideal for streaming and `jq`. |
| `markdown` | GitHub-flavoured Markdown table for PRs, docs, and Slack. |
| `csv` / `tsv` | Delimited rows for spreadsheets and `cut`/`awk`. |
| `template` | Custom one-line-per-row output (see `--template`). |

```bash
jeeves --format json job list | jq '.[] | select(.status == "failed")'
jeeves --format tree job list --expand
jeeves --format csv node list > agents.csv
jeeves --format markdown job list >> report.md
```

Config key: `format = "table"`

Structured formats (`json`, `ndjson`) emit semantic values, never the
decorative emoji. The JSON keys per command:

- **job list**: `name`, `type`, `color`, `status`, `health`, `url`
- **node list**: `name`, `status`, `executors`, `labels`, `url` (with `--stats`, adds `disk`, `temp`, `swap`, `response_ms`, `clock_ms`, `architecture` — raw bytes/ms; with `--address`, adds `address` — the agent's launcher host/IP, or `null` when unavailable)
- **queue**: `name`, `reason`, `stuck`, `url`

### `--template`

Row template used with `--format template`. Fields are the JSON keys above,
referenced in `{braces}`.

```bash
jeeves --format template --template "{name}: {status} ({health})" job list
jeeves --format template --template "{name} -> {url}" node list
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

### `completions [bash|zsh|fish]`

Print the shell completion script. Eval in your shell config:

```bash
eval "$(jeeves completions bash)"
```

Works with no config file or Jenkins connection set up.

## Other

### `--no-update-check`

Disable the automatic update check. Also honoured via the
`JEEVES_NO_UPDATE_CHECK` environment variable, set to any non-empty value.

Both `JEEVES_NO_COLOUR` and `JEEVES_NO_UPDATE_CHECK` are resolved by
**presence**, following the [no-color.org](https://no-color.org) convention:
any non-empty value switches the behaviour off, and only unset or empty leaves
it on. The value is never parsed, so `=0` and `=false` still disable — and a
stray `JEEVES_NO_COLOUR=maybe` in a shell profile is harmless rather than
fatal. `JEEVES_URL`, `JEEVES_USER`, `JEEVES_TOKEN` and `JEEVES_PROFILE` carry
values and are read normally.

Config key: `no-update-check = false`

### `--version`

Show the installed version and exit.
