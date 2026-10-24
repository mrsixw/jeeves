"""Step definitions that need a real Jenkins.

Kept apart from ``steps.py``, which knows only about running the binary and
reading its streams. Anything here pulls in the ``jenkins_container`` fixture
and so costs a container boot.

The fixture's job names are fixed and spelled literally in the feature files —
``e2e-freestyle``, ``e2e-pipeline``, ``e2e-folder/nested``. That is deliberate:
interpolating them would need placeholder syntax that collides with Gherkin's
own ``<...>`` outline parameters, and the literal names read better. The
``fixture inventory`` scenario guards the duplication, so a rename produces one
obvious failure rather than a dozen confusing ones.
"""

import json
import time

import pytest
import requests
from pytest_bdd import given, parsers, then

# No __all__ in this module, deliberately — and it must stay that way.
# conftest.py pulls these steps in with `import *`, which respects __all__;
# an empty one silently imports nothing, the generated `pytestbdd_stepdef_*`
# fixtures never arrive, and every scenario fails with
# StepDefinitionNotFoundError rather than anything pointing at the cause.
# The project's "every module declares __all__" rule covers src/jeeves/, not
# this package.


@given("a Jenkins estate")
def _jenkins_estate(cli_env, jenkins_container):
    """Point jeeves at the fixture Jenkins, with a real API token.

    These are the only three variables the suite injects. jeeves resolves them
    exactly as it would a user's shell environment, so nothing about the
    configuration path is faked.
    """
    cli_env["JEEVES_URL"] = jenkins_container.base_url
    cli_env["JEEVES_USER"] = jenkins_container.user
    cli_env["JEEVES_TOKEN"] = jenkins_container.token


@given("the credentials are wrong")
def _bad_credentials(cli_env, jenkins_container):
    """A reachable Jenkins that rejects us.

    Distinct from an unreachable one, and worth proving separately: the
    estate answers, the token does not. Only a real Jenkins settles which
    status it uses to say so.
    """
    cli_env["JEEVES_URL"] = jenkins_container.base_url
    cli_env["JEEVES_USER"] = jenkins_container.user
    cli_env["JEEVES_TOKEN"] = "definitely-not-a-valid-token"


@then("the fixture inventory is as documented")
def _inventory(jenkins_container):
    """One assertion covering every name the feature files hardcode.

    Drift in the fixture then fails here, once and legibly, instead of
    surfacing as a scatter of "job not found" errors across the suite.
    """
    assert jenkins_container.freestyle_job == "e2e-freestyle"
    assert jenkins_container.pipeline_job == "e2e-pipeline"
    assert jenkins_container.folder == "e2e-folder"
    assert jenkins_container.nested_job == "nested"
    assert jenkins_container.nested_path == "e2e-folder/nested"
    assert jenkins_container.input_waiter_job == "e2e-input-waiter"


@then(parsers.parse('the Jenkins job "{job}" has at least {count:d} build'))
@then(parsers.parse('the Jenkins job "{job}" has at least {count:d} builds'))
def _job_has_builds(jenkins_container, job, count):
    """Confirm against Jenkins directly, not through jeeves.

    Asserting a mutation happened by reading it back with the tool that
    performed it proves only that the tool is self-consistent. This asks
    Jenkins.
    """
    resp = requests.get(
        f"{jenkins_container.base_url}/job/{job}/api/json",
        params={"tree": "builds[number]"},
        auth=(jenkins_container.user, jenkins_container.token),
        timeout=15,
    )
    assert (
        resp.status_code == 200
    ), f"Jenkins said {resp.status_code}: {resp.text[:200]}"
    builds = resp.json().get("builds", [])
    assert (
        len(builds) >= count
    ), f"expected at least {count} build(s) of {job!r}, Jenkins reports {len(builds)}"


@then(parsers.parse('every record in the JSON payload has a "{key}" key'))
def _payload_keys(payload, key):
    assert isinstance(
        payload, list
    ), f"expected a JSON array, got {type(payload).__name__}"
    assert payload, "the JSON payload was empty, so the key assertion proves nothing"
    missing = [r for r in payload if key not in r]
    assert (
        not missing
    ), f"{len(missing)} record(s) lack {key!r}: {json.dumps(missing[:2])}"


