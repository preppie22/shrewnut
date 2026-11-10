from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from shrewnut import theme
from shrewnut.settings import update_setting
from shrewnut.theme import (
    DARK_COLORS, DARK_DISABLED_COLORS, LIGHT_COLORS, LIGHT_DISABLED_COLORS, AppTheme,
)

PALETTES = {
    "Light": (LIGHT_COLORS, LIGHT_DISABLED_COLORS),
    "Dark": (DARK_COLORS, DARK_DISABLED_COLORS),
}


def _collect(app_theme):
    heard = []
    app_theme.theme_changed.connect(lambda: heard.append(1))
    return heard


def _pinned_roles():
    palette = QApplication.palette()
    return [role.name for role in QPalette.ColorRole if role != QPalette.ColorRole.NColorRoles
            and any(palette.isBrushSet(group, role) for group in
                    (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled))]


def _stripes():
    return QApplication.palette().color(QPalette.ColorRole.AlternateBase).name()


def _system_says(scheme):
    hints = MagicMock()
    hints.colorScheme.return_value = scheme
    return patch.object(QApplication, "styleHints", return_value=hints)


# --- color_scheme ---

@pytest.mark.parametrize("saved, expected", [("Light", Qt.ColorScheme.Light), ("Dark", Qt.ColorScheme.Dark)])
def test_a_picked_theme_wins_whatever_the_desktop_says(saved, expected):
    # The Flatpak case: the portal swears it's Dark, the user said Light,
    # and the user is the one who has to look at it.
    update_setting("theme", saved)
    opposite = Qt.ColorScheme.Dark if expected == Qt.ColorScheme.Light else Qt.ColorScheme.Light

    with _system_says(opposite):
        assert AppTheme.color_scheme() == expected


@pytest.mark.parametrize("desktop", [Qt.ColorScheme.Light, Qt.ColorScheme.Dark, Qt.ColorScheme.Unknown])
def test_system_asks_the_desktop(desktop):
    update_setting("theme", "System")

    with _system_says(desktop):
        assert AppTheme.color_scheme() == desktop


# --- change_theme ---

@pytest.mark.parametrize("theme, window_color", [("Light", "#efefef"), ("Dark", "#202326")])
def test_a_picked_theme_repaints_the_whole_app(theme, window_color):
    update_setting("theme", theme)

    AppTheme().change_theme()

    assert QApplication.palette().color(QPalette.ColorRole.Window).name() == window_color


@pytest.mark.parametrize("theme", ["Light", "Dark"])
def test_every_listed_color_lands_where_it_belongs(theme):
    # Active and Inactive get the main list; Disabled gets the main list with
    # its own overrides on top. Miss one and a single role keeps the
    # desktop's color, which is exactly the sort of thing nobody spots until
    # a tooltip turns up in the wrong scheme.
    colors, disabled_colors = PALETTES[theme]
    update_setting("theme", theme)

    AppTheme().change_theme()

    palette = QApplication.palette()
    for role, color in colors.items():
        assert palette.color(QPalette.ColorGroup.Active, role) == color, role.name
        assert palette.color(QPalette.ColorGroup.Inactive, role) == color, role.name
        assert palette.color(QPalette.ColorGroup.Disabled, role) == disabled_colors.get(role, color), role.name


def test_dark_disabled_text_is_dim_but_not_invisible():
    # QPalette(QColor) would have built this palette from one color and
    # served #101113 text on a #202326 window: technically present,
    # practically a secret.
    update_setting("theme", "Dark")

    AppTheme().change_theme()

    palette = QApplication.palette()
    text = palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text).lightness()
    window = palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Window).lightness()
    assert text - window > 30


def test_going_back_to_system_hands_the_palette_back():
    # Every role still pinned after this would freeze that color, and the
    # next desktop switch would only half happen.
    app_theme = AppTheme()
    update_setting("theme", "Dark")
    app_theme.change_theme()

    update_setting("theme", "System")
    app_theme.change_theme()

    assert _pinned_roles() == []


@pytest.mark.parametrize("theme, scheme", [
    ("System", Qt.ColorScheme.Unknown), ("Light", Qt.ColorScheme.Light), ("Dark", Qt.ColorScheme.Dark),
])
def test_change_theme_still_asks_qt_first(theme, scheme):
    # Where Qt listens (the AppImage on KDE, Windows), it gets the request
    # too, so it doesn't keep insisting on the old scheme behind our backs.
    update_setting("theme", theme)
    app_theme = AppTheme()
    hints = MagicMock()

    with patch.object(QApplication, "styleHints", return_value=hints):
        app_theme.change_theme()

    hints.setColorScheme.assert_called_once_with(scheme)


