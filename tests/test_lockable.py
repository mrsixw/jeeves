"""Tests for the Lockable Resources plugin surface."""

from urllib.parse import parse_qs

import pytest
import requests_mock as req_mock

from jeeves.jenkins import JenkinsClient, JenkinsHTTPError
from jeeves.lockable import LockableError, LockableResources, resource_records

BASE = "http://jenkins.example.com"
ROSTER = f"{BASE}/lockable-resources/api/json"


@pytest.fixture
def lockable() -> LockableResources:
    client = JenkinsClient(BASE, "admin", "secret")
    client._crumb_fetched = True  # skip crumb in non-crumb tests
    return LockableResources(client)


def _resource(name: str = "r1", **overrides) -> dict:
    item = {
        "name": name,
        "description": "",
        "labels": "",
        "labelsAsList": [],
        "free": True,
        "reserved": False,
        "locked": False,
        "reservedBy": None,
    }
    item.update(overrides)
    return item


def _me(m: req_mock.Mocker, user: str = "admin") -> None:
    m.get(f"{BASE}/me/api/json", json={"id": user, "fullName": user.title()})


# ── resource_records ─────────────────────────────────────────────────────────


def test_records_derive_state_from_booleans() -> None:
    raw = [
        _resource("free-one"),
        _resource("held", free=False, reserved=True, reservedBy="bertie"),
        _resource("busy", free=False, locked=True, lockCause="build #7"),
    ]
    states = [r["state"] for r in resource_records(raw, BASE)]
    assert states == ["free", "reserved", "locked"]


def test_records_prefer_locked_over_reserved() -> None:
    """A resource both locked and reserved reads as locked."""
    raw = [_resource(free=False, locked=True, reserved=True, reservedBy="bertie")]
    assert resource_records(raw, BASE)[0]["state"] == "locked"


def test_records_use_labels_as_list() -> None:
    raw = [_resource(labels="db staging", labelsAsList=["db", "staging"])]
    assert resource_records(raw, BASE)[0]["labels"] == ["db", "staging"]


def test_records_fall_back_to_splitting_the_label_string() -> None:
    """Older payloads may omit labelsAsList."""
    raw = [{"name": "r1", "labels": "db staging"}]
    assert resource_records(raw, BASE)[0]["labels"] == ["db", "staging"]


def test_records_keep_reserved_timestamp_raw() -> None:
    """Plugin versions differ on ISO string versus epoch millis."""
    raw = [_resource(reservedTimestamp=1700000000000)]
    assert resource_records(raw, BASE)[0]["reserved_at"] == 1700000000000
    raw = [_resource(reservedTimestamp="2026-01-01T00:00:00Z")]
    assert resource_records(raw, BASE)[0]["reserved_at"] == "2026-01-01T00:00:00Z"


def test_records_point_at_the_roster_page() -> None:
    assert resource_records([_resource()], BASE)[0]["url"] == (
        f"{BASE}/lockable-resources/"
    )


def test_records_normalise_missing_fields_to_empty_strings() -> None:
    record = resource_records([{"name": "r1"}], BASE)[0]
    assert record["description"] == ""
    assert record["reserved_by"] == ""
    assert record["lock_cause"] == ""
    assert record["ephemeral"] is False


# ── reading ──────────────────────────────────────────────────────────────────


def test_resources_returns_the_roster(lockable: LockableResources) -> None:
    with req_mock.Mocker() as m:
        m.get(ROSTER, json={"resources": [_resource("r1"), _resource("r2")]})
        names = [item["name"] for item in lockable.resources()]
    assert names == ["r1", "r2"]


def test_resources_handles_an_empty_payload(lockable: LockableResources) -> None:
    with req_mock.Mocker() as m:
        m.get(ROSTER, json={})
        assert lockable.resources() == []


