import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests_mock as req_mock

from jeeves import updater as upd


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


def test_check_for_update_returns_butler_styled_message(monkeypatch):
    monkeypatch.setattr(upd, "pkg_version", lambda name: "1.0.0")
    monkeypatch.setattr(upd, "get_latest_version", lambda: "2.0.0")
    msg = upd.check_for_update()
    assert msg.startswith("📦 ") and not msg.startswith("📦  ")
    assert "sir" not in msg.lower()
    assert "v1.0.0" in msg and "v2.0.0" in msg


def test_check_for_update_no_update_available(monkeypatch):
    monkeypatch.setattr(upd, "pkg_version", lambda name: "2.0.0")
    monkeypatch.setattr(upd, "get_latest_version", lambda: "2.0.0")
    assert upd.check_for_update() is None


def test_check_for_update_with_summary_appends_release_notes(monkeypatch):
    monkeypatch.setattr(upd, "pkg_version", lambda name: "1.0.0")
    monkeypatch.setattr(upd, "get_latest_version", lambda: "2.0.0")
    monkeypatch.setattr(upd, "_read_cached_release_body", lambda: "- Fix A\n- Fix B")
    msg = upd.check_for_update(show_summary=True)
    assert "📋 " in msg
    assert "Fix A" in msg


_INSTALL_DIR = Path("/usr/local/bin")


@pytest.fixture
def installed_exe(fs):
    """A fake installed jeeves binary on pyfakefs' filesystem."""
    fs.create_file(_INSTALL_DIR / "jeeves", contents="old binary")
    return _INSTALL_DIR / "jeeves"


def test_perform_update_up_to_date_leaves_executable_untouched(
    monkeypatch, installed_exe
):
    monkeypatch.setattr(upd, "pkg_version", lambda name: "2.0.0")
    monkeypatch.setattr(upd, "get_latest_version", lambda: "2.0.0")

    status, current, detail = upd.perform_update(installed_exe)

    assert status is upd.UpdateStatus.UP_TO_DATE
    assert current == "2.0.0"
    assert detail == "2.0.0"
    assert installed_exe.read_text() == "old binary"


def test_perform_update_unknown_when_latest_cannot_be_determined(
    monkeypatch, installed_exe
):
    monkeypatch.setattr(upd, "pkg_version", lambda name: "1.0.0")
    monkeypatch.setattr(upd, "get_latest_version", lambda: None)

    status, current, detail = upd.perform_update(installed_exe)

    assert status is upd.UpdateStatus.UNKNOWN
    assert current == "1.0.0"
    assert detail is None
    assert installed_exe.read_text() == "old binary"


def test_perform_update_downloads_and_replaces_executable(monkeypatch, installed_exe):
    monkeypatch.setattr(upd, "pkg_version", lambda name: "1.0.0")
    monkeypatch.setattr(upd, "get_latest_version", lambda: "2.0.0")

    with req_mock.Mocker() as m:
        m.get(upd._RELEASE_ASSET_URL, content=b"new binary content")
        status, current, detail = upd.perform_update(installed_exe)

    assert status is upd.UpdateStatus.UPDATED
    assert current == "1.0.0"
    assert detail == "2.0.0"
    assert installed_exe.read_bytes() == b"new binary content"
    assert installed_exe.stat().st_mode & 0o111
    assert not (_INSTALL_DIR / "jeeves.new").exists()


def test_perform_update_download_failure_leaves_executable_untouched(
    monkeypatch, installed_exe
):
    monkeypatch.setattr(upd, "pkg_version", lambda name: "1.0.0")
    monkeypatch.setattr(upd, "get_latest_version", lambda: "2.0.0")

    with req_mock.Mocker() as m:
        m.get(upd._RELEASE_ASSET_URL, status_code=500)
        status, current, detail = upd.perform_update(installed_exe)

    assert status is upd.UpdateStatus.ERROR
    assert current == "1.0.0"
    assert detail
    assert installed_exe.read_text() == "old binary"
    assert not (_INSTALL_DIR / "jeeves.new").exists()
