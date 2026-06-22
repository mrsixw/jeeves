# Troubleshooting

## No colour output

If you see no colours, check:

- Are you using `--no-colour` or `JEEVES_NO_COLOUR=1`?
- Does your terminal support ANSI colours?
- Try `--theme default` explicitly.

## Seasonal colours not showing

- Seasonal colours only appear on themed dates. Check today's date and the calendar you're using.
- Try `--seasonal-calendar western` to use the default calendar.
- Pass `--no-seasonal-colours` to disable entirely.

## Config file not found

Run `jeeves --init-config` to create a default config at `~/.config/jeeves/config.toml`.

Use `jeeves --show-config` to see which config file is being used and what keys are set.

## Update check fails silently

The update check is non-fatal. If it fails (no network, GitHub rate limit),
jeeves continues normally. Pass `--no-update-check` to skip it entirely.

## Command not found after install

Add `~/.local/bin` to your PATH:

```bash
export PATH="${HOME}/.local/bin:${PATH}"
```
