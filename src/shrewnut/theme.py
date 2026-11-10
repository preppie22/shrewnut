"""The application's light or dark theme.

Qt's own ``setColorScheme`` request is ignored by some platform themes (the
Flatpak's portal theme, Qt's ``generic`` one), so off Windows a picked Light
or Dark theme also sets Shrewnut's own palette. Windows follows the request,
so there every theme uses the desktop's palette, except for grey row stripes
in dark mode, where Qt's default ones are navy.

Attributes:
    LIGHT_COLORS (dict[QPalette.ColorRole, QColor]): Light palette, every
        color group.
    LIGHT_DISABLED_COLORS (dict[QPalette.ColorRole, QColor]): Light palette
        colors that differ for disabled widgets.
    DARK_COLORS (dict[QPalette.ColorRole, QColor]): Dark palette, every
        color group.
    DARK_DISABLED_COLORS (dict[QPalette.ColorRole, QColor]): Dark palette
        colors that differ for disabled widgets.
"""
import sys

from PySide6.QtWidgets import (
    QApplication
)
from PySide6.QtGui import (
    QPalette,
    QColor
)
from PySide6.QtCore import (
    Qt,
    QObject,
    Signal
)

from shrewnut.settings import read_setting

LIGHT_COLORS = {
    QPalette.ColorRole.Window: QColor('#efefef'),
    QPalette.ColorRole.WindowText: QColor('#000000'),
    QPalette.ColorRole.Base: QColor('#ffffff'),
    QPalette.ColorRole.AlternateBase: QColor('#f7f7f7'),
    QPalette.ColorRole.Text: QColor('#000000'),
    QPalette.ColorRole.PlaceholderText: QColor('#80000000'),
    QPalette.ColorRole.Button: QColor('#efefef'),
    QPalette.ColorRole.ButtonText: QColor('#000000'),
    QPalette.ColorRole.BrightText: QColor('#ffffff'),
    QPalette.ColorRole.Highlight: QColor('#308cc6'),
    QPalette.ColorRole.HighlightedText: QColor('#ffffff'),
    QPalette.ColorRole.Link: QColor('#0000ff'),
    QPalette.ColorRole.LinkVisited: QColor('#ff00ff'),
    QPalette.ColorRole.ToolTipBase: QColor('#ffffdc'),
    QPalette.ColorRole.ToolTipText: QColor('#000000'),
    QPalette.ColorRole.Light: QColor('#ffffff'),
    QPalette.ColorRole.Midlight: QColor('#cacaca'),
    QPalette.ColorRole.Mid: QColor('#b8b8b8'),
    QPalette.ColorRole.Dark: QColor('#9f9f9f'),
    QPalette.ColorRole.Shadow: QColor('#767676'),
}
LIGHT_DISABLED_COLORS = {
    QPalette.ColorRole.WindowText: QColor('#bebebe'),
    QPalette.ColorRole.Text: QColor('#bebebe'),
    QPalette.ColorRole.ButtonText: QColor('#bebebe'),
    QPalette.ColorRole.Base: QColor('#efefef'),
    QPalette.ColorRole.Highlight: QColor('#919191'),
    QPalette.ColorRole.Dark: QColor('#bebebe'),
    QPalette.ColorRole.Shadow: QColor('#b1b1b1'),
}
DARK_COLORS = {
    QPalette.ColorRole.Window: QColor('#202326'),
    QPalette.ColorRole.WindowText: QColor('#fcfcfc'),
    QPalette.ColorRole.Base: QColor('#141618'),
    QPalette.ColorRole.AlternateBase: QColor('#1d1f22'),
    QPalette.ColorRole.Text: QColor('#fcfcfc'),
    QPalette.ColorRole.PlaceholderText: QColor('#a1a9b1'),
    QPalette.ColorRole.Button: QColor('#292c30'),
    QPalette.ColorRole.ButtonText: QColor('#fcfcfc'),
    QPalette.ColorRole.BrightText: QColor('#4b4b4b'),
    QPalette.ColorRole.Highlight: QColor('#3080aa'),
    QPalette.ColorRole.HighlightedText: QColor('#000000'),
    QPalette.ColorRole.Link: QColor('#3daee9'),
    QPalette.ColorRole.LinkVisited: QColor('#9b59b6'),
    QPalette.ColorRole.ToolTipBase: QColor('#292c30'),
    QPalette.ColorRole.ToolTipText: QColor('#fcfcfc'),
    QPalette.ColorRole.Light: QColor('#151618'),
    QPalette.ColorRole.Midlight: QColor('#1f2124'),
    QPalette.ColorRole.Mid: QColor('#373b40'),
    QPalette.ColorRole.Dark: QColor('#525860'),
    QPalette.ColorRole.Shadow: QColor('#191919'),
}
DARK_DISABLED_COLORS = {
    QPalette.ColorRole.Window: QColor('#292c30'),
    QPalette.ColorRole.WindowText: QColor('#525860'),
    QPalette.ColorRole.Text: QColor('#525860'),
    QPalette.ColorRole.ButtonText: QColor('#525860'),
    QPalette.ColorRole.Base: QColor('#292c30'),
    QPalette.ColorRole.BrightText: QColor('#ffffff'),
    QPalette.ColorRole.Highlight: QColor('#373b40'),
    QPalette.ColorRole.HighlightedText: QColor('#1f2124'),
    QPalette.ColorRole.Shadow: QColor('#252525'),
}

