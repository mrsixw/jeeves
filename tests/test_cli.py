from click.testing import CliRunner

from jeeves import cli as cli_mod
from jeeves import jenkins as jenkins_mod
from jeeves.cli import main
from jeeves.jenkins import JenkinsError


def _invoke(*args, **kwargs):
    runner = CliRunner()
    return runner.invoke(main, list(args), **kwargs)


# ── Infrastructure ───────────────────────────────────────────────────────────


def test_version():
    result = _invoke("--version")
    assert result.exit_code == 0
    assert "jeeves" in result.output or "0." in result.output


def test_help():
    result = _invoke("--help")
    assert result.exit_code == 0
    assert "--theme" in result.output
    assert "--completion" in result.output
    assert "status" in result.output
    assert "jobs" in result.output


def test_bare_invocation_shows_greeting():
    result = _invoke("--no-colour")
    assert result.exit_code == 0
    assert "Good morning" in result.output or "Jeeves" in result.output


def test_completion_bash():
    result = _invoke("--completion", "bash")
    assert result.exit_code == 0
    assert "_JEEVES_COMPLETE" in result.output


def test_completion_zsh():
    result = _invoke("--completion", "zsh")
    assert result.exit_code == 0


def test_completion_fish():
    result = _invoke("--completion", "fish")
    assert result.exit_code == 0


def test_init_config(tmp_path, monkeypatch):
    from jeeves import config as cfg_mod

    monkeypatch.setattr(cfg_mod, "get_config_dir", lambda: tmp_path / "jeeves")
    result = _invoke("--init-config")
    assert result.exit_code == 0
    assert "config.toml" in result.output


def test_show_config():
    result = _invoke("--show-config")
    assert result.exit_code == 0
    assert "Config file" in result.output


def test_no_update_check_skips_update(monkeypatch):
    called = {"n": 0}

    def counting_check(**kw):
        called["n"] += 1
        return None

    monkeypatch.setattr(cli_mod, "check_for_update", counting_check)
    _invoke("--no-update-check", "--no-colour", "status", catch_exceptions=False)
    assert called["n"] == 0


def test_update_check_runs_by_default(monkeypatch):
    called = {"n": 0}

    def counting_check(**kw):
        called["n"] += 1
        return None

    monkeypatch.setattr(cli_mod, "check_for_update", counting_check)
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "status",
        lambda self: {
            "mode": "NORMAL",
            "nodeDescription": "master",
            "numExecutors": 2,
            "jobs": [],
        },
    )
    _invoke("--no-colour", "status")
    assert called["n"] == 1


def test_invalid_config_exits_with_error(tmp_path):
    bad_cfg = tmp_path / "bad.toml"
    bad_cfg.write_text("not = [valid toml")
    result = _invoke("--config", str(bad_cfg))
    assert result.exit_code == 1


# ── status ───────────────────────────────────────────────────────────────────


def test_status_shows_butler_greeting(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "status",
        lambda self: {
            "mode": "NORMAL",
            "nodeDescription": "master",
            "numExecutors": 2,
            "jobs": [],
        },
    )
    result = _invoke("--no-colour", "--no-update-check", "status")
    assert result.exit_code == 0
    assert "Certainly" in result.output or "fine form" in result.output


def test_status_connection_error_shows_butler_error(monkeypatch):
    def _raise(self):
        raise JenkinsError("connection refused")

    monkeypatch.setattr(jenkins_mod.JenkinsClient, "status", _raise)
    result = _invoke("--no-colour", "--no-update-check", "status")
    assert result.exit_code == 1
    assert "bother" in result.output + (result.output or "")


# ── jobs ─────────────────────────────────────────────────────────────────────


def test_jobs_shows_roster(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None: [{"name": "deploy-prod", "color": "blue"}],
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs")
    assert result.exit_code == 0
    assert "deploy-prod" in result.output
    assert "roster" in result.output


def test_jobs_empty_shows_butler_message(monkeypatch):
    monkeypatch.setattr(jenkins_mod.JenkinsClient, "jobs", lambda self, folder=None: [])
    result = _invoke("--no-colour", "--no-update-check", "jobs")
    assert result.exit_code == 0
    assert "unoccupied" in result.output


# ── build ─────────────────────────────────────────────────────────────────────


def test_build_success_shows_dispatch_message(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient, "build", lambda self, job, params=None: None
    )
    result = _invoke("--no-colour", "--no-update-check", "build", "my-pipeline")
    assert result.exit_code == 0
    assert (
        "dispatch" in result.output
        or "forthwith" in result.output
        or "at once" in result.output
    )


def test_build_bad_param_format(monkeypatch):
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "build",
        "my-pipeline",
        "--param",
        "no-equals-sign",
    )
    assert result.exit_code == 1


# ── queue ─────────────────────────────────────────────────────────────────────


def test_queue_shows_items(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "queue",
        lambda self: [{"why": "waiting", "stuck": False, "task": {"name": "deploy"}}],
    )
    result = _invoke("--no-colour", "--no-update-check", "queue")
    assert result.exit_code == 0
    assert "waiting" in result.output or "pending" in result.output


def test_queue_empty_shows_butler_message(monkeypatch):
    monkeypatch.setattr(jenkins_mod.JenkinsClient, "queue", lambda self: [])
    result = _invoke("--no-colour", "--no-update-check", "queue")
    assert result.exit_code == 0
    assert "unoccupied" in result.output


# ── cancel ────────────────────────────────────────────────────────────────────


def test_cancel_shows_dismissed_message(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient, "cancel", lambda self, job, build: None
    )
    result = _invoke(
        "--no-colour", "--no-update-check", "cancel", "my-pipeline", "--build", "5"
    )
    assert result.exit_code == 0
    assert "dismissed" in result.output


# ── nodes ─────────────────────────────────────────────────────────────────────


def test_nodes_shows_household_staff(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "nodes",
        lambda self: [{"displayName": "agent1", "offline": False, "numExecutors": 2}],
    )
    result = _invoke("--no-colour", "--no-update-check", "nodes")
    assert result.exit_code == 0
    assert "agent1" in result.output
    assert "household" in result.output


def test_nodes_empty_shows_butler_message(monkeypatch):
    monkeypatch.setattr(jenkins_mod.JenkinsClient, "nodes", lambda self: [])
    result = _invoke("--no-colour", "--no-update-check", "nodes")
    assert result.exit_code == 0
    assert "unoccupied" in result.output


# ── whoami ────────────────────────────────────────────────────────────────────


def test_whoami_authenticated(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "whoami",
        lambda self: {"id": "alice", "fullName": "Alice Smith"},
    )
    result = _invoke("--no-colour", "--no-update-check", "whoami")
    assert result.exit_code == 0
    assert "alice" in result.output
    assert "Alice Smith" in result.output


def test_whoami_anonymous(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "whoami",
        lambda self: {"id": "anonymous", "fullName": "anonymous"},
    )
    result = _invoke("--no-colour", "--no-update-check", "whoami")
    assert result.exit_code == 0
    assert "anonymous" in result.output


def test_whoami_error_shows_butler_message(monkeypatch):
    def _raise(self):
        raise JenkinsError("Cannot reach Jenkins at http://jenkins.example.com")

    monkeypatch.setattr(jenkins_mod.JenkinsClient, "whoami", _raise)
    result = _invoke("--no-colour", "--no-update-check", "whoami")
    assert result.exit_code == 1
    assert "bother" in result.output
