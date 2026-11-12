"""
icons.py - Crisp vector SVG icons for the PySide6 desktop interface.
"""

from typing import Dict

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_SVG_TEMPLATES: Dict[str, str] = {
    "folder": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>'
        '</svg>'
    ),
    "file": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<polyline points="14 2 14 8 20 8"/>'
        '<line x1="16" y1="13" x2="8" y2="13"/>'
        '<line x1="16" y1="17" x2="8" y2="17"/>'
        '</svg>'
    ),
    "refresh": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="23 4 23 10 17 10"/>'
        '<polyline points="1 20 1 14 7 14"/>'
        '<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>'
        '</svg>'
    ),
    "plus": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="10"/>'
        '<line x1="12" y1="8" x2="12" y2="16"/>'
        '<line x1="8" y1="12" x2="16" y2="12"/>'
        '</svg>'
    ),
    "play": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polygon points="6 3 20 12 6 21 6 3"/>'
        '</svg>'
    ),
    "zap": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>'
        '</svg>'
    ),
    "terminal": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="4 17 10 11 4 5"/>'
        '<line x1="12" y1="19" x2="20" y2="19"/>'
        '</svg>'
    ),
    "check_circle": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>'
        '<polyline points="22 4 12 14.01 9 11.01"/>'
        '</svg>'
    ),
    "clock": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="10"/>'
        '<polyline points="12 6 12 12 16 14"/>'
        '</svg>'
    ),
    "layers": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polygon points="12 2 2 7 12 12 22 7 12 2"/>'
        '<polyline points="2 17 12 22 22 17"/>'
        '<polyline points="2 12 12 17 22 12"/>'
        '</svg>'
    ),
}


def get_pixmap(name: str, size: int = 16, color: str = "#334155") -> QPixmap:
    """Render a named SVG icon into a crisp QPixmap."""
    svg_template = _SVG_TEMPLATES.get(name, _SVG_TEMPLATES["layers"])
    svg_bytes = QByteArray(svg_template.format(color=color).encode("utf-8"))
    renderer = QSvgRenderer(svg_bytes)
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def get_icon(name: str, size: int = 16, color: str = "#334155") -> QIcon:
    """Return a QIcon rendered from the named SVG template."""
    return QIcon(get_pixmap(name, size=size, color=color))