def test_resources_404_means_the_plugin_is_missing(
    lockable: LockableResources,
) -> None:
    with req_mock.Mocker() as m:
        m.get(ROSTER, status_code=404)
        with pytest.raises(LockableError) as excinfo:
            lockable.resources()
    assert excinfo.value.reason == "plugin-missing"


def test_resources_other_errors_propagate(lockable: LockableResources) -> None:
    with req_mock.Mocker() as m:
        m.get(ROSTER, status_code=403)
        with pytest.raises(JenkinsHTTPError, match="403"):
            lockable.resources()


def test_resource_finds_by_name(lockable: LockableResources) -> None:
    with req_mock.Mocker() as m:
        m.get(ROSTER, json={"resources": [_resource("r1"), _resource("r2")]})
        assert lockable.resource("r2")["name"] == "r2"


def test_resource_unknown_returns_none(lockable: LockableResources) -> None:
    with req_mock.Mocker() as m:
        m.get(ROSTER, json={"resources": [_resource("r1")]})
        assert lockable.resource("nope") is None


# ── reserve ──────────────────────────────────────────────────────────────────


def test_reserve_posts_resource_and_reason(lockable: LockableResources) -> None:
    with req_mock.Mocker() as m:
        adapter = m.post(f"{BASE}/lockable-resources/reserve", status_code=200)
        assert lockable.reserve("r1", "migration") == "reserved"
    assert parse_qs(adapter.last_request.text) == {
        "resource": ["r1"],
        "reason": ["migration"],
    }


def test_reserve_omits_an_empty_reason(lockable: LockableResources) -> None:
    with req_mock.Mocker() as m:
        adapter = m.post(f"{BASE}/lockable-resources/reserve", status_code=200)
        lockable.reserve("r1")
    assert parse_qs(adapter.last_request.text) == {"resource": ["r1"]}


def test_reserve_busy_names_the_holder(lockable: LockableResources) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/lockable-resources/reserve", status_code=423)
        m.get(
            ROSTER,
            json={"resources": [_resource("r1", free=False, reservedBy="bertie")]},
        )
        _me(m)
        with pytest.raises(LockableError) as excinfo:
            lockable.reserve("r1")
    assert excinfo.value.reason == "busy"
    assert excinfo.value.holder == "bertie"


def test_reserve_already_ours_is_idempotent(lockable: LockableResources) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/lockable-resources/reserve", status_code=423)
        m.get(
            ROSTER,
            json={"resources": [_resource("r1", free=False, reservedBy="admin")]},
        )
        _me(m, "admin")
        assert lockable.reserve("r1") == "already"


def test_reserve_unreadable_identity_still_reports_busy(
    lockable: LockableResources,
) -> None:
    """An unreadable /me degrades to the plain busy message, not a failure."""
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/lockable-resources/reserve", status_code=423)
        m.get(
            ROSTER,
            json={"resources": [_resource("r1", free=False, reservedBy="admin")]},
        )
        m.get(f"{BASE}/me/api/json", status_code=403)
        with pytest.raises(LockableError) as excinfo:
            lockable.reserve("r1")
    assert excinfo.value.reason == "busy"
    assert excinfo.value.holder == "admin"


def test_reserve_unauthenticated(lockable: LockableResources) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/lockable-resources/reserve", status_code=401)
        with pytest.raises(LockableError) as excinfo:
            lockable.reserve("r1")
    assert excinfo.value.reason == "unauthenticated"


# ── unreserve, unlock, reset ─────────────────────────────────────────────────


def test_unreserve_posts_the_resource(lockable: LockableResources) -> None:
    with req_mock.Mocker() as m:
        adapter = m.post(f"{BASE}/lockable-resources/unreserve", status_code=200)
        assert lockable.unreserve("r1") == "unreserved"
    assert parse_qs(adapter.last_request.text) == {"resource": ["r1"]}


