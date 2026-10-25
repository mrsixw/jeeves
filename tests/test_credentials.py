"""Tests for the Credentials plugin surface (metadata only)."""

import pytest
import requests_mock as req_mock

from jeeves.credentials import CredentialsError, CredentialStores, credential_records
from jeeves.jenkins import JenkinsClient, JenkinsHTTPError

BASE = "http://jenkins.example.com"
ROOT = f"{BASE}/credentials/api/json"
FOLDER = f"{BASE}/job/team/credentials/api/json"
NESTED = f"{BASE}/job/team/job/app/credentials/api/json"


@pytest.fixture
def stores() -> CredentialStores:
    return CredentialStores(JenkinsClient(BASE, "admin", "secret"))


def _cred(cid: str, type_name: str = "Secret text", **overrides) -> dict:
    body = {
        "id": cid,
        "displayName": f"{cid} display",
        "typeName": type_name,
        "description": f"{cid} description",
    }
    body.update(overrides)
    return body


def _payload(store: str = "system", **domains: list[dict]) -> dict:
    """``_payload(_=[...], prod=[...])`` → one store with those domains."""
    return {
        "stores": {
            store: {
                "domains": {
                    key: {
                        "urlName": key,
                        "displayName": "Global" if key == "_" else key,
                        "credentials": creds,
                    }
                    for key, creds in domains.items()
                }
            }
        }
    }


# ── visible ──────────────────────────────────────────────────────────────────


def test_visible_flattens_the_root_stores(stores) -> None:
    with req_mock.Mocker() as m:
        m.get(ROOT, json=_payload(_=[_cred("gh-token")]))
        (entry,) = stores.visible()
    assert entry == {
        "id": "gh-token",
        "name": "gh-token display",
        "type": "Secret text",
        "description": "gh-token description",
        "store": "system",
        "domain": "Global",
        "domain_key": "_",
        "folder": "",
    }


def test_visible_pins_a_metadata_only_tree(stores) -> None:
    """Nothing beyond the exported metadata is ever asked for."""
    with req_mock.Mocker() as m:
        m.get(ROOT, json={"stores": {}})
        stores.visible()
        tree = m.last_request.qs["tree"][0]
    assert tree == (
        "stores[domains[urlname,displayname,"
        "credentials[id,displayname,typename,description]]]"
    )
    for forbidden in ("secret", "password", "fingerprint", "privatekey"):
        assert forbidden not in tree


def test_visible_orders_the_global_domain_first(stores) -> None:
    with req_mock.Mocker() as m:
        m.get(ROOT, json=_payload(aaa=[_cred("a")], _=[_cred("g")], zzz=[_cred("z")]))
        ids = [e["id"] for e in stores.visible()]
    assert ids == ["g", "a", "z"]


def test_visible_tolerates_empty_and_null_shapes(stores) -> None:
    payload = {"stores": {"system": {"domains": {"_": {"credentials": None}}}}}
    with req_mock.Mocker() as m:
        m.get(ROOT, json=payload)
        assert stores.visible() == []


def test_visible_from_a_folder_walks_up_to_the_root(stores) -> None:
    """A context exports only its own stores; inheritance is ours to walk."""
    with req_mock.Mocker() as m:
        m.get(ROOT, json=_payload(_=[_cred("root-cred")]))
        m.get(FOLDER, json=_payload("folder", _=[_cred("team-cred")]))
        m.get(NESTED, json=_payload("folder", _=[_cred("app-cred")]))
        entries = stores.visible("team/app")
    assert [(e["id"], e["folder"], e["store"]) for e in entries] == [
        ("app-cred", "team/app", "folder"),
        ("team-cred", "team", "folder"),
        ("root-cred", "", "system"),
    ]


