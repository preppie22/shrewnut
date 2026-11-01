"""Icon helpers that follow the application's light or dark color scheme.

Attributes:
    material_dark (dict[str, QColor]): Status indicator colors for dark mode.
    material_light (dict[str, QColor]): Status indicator colors for light mode.
"""

from importlib import resources

from PySide6.QtGui import (
    QIcon,
    QPainter,
    QColor,
    QPixmap,
    QPen,
    QPolygonF,
    QPalette,
)
from PySide6.QtCore import (
    Qt,
    QSize,
    QRectF,
    QPointF,
)
import PySide6.QtSvg # preloads Qt6Svg.dll for Windows targets. No effect on Linux.
from PySide6.QtSvg import QSvgRenderer

from shrewnut.theme import AppTheme

material_dark = {
    'blue': QColor('#56B4E9'),
    'green': QColor('#009E73'),
    'red': QColor('#D55E00'),
    'yellow': QColor('#F0E442'),
    'base': QColor('#FDFDFD')
}
material_light = {
    'blue': QColor('#0072B2'),
    'green': QColor('#009E73'),
    'red': QColor('#D55E00'),
    'yellow': QColor('#C9A800'),
    'base': QColor('#020202')
}

def get_logo() -> QIcon:
    """Return the Shrewnut application icon.

    Returns:
        QIcon: The application logo.
    """
    return QIcon(str(resources.files('shrewnut') / 'icons' / 'shrewnut.svg'))

def get_icon(icon_file: str) -> QIcon:
    """Load a bundled icon in the current palette's text color.

    Every ``currentColor`` in the SVG is replaced with the application
    palette's ``WindowText`` color, and the result is drawn into a 64x64
    pixmap that the icon scales down from.

    Args:
        icon_file (str): File name of the icon inside ``icons``.

    Returns:
        QIcon: The icon, colored for the current palette.
    """
    icon_color = AppTheme.palette().color(QPalette.ColorRole.WindowText).name()
    
    svg_text = (resources.files('shrewnut') / 'icons' / icon_file).read_text()
    svg_text = svg_text.replace("currentColor", icon_color)
    
    icon = QPixmap(QSize(64,64))
    icon.fill(Qt.GlobalColor.transparent)
    painter = QPainter(icon)
    icon_svg = QSvgRenderer(svg_text.encode())
    icon_svg.render(painter)
    painter.end()
    
    return QIcon(icon)

def status_indicator(color: str = "") -> QIcon:
    """Draw a status indicator whose shape and color both show the state.

    Each state has its own shape, so it can be told apart without relying
    on color alone: a ring for ``'base'`` (queued), a downward triangle for
    ``'blue'`` (downloading), a check mark for ``'green'`` (done), an X for
    ``'red'`` (failed) and two vertical bars for ``'yellow'`` (paused).

    Args:
        color (str): One of ``'blue'``, ``'green'``, ``'red'`` or
            ``'yellow'``. Any other value draws the neutral ``'base'``
            ring.

    Returns:
        QIcon: A 16x16 indicator in the palette of the current color
        scheme.
    """
    color_scheme = AppTheme.color_scheme()
    if color_scheme == Qt.ColorScheme.Dark:
        icon_color = material_dark.get(color, material_dark['base'])
    else:
        icon_color = material_light.get(color, material_light['base'])
    indicator = QPixmap(QSize(16,16))
    indicator.fill(Qt.GlobalColor.transparent)
    painter = QPainter(indicator)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    match color:
        case 'blue':
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(icon_color)
            painter.drawPolygon(QPolygonF([
                QPointF(2,4),
                QPointF(14,4),
                QPointF(8,13)
            ]))
        case 'green':
            pen = QPen(icon_color, 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolyline([
                QPointF(2.5,8.5),
                QPointF(6.5,12.5),
                QPointF(13.5,3.5)
            ])
        case 'red':
            pen = QPen(icon_color, 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(QPointF(3,3),QPointF(13,13))
            painter.drawLine(QPointF(13,3),QPointF(3,13))
        case 'yellow':
            painter.setBrush(icon_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(QRectF(3, 2, 4, 12))
            painter.drawRect(QRectF(9, 2, 4, 12))
        case _:
            pen = QPen(icon_color, 2)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(pen)
            painter.drawEllipse(indicator.rect().adjusted(1, 1, -1, -1))
    painter.end()
    return QIcon(indicator)
