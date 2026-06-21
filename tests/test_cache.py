import json
from datetime import datetime, timedelta, timezone

import pytest

from fiveclis import cache as cache_mod


def test_parse_ttl_seconds():
    assert cache_mod.parse_ttl(300) == 300


def test_parse_ttl_string_int():
    assert cache_mod.parse_ttl("300") == 300


def test_parse_ttl_minutes():
    assert cache_mod.parse_ttl("5m") == 300


def test_parse_ttl_hours():
    assert cache_mod.parse_ttl("2h") == 7200


def test_parse_ttl_seconds_suffix():
    assert cache_mod.parse_ttl("30s") == 30


def test_parse_ttl_invalid_raises():
    with pytest.raises(ValueError):
        cache_mod.parse_ttl("bad")


def test_parse_ttl_zero_raises():
    with pytest.raises(ValueError):
        cache_mod.parse_ttl(0)


def test_parse_ttl_bool_raises():
    with pytest.raises(ValueError):
        cache_mod.parse_ttl(True)


def test_write_and_read_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_mod, "_CACHE_DIR", tmp_path)
    payload = {"answer": 42, "items": ["a", "b"]}
    cache_mod.write_cache("test_key", payload)
    result = cache_mod.read_cache("test_key", ttl=3600)
    assert result == payload


def test_read_cache_miss_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_mod, "_CACHE_DIR", tmp_path)
    assert cache_mod.read_cache("missing_key", ttl=300) is None


def test_read_cache_expired(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_mod, "_CACHE_DIR", tmp_path)
    payload = {"x": 1}
    cache_mod.write_cache("expired_key", payload)
    # Backdate the cache file
    path = tmp_path / "expired_key.json"
    data = json.loads(path.read_text())
    old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    data["fetched_at"] = old_time
    path.write_text(json.dumps(data))
    assert cache_mod.read_cache("expired_key", ttl=300) is None


def test_clear_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_mod, "_CACHE_DIR", tmp_path)
    cache_mod.write_cache("clear_key", {"v": 1})
    assert cache_mod.clear_cache("clear_key") is True
    assert cache_mod.read_cache("clear_key", ttl=3600) is None


def test_clear_cache_missing_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_mod, "_CACHE_DIR", tmp_path)
    assert cache_mod.clear_cache("nonexistent") is False
