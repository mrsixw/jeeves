import json
from datetime import datetime, timedelta, timezone

import requests_mock as req_mock

from fiveclis import updater as upd


def test_parse_version_tuple_basic():
    assert upd._parse_version_tuple("1.2.3") == (1, 2, 3)


def test_parse_version_tuple_prerelease():
    assert upd._parse_version_tuple("1.0.0a1") == (1, 0, 0)


def test_parse_version_tuple_empty():
    assert upd._parse_version_tuple("") == ()


def test_get_release_summary_bullets():
    body = "## What's new\n- Fix A\n- Fix B\n- Fix C\n- Fix D"
    summary = upd.get_release_summary(body)
    assert "Fix A" in summary
    assert "Fix D" not in summary  # only first 3


def test_get_release_summary_strips_urls():
    body = "- See https://example.com for details"
    summary = upd.get_release_summary(body)
    assert "https://" not in summary


def test_get_release_summary_truncates():
    body = "- " + "x" * 300
    summary = upd.get_release_summary(body, max_chars=50)
    assert len(summary) <= 50


def test_get_release_summary_empty():
    assert upd.get_release_summary("") == ""


def test_get_latest_version_from_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(upd, "_CACHE_DIR", tmp_path)
    cache_file = tmp_path / "latest_version.json"
    cache_file.write_text(
        json.dumps(
            {
                "latest_version": "9.9.9",
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    )
    assert upd.get_latest_version() == "9.9.9"


def test_get_latest_version_expired_cache_fetches_api(tmp_path, monkeypatch):
    monkeypatch.setattr(upd, "_CACHE_DIR", tmp_path)
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    cache_file = tmp_path / "latest_version.json"
    cache_file.write_text(json.dumps({"latest_version": "0.0.1", "checked_at": old}))

    with req_mock.Mocker() as m:
        m.get(
            f"https://api.github.com/repos/{upd._UPDATE_CHECK_REPO}/releases/latest",
            json={"tag_name": "v2.0.0", "body": None},
        )
        result = upd.get_latest_version()
    assert result == "2.0.0"
