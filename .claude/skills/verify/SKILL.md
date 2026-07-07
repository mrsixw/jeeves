---
name: verify
description: Verify a jeeves change end-to-end by driving the real CLI against a local fake Jenkins HTTP server.
---

# Verify jeeves changes

jeeves is a Click CLI that talks to Jenkins over HTTP. Verify changes by
running the real command against a throwaway fake Jenkins server — no real
Jenkins needed.

## Recipe

1. Write a small `http.server` script (scratchpad, not the repo) that serves
   the endpoints the change touches, e.g.:
   - `GET /computer/api/json` → `{"computer": [...]}`
   - `GET /computer/{name}/config.xml` → XML (or 403/404 for error paths)
   - `GET /api/json`, `/queue/api/json`, `/job/{name}/api/json`, `/me/api/json`
   Log each request path so you can assert which requests the CLI made
   (and did NOT make).
2. Run it in the background bound to `127.0.0.1:18080`.
3. Drive the CLI with connection flags — no config file needed:

   ```bash
   uv run jeeves --no-colour --no-update-check --url http://127.0.0.1:18080 <command...>
   ```

4. Probe beyond the happy path: `--format json|csv|template`, flag
   combinations, error responses (403/404), malformed payloads, typo'd flags.

## Gotchas

- The very first CLI run can race the server startup — curl the server once
  before driving the CLI.
- Butler headers/errors go to stderr; data goes to stdout. Capture both.
- `--no-update-check` avoids a GitHub API call; `--no-colour` gives greppable
  output.
- `--format template` renders raw record values, so `None` fields print as
  `None` (pre-existing behaviour across commands).
