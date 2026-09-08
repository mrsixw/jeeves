# Troubleshooting

## No colour output

If you see no colours, check:

- Are you using `--no-colour`, or is `JEEVES_NO_COLOUR` set to anything at
  all? Any non-empty value disables colour, including `0` and `false`.
- Does your terminal support ANSI colours?
- Try `--theme default` explicitly.

## Seasonal colours not showing

- Seasonal colours only appear on themed dates. Check today's date and the calendar you're using.
- Try `--seasonal-calendar western` to use the default calendar.
- Pass `--no-seasonal-colours` to disable entirely.

## Config file not found

Run `jeeves --init-config` to create a default config at `~/.config/jeeves/config.toml`.

Use `jeeves --show-config` to see which config file is being used and what keys are set.

## "Jenkins requires browser login" / redirect loops

Some SSO or reverse-proxy-backed Jenkins deployments redirect unauthenticated
API requests to a login page (`securityRealm/commenceLogin`) until you have an
active browser session — even when your API token and username are correct.
Without that session you may otherwise see a generic `Exceeded 30 redirects`
error.

When jeeves detects this, it explains that a browser login is required. In an
interactive terminal it opens the Jenkins URL in your default browser; when
output is piped or non-interactive, it prints the URL instead. Log in through
the browser, then re-run the command.

If it persists after logging in:

- Confirm you're using an API token (not your account password) — see the
  [Jenkins guide to authenticating scripted clients](https://www.jenkins.io/doc/book/system-administration/authenticating-scripted-clients/).
- Check any reverse proxy in front of Jenkins isn't stripping the
  `Authorization` header — see
  [reverse proxy troubleshooting](https://www.jenkins.io/doc/book/system-administration/reverse-proxy-configuration-troubleshooting/).
- If the controller uses OIDC, ask your Jenkins administrator to check the
  OIDC session gating described below.

### OIDC session gating

Where Jenkins authenticates through OIDC, the controller may additionally
require an *active OIDC session* before it will honour any request — including
one carrying a perfectly valid username and API token. The symptom is identical
to the redirect loop above: correct credentials, but every API call bounces to
the login page. This is especially awkward for non-interactive automation,
which has no browser session to establish.

Only a Jenkins administrator can change this. Ask them whether API-token access
is allowed without an active OIDC session. Deployments expose this differently:
the OIDC plugin commonly offers a setting named
`allowTokenAccessWithoutOicSession`, while others provide an equivalent option
or a more general session-gate toggle. The name matters less than the question —
*can this controller accept API tokens without a browser session?*

## Update check fails silently

The update check is non-fatal. If it fails (no network, GitHub rate limit),
jeeves continues normally. Pass `--no-update-check` to skip it entirely.

## Command not found after install

Add `~/.local/bin` to your PATH:

```bash
export PATH="${HOME}/.local/bin:${PATH}"
```