def test_unreserve_of_a_free_resource_is_idempotent(
    lockable: LockableResources,
) -> None:
    """Jenkins 403s a non-admin releasing a reservation nobody holds."""
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/lockable-resources/unreserve", status_code=403)
        m.get(ROSTER, json={"resources": [_resource("r1", free=True)]})
        assert lockable.unreserve("r1") == "already"


def test_unreserve_of_a_locked_but_unreserved_resource_is_idempotent(
    lockable: LockableResources,
) -> None:
    """A build's lock makes a resource unfree while leaving nothing reserved."""
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/lockable-resources/unreserve", status_code=403)
        m.get(
            ROSTER,
            json={
                "resources": [_resource("r1", free=False, locked=True, reservedBy=None)]
            },
        )
        assert lockable.unreserve("r1") == "already"


def test_unreserve_of_someone_elses_is_forbidden(lockable: LockableResources) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/lockable-resources/unreserve", status_code=403)
        m.get(
            ROSTER,
            json={"resources": [_resource("r1", free=False, reservedBy="bertie")]},
        )
        with pytest.raises(LockableError) as excinfo:
            lockable.unreserve("r1")
    assert excinfo.value.reason == "forbidden"


def test_unlock_posts_the_resource(lockable: LockableResources) -> None:
    with req_mock.Mocker() as m:
        m.get(ROSTER, json={"resources": [_resource("r1", free=False, locked=True)]})
        adapter = m.post(f"{BASE}/lockable-resources/unlock", status_code=200)
        assert lockable.unlock("r1") == "unlocked"
    assert parse_qs(adapter.last_request.text) == {"resource": ["r1"]}


def test_unlock_of_an_unlocked_resource_is_idempotent(
    lockable: LockableResources,
) -> None:
    """Upstream answers 200 either way, so this reads before it writes."""
    with req_mock.Mocker() as m:
        m.get(ROSTER, json={"resources": [_resource("r1", locked=False)]})
        adapter = m.post(f"{BASE}/lockable-resources/unlock", status_code=200)
        assert lockable.unlock("r1") == "already"
    assert adapter.call_count == 0


def test_unlock_of_an_unknown_resource_is_unknown(
    lockable: LockableResources,
) -> None:
    with req_mock.Mocker() as m:
        m.get(ROSTER, json={"resources": []})
        with pytest.raises(LockableError) as excinfo:
            lockable.unlock("r1")
    assert excinfo.value.reason == "unknown"


def test_reset_posts_the_resource(lockable: LockableResources) -> None:
    with req_mock.Mocker() as m:
        m.get(ROSTER, json={"resources": [_resource("r1", free=False, locked=True)]})
        adapter = m.post(f"{BASE}/lockable-resources/reset", status_code=200)
        assert lockable.reset("r1") == "reset"
    assert parse_qs(adapter.last_request.text) == {"resource": ["r1"]}


def test_reset_of_a_free_resource_is_idempotent(lockable: LockableResources) -> None:
    with req_mock.Mocker() as m:
        m.get(ROSTER, json={"resources": [_resource("r1", free=True)]})
        adapter = m.post(f"{BASE}/lockable-resources/reset", status_code=200)
        assert lockable.reset("r1") == "already"
    assert adapter.call_count == 0


def test_unlock_forbidden_is_a_permission_problem(
    lockable: LockableResources,
) -> None:
    """Only unreserve has an idempotent 403; a 403 on unlock is a permission."""
    with req_mock.Mocker() as m:
        m.get(ROSTER, json={"resources": [_resource("r1", free=False, locked=True)]})
        m.post(f"{BASE}/lockable-resources/unlock", status_code=403)
        with pytest.raises(LockableError) as excinfo:
            lockable.unlock("r1")
    assert excinfo.value.reason == "forbidden"


# ── create and delete ────────────────────────────────────────────────────────


