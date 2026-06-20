"""jeeves — a Jenkins CI/CD butler.

Good morning, sir. I shall attend to your Jenkins affairs with the
utmost discretion and efficiency.
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass, field

import click
from tabulate import tabulate

from .config import get_jenkins_config, load_config, show_config, write_default_config
from .jenkins import JenkinsClient, JenkinsError
from .logger import configure as configure_logging
from .ui import THEME_NAMES, apply_seasonal_colour, get_theme
from .updater import check_for_update

_ENVVAR_PREFIX = "JEEVES"
_BUTLER_ITEMS = ["🎩", "🥂", "🤵", "📋", "🫗"]


@dataclass
class _Ctx:
    cfg: dict = field(default_factory=dict)
    colour: bool = True
    theme: object = None
    no_update_check: bool = False


def _butler_error(msg: str, colour: bool) -> None:
    click.echo(
        click.style(f"I'm afraid there's been a spot of bother, sir: {msg}", fg="red"),
        err=True,
        color=colour,
    )


def _make_client(
    ctx: _Ctx, url: str | None, user: str | None, token: str | None
) -> JenkinsClient:
    cfg_url, cfg_user, cfg_token = get_jenkins_config(ctx.cfg)
    return JenkinsClient(url or cfg_url, user or cfg_user, token or cfg_token)


# ── Shared connection options ────────────────────────────────────────────────
_url_opt = click.option(
    "--url",
    default=None,
    metavar="URL",
    envvar="JEEVES_URL",
    help="Jenkins server URL (overrides config).",
)
_user_opt = click.option(
    "--user",
    default=None,
    metavar="USER",
    envvar="JEEVES_USER",
    help="Jenkins username (overrides config).",
)
_token_opt = click.option(
    "--token",
    default=None,
    metavar="TOKEN",
    envvar="JEEVES_TOKEN",
    help="Jenkins API token (overrides config).",
)


# ── Group ────────────────────────────────────────────────────────────────────


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    invoke_without_command=True,
)
@click.version_option(package_name="jeeves")
# ── Shell completions ──────────────────────────────────────────────────────
@click.option(
    "--completion",
    "completion_shell",
    type=click.Choice(["bash", "zsh", "fish"]),
    default=None,
    is_eager=True,
    expose_value=True,
    help="Print shell completion script for SHELL and exit. Eval in your shell config.",
)
# ── Config ─────────────────────────────────────────────────────────────────
@click.option(
    "--config",
    "config_path",
    default=None,
    metavar="PATH",
    help="Path to a TOML config file.",
)
@click.option(
    "--show-config",
    "do_show_config",
    is_flag=True,
    default=False,
    help="Print resolved config and exit.",
)
@click.option(
    "--init-config",
    "do_init_config",
    is_flag=True,
    default=False,
    help="Write a default config file and exit.",
)
# ── Display ─────────────────────────────────────────────────────────────────
@click.option(
    "--theme",
    type=click.Choice(THEME_NAMES, case_sensitive=False),
    default=None,
    help=f"Colour theme. Choices: {', '.join(THEME_NAMES)}.",
)
@click.option(
    "--seasonal-colours/--no-seasonal-colours",
    default=None,
    help="Apply seasonal ANSI colours based on the current date.",
)
@click.option(
    "--seasonal-calendar",
    type=click.Choice(
        ["western", "jewish", "islamic", "hindu", "sikh", "east-asian"],
        case_sensitive=False,
    ),
    default=None,
    help="Which cultural calendar drives seasonal colours (default: western).",
)
@click.option(
    "--no-colour",
    "no_colour",
    is_flag=True,
    default=False,
    envvar=f"{_ENVVAR_PREFIX}_NO_COLOUR",
    help="Disable all ANSI colour output.",
)
# ── Caching ─────────────────────────────────────────────────────────────────
@click.option(
    "--cache/--no-cache",
    default=None,
    help="Enable disk caching of results (off by default).",
)
@click.option(
    "--cache-ttl",
    default=None,
    metavar="TTL",
    help="Cache TTL: seconds (300), or suffixed (5m, 2h). Default: 300.",
)
# ── Updates ─────────────────────────────────────────────────────────────────
@click.option(
    "--no-update-check",
    is_flag=True,
    default=False,
    envvar=f"{_ENVVAR_PREFIX}_NO_UPDATE_CHECK",
    help="Disable the automatic update check.",
)
@click.pass_context
def main(
    ctx,
    completion_shell,
    config_path,
    do_show_config,
    do_init_config,
    theme,
    seasonal_colours,
    seasonal_calendar,
    no_colour,
    cache,
    cache_ttl,
    no_update_check,
):
    """🎩 jeeves — your Jenkins CI/CD butler.

    Good morning, sir. How may Jeeves be of assistance?
    """
    configure_logging()
    colour = not no_colour

    # ── Shell completion ────────────────────────────────────────────────────
    if completion_shell:
        from click.shell_completion import get_completion_class

        comp_cls = get_completion_class(completion_shell)
        comp = comp_cls(
            cli=main,
            ctx_args={},
            prog_name="jeeves",
            complete_var="_JEEVES_COMPLETE",
        )
        click.echo(comp.source(), nl=False)
        sys.exit(0)

    # ── Config resolution ──────────────────────────────────────────────────
    try:
        cfg = load_config(config_path)
    except ValueError as exc:
        click.echo(click.style(str(exc), fg="red"), err=True, color=colour)
        sys.exit(1)

    if do_init_config:
        path = write_default_config()
        click.echo(f"Very good, sir. Default config written to: {path}")
        sys.exit(0)

    if do_show_config:
        click.echo(show_config(cfg, config_path))
        sys.exit(0)

    # ── Resolve display options ────────────────────────────────────────────
    theme_name = theme if theme is not None else cfg.get("theme", "default")
    seasonal_colours = (
        seasonal_colours
        if seasonal_colours is not None
        else cfg.get("seasonal-colours", True)
    )
    seasonal_calendar = (
        seasonal_calendar
        if seasonal_calendar is not None
        else cfg.get("seasonal-calendar", "western")
    )
    no_update_check = no_update_check or cfg.get("no-update-check", False)

    active_theme = get_theme(theme_name)

    ctx.obj = _Ctx(
        cfg=cfg, colour=colour, theme=active_theme, no_update_check=no_update_check
    )
    ctx.ensure_object(_Ctx)

    # ── Bare invocation: greet the user ───────────────────────────────────
    if ctx.invoked_subcommand is None:
        spinner = random.choice(_BUTLER_ITEMS)
        greeting = (
            f"{spinner}  Good morning, sir. "
            "How may Jeeves be of assistance? Try --help."
        )
        if seasonal_colours and not no_colour:
            greeting = apply_seasonal_colour(greeting, 0, calendar=seasonal_calendar)
        elif not no_colour:
            greeting = active_theme.apply(greeting, role="primary")
        click.echo(greeting, color=colour)
        return

    # ── Update check (runs after the subcommand via close callback) ────────
    if not no_update_check:

        def _check() -> None:
            msg = check_for_update()
            if msg:
                click.echo(
                    click.style(msg, fg="cyan", bold=True), err=True, color=colour
                )

        ctx.call_on_close(_check)


# ── status ──────────────────────────────────────────────────────────────────


@main.command()
@_url_opt
@_user_opt
@_token_opt
@click.pass_obj
def status(ctx: _Ctx, url: str | None, user: str | None, token: str | None) -> None:
    """Check Jenkins server health."""
    client = _make_client(ctx, url, user, token)
    try:
        data = client.status()
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    desc = data.get("nodeDescription", "Jenkins")
    mode = data.get("mode", "unknown")
    executors = data.get("numExecutors", "?")
    jobs_count = len(data.get("jobs", []))

    click.echo(
        click.style(f"Certainly, sir. {desc} is in fine form.", fg="green"),
        color=ctx.colour,
    )
    rows = [["Mode", mode], ["Executors", executors], ["Jobs", jobs_count]]
    click.echo(tabulate(rows, tablefmt="simple"))


# ── jobs ────────────────────────────────────────────────────────────────────

_JOB_COLOUR_MAP: dict[str, tuple[str, str]] = {
    "blue": ("green", "passed"),
    "blue_anime": ("green", "running"),
    "red": ("red", "failed"),
    "red_anime": ("red", "running"),
    "yellow": ("yellow", "unstable"),
    "yellow_anime": ("yellow", "running"),
    "grey": ("white", "disabled"),
    "notbuilt": ("white", "not built"),
    "aborted": ("white", "aborted"),
    "aborted_anime": ("white", "running"),
}


@main.command()
@_url_opt
@_user_opt
@_token_opt
@click.option(
    "--folder", default=None, metavar="NAME", help="Limit to a Jenkins folder."
)
@click.pass_obj
def jobs(
    ctx: _Ctx, url: str | None, user: str | None, token: str | None, folder: str | None
) -> None:
    """List all Jenkins jobs."""
    client = _make_client(ctx, url, user, token)
    try:
        job_list = client.jobs(folder=folder)
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    if not job_list:
        click.echo("The staff roster appears to be unoccupied at present, sir.")
        return

    click.echo(
        click.style("Allow me to present the staff roster, sir.", fg="cyan"),
        color=ctx.colour,
    )
    rows = []
    for j in job_list:
        raw = j.get("color", "grey")
        _, label = _JOB_COLOUR_MAP.get(raw, ("white", raw))
        rows.append([j.get("name", "?"), label])
    click.echo(tabulate(rows, headers=["Job", "Status"], tablefmt="simple"))


# ── build ───────────────────────────────────────────────────────────────────


@main.command()
@click.argument("job")
@_url_opt
@_user_opt
@_token_opt
@click.option(
    "--param",
    "params",
    multiple=True,
    metavar="KEY=VALUE",
    help="Build parameter in KEY=VALUE format. Repeatable.",
)
@click.pass_obj
def build(
    ctx: _Ctx,
    job: str,
    url: str | None,
    user: str | None,
    token: str | None,
    params: tuple[str, ...],
) -> None:
    """Trigger a Jenkins build.

    JOB is the job name (or folder/job path for nested jobs).
    """
    param_dict: dict[str, str] = {}
    for p in params:
        if "=" not in p:
            click.echo(
                click.style(
                    f"I'm afraid '{p}' is not in KEY=VALUE format, sir.", fg="red"
                ),
                err=True,
                color=ctx.colour,
            )
            sys.exit(1)
        k, _, v = p.partition("=")
        param_dict[k] = v

    client = _make_client(ctx, url, user, token)
    try:
        client.build(job, params=param_dict or None)
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    click.echo(
        click.style(f"I shall dispatch '{job}' at once, sir. Very good.", fg="green"),
        color=ctx.colour,
    )


# ── log ─────────────────────────────────────────────────────────────────────


@main.command()
@click.argument("job")
@_url_opt
@_user_opt
@_token_opt
@click.option(
    "--build",
    "build_id",
    default="lastBuild",
    metavar="N",
    help="Build number (default: lastBuild).",
)
@click.pass_obj
def log(
    ctx: _Ctx,
    job: str,
    url: str | None,
    user: str | None,
    token: str | None,
    build_id: str,
) -> None:
    """Show the console log for a build.

    JOB is the job name. Use --build to specify a build number.
    """
    client = _make_client(ctx, url, user, token)
    try:
        text = client.log(job, build=build_id)
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    click.echo(text, nl=False)


# ── queue ───────────────────────────────────────────────────────────────────


@main.command()
@_url_opt
@_user_opt
@_token_opt
@click.pass_obj
def queue(ctx: _Ctx, url: str | None, user: str | None, token: str | None) -> None:
    """Show the Jenkins build queue."""
    client = _make_client(ctx, url, user, token)
    try:
        items = client.queue()
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    if not items:
        click.echo("The queue appears to be unoccupied at present, sir.")
        return

    click.echo(click.style("The pending requests, sir.", fg="cyan"), color=ctx.colour)
    rows = []
    for item in items:
        task = item.get("task", {}).get("name", "?")
        why = item.get("why", "")
        stuck = "yes" if item.get("stuck") else "no"
        rows.append([task, why, stuck])
    click.echo(tabulate(rows, headers=["Job", "Reason", "Stuck"], tablefmt="simple"))


# ── cancel ──────────────────────────────────────────────────────────────────


@main.command()
@click.argument("job")
@_url_opt
@_user_opt
@_token_opt
@click.option(
    "--build",
    "build_id",
    required=True,
    type=int,
    metavar="N",
    help="Build number to cancel.",
)
@click.pass_obj
def cancel(
    ctx: _Ctx,
    job: str,
    url: str | None,
    user: str | None,
    token: str | None,
    build_id: int,
) -> None:
    """Cancel a running Jenkins build.

    JOB is the job name. --build N is required.
    """
    client = _make_client(ctx, url, user, token)
    try:
        client.cancel(job, build_id)
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    click.echo(
        click.style(
            f"Consider build #{build_id} of '{job}' dismissed, sir.", fg="green"
        ),
        color=ctx.colour,
    )


# ── nodes ───────────────────────────────────────────────────────────────────


@main.command()
@_url_opt
@_user_opt
@_token_opt
@click.pass_obj
def nodes(ctx: _Ctx, url: str | None, user: str | None, token: str | None) -> None:
    """List Jenkins build nodes (agents)."""
    client = _make_client(ctx, url, user, token)
    try:
        node_list = client.nodes()
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    if not node_list:
        click.echo("The household staff appears to be unoccupied at present, sir.")
        return

    click.echo(click.style("The household staff, sir.", fg="cyan"), color=ctx.colour)
    rows = []
    for n in node_list:
        name = n.get("displayName", "?")
        offline = "offline" if n.get("offline") else "online"
        executors = n.get("numExecutors", "?")
        rows.append([name, offline, executors])
    click.echo(
        tabulate(rows, headers=["Node", "Status", "Executors"], tablefmt="simple")
    )
