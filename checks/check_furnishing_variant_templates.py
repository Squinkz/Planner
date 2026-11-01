"""Frozen SVG bytes and exact pixels across furnishing transform/cache changes."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from planner_app.graphics import furnishings
from planner_app.graphics.fonts import LoadApplicationFonts
from fixtures.furnishing_variant_cases_20261031 import MakeRenderer, VariantCases, EdgeSource


def Pixels(renderer, frame, nominal, vector = False, physical = True):
    dpr = float(os.environ.get("QT_SCALE_FACTOR", "1"))
    image = QtGui.QImage(round(540 * dpr), round(420 * dpr), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(dpr)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    device = image
    if vector:
        data = QtCore.QByteArray()
        buffer = QtCore.QBuffer(data)
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        device = QtSvg.QSvgGenerator()
        device.setOutputDevice(buffer)
        device.setSize(QtCore.QSize(540, 420))
        device.setViewBox(QtCore.QRect(0, 0, 540, 420))
    with QtGui.QPainter(device) as painter:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setClipRect(QtCore.QRectF(7, 11, 525, 398))
        painter.setOpacity(.73 if frame % 3 else 1)
        painter.translate(270.37 + frame % 5, 210.71)
        painter.rotate(frame * 13.17)
        painter.scale(-.8 if frame % 5 == 0 else 1.13, .67 + frame % 4 * .13)
        painter.shear(.12 if frame % 4 == 0 else 0, -.07)
        bounds = QtCore.QRectF(-190.21, -130.37, 300 + frame * .71, 220 + frame * .37)
        worldSize = (nominal[0] * (1 + frame * .013), nominal[1] * (1 - frame * .003)) if physical else None
        if frame == 32:
            worldSize = (0, nominal[1])
        elif frame == 33:
            worldSize = (-nominal[0], nominal[1])
        elif frame == 34:
            bounds.setWidth(0)
        elif frame == 35:
            painter.scale(0, 1)
        renderer.render(painter, bounds, worldSize = worldSize)
    if vector:
        # Compare ordinary export rasterization independently of the SVG bytes.
        with QtGui.QPainter(image) as painter:
            QtSvg.QSvgRenderer(data).render(painter, QtCore.QRectF(0, 0, 540, 420))
        return image, bytes(data)
    return image


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    cases = VariantCases() + [("nested/clip/gradient", EdgeSource(), (900, 600))]
    cases.append(("duplicate text IDs", EdgeSource().replace(b'</g></svg>', b'<text id="caption" x="50" y="60">Z</text></g></svg>'), (900, 600)))
    comparisons = 0
    native = QtSvg.QSvgRenderer
    for index, (name, source, nominal) in enumerate(cases):
        options = dict(solidBackground = index % 2 == 0, selectionColor = "#59ad23" if index % 3 == 0 else None,
                       lineWidth = .35 if index % 2 else 1.4)
        current = MakeRenderer(source, nominal, **options)
        reference = MakeRenderer(source, nominal, reference = True, **options)
        currentSources = set()
        for frame in (*range(36), 2, 35, 0, 16):
            with patch.object(furnishings.QtSvg, "QSvgRenderer", wraps = native) as construct:
                expected = Pixels(reference, frame, nominal, physical = frame % 7 != 0)
                referenceSources = [bytes(call.args[0]) for call in construct.call_args_list]
            with patch.object(furnishings.QtSvg, "QSvgRenderer", wraps = native) as construct:
                actual = Pixels(current, frame, nominal, physical = frame % 7 != 0)
                currentSources.update(bytes(call.args[0]) for call in construct.call_args_list)
            assert actual == expected, (name, frame, "native raster")
            assert all(source in currentSources for source in referenceSources), (name, frame, "serialized SVG changed")
            assert len(current.letteringVariants) <= 16
            comparisons += 1
        for frame in (1, 5, 19, 32, 33):
            assert Pixels(current, frame, nominal, vector = True) == Pixels(reference, frame, nominal, vector = True), (name, frame, "SVG output")
            comparisons += 1
    # After the first variant, continuous lettering edits need neither a tree
    # copy nor a full XML serialization. Qt still parses genuinely new variants.
    source, nominal = cases[0][1:]
    renderer = MakeRenderer(source, nominal)
    Pixels(renderer, 1, nominal)
    with patch.object(furnishings, "deepcopy", side_effect = AssertionError("Repeated SVG tree copy")), \
            patch.object(furnishings.ElementTree, "tostring", side_effect = AssertionError("Repeated SVG serialization")):
        for frame in range(2, 25):
            Pixels(renderer, frame, nominal)
    assert len(renderer.letteringVariants) == 16
    # Fixed-detail-only variants are independent of camera/bounds. Physical size
    # edits still make distinct variants, including a return to an earlier size.
    source, nominal = cases[1][1:]
    renderer = MakeRenderer(source, nominal)
    image = QtGui.QImage(540, 420, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    with patch.object(furnishings.QtSvg, "QSvgRenderer", wraps = native) as construct:
        for frame in range(25):
            image.fill(QtCore.Qt.GlobalColor.transparent)
            with QtGui.QPainter(image) as painter:
                painter.translate(200, 200)
                painter.rotate(frame * 7.31)
                painter.scale(.5 + frame * .03, 1.3)
                renderer.render(painter, QtCore.QRectF(-100, -75, 200 + frame, 150), worldSize = nominal)
        assert construct.call_count == 1, "Camera-only changes rebuilt a fixed-detail SVG"
    assert len(renderer.letteringVariants) == 1
    print(f"PASS: {comparisons} exact frozen raster/SVG comparisons, identical variant bytes, degenerate/mirrored transforms, bounded reuse and no warm tree serialization.")


if __name__ == "__main__":
    Main()
