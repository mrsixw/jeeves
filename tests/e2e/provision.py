"""Bringing the fixture Jenkins up, and furnishing it.

Split out of ``conftest.py`` deliberately: that file holds fixtures and the
collection hook, and this is the part with actual logic in it — the readiness
poll, minting an API token, and creating the seed jobs.

Everything here talks to Jenkins over HTTP with ``requests`` directly rather
than through ``JenkinsClient``. That is the point: the client is the thing
under test, so the fixture must not depend on it being correct. If
``JenkinsClient`` had the bug, a fixture built on it would set up a Jenkins
that matched the bug.
"""

import socket
import time

import requests

__all__ = [
    "ProvisionError",
    "create_job",
    "free_port",
    "mint_api_token",
    "wait_until_ready",
]

# The fixture's own account, matching docker/casc.yaml. Public on purpose: the
# instance is a throwaway container, and the password is used exactly once, to
# mint the token that every jeeves invocation then uses instead.
ADMIN_USER = "jeeves-e2e"
ADMIN_PASSWORD = "jeeves-e2e-password"


class ProvisionError(Exception):
    """Raised when the fixture Jenkins could not be brought up or furnished.

    A genuine failure: something is wrong with the image, the configuration or
    the test code, and the suite should say so loudly.
    """


class NotReachable(ProvisionError):
    """Jenkins is serving inside its container but the host cannot reach it.

    A property of the host's container networking, not of jeeves or of the
    fixture — so locally this is a skip with an explanation, while in CI
    ``JEEVES_E2E_REQUIRE_DOCKER`` makes it a hard failure like any other.
    """


def free_port() -> int:
    """Ask the OS for an unused localhost port.

    Inherently racy — something could claim it between the close and the
    container binding it — but the container start then fails loudly rather
        than silently, which is the acceptable failure mode here.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_until_ready(
    base_url: str, *, timeout: float, diagnostics, classify=None
) -> None:
    """Block until Jenkins is serving, or raise ``ProvisionError``.

    Two gates, in order, because they fail differently:

    1. ``/login`` answering at all means the web tier is up. Deliberately not
       ``/api/json``, which can answer before plugins have finished loading.
    2. ``/api/json`` with credentials means the security realm from
       Configuration-as-Code has actually been applied. Without this the
       fixture can race ahead and mint a token against a Jenkins that is still
       anonymous.

    ``diagnostics`` is called on timeout and its return value appended to the
    error, so a CI failure carries the container's log rather than just a
    stopwatch reading.
    """
    deadline = time.monotonic() + timeout
    last = "no attempt completed"
    while time.monotonic() < deadline:
        try:
            resp = requests.get(f"{base_url}/login", timeout=5)
            if resp.status_code == 200:
                authed = requests.get(
                    f"{base_url}/api/json",
                    auth=(ADMIN_USER, ADMIN_PASSWORD),
                    timeout=5,
                )
                if authed.status_code == 200:
                    return
                last = (
                    "/login was 200 but authenticated /api/json was "
                    f"{authed.status_code}"
                )
            else:
                last = f"/login returned {resp.status_code}"
        except requests.exceptions.RequestException as exc:
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(2)

    # Before blaming the image, ask whether Jenkins is in fact serving and
    # merely unreachable. `classify` reports that from inside the container,
    # which is the only place the two cases look different.
    if classify is not None and classify():
        raise NotReachable(
            f"Jenkins is serving inside its container but {base_url} is not "
            "reachable from this host, so the container-backed scenarios "
            "cannot run here. Published-port forwarding is the usual "
            "culprit.\nSet JEEVES_E2E_REQUIRE_DOCKER=1 to treat this as a "
            "failure instead of a skip."
        )

    raise ProvisionError(
        f"Jenkins at {base_url} was not ready within {timeout:.0f}s "
        f"(last: {last})\n--- container logs ---\n{diagnostics()}"
    )


def _crumbed_session(auth: tuple[str, str], base_url: str) -> requests.Session:
    """A session carrying a CSRF crumb and the cookie it was issued against.

    The cookie matters and is easy to miss: Jenkins binds the crumb to the
    HTTP session, so fetching a crumb and then posting without carrying the
    cookie jar forward fails with "No valid crumb". Using one ``Session`` for
    both requests is what keeps them together.
    """
    session = requests.Session()
    session.auth = auth
    resp = session.get(f"{base_url}/crumbIssuer/api/json", timeout=10)
    if resp.status_code != 200:
        raise ProvisionError(
            f"could not fetch a CSRF crumb: {resp.status_code} {resp.text[:200]}"
        )
    data = resp.json()
    session.headers[data["crumbRequestField"]] = data["crumb"]
    return session


def mint_api_token(base_url: str, *, name: str = "jeeves-e2e") -> str:
    """Create an API token for the fixture user and return its value.

    jeeves authenticates with a username and an API token, and
    Configuration-as-Code can declare a user with a password but cannot mint a
    token. So the fixture asks Jenkins for one the way a user would, through
    the web API, using the password exactly once. Every jeeves invocation in
    the suite then uses the token — the path the project documents.
    """
    session = _crumbed_session((ADMIN_USER, ADMIN_PASSWORD), base_url)
    resp = session.post(
        f"{base_url}/me/descriptorByName/jenkins.security.ApiTokenProperty/"
        "generateNewToken",
        data={"newTokenName": name},
        timeout=15,
    )
    if resp.status_code != 200:
        raise ProvisionError(
            f"minting an API token failed: {resp.status_code} {resp.text[:300]}"
        )
    payload = resp.json()
    token = payload.get("data", {}).get("tokenValue")
    if not token:
        raise ProvisionError(f"no tokenValue in the reply: {payload}")
    return token


def create_job(
    base_url: str, *, token: str, name: str, config_xml: str, folder: str = ""
) -> None:
    """Create a job or folder from a config.xml, the way a user would.

    Jobs are created here rather than in Configuration-as-Code because they
    are per-run state rather than image state — and because ``/createItem``
    with a config.xml needs no extra plugin, where job-dsl would.

    ``folder`` nests the new item inside an existing folder. Note the URL is
    built here by hand rather than with ``normalize_jenkins_path``: that
    function is part of what the suite is testing, so using it to construct
    the fixture would let a bug in it hide itself.
    """
    prefix = f"/job/{folder}" if folder else ""
    session = _crumbed_session((ADMIN_USER, token), base_url)
    resp = session.post(
        f"{base_url}{prefix}/createItem",
        params={"name": name},
        data=config_xml.encode("utf-8"),
        headers={"Content-Type": "application/xml; charset=utf-8"},
        timeout=30,
    )
    # 200 is the success path. A job that already exists answers 400, which is
    # fine for a session-scoped fixture being reused against a live container.
    if resp.status_code not in (200, 400):
        raise ProvisionError(
            f"creating job {name!r} failed: {resp.status_code} {resp.text[:300]}"
        )