def test_create_posts_space_separated_labels(lockable: LockableResources) -> None:
    with req_mock.Mocker() as m:
        adapter = m.post(f"{BASE}/lockable-resources/createResource", status_code=200)
        assert lockable.create("r1", "the prod database", ("db", "prod")) == "created"
    assert parse_qs(adapter.last_request.text) == {
        "name": ["r1"],
        "description": ["the prod database"],
        "labels": ["db prod"],
    }


def test_create_existing_is_idempotent(lockable: LockableResources) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/lockable-resources/createResource", status_code=409)
        assert lockable.create("r1") == "already"


def test_create_404_with_a_working_roster_means_an_old_plugin(
    lockable: LockableResources,
) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/lockable-resources/createResource", status_code=404)
        m.get(ROSTER, json={"resources": []})
        with pytest.raises(LockableError) as excinfo:
            lockable.create("r1")
    assert excinfo.value.reason == "endpoint-missing"


def test_create_404_with_a_404_roster_means_no_plugin(
    lockable: LockableResources,
) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/lockable-resources/createResource", status_code=404)
        m.get(ROSTER, status_code=404)
        with pytest.raises(LockableError) as excinfo:
            lockable.create("r1")
    assert excinfo.value.reason == "plugin-missing"


def test_delete_posts_the_resource(lockable: LockableResources) -> None:
    with req_mock.Mocker() as m:
        adapter = m.post(f"{BASE}/lockable-resources/deleteResource", status_code=200)
        assert lockable.delete("r1") == "deleted"
    assert parse_qs(adapter.last_request.text) == {"resource": ["r1"]}


def test_delete_404_of_an_absent_resource_is_idempotent(
    lockable: LockableResources,
) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/lockable-resources/deleteResource", status_code=404)
        m.get(ROSTER, json={"resources": [_resource("other")]})
        assert lockable.delete("r1") == "already"


def test_delete_404_of_a_listed_resource_means_an_old_plugin(
    lockable: LockableResources,
) -> None:
    """The endpoint is missing, not the resource — it is right there on the roster."""
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/lockable-resources/deleteResource", status_code=404)
        m.get(ROSTER, json={"resources": [_resource("r1")]})
        with pytest.raises(LockableError) as excinfo:
            lockable.delete("r1")
    assert excinfo.value.reason == "endpoint-missing"


def test_delete_busy_resource(lockable: LockableResources) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/lockable-resources/deleteResource", status_code=423)
        with pytest.raises(LockableError) as excinfo:
            lockable.delete("r1")
    assert excinfo.value.reason == "busy"


# ── the 404 ambiguity ────────────────────────────────────────────────────────


def test_reserve_404_with_a_404_roster_means_no_plugin(
    lockable: LockableResources,
) -> None:
    """With the plugin absent there is no reserve endpoint either."""
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/lockable-resources/reserve", status_code=404)
        m.get(ROSTER, status_code=404)
        with pytest.raises(LockableError) as excinfo:
            lockable.reserve("r1")
    assert excinfo.value.reason == "plugin-missing"


def test_reserve_404_with_a_working_roster_means_an_unknown_resource(
    lockable: LockableResources,
) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/lockable-resources/reserve", status_code=404)
        m.get(ROSTER, json={"resources": []})
        with pytest.raises(LockableError) as excinfo:
            lockable.reserve("r1")
    assert excinfo.value.reason == "unknown"


def test_a_forbidden_roster_probe_propagates_rather_than_guessing(
    lockable: LockableResources,
) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/lockable-resources/reserve", status_code=404)
        m.get(ROSTER, status_code=403)
        with pytest.raises(JenkinsHTTPError, match="403"):
            lockable.reserve("r1")


def test_unexpected_status_propagates_unwrapped(lockable: LockableResources) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/lockable-resources/reserve", status_code=500)
        with pytest.raises(JenkinsHTTPError) as excinfo:
            lockable.reserve("r1")
    assert not isinstance(excinfo.value, LockableError)
    assert excinfo.value.status == 500
