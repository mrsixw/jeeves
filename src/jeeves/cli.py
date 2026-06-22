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
from .ui import THEME_NAMES, apply_seasonal_colour, colour_grade_number, get_theme
from .updater import check_for_update

_ENVVAR_PREFIX = "JEEVES"
_BUTLER_ITEMS = ["🎩", "🥂", "🤵", "📋", "🫗"]


@dataclass
class _Ctx:
    cfg: dict = field(default_factory=dict)
    colour: bool = True
    theme: object = None
    no_update_check: bool = False
    seasonal_colours: bool = True
    seasonal_calendar: str = "western"


def _butler_error(msg: str, colour: bool) -> None:
    if "Cannot reach Jenkins at" in msg:
        url = msg.split("Cannot reach Jenkins at ", 1)[-1].strip()
        text = (
            f"I'm afraid the Jenkins estate at {url} appears to be quite unreachable, "
            "sir. The line seems entirely dead."
        )
    elif "Jenkins returned 403" in msg:
        text = (
            "Jenkins has turned us away at the door, sir. A 403 — most irregular. "
            "One suspects our credentials may not be in order."
        )
    elif "Jenkins returned 404" in msg:
        text = (
            "I searched the premises most thoroughly, sir, but the requested resource "
            "could not be found. A 404. It has vanished like Bertie's good intentions."
        )
    elif "Jenkins returned" in msg:
        code = msg.split("Jenkins returned ", 1)[-1].strip()
        text = (
            f"Jenkins appears to be in a considerable state of disarray, sir. "
            f"A {code}. Perhaps a restorative cup of tea is called for."
        )
    else:
        text = f"I'm afraid there's been a spot of bother, sir: {msg}"
    click.echo(
        click.style(f"🎩 {text}", fg="red"),
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
        cfg=cfg,
        colour=colour,
        theme=active_theme,
        no_update_check=no_update_check,
        seasonal_colours=seasonal_colours if seasonal_colours is not None else True,
        seasonal_calendar=seasonal_calendar or "western",
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
        click.style(f"✅ Certainly, sir. {desc} is in fine form.", fg="green"),
        color=ctx.colour,
    )
    mode_str = (
        click.style(mode, fg="green", bold=True)
        if ctx.colour and mode.upper() == "NORMAL"
        else click.style(mode, fg="yellow", bold=True) if ctx.colour else mode
    )
    exec_cell = (
        colour_grade_number(executors)
        if ctx.colour and isinstance(executors, int)
        else executors
    )
    rows = [
        ["Mode", mode_str],
        ["Executors", exec_cell],
        ["Jobs", colour_grade_number(jobs_count) if ctx.colour else jobs_count],
    ]
    click.echo(tabulate(rows, tablefmt="simple"), color=ctx.colour)


# ── jobs ────────────────────────────────────────────────────────────────────

# (colour, label, emoji)
_JOB_COLOUR_MAP: dict[str, tuple[str, str, str]] = {
    "blue": ("green", "passed", "✅"),
    "blue_anime": ("green", "running", "▶️"),
    "red": ("red", "failed", "❌"),
    "red_anime": ("red", "running", "▶️"),
    "yellow": ("yellow", "unstable", "⚠️"),
    "yellow_anime": ("yellow", "running", "▶️"),
    "grey": ("white", "disabled", "⏸️"),
    "notbuilt": ("white", "not built", "🔘"),
    "aborted": ("white", "aborted", "🚫"),
    "aborted_anime": ("white", "running", "▶️"),
}

_FOLDER_CLASS_FRAGMENTS = ("Folder", "MultiBranch", "OrganizationFolder")

# (class fragment, icon) — first match wins
_JOB_TYPE_ICONS: list[tuple[str, str]] = [
    ("WorkflowJob", "🔁"),
    ("FreeStyleProject", "🔧"),
    ("MatrixProject", "🔢"),
]

