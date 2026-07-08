import pytest

from jeeves.config import (
    _DEFAULT_CONFIG_CONTENT,
    get_jenkins_config,
    list_profiles,
    load_config,
    show_config,
    write_default_config,
)


def test_load_config_no_file_returns_empty(tmp_path):
    result = load_config(str(tmp_path / "nonexistent.toml"))
    assert result == {}


def test_load_config_reads_toml(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('theme = "rainbow"\ncache = true\n')
    result = load_config(str(cfg_file))
    assert result["theme"] == "rainbow"
    assert result["cache"] is True


def test_load_config_invalid_toml_raises(tmp_path):
    cfg_file = tmp_path / "bad.toml"
    cfg_file.write_text("not = [valid toml")
    with pytest.raises(ValueError, match="Config parse error"):
        load_config(str(cfg_file))


def test_write_default_config_creates_file(tmp_path, monkeypatch):
    from jeeves import xdg

    monkeypatch.setattr(xdg, "get_config_dir", lambda: tmp_path / "jeeves")
    from jeeves import config as cfg_mod

    monkeypatch.setattr(cfg_mod, "get_config_dir", lambda: tmp_path / "jeeves")
    path = write_default_config()
    assert path.exists()
    assert "theme" in path.read_text()


def test_default_config_content_has_all_keys():
    assert "theme" in _DEFAULT_CONFIG_CONTENT
    assert "cache" in _DEFAULT_CONFIG_CONTENT
    assert "seasonal-colours" in _DEFAULT_CONFIG_CONTENT
    assert "no-update-check" in _DEFAULT_CONFIG_CONTENT


def test_show_config_empty():
    output = show_config({})
    assert "no config keys set" in output


def test_show_config_with_values():
    output = show_config({"theme": "rainbow", "cache": True})
    assert "theme" in output
    assert "rainbow" in output


# ── connection profiles ───────────────────────────────────────────────────────

_TWO_PROFILES = {
    "profiles": {
        "prod": {
            "url": "http://prod.example.com",
            "username": "steve",
            "token": "prod-tok",
        },
        "staging": {"url": "http://staging.example.com"},
    }
}


def _no_jeeves_env(monkeypatch):
    for var in ("JEEVES_URL", "JEEVES_USER", "JEEVES_TOKEN"):
        monkeypatch.delenv(var, raising=False)


def test_load_config_parses_profiles(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '[profiles.prod]\nurl = "http://prod.example.com"\ntoken = "abc"\n'
        '\n[profiles.staging]\nurl = "http://staging.example.com"\n'
    )
    result = load_config(str(cfg_file))
    assert result["profiles"]["prod"]["url"] == "http://prod.example.com"
    assert result["profiles"]["staging"]["url"] == "http://staging.example.com"


def test_get_jenkins_config_flat_backcompat(monkeypatch):
    _no_jeeves_env(monkeypatch)
    cfg = {"jenkins-url": "http://flat.example.com", "jenkins-username": "bertie"}
    url, username, token = get_jenkins_config(cfg)
    assert url == "http://flat.example.com"
    assert username == "bertie"
    assert token == ""


def test_get_jenkins_config_profile_fields(monkeypatch):
    _no_jeeves_env(monkeypatch)
    url, username, token = get_jenkins_config(_TWO_PROFILES, "prod")
    assert url == "http://prod.example.com"
    assert username == "steve"
    assert token == "prod-tok"


def test_get_jenkins_config_profile_never_falls_back_to_flat_keys(monkeypatch):
    _no_jeeves_env(monkeypatch)
    cfg = {"jenkins-url": "http://flat.example.com", **_TWO_PROFILES}
    url, username, token = get_jenkins_config(cfg, "staging")
    assert url == "http://staging.example.com"
    # staging has no username/token; flat keys must not leak in
    cfg["jenkins-username"] = "flat-user"
    cfg["jenkins-token"] = "flat-tok"
    url, username, token = get_jenkins_config(cfg, "staging")
    assert username == ""
    assert token == ""


def test_get_jenkins_config_profile_env_fallback(monkeypatch):
    _no_jeeves_env(monkeypatch)
    monkeypatch.setenv("JEEVES_USER", "env-user")
    monkeypatch.setenv("JEEVES_TOKEN", "env-tok")
    url, username, token = get_jenkins_config(_TWO_PROFILES, "staging")
    assert url == "http://staging.example.com"
    assert username == "env-user"
    assert token == "env-tok"


def test_get_jenkins_config_profile_missing_url_uses_default(monkeypatch):
    _no_jeeves_env(monkeypatch)
    cfg = {"profiles": {"bare": {"token": "abc"}}}
    url, _username, _token = get_jenkins_config(cfg, "bare")
    assert url == "http://localhost:8080"


def test_get_jenkins_config_unknown_profile_raises():
    with pytest.raises(ValueError, match="Unknown profile"):
        get_jenkins_config(_TWO_PROFILES, "bogus")


def test_get_jenkins_config_profiles_not_a_table():
    with pytest.raises(ValueError, match="Unknown profile"):
        get_jenkins_config({"profiles": "oops"}, "prod")


def test_list_profiles_sorted():
    assert list_profiles(_TWO_PROFILES) == ["prod", "staging"]


def test_list_profiles_empty_config():
    assert list_profiles({}) == []


def test_list_profiles_ignores_non_table_entries():
    cfg = {"profiles": {"prod": {"url": "http://x"}, "oops": "scalar"}}
    assert list_profiles(cfg) == ["prod"]


def test_list_profiles_profiles_not_a_table():
    assert list_profiles({"profiles": "oops"}) == []


def test_default_config_content_has_profiles():
    assert "[profiles.prod]" in _DEFAULT_CONFIG_CONTENT
    assert "default-profile" in _DEFAULT_CONFIG_CONTENT


def test_show_config_renders_profiles_and_masks_tokens():
    cfg = {"jenkins-token": "flat-secret", **_TWO_PROFILES}
    output = show_config(cfg)
    assert "prod" in output
    assert "http://prod.example.com" in output
    assert "staging" in output
    assert "prod-tok" not in output
    assert "flat-secret" not in output
    assert "***" in output


def test_show_config_profiles_not_a_table_falls_through():
    output = show_config({"profiles": "oops"})
    assert "profiles = 'oops'" in output
