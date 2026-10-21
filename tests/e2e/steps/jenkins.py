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
