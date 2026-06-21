from pathlib import Path

from fiveclis import xdg


def test_get_cache_dir_default(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert xdg.get_cache_dir() == tmp_path / ".cache" / "fiveclis"


def test_get_cache_dir_with_env(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert xdg.get_cache_dir() == tmp_path / "fiveclis"


def test_get_cache_dir_ignores_relative_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", "relative/path")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert xdg.get_cache_dir() == tmp_path / ".cache" / "fiveclis"


def test_get_config_dir_default(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert xdg.get_config_dir() == tmp_path / ".config" / "fiveclis"


def test_get_config_dir_with_env(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert xdg.get_config_dir() == tmp_path / "fiveclis"


def test_get_state_dir_default(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert xdg.get_state_dir() == tmp_path / ".local" / "state" / "fiveclis"


def test_get_config_paths_returns_three_paths(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    paths = xdg.get_config_paths()
    assert len(paths) == 3
    assert any("fiveclis" in str(p) for p in paths)