class AppTheme(QObject):
    """Applies the saved theme and tells the windows when it changes.

    Signals:
        theme_changed: The active scheme may have changed and icons should
            be reloaded. Emitted on every ``change_theme`` call, and on a
            desktop scheme change while the theme is ``'System'``.
    """
    theme_changed = Signal()

    def __init__(self, parent = None):
        """Start listening for desktop scheme changes.

        Needs a ``QApplication`` to exist already.

        Args:
            parent (QObject): Optional parent object.
        """
        super().__init__(parent)
        QApplication.instance().styleHints().colorSchemeChanged.connect(self._on_theme_change)

    @staticmethod
    def color_scheme() -> Qt.ColorScheme:
        """Return the scheme Shrewnut is drawn in.

        Returns:
            Qt.ColorScheme: The picked scheme for ``'Light'`` or ``'Dark'``,
            otherwise the desktop's, which can be ``Unknown``.
        """
        saved_scheme = read_setting('theme')
        match saved_scheme:
            case 'Light':
                return Qt.ColorScheme.Light
            case 'Dark':
                return Qt.ColorScheme.Dark
            case _:
                return QApplication.instance().styleHints().colorScheme()

    @staticmethod
    def palette():
        """Return the application palette.

        Returns:
            QPalette: Shrewnut's own palette for ``'Light'`` or ``'Dark'``,
            the desktop's for ``'System'``.
        """
        return QApplication.palette()

    @staticmethod
    def _system_palette() -> QPalette:
        """Return the desktop's palette, fixed up where Qt gets it wrong.

        In Windows dark mode Qt's row stripes (``AlternateBase``) are navy,
        so only that role is set, to grey. Every other role stays unset and
        keeps following the desktop. Whether it's dark mode comes from
        ``color_scheme``, so a picked theme counts, not just the desktop's.

        Returns:
            QPalette: The palette for ``'System'``, and for every theme on
            Windows.
        """
        base_palette = QPalette()
        if sys.platform == "win32":
            scheme = AppTheme.color_scheme()
            if scheme == Qt.ColorScheme.Dark:
                base_palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#383838"))
        return base_palette
        

    def _on_theme_change(self):
        """Follow a desktop scheme change, if the theme is ``'System'``.

        Reapplies the system palette, so the Windows stripe fix matches the
        new scheme, then emits ``theme_changed``.
        """
        if read_setting('theme') == "System":
            QApplication.setPalette(self._system_palette())
            self.theme_changed.emit()

    def change_theme(self):
        """Apply the saved theme setting to the application.

        Qt is always asked for the matching scheme first. ``'System'``
        hands the desktop's palette back. ``'Light'`` and ``'Dark'`` set
        Shrewnut's own palette, except on Windows, where Qt follows the
        request and the desktop's palette is used for them too. Windows dark
        mode gets grey row stripes either way. Emits ``theme_changed``.
        """
        theme = read_setting('theme')
        match theme:
            case 'System': 
                QApplication.instance().styleHints().setColorScheme(Qt.ColorScheme.Unknown)
                QApplication.setPalette(self._system_palette())
            case 'Light':
                QApplication.instance().styleHints().setColorScheme(Qt.ColorScheme.Light)
                if sys.platform == "win32":
                    QApplication.setPalette(self._system_palette())
                else:
                    QApplication.setPalette(_build_palette(LIGHT_COLORS, LIGHT_DISABLED_COLORS))
            case 'Dark': 
                QApplication.instance().styleHints().setColorScheme(Qt.ColorScheme.Dark)
                if sys.platform == "win32":
                    QApplication.setPalette(self._system_palette())
                else:
                    QApplication.setPalette(_build_palette(DARK_COLORS, DARK_DISABLED_COLORS))
        self.theme_changed.emit()

def _build_palette(colors: dict, disabled_colors: dict) -> QPalette:
    """Build a palette from role-to-color maps.

    Args:
        colors (dict[QPalette.ColorRole, QColor]): Colors for every group.
        disabled_colors (dict[QPalette.ColorRole, QColor]): Colors that
            replace those in the Disabled group only.

    Returns:
        QPalette: The finished palette.
    """
    palette = QPalette()
    for role, color in colors.items():
        palette.setColor(role, color)
    for role, color in disabled_colors.items():
        palette.setColor(QPalette.ColorGroup.Disabled, role, color)
    return palette