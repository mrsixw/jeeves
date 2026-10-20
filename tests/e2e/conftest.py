"""Fixtures for the end-to-end suite.

These tests drive the **built** ``dist/jeeves`` zipapp as a subprocess. Nothing
here fakes any part of jeeves — if a test needs to, it is a unit test and
belongs in ``tests/``. See ``docs/design/testing.md``.

Step definitions live in ``steps/``; only fixtures and the collection hook
belong in this file.

**On the name.** ``conftest.py`` is not a name we chose and cannot be changed:
pytest hardcodes it. It is the only filename pytest will load fixtures and
hooks from without registering a plugin, and what it defines applies to every
test in its directory and below. Hence ``pytest_collection_modifyitems`` in
particular has to live here — hooks come from ``conftest.py`` and plugins,
nowhere else. Read it as "configuration for the tests in this directory"; the
file is a pytest interface, not a description of its contents.
"""

import os
import shlex
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

# These star imports are load-bearing, not laziness. `@given`/`@when`/`@then`
# register a step by injecting a pytest fixture into the *defining* module's
# namespace, under a generated name (`pytestbdd_stepdef_*`). pytest only scans
# conftest and test modules for fixtures, so a step defined in a plain module
# is invisible until its namespace is pulled in here. Replace these with named
# imports and every scenario fails to find its steps.
from .steps.steps import *  # noqa: F401,F403

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BINARY = REPO_ROOT / "dist" / "jeeves"

# The zipapp shebang is `#!/usr/bin/env python3`, so PATH is load-bearing.
# Everything else is deliberately withheld: starting from an empty environment
# is what makes the "nothing is configured" scenarios trustworthy, because a
# JEEVES_URL in the developer's own shell cannot leak in and silently point the
# suite at a real Jenkins.
_PASSTHROUGH = ("PATH", "TMPDIR")


def _refused(port: int) -> bool:
    """True if connecting to ``port`` on loopback is actively refused."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(1.0)
        try:
            probe.connect(("127.0.0.1", port))
        except ConnectionRefusedError:
            return True
        except OSError:
            # Anything else — a timeout, an unreachable host — is not the
            # clean refusal the scenarios need, so treat the port as unusable.
            return False
        return False


def pytest_collection_modifyitems(items):
    """Stamp ``e2e`` on everything here, tagged or not.

    Feature-level ``@e2e`` tags already become markers, but an untagged feature
    file must never leak into ``make test``.
    """
    here = Path(__file__).parent
    for item in items:
        if here in Path(str(item.fspath)).parents:
            item.add_marker(pytest.mark.e2e)


@pytest.fixture(scope="session")
def unreachable_url():
    """A loopback URL that is verified to refuse connections.

    Scenarios need "the estate is unreachable" to be deterministic. Hardcoding
    a port nobody *ought* to use is an assumption; this checks instead. Bind
    port 0 so the OS names a free port, close it, then confirm a connection is
    actually refused before handing the URL out — so if the OS has handed that
    port to something else in between, we find out here rather than in a
    scenario that silently talked to whatever was listening.
    """
    for _ in range(10):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        if _refused(port):
            return f"http://127.0.0.1:{port}"
    pytest.fail(
        "could not find a loopback port that refuses connections — "
        "something is accepting on every port we were offered"
    )


@dataclass(frozen=True)
class RunResult:
    """One completed ``jeeves`` invocation."""

    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


@pytest.fixture(scope="session")
def shiv_root(tmp_path_factory):
    """Extract the zipapp once per session, not once per scenario.

    Without this, ``SHIV_ROOT`` is unset, shiv falls back to ``~/.shiv``, and
    because every scenario gets a fresh sandboxed ``HOME`` it would re-extract
    the whole zipapp each time.
    """
    return tmp_path_factory.mktemp("shiv-root")


@pytest.fixture(scope="session")
def jeeves_binary():
    """Locate the built zipapp, or skip/fail with something actionable."""
    override = os.environ.get("JEEVES_E2E_BINARY")
    path = Path(override).resolve() if override else DEFAULT_BINARY
    if not path.is_file():
        message = f"zipapp not found at {path} — run `make build` first"
        if os.environ.get("JEEVES_E2E_REQUIRE"):
            pytest.fail(message)
        pytest.skip(message)
    if not os.access(path, os.X_OK):
        pytest.fail(f"{path} is not executable — `chmod +x` it after download")
    return path


@pytest.fixture
def sandbox(tmp_path):
    """Per-scenario HOME, XDG dirs and cwd."""
    dirs = {n: tmp_path / n for n in ("home", "cache", "config", "state", "cwd")}
    for directory in dirs.values():
        directory.mkdir(parents=True)
    return dirs


@pytest.fixture
def cli_env(sandbox, shiv_root):
    """A hermetic environment for the subprocess.

    An allowlist, not a blocklist. Each entry below closes a trap found by
    reading the source rather than by guessing.
    """
    env = {key: os.environ[key] for key in _PASSTHROUGH if key in os.environ}
    env.update(
        # xdg._xdg_override only honours a value when Path(value).is_absolute()
        # (xdg.py), otherwise falling back to Path.home() — so a relative path
        # here would quietly write into the developer's real cache.
        HOME=str(sandbox["home"]),
        XDG_CACHE_HOME=str(sandbox["cache"]),
        XDG_CONFIG_HOME=str(sandbox["config"]),
        XDG_STATE_HOME=str(sandbox["state"]),
        SHIV_ROOT=str(shiv_root),
        # Otherwise every run hits the GitHub releases API and may print a
        # banner that the stream-discipline scenarios would then see.
        JEEVES_NO_UPDATE_CHECK="1",
        # render.py compares table width against shutil.get_terminal_size(),
        # which honours COLUMNS; unset in a pipe it falls back to 80 and the
        # renderer starts *dropping columns*.
        COLUMNS="200",
        LINES="50",
        LC_ALL="C.UTF-8",
        LANG="C.UTF-8",
        PYTHONIOENCODING="utf-8",
        PYTHONUNBUFFERED="1",
        TZ="UTC",
    )
    return env


@pytest.fixture
def run_jeeves(jeeves_binary, cli_env, sandbox):
    """Run the zipapp and capture its real streams.

    ``cwd`` is a temp directory because xdg.get_config_paths() includes
    ``Path.cwd() / ".jeeves.toml"``, so a stray config in the repo root would
    otherwise change results.
    """

    def _run(args, *, timeout=int(os.environ.get("JEEVES_E2E_TIMEOUT", "90"))):
        argv = [str(jeeves_binary), *args]
        try:
            completed = subprocess.run(
                argv,
                cwd=sandbox["cwd"],
                env=cli_env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            pytest.fail(
                f"`{shlex.join(argv)}` timed out after {timeout}s\n"
                f"--- stdout ---\n{exc.stdout}\n--- stderr ---\n{exc.stderr}"
            )
        return RunResult(argv, completed.returncode, completed.stdout, completed.stderr)

    return _run
