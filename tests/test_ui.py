import datetime

from fiveclis.ui import (
    HOLI_RAINBOW,
    PRIDE_RAINBOW,
    SEASONAL_PALETTES,
    THEME_NAMES,
    THEMES,
    apply_seasonal_colour,
    get_theme,
)


def test_seasonal_palettes_has_expected_keys():
    expected = (
        "green",
        "purple",
        "yellow",
        "orange",
        "red",
        "pink",
        "lny",
        "blue",
        "spring_green",
        "gold",
    )
    for key in expected:
        assert key in SEASONAL_PALETTES


def test_pride_rainbow_has_six_colours():
    assert len(PRIDE_RAINBOW) == 6


def test_holi_rainbow_has_six_colours():
    assert len(HOLI_RAINBOW) == 6


def test_themes_registry_has_all_names():
    for name in ("default", "dark", "light", "mono", "rainbow"):
        assert name in THEMES


def test_theme_names_list():
    assert "rainbow" in THEME_NAMES
    assert "mono" in THEME_NAMES


def test_get_theme_known():
    t = get_theme("rainbow")
    assert t.cycle == PRIDE_RAINBOW


def test_get_theme_unknown_falls_back_to_default():
    t = get_theme("nonexistent")
    assert t is THEMES["default"]


def test_mono_theme_has_no_colours():
    t = get_theme("mono")
    assert t.primary is None
    assert t.accent is None


def test_theme_apply_mono_returns_plain(monkeypatch):
    t = get_theme("mono")
    result = t.apply("hello", role="primary")
    assert result == "hello"


def test_theme_apply_cycle(monkeypatch):
    t = get_theme("rainbow")
    result_0 = t.apply_cycle("a", 0)
    result_1 = t.apply_cycle("a", 1)
    assert result_0 != result_1


def test_apply_seasonal_colour_off():
    result = apply_seasonal_colour("hello", 0, calendar="off")
    assert result == "hello"


def test_apply_seasonal_colour_unknown_calendar():
    result = apply_seasonal_colour("hello", 0, calendar="martian")
    assert result == "hello"


def test_apply_seasonal_colour_january(monkeypatch):
    fixed = datetime.date(2026, 1, 15)
    monkeypatch.setattr(
        "fiveclis.ui.datetime.date",
        type("MockDate", (), {"today": staticmethod(lambda: fixed)}),
    )
    result = apply_seasonal_colour("hello", 0, calendar="western")
    assert SEASONAL_PALETTES["purple"] in result


def test_apply_seasonal_colour_june_cycles(monkeypatch):
    fixed = datetime.date(2026, 6, 15)
    monkeypatch.setattr(
        "fiveclis.ui.datetime.date",
        type("MockDate", (), {"today": staticmethod(lambda: fixed)}),
    )
    r0 = apply_seasonal_colour("a", 0, calendar="western")
    r1 = apply_seasonal_colour("a", 1, calendar="western")
    assert r0 != r1
