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
        raise JenkinsError("Cannot reach Jenkins at http://jenkins.example.com")

    monkeypatch.setattr(jenkins_mod.JenkinsClient, "status", _raise)
    result = _invoke("--no-colour", "--no-update-check", "status")
    assert result.exit_code == 1
    assert "unreachable" in result.output


def test_error_403_shows_credentials_message(monkeypatch):
    def _raise(self):
        raise JenkinsError("Jenkins returned 403")

    monkeypatch.setattr(jenkins_mod.JenkinsClient, "status", _raise)
    result = _invoke("--no-colour", "--no-update-check", "status")
    assert result.exit_code == 1
    assert "403" in result.output
    assert "credentials" in result.output


def test_error_404_shows_not_found_message(monkeypatch):
    def _raise(self):
        raise JenkinsError("Jenkins returned 404")

    monkeypatch.setattr(jenkins_mod.JenkinsClient, "status", _raise)
    result = _invoke("--no-colour", "--no-update-check", "status")
    assert result.exit_code == 1
    assert "404" in result.output


def test_error_generic_shows_bother_message(monkeypatch):
    def _raise(self):
        raise JenkinsError("something went wrong")

    monkeypatch.setattr(jenkins_mod.JenkinsClient, "status", _raise)
    result = _invoke("--no-colour", "--no-update-check", "status")
    assert result.exit_code == 1
    assert "bother" in result.output


# ── jobs ─────────────────────────────────────────────────────────────────────


def test_jobs_shows_roster(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None, depth=0: [{"name": "deploy-prod", "color": "blue"}],
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs", "--no-weather")
    assert result.exit_code == 0
    assert "deploy-prod" in result.output
    assert "roster" in result.output


def test_jobs_shows_status_labels(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None, depth=0: [
            {"name": "a", "color": "blue"},
            {"name": "b", "color": "red"},
            {"name": "c", "color": "yellow"},
            {"name": "d", "color": "grey"},
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs", "--no-weather")
    assert result.exit_code == 0
    assert "passed" in result.output
    assert "failed" in result.output
    assert "unstable" in result.output
    assert "disabled" in result.output


def test_jobs_shows_folder_icon(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None, depth=0: [
            {
                "name": "my-folder",
                "_class": "com.cloudbees.hudson.plugins.folder.Folder",
            }
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs", "--no-weather")
    assert result.exit_code == 0
    assert "my-folder" in result.output
    assert "folder" in result.output


def test_jobs_shows_type_icons(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None, depth=0: [
            {
                "name": "pipe",
                "color": "blue",
                "_class": "org.jenkinsci.plugins.workflow.job.WorkflowJob",
            },
            {
                "name": "free",
                "color": "blue",
                "_class": "hudson.model.FreeStyleProject",
            },
            {
                "name": "unknown",
                "color": "blue",
                "_class": "some.UnknownClass",
            },
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs", "--no-weather")
    assert result.exit_code == 0
    assert "🔁" in result.output
    assert "🔧" in result.output
    assert "🔨" in result.output


def test_jobs_expand_recurses_into_folders(monkeypatch):
    def _mock_jobs(self, folder=None, depth=0):
        if folder is None:
            return [
                {
                    "name": "my-folder",
                    "_class": "com.cloudbees.hudson.plugins.folder.Folder",
                }
            ]
        if folder == "my-folder":
            return [
                {
                    "name": "child-job",
                    "color": "blue",
                    "_class": "org.jenkinsci.plugins.workflow.job.WorkflowJob",
                }
            ]
        return []

    monkeypatch.setattr(jenkins_mod.JenkinsClient, "jobs", _mock_jobs)
    result = _invoke(
        "--no-colour", "--no-update-check", "jobs", "--expand", "--no-weather"
    )
    assert result.exit_code == 0
    assert "my-folder" in result.output
    assert "my-folder/child-job" in result.output


def test_jobs_shows_weather_column(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None, depth=0: [
            {
                "name": "healthy",
                "color": "blue",
                "healthReport": [{"score": 90}],
            },
            {
                "name": "sick",
                "color": "red",
                "healthReport": [{"score": 10}],
            },
            {
                "name": "no-report",
                "color": "grey",
                "healthReport": [],
            },
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs")
    assert result.exit_code == 0
    assert "Weather" in result.output
    assert "sunny" in result.output
    assert "stormy" in result.output
    assert "—" in result.output


def test_jobs_no_weather_skips_column(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None, depth=0: [{"name": "x", "color": "blue"}],
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs", "--no-weather")
    assert result.exit_code == 0
    assert "Weather" not in result.output


def test_jobs_empty_shows_butler_message(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient, "jobs", lambda self, folder=None, depth=0: []
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs")
    assert result.exit_code == 0
    assert "bare" in result.output or "positions" in result.output


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


def test_queue_shows_stuck_label(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "queue",
        lambda self: [{"why": "blocked", "stuck": True, "task": {"name": "deploy"}}],
    )
    result = _invoke("--no-colour", "--no-update-check", "queue")
    assert result.exit_code == 0
    assert "yes" in result.output


def test_queue_empty_shows_butler_message(monkeypatch):
    monkeypatch.setattr(jenkins_mod.JenkinsClient, "queue", lambda self: [])
    result = _invoke("--no-colour", "--no-update-check", "queue")
    assert result.exit_code == 0
    assert "empty" in result.output or "leisure" in result.output


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


def test_nodes_shows_online_offline_labels(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "nodes",
        lambda self: [
            {"displayName": "up", "offline": False, "numExecutors": 2},
            {"displayName": "down", "offline": True, "numExecutors": 0},
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "nodes")
    assert result.exit_code == 0
    assert "online" in result.output
    assert "offline" in result.output


def test_nodes_empty_shows_butler_message(monkeypatch):
    monkeypatch.setattr(jenkins_mod.JenkinsClient, "nodes", lambda self: [])
    result = _invoke("--no-colour", "--no-update-check", "nodes")
    assert result.exit_code == 0
    assert "absented" in result.output or "notice" in result.output


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
    assert "unreachable" in result.output