@pytest.mark.parametrize("theme", ["System", "Light", "Dark"])
def test_change_theme_announces_itself_even_when_qt_shrugs(theme):
    # Offscreen Qt, like the Flatpak's portal theme, ignores the request and
    # never fires colorSchemeChanged. The windows still need to hear about it.
    update_setting("theme", theme)
    app_theme = AppTheme()
    heard = _collect(app_theme)

    app_theme.change_theme()
    QApplication.processEvents()

    assert len(heard) == 1


# --- desktop switches ---

def test_a_desktop_switch_is_passed_on_when_following_the_system():
    update_setting("theme", "System")
    app_theme = AppTheme()
    heard = _collect(app_theme)

    QApplication.instance().styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)

    assert len(heard) == 1


@pytest.mark.parametrize("theme", ["Light", "Dark"])
def test_a_desktop_switch_is_none_of_our_business_when_a_theme_is_picked(theme):
    # The user picked a side. The desktop changing its mind doesn't change theirs.
    update_setting("theme", theme)
    app_theme = AppTheme()
    heard = _collect(app_theme)

    QApplication.instance().styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)

    assert heard == []


# --- Windows row stripes ---

WINDOWS_GREY = "#383838"  # Qt 6.12 hands Fusion navy (#001a68) in Windows dark mode instead


@pytest.fixture
def on_windows(monkeypatch):
    # Pretend to be Windows for theme.py only. conftest hands the palette
    # back afterwards, so the stripes don't haunt the next test.
    monkeypatch.setattr(theme, "sys", SimpleNamespace(platform="win32"))


def _desktop_switches_to(scheme):
    # Offscreen Qt never switches on its own, so play the desktop: fake the
    # new answer and fire the signal Windows would fire. Grab the real signal
    # first, once styleHints is patched it hands out the mock's instead.
    switched = QApplication.instance().styleHints().colorSchemeChanged
    with _system_says(scheme):
        switched.emit(scheme)
    QApplication.processEvents()


def test_windows_dark_mode_gets_grey_stripes_instead_of_navy(on_windows):
    update_setting("theme", "System")

    with _system_says(Qt.ColorScheme.Dark):
        AppTheme().change_theme()

    assert _stripes() == WINDOWS_GREY


def test_windows_dark_mode_only_touches_the_stripes(on_windows):
    # Everything else still comes from Windows. Pinning the whole palette
    # would freeze it, and the next desktop switch would only half happen.
    update_setting("theme", "System")

    with _system_says(Qt.ColorScheme.Dark):
        AppTheme().change_theme()

    assert _pinned_roles() == ["AlternateBase"]


def test_windows_light_mode_keeps_its_own_stripes(on_windows):
    update_setting("theme", "System")

    with _system_says(Qt.ColorScheme.Light):
        AppTheme().change_theme()

    assert _pinned_roles() == []


def test_desktop_going_light_hands_the_stripes_back_to_windows(on_windows):
    # The grey override outlives the switch unless someone takes it off.
    # Without that, light mode would wear #383838 stripes on white like a
    # zebra in mourning.
    update_setting("theme", "System")
    app_theme = AppTheme()
    with _system_says(Qt.ColorScheme.Dark):
        app_theme.change_theme()

    _desktop_switches_to(Qt.ColorScheme.Light)

    assert _pinned_roles() == []


def test_desktop_going_dark_gets_grey_stripes_too(on_windows):
    # Starting in light and switching later is the same navy problem,
    # it just shows up after lunch instead of at startup.
    update_setting("theme", "System")
    app_theme = AppTheme()
    with _system_says(Qt.ColorScheme.Light):
        app_theme.change_theme()

    _desktop_switches_to(Qt.ColorScheme.Dark)

    assert _stripes() == WINDOWS_GREY


def test_picking_light_on_windows_looks_like_windows_light(on_windows):
    # Windows actually listens to setColorScheme, so Light is Windows' own
    # light palette, accent colour and all. Shrewnut's palette would just
    # make Light and System-light look like distant cousins. The desktop
    # says Dark to prove the pick wins.
    update_setting("theme", "Light")

    with _system_says(Qt.ColorScheme.Dark):
        AppTheme().change_theme()

    assert _pinned_roles() == []


def test_picking_dark_on_windows_still_gets_grey_stripes(on_windows):
    # Windows' dark palette, navy stripes and all, unless we step in. The
    # desktop says Light to prove the stripes follow the pick, not the desktop.
    update_setting("theme", "Dark")

    with _system_says(Qt.ColorScheme.Light):
        AppTheme().change_theme()

    assert _pinned_roles() == ["AlternateBase"]
    assert _stripes() == WINDOWS_GREY


def test_other_platforms_keep_their_own_stripes(monkeypatch):
    # Linux takes its colours from KDE or GNOME, which get this right.
    monkeypatch.setattr(theme, "sys", SimpleNamespace(platform="linux"))
    update_setting("theme", "System")

    with _system_says(Qt.ColorScheme.Dark):
        AppTheme().change_theme()

    assert _pinned_roles() == []
