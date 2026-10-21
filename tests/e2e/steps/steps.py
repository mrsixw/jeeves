"""The general step definitions: running the binary, inspecting its streams.

Nothing here knows what a Jenkins job is. Steps that do will belong beside
this one, in their own module, once the container lands.
"""

import json
import shlex
from pathlib import Path

from pytest_bdd import given, parsers, then, when

REPO_ROOT = Path(__file__).resolve().parents[3]


# ── given ───────────────────────────────────────────────────────────────────


@given("no Jenkins connection is configured")
def _no_connection(cli_env):
    """Prove the absence rather than assume it.

    The environment is already an allowlist, so these are never set — but a
    scenario that *depends* on them being unset should say so, and would
    otherwise pass for the wrong reason if the allowlist ever grew.
    """
    for key in ("JEEVES_URL", "JEEVES_USER", "JEEVES_TOKEN", "JEEVES_PROFILE"):
        cli_env.pop(key, None)


@given("the Jenkins URL points at a closed port")
def _unreachable(cli_env, unreachable_url):
    cli_env["JEEVES_URL"] = unreachable_url


@given(parsers.parse('the config file contains "{line}"'))
def _config_line(sandbox, line):
    """Append one line to the sandbox config, creating it on first use.

    Repeat the step to build up a multi-line file. Use TOML's single-quoted
    literal strings for values, so the Gherkin double quotes stay unambiguous.
    """
    path = sandbox["config"] / "jeeves" / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


# ── when ────────────────────────────────────────────────────────────────────


@when(parsers.parse("I run `jeeves {args}`"), target_fixture="result")
def _run_with_args(run_jeeves, args):
    return run_jeeves(shlex.split(args))


# ── then: exit status ───────────────────────────────────────────────────────


@then(parsers.parse("the exit code is {code:d}"))
def _exit_code(result, code):
    assert result.returncode == code, (
        f"expected exit {code}, got {result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )


# ── then: streams ───────────────────────────────────────────────────────────
#
# Assert on stderr with `in`, never equality: apply_seasonal_colour decorates
# output on certain dates and cli.py carries a date-gated greeting. Those are
# gated on colour, so scenarios pass --no-colour, but exact-match assertions
# would still be a hostage to the calendar.


@then("stdout is empty")
def _stdout_empty(result):
    assert result.stdout.strip() == "", f"stdout was:\n{result.stdout}"


@then("stderr is empty")
def _stderr_empty(result):
    assert result.stderr.strip() == "", f"stderr was:\n{result.stderr}"


@then(parsers.parse('stdout contains "{text}"'))
def _stdout_contains(result, text):
    assert text in result.stdout, f"stdout was:\n{result.stdout}"


@then(parsers.parse('stdout does not contain "{text}"'))
def _stdout_lacks(result, text):
    assert text not in result.stdout, f"{text!r} leaked onto stdout:\n{result.stdout}"


@then(parsers.parse('stderr contains "{text}"'))
def _stderr_contains(result, text):
    assert text in result.stderr, f"stderr was:\n{result.stderr}"


@then("stdout is valid JSON", target_fixture="payload")
def _stdout_json(result):
    return json.loads(result.stdout)


# ── then: specifics ─────────────────────────────────────────────────────────


@then("stdout reports the version from the VERSION file")
def _version_matches(result):
    """Pin the shipped artifact to the repository's VERSION file.

    This is the one assertion that genuinely exercises packaging: the zipapp
    carries its own copy of the metadata, so a build that picked up a stale
    version would pass every mocked test and fail here.
    """
    expected = (REPO_ROOT / "VERSION").read_text().strip()
    assert result.stdout.strip().endswith(
        expected
    ), f"expected version {expected!r}, stdout was:\n{result.stdout}"


@then("the config file exists in the sandbox")
def _config_written(sandbox):
    path = sandbox["config"] / "jeeves" / "config.toml"
    assert path.is_file(), f"{path} was not created — is XDG_CONFIG_HOME honoured?"


@then("nothing was written directly to the home directory")
def _xdg_dirs_were_used(sandbox):
    """Prove the XDG dirs were honoured rather than bypassed.

    If ``HOME`` were honoured but ``XDG_*`` ignored — the relative-path trap in
    ``xdg.py`` — jeeves would write to ``$HOME/.config`` instead of the
    sandboxed config dir, and every scenario would still pass while the suite
    quietly stopped being isolated.

    Deliberately narrow: both paths are inside the per-scenario ``tmp_path``,
    so this cannot detect an escape to the developer's *real* home. It checks
    the one failure it can see, and is named for that.
    """
    stray = sorted(
        p.relative_to(sandbox["home"])
        for p in sandbox["home"].rglob("*")
        if p.is_file() and ".shiv" not in p.parts
    )
    assert not stray, f"jeeves wrote into HOME rather than the XDG dirs: {stray}"
