"""five-clis — a batteries-included Python CLI template.

Replace the ``greet`` command with your own business logic.
All infrastructure (themes, caching, update checks, shell completions,
config file, XDG dirs, logging) is already wired up.
"""

import random
import sys

import click

from .config import load_config, show_config, write_default_config
from .logger import configure as configure_logging
from .ui import APP_ITEMS, THEME_NAMES, apply_seasonal_colour, get_theme
from .updater import check_for_update

_ENVVAR_PREFIX = "FIVE_CLIS"


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="fiveclis")
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
# ── Greeting (demo command — replace with your own) ─────────────────────────
@click.option(
    "--name",
    default=None,
    metavar="NAME",
    help="Name to greet. Defaults to the current user.",
)
def main(
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
    name,
):
    """🍔 five-clis — a batteries-included Python CLI template.

    A working 'hello world' that demonstrates themes, seasonal colours,
    caching, config files, shell completions, and auto-update checks.
    Replace the greeting logic with your own business logic.
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
            prog_name="five-clis",
            complete_var="_FIVE_CLIS_COMPLETE",
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
        click.echo(f"✅ Default config written to: {path}")
        sys.exit(0)

    if do_show_config:
        click.echo(show_config(cfg, config_path))
        sys.exit(0)

    # ── Resolve options vs config ──────────────────────────────────────────
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

    # ── Progress spinner ───────────────────────────────────────────────────
    spinner = random.choice(APP_ITEMS)
    click.echo(
        click.style(f"Cooking up your CLI... {spinner}", fg="cyan"),
        err=True,
        color=colour,
    )

    # ── Business logic (replace this section) ─────────────────────────────
    import os

    if name is None:
        name = os.environ.get("USER", os.environ.get("USERNAME", "world"))

    greeting = f"Hello, {name}! 🍔"
    if seasonal_colours and not no_colour:
        greeting = apply_seasonal_colour(greeting, 0, calendar=seasonal_calendar)
    elif not no_colour:
        greeting = active_theme.apply(greeting, role="primary")

    click.echo(greeting)

    # Show theme info
    if not no_colour:
        theme_label = active_theme.apply(f"  Theme: {theme_name}", role="accent")
        click.echo(theme_label)

    # Demonstrate rainbow cycling
    if theme_name == "rainbow" and not no_colour:
        items = ["burgers", "shakes", "fries", "nuggets", "sodas"]
        for i, item in enumerate(items):
            click.echo(active_theme.apply_cycle(f"  • {item}", i))

    # ── Update check ──────────────────────────────────────────────────────
    if not no_update_check:
        update_msg = check_for_update()
        if update_msg:
            click.echo(
                click.style(update_msg, fg="cyan", bold=True), err=True, color=colour
            )
