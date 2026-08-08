import json
from datetime import datetime, timedelta, timezone

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


def test_perform_update_up_to_date_leaves_executable_untouched(monkeypatch, tmp_path):
    monkeypatch.setattr(upd, "pkg_version", lambda name: "2.0.0")
    monkeypatch.setattr(upd, "get_latest_version", lambda: "2.0.0")
    exe = tmp_path / "jeeves"
    exe.write_text("old binary")

    status, current, detail = upd.perform_update(exe)

    assert status == "up_to_date"
    assert current == "2.0.0"
    assert detail == "2.0.0"
    assert exe.read_text() == "old binary"


def test_perform_update_unknown_when_latest_cannot_be_determined(monkeypatch, tmp_path):
    monkeypatch.setattr(upd, "pkg_version", lambda name: "1.0.0")
    monkeypatch.setattr(upd, "get_latest_version", lambda: None)
    exe = tmp_path / "jeeves"
    exe.write_text("old binary")

    status, current, detail = upd.perform_update(exe)

    assert status == "unknown"
    assert current == "1.0.0"
    assert detail is None
    assert exe.read_text() == "old binary"


def test_perform_update_downloads_and_replaces_executable(monkeypatch, tmp_path):
    monkeypatch.setattr(upd, "pkg_version", lambda name: "1.0.0")
    monkeypatch.setattr(upd, "get_latest_version", lambda: "2.0.0")
    exe = tmp_path / "jeeves"
    exe.write_text("old binary")

    with req_mock.Mocker() as m:
        m.get(upd._RELEASE_ASSET_URL, content=b"new binary content")
        status, current, detail = upd.perform_update(exe)

    assert status == "updated"
    assert current == "1.0.0"
    assert detail == "2.0.0"
    assert exe.read_bytes() == b"new binary content"
    assert exe.stat().st_mode & 0o111
    assert not (tmp_path / "jeeves.new").exists()


def test_perform_update_download_failure_leaves_executable_untouched(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(upd, "pkg_version", lambda name: "1.0.0")
    monkeypatch.setattr(upd, "get_latest_version", lambda: "2.0.0")
    exe = tmp_path / "jeeves"
    exe.write_text("old binary")

    with req_mock.Mocker() as m:
        m.get(upd._RELEASE_ASSET_URL, status_code=500)
        status, current, detail = upd.perform_update(exe)

    assert status == "error"
    assert current == "1.0.0"
    assert detail
    assert exe.read_text() == "old binary"
    assert not (tmp_path / "jeeves.new").exists()
