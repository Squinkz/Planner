"""Endpoint edit raster pixels match direct painting through live changes."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner_app.models import Wall, Door, SilledWindow, Fireplace, Counter, Stair, Railing, Furnishing, Label, NorthArrow, Column
from planner_app.ui.main_window import MainWindow
from planner_app.graphics.fonts import LoadApplicationFonts


def Compare(viewport):
    cached = viewport.grab().toImage()
    names = ("viewportEditRaster", "viewportEditKey", "viewportEditSnapshot", "viewportEditState", "viewportEditDirtyRects",
             "viewportEditFrameKey", "viewportEditBackgroundKey")
    state = [getattr(viewport, name) for name in names]
    viewport.editPaintEnabled = False
    try:
        direct = viewport.grab().toImage()
    finally:
        viewport.editPaintEnabled = True
        for name, value in zip(names, state):
            setattr(viewport, name, value)
    if cached != direct:
        # Qt's intersected clip masks can round an antialiased stroke slightly
        # differently in a partial repaint (one stair-tip pixel differs by
        # 4/255 at 150% scaling). Limit both the channel error and pixel count.
        first = memoryview(cached.constBits()).cast("I")
        second = memoryview(direct.constBits()).cast("I")
        differences = []
        minorCount = 0
        for index, (left, right) in enumerate(zip(first, second)):
            if left != right:
                minorCount += 1
                if any(abs((left >> shift & 255) - (right >> shift & 255)) > 4 for shift in (0, 8, 16, 24)):
                    differences.append((index % cached.width(), index // cached.width()))
        assert minorCount <= max(128, cached.width() * cached.height() // 5000), minorCount
        if not differences:
            return
        cached.save(str(Path(__file__).resolve().parent.parent / "diagnostics/edit-cache-cached.png"))
        direct.save(str(Path(__file__).resolve().parent.parent / "diagnostics/edit-cache-direct.png"))
        raise AssertionError((len(differences), differences[:10], viewport.viewportEditDirtyRects))


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    main = MainWindow()
    main.resize(1440, 900)
    main.show()
    app.processEvents()
    viewport = main.viewport
    viewport.editPaintMinimumObjects = 0
    viewport.editDirtyFractionLimit = 1.1
    viewport.performanceTimer.stop()
    viewport.performanceLabel.hide()
    point = QtCore.QPointF
    source = Wall(point(-1600, 1300), point(1800, 1300), 240, material = "Brick")
    branch = Wall(point(-1600, 1300), point(-1600, -1300), 180, material = "Lumber")
    bottom = Wall(point(-1600, -1300), point(1800, -1300), 240)
    contained = Wall(point(-500, 1300), point(200, 1300), 80)
    viewport.walls = [source, branch, bottom, contained,
                      Counter(point(-1200, -800), point(700, -800), 600),
                      Stair(point(1200, -1100), point(1200, 300), 700),
                      Railing(point(-1000, -1700), point(1000, -1700), 80),
                      Column(point(-700, -200), point(-700, 200), 400)]
    viewport.windows = [Door(source, .25, .5), SilledWindow(branch, .2, .45), Fireplace(bottom, .3, .6)]
    viewport.furnishings = [Furnishing(viewport.furnishingDefinitions["desk"], point(100, 0)), NorthArrow(point(-2000, 1800))]
    viewport.labels = [Label(point(0, -1900), "Retained scene")]
    viewport.zoom = .7
    viewport.panOffset = point(.37, .71)
    viewport.snapEnabled = False
    viewport.SetSelection([(source, 1)])
    start = viewport.WorldToViewport(source.secondVertex).toPoint()
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos = start)
    for index, delta in enumerate((point(20, 30), point(35, -25), point(-40, 55), point(150, 80),
                                   point(-150, 200), point(50, -90), point(5, 5))):
        viewport.UpdateInteraction(point(start) + delta, QtCore.Qt.KeyboardModifier.NoModifier)
        viewport.repaint()
        assert viewport.viewportEditRaster is not None
        with patch.object(viewport, "DrawScene", wraps = viewport.DrawScene) as draw:
            viewport.repaint()
            assert draw.call_count == 0, "An unchanged edit frame repainted physical objects"
        if index == 2:
            viewport.windows[0].swingsOutwards = True
        if index == 3:
            source.material = "Lumber"
        if index == 4:
            viewport.lineWidths["walls"] *= 1.4
        if index == 5:
            viewport.zoom *= 1.1
        Compare(viewport)
        assert viewport.rasterCacheBudget.RetainedBytes() <= viewport.viewportRasterByteLimit
    viewport.walls = [obj for obj in viewport.walls if not isinstance(obj, Column)]
    for delta in (point(60, 30), point(110, -50), point(-50, 90)):
        viewport.UpdateInteraction(point(start) + delta, QtCore.Qt.KeyboardModifier.NoModifier)
        viewport.repaint()
        Compare(viewport)
    for theme in ("Light Canvas", "Blueprint Canvas", "Dark Canvas"):
        main.SetThemes(canvasTheme = theme)
        viewport.repaint()
        Compare(viewport)
        viewport.UpdateInteraction(point(start) + point(60, 40), QtCore.Qt.KeyboardModifier.NoModifier)
        viewport.repaint()
        Compare(viewport)
    # Guides keep their existing layering by using direct rendering.
    viewport.alignmentGuides = [(0, 100)]
    viewport.repaint()
    assert viewport.viewportEditRaster is None
    Compare(viewport)
    viewport.alignmentGuides = []
    viewport.repaint()
    Compare(viewport)
    viewport.editDirtyFractionLimit = 0
    viewport.UpdateInteraction(point(start) + point(70, 110), QtCore.Qt.KeyboardModifier.NoModifier)
    viewport.repaint()
    assert viewport.viewportEditRaster is not None
    assert viewport.viewportEditSuppressedGesture is viewport.interactionBefore
    Compare(viewport)
    viewport.viewportEditSuppressedGesture = None
    viewport.editDirtyFractionLimit = 1.1
    # Refusing an extra full frame must fall back without retaining it.
    viewport.viewportRasterByteLimit = 1
    viewport.repaint()
    assert viewport.viewportEditRaster is None
    Compare(viewport)
    viewport.viewportRasterByteLimit = 128 * 1024 * 1024
    viewport.repaint()
    Compare(viewport)
    viewport.CancelInteraction()
    viewport.repaint()
    assert viewport.viewportEditRaster is None
    Compare(viewport)
    parent = Wall(point(-2000, 0), point(2000, 0), 240)
    source = Wall(point(0, 900), point(0, -100), 120)
    attach = Wall(point(0, 900), point(1000, 900), 120)
    opening = Door(parent, .4, .6)
    opening.geometryIssues = ["opening_obstruction"]
    viewport.walls = [parent, source, attach]
    viewport.windows = [opening]
    viewport.furnishings = viewport.labels = []
    viewport.zoom = .7
    viewport.panOffset = point(.37, .71)
    viewport.SetSelection([(source, 1)])
    start = viewport.WorldToViewport(source.secondVertex).toPoint()
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos = start)
    for delta in (point(5, 5), point(5, -40), point(-10, 10)):
        viewport.UpdateInteraction(point(start) + delta, QtCore.Qt.KeyboardModifier.NoModifier)
        viewport.repaint()
        Compare(viewport)
    viewport.CancelInteraction()
    main.close()
    print("PASS: edit pixels, attachments, materials, openings, columns, camera/width changes, guides and budget fallback.")


if __name__ == "__main__":
    Main()
