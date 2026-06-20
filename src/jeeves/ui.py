"""Terminal colour, theming, and formatting utilities.

Ported from the breakfast project and extended with an explicit theme registry.
Two complementary systems:
  - Seasonal/cultural calendar colours (automatic, date-driven)
  - Explicit ``--theme`` override (user-controlled, persistent)
"""

import datetime
import math
from dataclasses import dataclass, field
from datetime import date as _real_date
from datetime import timedelta as _real_timedelta

import click

# ---------------------------------------------------------------------------
# Named colour palette
# ---------------------------------------------------------------------------

SEASONAL_PALETTES = {
    "green": "\033[32m",
    "purple": "\033[38;5;141m",
    "yellow": "\033[38;5;226m",
    "orange": "\033[38;5;208m",
    "red": "\033[31m",
    "pink": "\033[38;5;218m",
    "lny": "\033[38;5;196m",
    "blue": "\033[38;5;75m",
    "spring_green": "\033[38;5;120m",
    "gold": "\033[38;5;220m",
}

# Pride Month 🏳️‍🌈 rainbow: one colour per row, cycling by index.
PRIDE_RAINBOW = [
    "\033[31m",  # red
    "\033[38;5;208m",  # orange
    "\033[38;5;226m",  # yellow
    "\033[32m",  # green
    "\033[38;5;63m",  # blue
    "\033[38;5;141m",  # purple
]

# Holi rainbow: a burst of festival colours 🎨
HOLI_RAINBOW = [
    "\033[38;5;218m",  # pink
    "\033[38;5;226m",  # yellow
    "\033[32m",  # green
    "\033[38;5;208m",  # orange
    "\033[38;5;141m",  # purple
    "\033[38;5;75m",  # blue
]

# Spinner items — fast food themed 🍔🍟🥤
APP_ITEMS = ["🍔", "🧃", "🍟", "🥤", "🍦", "🍕", "🌮", "🌯", "🥪", "🍿"]

_RESET = "\033[0m"


# ---------------------------------------------------------------------------
# Explicit theme registry
# ---------------------------------------------------------------------------


@dataclass
class Theme:
    """A named terminal colour theme."""

    primary: str | None = "cyan"
    accent: str | None = "yellow"
    success: str | None = "green"
    warn: str | None = "yellow"
    error: str | None = "red"
    muted: str | None = None
    cycle: list[str] = field(default_factory=list)

    def apply(self, text: str, role: str = "primary") -> str:
        """Apply this theme's colour for *role* to *text* using click.style."""
        colour = getattr(self, role, self.primary)
        if colour is None:
            return text
        return click.style(text, fg=colour)

    def apply_cycle(self, text: str, index: int) -> str:
        """Apply a cycling colour from this theme's ``cycle`` list."""
        if not self.cycle:
            return self.apply(text)
        ansi = self.cycle[index % len(self.cycle)]
        return f"{ansi}{text}{_RESET}"


THEMES: dict[str, Theme] = {
    "default": Theme(
        primary="cyan",
        accent="yellow",
        success="green",
        warn="yellow",
        error="red",
        muted=None,
        cycle=[],
    ),
    "dark": Theme(
        primary="bright_blue",
        accent="bright_magenta",
        success="bright_green",
        warn="bright_yellow",
        error="bright_red",
        muted=None,
        cycle=[],
    ),
    "light": Theme(
        primary="blue",
        accent="green",
        success="green",
        warn="yellow",
        error="red",
        muted=None,
        cycle=[],
    ),
    "mono": Theme(
        primary=None,
        accent=None,
        success=None,
        warn=None,
        error=None,
        muted=None,
        cycle=[],
    ),
    "rainbow": Theme(
        primary="cyan",
        accent="yellow",
        success="green",
        warn="yellow",
        error="red",
        muted=None,
        cycle=PRIDE_RAINBOW,
    ),
}

THEME_NAMES = list(THEMES.keys())


def get_theme(name: str) -> Theme:
    """Return the named theme, falling back to ``"default"`` for unknown names."""
    return THEMES.get(name, THEMES["default"])


# ---------------------------------------------------------------------------
# Astronomical helpers for the seasonal calendar system
# ---------------------------------------------------------------------------