def test_visible_ignores_stray_slashes_in_the_folder(stores) -> None:
    with req_mock.Mocker() as m:
        m.get(ROOT, json={"stores": {}})
        m.get(FOLDER, json=_payload("folder", _=[_cred("t")]))
        assert [e["folder"] for e in stores.visible("/team/")] == ["team"]


def test_root_404_means_the_plugin_is_missing(stores) -> None:
    with req_mock.Mocker() as m:
        m.get(ROOT, status_code=404)
        with pytest.raises(CredentialsError) as exc:
            stores.visible()
    assert exc.value.reason == "plugin-missing"


def test_folder_404_with_the_plugin_present_means_no_such_folder(stores) -> None:
    with req_mock.Mocker() as m:
        m.get(ROOT, json={"stores": {}})
        m.get(FOLDER, status_code=404)
        with pytest.raises(CredentialsError) as exc:
            stores.visible("team")
    assert (exc.value.reason, exc.value.detail) == ("no-folder", "team")


def test_plugin_missing_wins_over_a_missing_folder(stores) -> None:
    """The root is read first, so an absent plugin is not blamed on the folder."""
    with req_mock.Mocker() as m:
        m.get(ROOT, status_code=404)
        m.get(FOLDER, status_code=404)
        with pytest.raises(CredentialsError) as exc:
            stores.visible("team")
    assert exc.value.reason == "plugin-missing"


def test_a_forbidden_read_propagates(stores) -> None:
    with req_mock.Mocker() as m:
        m.get(ROOT, status_code=403)
        with pytest.raises(JenkinsHTTPError) as exc:
            stores.visible()
    assert exc.value.status == 403


# ── credential ───────────────────────────────────────────────────────────────


def test_credential_finds_one_by_id(stores) -> None:
    with req_mock.Mocker() as m:
        m.get(ROOT, json=_payload(_=[_cred("a"), _cred("b")]))
        assert [e["id"] for e in stores.credential("b")] == ["b"]


def test_credential_returns_every_shadowing_copy_nearest_first(stores) -> None:
    with req_mock.Mocker() as m:
        m.get(ROOT, json=_payload(_=[_cred("deploy")]))
        m.get(FOLDER, json=_payload("folder", _=[_cred("deploy")]))
        found = stores.credential("deploy", "team")
    assert [e["folder"] for e in found] == ["team", ""]


def test_credential_unknown_is_named(stores) -> None:
    with req_mock.Mocker() as m:
        m.get(ROOT, json=_payload(_=[_cred("a")]))
        with pytest.raises(CredentialsError) as exc:
            stores.credential("nope")
    assert (exc.value.reason, exc.value.detail) == ("unknown", "nope")


# ── credential_records ───────────────────────────────────────────────────────


def _entry(**overrides) -> dict:
    entry = {
        "id": "gh-token",
        "name": "GitHub",
        "type": "Secret text",
        "description": "",
        "store": "system",
        "domain": "Global",
        "domain_key": "_",
        "folder": "",
    }
    entry.update(overrides)
    return entry


def test_records_link_to_the_credential_page() -> None:
    (record,) = credential_records([_entry()], f"{BASE}/")
    assert record["url"] == (
        f"{BASE}/credentials/store/system/domain/_/credential/gh-token/"
    )


def test_records_link_through_nested_folders() -> None:
    (record,) = credential_records(
        [_entry(store="folder", folder="team/app", domain_key="prod")], BASE
    )
    assert record["url"] == (
        f"{BASE}/job/team/job/app/credentials/store/folder/domain/prod"
        "/credential/gh-token/"
    )


def test_records_url_encode_awkward_ids() -> None:
    (record,) = credential_records([_entry(id="a b/c")], BASE)
    assert record["url"].endswith("/credential/a%20b%2Fc/")


def test_records_carry_no_internal_keys() -> None:
    (record,) = credential_records([_entry()], BASE)
    assert set(record) == {
        "id",
        "name",
        "type",
        "description",
        "store",
        "domain",
        "folder",
        "url",
    }