_WEATHER_MAP: list[tuple[int, str, str, str]] = [
    (80, "green", "☀️", "sunny"),
    (60, "yellow", "🌤️", "fair"),
    (40, "yellow", "☁️", "cloudy"),
    (20, 208, "🌧️", "rainy"),
    (0, "red", "⛈️", "stormy"),
]


def _is_folder(job: dict) -> bool:
    cls = job.get("_class", "")
    return any(f in cls for f in _FOLDER_CLASS_FRAGMENTS)


def _job_type_icon(job: dict) -> str:
    cls = job.get("_class", "")
    for fragment, icon in _JOB_TYPE_ICONS:
        if fragment in cls:
            return icon
    return "🔨"


def _format_job_status(raw: str, colour: bool) -> str:
    fg, label, emoji = _JOB_COLOUR_MAP.get(raw, ("white", raw, "❓"))
    text = f"{emoji} {label}"
    return click.style(text, fg=fg, bold=True) if colour else text


def _format_weather(score: int | None, colour: bool) -> str:
    if score is None:
        return "—"
    for threshold, fg, emoji, label in _WEATHER_MAP:
        if score >= threshold:
            text = f"{emoji} {label}"
            return click.style(text, fg=fg, bold=True) if colour else text
    return "—"


def _collect_job_rows(
    client: "JenkinsClient",
    job_list: list[dict],
    colour: bool,
    seasonal_colours: bool,
    seasonal_calendar: str,
    no_weather: bool,
    expand: bool,
    path_prefix: str,
    colour_index: list[int],
) -> list[list]:
    """Recursively build table rows, expanding folders when expand=True."""
    rows = []
    for j in job_list:
        name = j.get("name", "?")
        full_path = f"{path_prefix}/{name}" if path_prefix else name

        if _is_folder(j):
            type_icon = ""
            folder_label = "📁 folder"
            status_cell = (
                click.style(folder_label, fg="cyan") if colour else folder_label
            )
            weather_cell = "—"
        else:
            type_icon = _job_type_icon(j)
            raw = j.get("color", "grey")
            status_cell = _format_job_status(raw, colour)
            reports = j.get("healthReport") or []
            score = reports[0].get("score") if reports else None
            weather_cell = _format_weather(score, colour)

        display_name = f"{type_icon} {full_path}".strip() if type_icon else full_path
        idx = colour_index[0]
        colour_index[0] += 1
        if colour and seasonal_colours:
            display_name = apply_seasonal_colour(
                display_name, idx, calendar=seasonal_calendar
            )

        row = [display_name, status_cell]
        if not no_weather:
            row.append(weather_cell)
        rows.append(row)

        if expand and _is_folder(j):
            try:
                depth = 0 if no_weather else 1
                child_jobs = client.jobs(folder=full_path, depth=depth)
            except JenkinsError:
                child_jobs = []
            rows.extend(
                _collect_job_rows(
                    client,
                    child_jobs,
                    colour,
                    seasonal_colours,
                    seasonal_calendar,
                    no_weather,
                    expand,
                    full_path,
                    colour_index,
                )
            )

    return rows