def _easter_month(year: int) -> int:
    """Return 3 (March) or 4 (April): the month Easter falls in for *year*.

    Uses the Anonymous Gregorian algorithm (Meeus/Jones/Butcher).
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    return (h + ll - 7 * m + 114) // 31


def _new_moon_jde(k: float) -> float:
    """Julian Ephemeris Day of new moon k (Meeus, Astronomical Algorithms, ch. 49)."""
    T = k / 1236.85
    jde = (
        2451550.09766
        + 29.530588861 * k
        + 0.00015437 * T**2
        - 0.000000150 * T**3
        + 0.00000000073 * T**4
    )
    M = math.radians(2.5534 + 29.10535670 * k - 0.0000014 * T**2)
    Mp = math.radians(
        201.5643 + 385.81693528 * k + 0.0107582 * T**2 + 0.00001238 * T**3
    )
    F = math.radians(160.7108 + 390.67050284 * k - 0.0016118 * T**2 - 0.00000227 * T**3)
    Om = math.radians(124.7746 - 1.56375588 * k + 0.0020672 * T**2)
    E = 1 - 0.002516 * T - 0.0000074 * T**2
    corr = (
        -0.40720 * math.sin(Mp)
        + 0.17241 * E * math.sin(M)
        + 0.01608 * math.sin(2 * Mp)
        + 0.01039 * math.sin(2 * F)
        + 0.00739 * E * math.sin(Mp - M)
        - 0.00514 * E * math.sin(Mp + M)
        + 0.00208 * E**2 * math.sin(2 * M)
        - 0.00111 * math.sin(Mp - 2 * F)
        - 0.00057 * math.sin(Mp + 2 * F)
        + 0.00056 * E * math.sin(2 * Mp + M)
        - 0.00042 * math.sin(3 * Mp)
        + 0.00042 * E * math.sin(M + 2 * F)
        + 0.00038 * E * math.sin(M - 2 * F)
        - 0.00024 * E * math.sin(2 * Mp - M)
        - 0.00017 * math.sin(Om)
    )
    return jde + corr


def _jde_to_date_cst(jde: float) -> tuple[int, int, int]:
    """Convert a Julian Ephemeris Day to Gregorian (year, month, day) in CST (UTC+8)."""
    jd = jde + 8.0 / 24.0
    Z = int(jd + 0.5)
    alpha = int((Z - 1867216.25) / 36524.25)
    A = Z + 1 + alpha - alpha // 4
    B = A + 1524
    C = int((B - 122.1) / 365.25)
    D = int(365.25 * C)
    E_val = int((B - D) / 30.6001)
    day = B - D - int(30.6001 * E_val)
    month = E_val - 1 if E_val < 14 else E_val - 13
    year = C - 4716 if month > 2 else C - 4715
    return year, month, day


def _lny_date(year: int) -> tuple[int, int]:
    """Return (month, day) of Lunar New Year for *year* in Chinese Standard Time."""
    k_approx = round((year - 2000) * 12.3685)
    for dk in range(-2, 4):
        jde = _new_moon_jde(k_approx + dk)
        y, m, d = _jde_to_date_cst(jde)
        if y == year and ((m == 1 and d >= 21) or (m == 2 and d <= 20)):
            return m, d
    raise ValueError(f"Could not calculate Lunar New Year for {year}")


# ---------------------------------------------------------------------------
# Holiday lookup tables (2024–2045)
# ---------------------------------------------------------------------------

_DIWALI: dict[int, tuple[int, int]] = {
    2024: (11, 1),
    2025: (10, 20),
    2026: (11, 8),
    2027: (10, 29),
    2028: (10, 17),
    2029: (11, 5),
    2030: (10, 26),
    2031: (11, 14),
    2032: (11, 2),
    2033: (10, 22),
    2034: (11, 11),
    2035: (11, 1),
    2036: (10, 19),
    2037: (11, 7),
    2038: (10, 28),
    2039: (10, 18),
    2040: (11, 4),
    2041: (10, 24),
    2042: (11, 13),
    2043: (11, 3),
    2044: (10, 21),
    2045: (11, 9),
}
_EID_AL_ADHA: dict[int, tuple[int, int]] = {
    2024: (6, 16),
    2025: (6, 6),
    2026: (5, 26),
    2027: (5, 16),
    2028: (5, 4),
    2029: (4, 24),
    2030: (4, 13),
    2031: (4, 2),
    2032: (3, 22),
    2033: (3, 11),
    2034: (3, 1),
    2035: (2, 18),
    2036: (2, 7),
    2037: (1, 26),
    2038: (1, 16),
    2039: (12, 26),
    2040: (12, 14),
    2041: (12, 4),
    2042: (11, 23),
    2043: (11, 13),
    2044: (11, 1),
    2045: (10, 22),
}
_EID_AL_FITR: dict[int, tuple[int, int]] = {
    2024: (4, 10),
    2025: (3, 30),
    2026: (3, 20),
    2027: (3, 9),
    2028: (2, 26),
    2029: (2, 15),
    2030: (2, 4),
    2031: (1, 24),
    2032: (1, 13),
    2033: (1, 2),
    2034: (12, 11),
    2035: (11, 30),
    2036: (11, 19),
    2037: (11, 8),
    2038: (10, 28),
    2039: (10, 17),
    2040: (10, 6),
    2041: (9, 25),
    2042: (9, 14),
    2043: (9, 4),
    2044: (8, 23),
    2045: (8, 12),
}
_HANUKKAH_START: dict[int, tuple[int, int]] = {
    2024: (12, 25),
    2025: (12, 14),
    2026: (12, 4),
    2027: (12, 24),
    2028: (12, 12),
    2029: (12, 1),
    2030: (12, 20),
    2031: (12, 9),
    2032: (11, 27),
    2033: (12, 16),
    2034: (12, 5),
    2035: (12, 25),
    2036: (12, 13),
    2037: (12, 2),
    2038: (12, 22),
    2039: (12, 11),
    2040: (11, 29),
    2041: (12, 18),
    2042: (12, 8),
    2043: (12, 27),
    2044: (12, 15),
    2045: (12, 5),
}
_HOLI: dict[int, tuple[int, int]] = {
    2024: (3, 25),
    2025: (3, 14),
    2026: (3, 3),
    2027: (3, 22),
    2028: (3, 11),
    2029: (3, 1),
    2030: (3, 20),
    2031: (3, 10),
    2032: (2, 27),
    2033: (3, 17),
    2034: (3, 7),
    2035: (3, 26),
    2036: (3, 14),
    2037: (3, 4),
    2038: (3, 23),
    2039: (3, 13),
    2040: (3, 1),
    2041: (3, 19),
    2042: (3, 8),
    2043: (3, 28),
    2044: (3, 16),
    2045: (3, 5),
}
_MID_AUTUMN: dict[int, tuple[int, int]] = {
    2024: (9, 17),
    2025: (10, 6),
    2026: (9, 25),
    2027: (9, 15),
    2028: (10, 3),
    2029: (9, 22),
    2030: (9, 12),
    2031: (10, 1),
    2032: (9, 19),
    2033: (9, 8),
    2034: (9, 27),
    2035: (9, 16),
    2036: (10, 4),
    2037: (9, 24),
    2038: (9, 13),
    2039: (10, 2),
    2040: (9, 20),
    2041: (9, 9),
    2042: (9, 28),
    2043: (9, 17),
    2044: (10, 5),
    2045: (9, 24),
}
_PASSOVER_START: dict[int, tuple[int, int]] = {
    2024: (4, 22),
    2025: (4, 12),
    2026: (4, 1),
    2027: (4, 21),
    2028: (4, 10),
    2029: (3, 29),
    2030: (4, 17),
    2031: (4, 7),
    2032: (3, 27),
    2033: (4, 14),
    2034: (4, 3),
    2035: (4, 23),
    2036: (4, 11),
    2037: (4, 1),
    2038: (4, 20),
    2039: (4, 9),
    2040: (3, 29),
    2041: (4, 16),
    2042: (4, 6),
    2043: (4, 25),
    2044: (4, 13),
    2045: (4, 3),
}
_ROSH_HASHANAH: dict[int, tuple[int, int]] = {
    2024: (10, 2),
    2025: (9, 22),
    2026: (9, 11),
    2027: (10, 1),
    2028: (9, 20),
    2029: (9, 9),
    2030: (9, 27),
    2031: (9, 18),
    2032: (9, 5),
    2033: (9, 24),
    2034: (9, 14),
    2035: (10, 3),
    2036: (9, 21),
    2037: (9, 10),
    2038: (9, 29),
    2039: (9, 19),
    2040: (9, 7),
    2041: (9, 25),
    2042: (9, 15),
    2043: (10, 4),
    2044: (9, 22),
    2045: (9, 12),
}
_SUKKOT_START: dict[int, tuple[int, int]] = {
    2024: (10, 16),
    2025: (10, 6),
    2026: (9, 25),
    2027: (10, 15),
    2028: (10, 4),
    2029: (9, 23),
    2030: (10, 12),
    2031: (10, 1),
    2032: (9, 19),
    2033: (10, 8),
    2034: (9, 28),
    2035: (10, 17),
    2036: (10, 4),
    2037: (9, 24),
    2038: (10, 13),
    2039: (10, 3),
    2040: (9, 21),
    2041: (10, 10),
    2042: (9, 30),
    2043: (10, 18),
    2044: (10, 5),
    2045: (9, 25),
}


# ---------------------------------------------------------------------------
# Seasonal calendar functions
# ---------------------------------------------------------------------------


def _in_holiday_window(
    today: datetime.date,
    table: dict[int, tuple[int, int]],
    days: int = 1,
) -> bool:
    """Return True if *today* falls within *days* days of the holiday in *table*."""
    entry = table.get(today.year)
    if entry is None:
        return False
    try:
        start = _real_date(today.year, entry[0], entry[1])
        return start <= today < start + _real_timedelta(days=days)
    except ValueError:
        return False


def _east_asian_calendar(today: datetime.date) -> "str | list[str] | None":
    if today.month == 4 and 13 <= today.day <= 15:
        return SEASONAL_PALETTES["blue"]
    if today.month == 4 and 1 <= today.day <= 7:
        return SEASONAL_PALETTES["pink"]
    try:
        lny_m, lny_d = _lny_date(today.year)
        lny_start = _real_date(today.year, lny_m, lny_d)
        if lny_start <= today < lny_start + _real_timedelta(days=3):
            return SEASONAL_PALETTES["lny"]
    except ValueError:
        pass
    if _in_holiday_window(today, _MID_AUTUMN, days=2):
        return SEASONAL_PALETTES["yellow"]
    return None


def _hindu_calendar(today: datetime.date) -> "str | list[str] | None":
    if _in_holiday_window(today, _DIWALI, days=5):
        return SEASONAL_PALETTES["gold"]
    if _in_holiday_window(today, _HOLI, days=2):
        return HOLI_RAINBOW
    return None


def _islamic_calendar(today: datetime.date) -> "str | list[str] | None":
    if _in_holiday_window(today, _EID_AL_FITR, days=3):
        return SEASONAL_PALETTES["green"]
    if _in_holiday_window(today, _EID_AL_ADHA, days=3):
        return SEASONAL_PALETTES["green"]
    return None


def _jewish_calendar(today: datetime.date) -> "str | list[str] | None":
    if _in_holiday_window(today, _HANUKKAH_START, days=8):
        return SEASONAL_PALETTES["blue"]
    if _in_holiday_window(today, _ROSH_HASHANAH, days=2):
        return SEASONAL_PALETTES["gold"]
    if _in_holiday_window(today, _PASSOVER_START, days=7):
        return SEASONAL_PALETTES["spring_green"]
    if _in_holiday_window(today, _SUKKOT_START, days=7):
        return SEASONAL_PALETTES["orange"]
    return None


def _sikh_calendar(today: datetime.date) -> "str | list[str] | None":
    if today.month == 4 and today.day == 13:
        return SEASONAL_PALETTES["spring_green"]
    if _in_holiday_window(today, _DIWALI, days=5):
        return SEASONAL_PALETTES["gold"]
    return None


def _western_calendar(today: datetime.date) -> "str | list[str] | None":
    """Return seasonal colour(s) for the western/Gregorian calendar."""
    month = today.month
    day = today.day

    if month == 12:
        return [SEASONAL_PALETTES["red"], SEASONAL_PALETTES["green"]]
    if month == 6:
        return PRIDE_RAINBOW
    if month == 2 and day == 14:
        return SEASONAL_PALETTES["pink"]
    lny = _lny_date(today.year)
    if lny == (month, day) and month == 2:
        return SEASONAL_PALETTES["lny"]
    if month == _easter_month(today.year):
        return SEASONAL_PALETTES["yellow"]
    if month == 10:
        return SEASONAL_PALETTES["orange"]
    return None


CALENDARS: dict[str, object] = {
    "east-asian": _east_asian_calendar,
    "hindu": _hindu_calendar,
    "islamic": _islamic_calendar,
    "jewish": _jewish_calendar,
    "sikh": _sikh_calendar,
    "western": _western_calendar,
}


def apply_seasonal_colour(text: str, index: int, calendar: str = "western") -> str:
    """Wrap *text* in a seasonal ANSI colour based on the current date.

    Lists (December candy-cane, June Pride, Holi rainbow) cycle by *index*.
    Pass ``calendar="off"`` to disable entirely.
    """
    if calendar == "off":
        return text
    calendar_fn = CALENDARS.get(calendar)
    if calendar_fn is None:
        return text
    today = datetime.date.today()
    if today.month == 1:
        colour = SEASONAL_PALETTES["purple"]
        return f"{colour}{text}{_RESET}"
    result = calendar_fn(today)
    if result is None:
        return text
    if isinstance(result, list):
        colour = result[index % len(result)]
    else:
        colour = result
    return f"{colour}{text}{_RESET}"


# ---------------------------------------------------------------------------
# Generic formatting helpers
# ---------------------------------------------------------------------------


def colour_grade_number(num: int | float) -> str:
    """Return *num* as a click-styled string graded green/yellow/orange/red."""
    colour: str | int = "red"
    if num < 10:
        colour = "green"
    elif num < 20:
        colour = "yellow"
    elif num < 50:
        colour = 208  # orange (256-colour)
    return click.style(str(num), fg=colour, bold=True)


def echo_err(msg: str, colour: bool = True, fg: str = "yellow") -> None:
    """Print *msg* to stderr with optional click styling."""
    click.echo(click.style(msg, fg=fg), err=True, color=colour)