def _resources(jenkins_container):
    """The plugin's own roster, read directly rather than through jeeves."""
    resp = requests.get(
        f"{jenkins_container.base_url}/lockable-resources/api/json",
        auth=(jenkins_container.user, jenkins_container.token),
        timeout=15,
    )
    assert (
        resp.status_code == 200
    ), f"the plugin's roster said {resp.status_code}: {resp.text[:200]}"
    return {r["name"]: r for r in resp.json().get("resources", [])}


@then("the lockable fixture inventory is as documented")
def _lockable_inventory(jenkins_container):
    """Guard the resource names the lockable feature file spells literally.

    Same reasoning as ``the fixture inventory is as documented``: a rename
    fails here, once, instead of as a scatter of "no resource by that name"
    errors across the file.

    Unlike the job inventory, this asks **Jenkins** rather than comparing the
    fixture's own attributes to literals. The jobs are created by the fixture,
    so its attributes are the source of truth for them; the resources are
    declared in casc.yaml, so the fixture's names are a second copy. Checking
    the copy against itself would pass happily while casc.yaml drifted — which
    is the one failure this scenario exists to catch.
    """
    assert jenkins_container.lock_holder_job == "e2e-lock-holder"

    found = _resources(jenkins_container)
    expected = {
        "e2e-lock-free": {"e2e-pool", "linux"},
        "e2e-lock-spare": {"e2e-pool"},
        "e2e-lock-held": {"e2e-held"},
    }
    assert set(expected) <= set(found), (
        f"casc.yaml declares {sorted(found)}, but the feature file expects "
        f"{sorted(expected)}"
    )
    for name, labels in expected.items():
        actual = set(found[name].get("labelsAsList") or [])
        assert actual == labels, (
            f"{name!r} carries labels {sorted(actual)}, "
            f"the scenarios expect {sorted(labels)}"
        )

    # The fixture's own copies, so a scenario reading them agrees with Jenkins.
    assert jenkins_container.free_resource == "e2e-lock-free"
    assert jenkins_container.spare_resource == "e2e-lock-spare"
    assert jenkins_container.held_resource == "e2e-lock-held"
    assert jenkins_container.pool_label == "e2e-pool"


@then(parsers.parse('Jenkins reports the resource "{name}" as reserved by "{who}"'))
def _reserved_by(jenkins_container, name, who):
    """Confirm a reservation against the plugin, not against jeeves.

    Reading a mutation back with the tool that made it proves only that the
    tool is self-consistent.
    """
    found = _resources(jenkins_container)
    assert name in found, f"no resource named {name!r}; saw {sorted(found)}"
    assert found[name].get("reservedBy") == who, (
        f"expected {name!r} reserved by {who!r}, "
        f"the plugin says {found[name].get('reservedBy')!r}"
    )


@then(parsers.parse('Jenkins reports the resource "{name}" as free'))
def _resource_free(jenkins_container, name):
    found = _resources(jenkins_container)
    assert name in found, f"no resource named {name!r}; saw {sorted(found)}"
    r = found[name]
    assert r.get("free") and not r.get("reservedBy"), (
        f"expected {name!r} to be free, the plugin says "
        f"free={r.get('free')!r} reservedBy={r.get('reservedBy')!r}"
    )


@then(parsers.parse('Jenkins has no resource named "{name}"'))
def _resource_absent(jenkins_container, name):
    found = _resources(jenkins_container)
    assert name not in found, f"{name!r} is still on the register: {found.get(name)}"


@then(parsers.parse('Jenkins has a resource named "{name}"'))
def _resource_present(jenkins_container, name):
    found = _resources(jenkins_container)
    assert name in found, f"{name!r} is not on the register; saw {sorted(found)}"