@main.command()
@_url_opt
@_user_opt
@_token_opt
@click.option(
    "--folder", default=None, metavar="NAME", help="Limit to a Jenkins folder."
)
@click.option(
    "--no-weather",
    "no_weather",
    is_flag=True,
    default=False,
    help="Skip build health (weather) column; faster on large instances.",
)
@click.option(
    "--expand",
    "expand",
    is_flag=True,
    default=False,
    help="Recursively expand folders to show all descendant jobs.",
)
@click.pass_obj
def jobs(
    ctx: _Ctx,
    url: str | None,
    user: str | None,
    token: str | None,
    folder: str | None,
    no_weather: bool,
    expand: bool,
) -> None:
    """List all Jenkins jobs."""
    client = _make_client(ctx, url, user, token)
    depth = 0 if no_weather else 1
    try:
        job_list = client.jobs(folder=folder, depth=depth)
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    if not job_list:
        click.echo(
            "The staff roster appears entirely bare, sir. "
            "Jenkins would seem to have no positions filled at present."
        )
        return

    click.echo(
        click.style("📋 Allow me to present the staff roster, sir.", fg="cyan"),
        color=ctx.colour,
    )
    rows = _collect_job_rows(
        client,
        job_list,
        ctx.colour,
        ctx.seasonal_colours,
        ctx.seasonal_calendar,
        no_weather,
        expand,
        path_prefix=folder or "",
        colour_index=[0],
    )
    headers = ["Job", "Status"] + ([] if no_weather else ["Weather"])
    click.echo(
        tabulate(rows, headers=headers, tablefmt="simple", disable_numparse=True),
        color=ctx.colour,
    )


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
        click.style(
            f"🚀 I shall dispatch '{job}' at once, sir. Very good.", fg="green"
        ),
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
        click.echo(
            "The queue stands quite empty, sir. "
            "Jenkins is evidently at leisure — a rare and precious state of affairs."
        )
        return

    click.echo(
        click.style("⏳ The pending requests, sir.", fg="cyan"), color=ctx.colour
    )
    rows = []
    for idx, item in enumerate(items):
        task = item.get("task", {}).get("name", "?")
        if ctx.colour and ctx.seasonal_colours:
            task = apply_seasonal_colour(task, idx, calendar=ctx.seasonal_calendar)
        why = item.get("why", "")
        is_stuck = item.get("stuck", False)
        if ctx.colour:
            stuck = (
                click.style("⚠️ yes", fg="red", bold=True)
                if is_stuck
                else click.style("no", fg="green")
            )
        else:
            stuck = "yes" if is_stuck else "no"
        rows.append([task, why, stuck])
    click.echo(
        tabulate(
            rows,
            headers=["Job", "Reason", "Stuck"],
            tablefmt="simple",
            disable_numparse=True,
        ),
        color=ctx.colour,
    )


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
            f"🛑 Consider build #{build_id} of '{job}' dismissed, sir.", fg="green"
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
        click.echo(
            "The household staff appears to have entirely absented themselves, sir. "
            "One trusts they haven't all handed in their notice."
        )
        return

    click.echo(click.style("🏠 The household staff, sir.", fg="cyan"), color=ctx.colour)
    rows = []
    for idx, n in enumerate(node_list):
        name = n.get("displayName", "?")
        if ctx.colour and ctx.seasonal_colours:
            name = apply_seasonal_colour(name, idx, calendar=ctx.seasonal_calendar)
        is_offline = n.get("offline", False)
        if ctx.colour:
            status = (
                click.style("🔴 offline", fg="red", bold=True)
                if is_offline
                else click.style("✅ online", fg="green", bold=True)
            )
        else:
            status = "offline" if is_offline else "online"
        executors = n.get("numExecutors", "?")
        exec_cell = (
            colour_grade_number(executors)
            if ctx.colour and isinstance(executors, int)
            else executors
        )
        rows.append([name, status, exec_cell])
    click.echo(
        tabulate(
            rows,
            headers=["Node", "Status", "Executors"],
            tablefmt="simple",
            disable_numparse=True,
        ),
        color=ctx.colour,
    )


# ── whoami ───────────────────────────────────────────────────────────────────


@main.command()
@_url_opt
@_user_opt
@_token_opt
@click.pass_obj
def whoami(ctx: _Ctx, url: str | None, user: str | None, token: str | None) -> None:
    """Show the currently authenticated Jenkins user."""
    client = _make_client(ctx, url, user, token)
    try:
        data = client.whoami()
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    user_id = data.get("id", "anonymous")
    full_name = data.get("fullName", "")

    if user_id == "anonymous":
        click.echo(
            click.style(
                "👤 Connected as anonymous, sir. No credentials were presented.",
                fg="yellow",
            ),
            color=ctx.colour,
        )
        return

    if full_name and full_name != user_id:
        identity = f"{user_id} ({full_name})"
    else:
        identity = user_id

    click.echo(
        click.style(f"👤 Authenticated as: {identity}", fg="green"),
        color=ctx.colour,
    )
