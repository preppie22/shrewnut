from importlib import resources
from unittest.mock import patch

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from shrewnut.icon_utils import get_icon, material_dark, material_light, status_indicator


ICONS_DIR = resources.files("shrewnut") / "icons"
THEMED_ICONS = sorted(f.name for f in ICONS_DIR.iterdir() if f.name.endswith(".svg") and f.name != "shrewnut.svg")


def painted_colors(icon):
    image = icon.pixmap(QSize(32, 32)).toImage()
    # Opaque pixels only. The antialiased edges are a blend with
    # transparency and would vote for colors nobody picked.
    return {
        image.pixelColor(x, y).name()
        for x in range(image.width()) for y in range(image.height())
        if image.pixelColor(x, y).alpha() == 255
    }


def test_get_icon_returns_a_non_null_icon():
    icon = get_icon("download.svg")

    assert not icon.isNull()


@pytest.mark.parametrize("text_color", ["#ff00ff", "#00ff00"])
def test_get_icon_paints_in_the_palettes_text_color(text_color):
    # Two colors no theme would ever ship, so a pass can't be a lucky match
    # with whatever the test machine's palette happens to be.
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.WindowText, QColor(text_color))
    QApplication.setPalette(palette)

    colors = painted_colors(get_icon("download.svg"))

    assert colors == {text_color}


def test_get_icon_follows_a_palette_change_on_the_next_call():
    # Icons reload on theme_changed, after change_theme swapped the palette.
    # Nothing may be cached in between, or the reload hands out yesterday's ink.
    for text_color in ("#ff00ff", "#00ff00"):
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.WindowText, QColor(text_color))
        QApplication.setPalette(palette)

        assert painted_colors(get_icon("download.svg")) == {text_color}


@pytest.mark.parametrize("icon_file", THEMED_ICONS)
def test_every_bundled_icon_takes_its_color_from_the_theme(icon_file):
    # An icon pasted in with a hardcoded fill skips the recoloring and
    # turns up black on black in dark mode. currentColor is the only hook.
    svg_text = (ICONS_DIR / icon_file).read_text()

    assert "currentColor" in svg_text
    assert not painted_colors(get_icon(icon_file)) - {QApplication.palette().color(QPalette.ColorRole.WindowText).name()}


# --- status_indicator ---

STATES = ["base", "blue", "green", "red", "yellow"]


def draw_indicator(mock_theme_cls, scheme, state):
    mock_theme_cls.color_scheme.return_value = scheme
    return status_indicator(state).pixmap(QSize(16, 16)).toImage()


def shape_of(image):
    # Only where paint landed, never what color it is. This is what a
    # colour-blind user (or a greyscale screenshot) gets to work with.
    return {(x, y) for x in range(image.width()) for y in range(image.height()) if image.pixelColor(x, y).alpha() > 128}


@pytest.mark.parametrize("scheme", [Qt.ColorScheme.Light, Qt.ColorScheme.Dark])
@pytest.mark.parametrize("state", STATES + ["mystery"])
@patch("shrewnut.icon_utils.AppTheme")
def test_status_indicator_paints_something_for_every_state(mock_theme_cls, state, scheme):
    # A shape that throws halfway through painting takes the whole app down
    # with it (a QPainter that never ends is a segfault waiting to happen),
    # so every state has to make it to the finish line in both schemes.
    image = draw_indicator(mock_theme_cls, scheme, state)

    assert image.size() == QSize(16, 16)
    assert len(shape_of(image)) > 10


@patch("shrewnut.icon_utils.AppTheme")
def test_every_state_has_its_own_shape_regardless_of_color(mock_theme_cls):
    shapes = {state: shape_of(draw_indicator(mock_theme_cls, Qt.ColorScheme.Dark, state)) for state in STATES}

    for i, first in enumerate(STATES):
        for second in STATES[i + 1:]:
            assert shapes[first] != shapes[second], f"{first} and {second} are the same shape"


@patch("shrewnut.icon_utils.AppTheme")
def test_unknown_state_falls_back_to_the_queued_ring(mock_theme_cls):
    ring = draw_indicator(mock_theme_cls, Qt.ColorScheme.Dark, "base")

    assert draw_indicator(mock_theme_cls, Qt.ColorScheme.Dark, "mystery") == ring
    assert draw_indicator(mock_theme_cls, Qt.ColorScheme.Dark, "") == ring


@pytest.mark.parametrize("state", STATES)
@patch("shrewnut.icon_utils.AppTheme")
def test_status_indicator_uses_the_palette_of_the_active_scheme(mock_theme_cls, state):
    for scheme, palette in [(Qt.ColorScheme.Dark, material_dark), (Qt.ColorScheme.Light, material_light)]:
        image = draw_indicator(mock_theme_cls, scheme, state)
        drawn = {image.pixelColor(x, y).rgb() for x, y in shape_of(image) if image.pixelColor(x, y).alpha() == 255}

        # The middle of a stroke is fully opaque and exactly the palette color.
        assert palette[state].rgb() in drawn


@patch("shrewnut.icon_utils.AppTheme")
def test_status_indicator_looks_different_in_dark_and_light(mock_theme_cls):
    # Blue on purpose: green and red happen to be the same in both schemes,
    # which makes for a very boring comparison.
    dark = draw_indicator(mock_theme_cls, Qt.ColorScheme.Dark, "blue")
    light = draw_indicator(mock_theme_cls, Qt.ColorScheme.Light, "blue")

    assert dark != light
