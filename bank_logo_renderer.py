"""Render the supported logo sources consistently in Qt (SVG Tiny)."""
from copy import deepcopy
import xml.etree.ElementTree as ET
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

SVG = '{http://www.w3.org/2000/svg}'

def qt_svg_bytes(path):
    root = ET.parse(path).getroot()
    # Qt renders SVG symbols/use incompletely. Expand local symbols while
    # preserving their viewport mapping and original transform.
    symbols = {node.get('id'): node for node in root.iter(SVG + 'symbol')}
    for parent in list(root.iter()):
        for node in list(parent):
            href = node.get('{http://www.w3.org/1999/xlink}href', node.get('href', ''))
            if node.tag != SVG + 'use' or href.lstrip('#') not in symbols:
                continue
            symbol = symbols[href[1:]]
            vb = [float(v) for v in symbol.get('viewBox', '0 0 1 1').split()]
            x, y = float(node.get('x', 0)), float(node.get('y', 0))
            w, h = float(node.get('width', vb[2])), float(node.get('height', vb[3]))
            scale = min(w / vb[2], h / vb[3])
            tx = x + (w - vb[2] * scale) / 2 - vb[0] * scale
            ty = y + (h - vb[3] * scale) / 2 - vb[1] * scale
            group = ET.Element(SVG + 'g', {'transform': node.get('transform', '')})
            mapped = ET.SubElement(group, SVG + 'g',
                {'transform': f'translate({tx} {ty}) scale({scale})'})
            for child in symbol:
                mapped.append(deepcopy(child))
            parent.insert(list(parent).index(node), group)
            parent.remove(node)
    # This source paints a rectangle through a wordmark clip. Qt ignores that
    # clipping construct; the clip itself is the complete green logo outline.
    if path.stem == 'sekerbank':
        shape = root.find('.//' + SVG + 'clipPath/' + SVG + 'path')
        if shape is not None:
            clean = ET.Element(SVG + 'svg', {'viewBox': root.get('viewBox')})
            outline = deepcopy(shape)
            outline.set('fill', '#007a3d')
            clean.append(outline)
            root = clean
    # The Fibabanka source includes a filter-compositing background. Qt does
    # not implement that filter and paints its backing rectangle black. The
    # remaining paths already contain the complete coloured foreground.
    if path.stem == 'fibabanka':
        for node in list(root):
            if node.tag == SVG + 'g' and node.get('filter'):
                root.remove(node)
    return ET.tostring(root)

def bank_icon(path, width=96, height=24):
    if not path:
        return QIcon()
    try:
        renderer = QSvgRenderer(QByteArray(qt_svg_bytes(path)))
    except (OSError, ET.ParseError, ValueError):
        return QIcon()
    if not renderer.isValid() or renderer.viewBoxF().width() <= 0 or renderer.viewBoxF().height() <= 0:
        return QIcon()
    density = 3
    canvas = QPixmap(width * density, height * density)
    canvas.setDevicePixelRatio(density)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    box = renderer.viewBoxF()
    scale = min((width - 8) / box.width(), (height - 4) / box.height())
    w, h = box.width() * scale, box.height() * scale
    renderer.render(painter, QRectF((width-w)/2, (height-h)/2, w, h))
    painter.end()
    return QIcon(canvas)

def menu_icon(path):
    """96px logo plus a 14px transparent text gutter, at 3x density."""
    source = bank_icon(path, 96, 24)
    if source.isNull():
        return source
    canvas = QPixmap(330, 72)
    canvas.setDevicePixelRatio(3)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    from PySide6.QtCore import QSize
    painter.drawPixmap(0, 0, source.pixmap(QSize(96, 24), 3))
    painter.end()
    return QIcon(canvas)
