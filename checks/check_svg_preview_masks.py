"""Native preview clipping preserves holes at zooms exceeding SVG mask limits."""
import os
import sys
from pathlib import Path
from xml.etree import ElementTree

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from planner_app.graphics.svg_preview import SvgPreviewRenderer


def Main():
    app = QtWidgets.QApplication([])
    data = b'''<svg xmlns="http://www.w3.org/2000/svg" width="120" height="100" viewBox="0 0 120 100">
      <defs>
        <clipPath id="door" clipPathUnits="userSpaceOnUse">
          <path fill-rule="evenodd" clip-rule="evenodd" d="M0 0H120V100H0Z M40 30H80V70H40Z"/>
        </clipPath>
        <clipPath id="crop" clipPathUnits="userSpaceOnUse"><path d="M10 10H110V90H10Z"/></clipPath>
      </defs>
      <rect width="120" height="100" fill="#101010"/>
      <g clip-path="url(#crop)"><g clip-path="url(#door)">
        <path d="M0 50H120" stroke="#ffffff" stroke-width="10"/>
      </g></g>
    </svg>'''
    ns = "{http://www.w3.org/2000/svg}"
    assert ElementTree.fromstring(data).findall(f".//{ns}clipPath"), "Export bytes were changed"
    renderer = SvgPreviewRenderer(data)
    assert renderer.isValid()
    for zoom in (1, 2, 4):
        image = QtGui.QImage(120 * zoom, 100 * zoom, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(image)
        renderer.render(painter)
        painter.end()
        assert image.pixelColor(60 * zoom, 50 * zoom) == QtGui.QColor("#101010"), "Wall outline crosses the door opening"
        assert image.pixelColor(5 * zoom, 50 * zoom) == QtGui.QColor("#101010"), "Outer crop was ignored"
        assert image.pixelColor(25 * zoom, 50 * zoom) == QtGui.QColor("#ffffff"), "Clipping removed the solid wall"
    # A small viewport looking at a very large magnification must still show
    # the wall. Bitmap mask rendering would allocate the entire scaled group.
    for zoom in (20, 100, 1000):
        image = QtGui.QImage(300, 300, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(image)
        target = QtCore.QRectF(150 - 25 * zoom, 150 - 50 * zoom, 120 * zoom, 100 * zoom)
        renderer.render(painter, target)
        painter.end()
        assert image.pixelColor(150, 150) == QtGui.QColor("#ffffff"), "Wall vanished at high zoom"
    print("PASS: clipping holes, nested crops, extreme zoom and original export preservation")


if __name__ == "__main__":
    Main()