@given(parsers.parse('a build is holding the resource "{name}"'))
def _build_holds(jenkins_container, name):
    """Trigger the holder pipeline and wait until the lock is actually taken.

    Polls the plugin rather than sleeping a guessed interval: the queue has to
    assign an executor first, and on a loaded CI runner that is not instant.
    The hold is long enough that the assertions after this step run inside it,
    and the build releases the lock on its own, so nothing needs tearing down.
    """
    resp = requests.post(
        f"{jenkins_container.base_url}"
        f"/job/{jenkins_container.lock_holder_job}/buildWithParameters",
        # A form body, not a query string — the shape Jenkins actually wants.
        data={"HOLD_SECONDS": "45"},
        auth=(jenkins_container.user, jenkins_container.token),
        timeout=30,
    )
    assert resp.status_code in (200, 201), f"trigger said {resp.status_code}"

    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        found = _resources(jenkins_container)
        if found.get(name, {}).get("locked"):
            return
        time.sleep(1)
    pytest.fail(
        f"{name!r} was never locked within 120s. The holder build may have "
        f"failed; the plugin reports {_resources(jenkins_container).get(name)}"
    )


def _get(jenkins_container, path, **params):
    resp = requests.get(
        f"{jenkins_container.base_url}/{path.lstrip('/')}",
        params=params,
        auth=(jenkins_container.user, jenkins_container.token),
        timeout=15,
    )
    return resp


def _last_build(jenkins_container, job):
    resp = _get(
        jenkins_container, f"job/{job}/lastBuild/api/json", tree="number,result"
    )
    assert resp.status_code == 200, f"lastBuild of {job!r} said {resp.status_code}"
    return resp.json()


def _pending_inputs(jenkins_container, job, number):
    """The plugin's own view of a build's pending inputs, not jeeves'."""
    resp = _get(
        jenkins_container,
        f"job/{job}/{number}/input/api/json",
        tree="executions[id,settled]",
    )
    if resp.status_code == 404:
        return []
    assert resp.status_code == 200, f"input action said {resp.status_code}"
    return [e for e in resp.json().get("executions", []) if not e.get("settled")]


@given(parsers.parse('a build of "{job}" is paused at an input'))
def _paused_at_input(jenkins_container, job):
    """Trigger the job and wait until Jenkins itself reports it paused.

    Polls the plugin rather than sleeping: the build must be queued, started,
    and reach the step before /input/ even exists.
    """
    before = _get(jenkins_container, f"job/{job}/api/json", tree="nextBuildNumber")
    assert before.status_code == 200, f"{job!r} said {before.status_code}"
    number = before.json()["nextBuildNumber"]

    resp = requests.post(
        f"{jenkins_container.base_url}/job/{job}/build",
        auth=(jenkins_container.user, jenkins_container.token),
        timeout=30,
    )
    assert resp.status_code in (200, 201), f"trigger said {resp.status_code}"

    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        build = _get(jenkins_container, f"job/{job}/{number}/api/json", tree="number")
        if build.status_code == 200 and _pending_inputs(jenkins_container, job, number):
            return
        time.sleep(1)
    pytest.fail(f"build #{number} of {job!r} never paused at an input within 120s")


@then(parsers.parse('the last build of "{job}" finishes with result "{result}"'))
def _finishes_with(jenkins_container, job, result):
    deadline = time.monotonic() + 120
    seen = None
    while time.monotonic() < deadline:
        seen = _last_build(jenkins_container, job).get("result")
        if seen is not None:
            break
        time.sleep(1)
    assert seen == result, f"expected {result!r}, Jenkins reports {seen!r}"


@then(parsers.parse('the console of the last build of "{job}" contains "{text}"'))
def _console_contains(jenkins_container, job, text):
    resp = _get(jenkins_container, f"job/{job}/lastBuild/consoleText")
    assert resp.status_code == 200, f"consoleText said {resp.status_code}"
    assert text in resp.text, f"{text!r} not in the console:\n{resp.text[-1500:]}"


@then(parsers.parse('Jenkins reports nothing pending on the last build of "{job}"'))
def _nothing_pending(jenkins_container, job):
    number = _last_build(jenkins_container, job)["number"]
    pending = _pending_inputs(jenkins_container, job, number)
    assert not pending, f"build #{number} still awaits {pending}"
