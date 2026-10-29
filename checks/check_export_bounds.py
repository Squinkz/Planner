"""Shared auto crop, draggable full-canvas guides and selection-free preview."""
import copy
import json
import os
import sys
import tempfile
from types import SimpleNamespace
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall
from planner_app.export_bounds import AutomaticBounds
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.graphics.palette import themeColors
from planner_app.project_codec import DecodeProject
from planner_app.export_plan import RenderPlan


def Main():
    # Automatic bounds retain exact footprints and one metre of padding.
    fixture = SimpleNamespace(walls = [], windows = [], furnishings = [], labels = [],
                              IsObjectVisible = lambda obj: True, ObjectFootprint = lambda obj: (None, obj))
    for left, bottom, right, top in ((1234, 1567, 3456, 3789), (-3789, -3456, -1567, -1234),
                                   (-1234, -1567, 3456, 3789), (0, 0, 1000, 2000)):
        fixture.walls = [(QtCore.QPointF(left, bottom), QtCore.QPointF(right, top))]
        x, y, width, height = AutomaticBounds(fixture)
        assert (x, y, width, height) == (left - 1000, bottom - 1000, right - left + 2000, top - bottom + 2000)
    with tempfile.TemporaryDirectory(dir = Path(__file__).parent) as folder:
        os.environ["PLANNER_SESSION_PATH"] = str(Path(folder) / "session.json")
        os.environ["PLANNER_STARTUP_PATH"] = str(Path(folder) / "startup.plan")
        app = QtWidgets.QApplication([])
        ApplyApplicationTheme(app)
        main = MainWindow()
        main.show()
        v = main.viewport
        wall = Wall(QtCore.QPointF(-1000, 0), QtCore.QPointF(1000, 0), 240)
        v.walls = [wall]
        v.EnsureObjectIds()
        v.sceneRevision += 1
        v.sceneChanged.emit()
        v.SetSelection([(wall, None)])
        selectedState = v.CaptureState()
        baseline = AutomaticBounds(v)
        assert baseline == (-2000.0, -1120.0, 4000.0, 2240.0)
        main.MarkProjectClean()
        v.zoom = 1.7
        main.sidebarTabs.setCurrentWidget(main.exportPanel)
        app.processEvents()
        overlay = v.exportOverlay
        assert overlay.active and overlay.bounds == baseline
        assert v.zoom == main.exportPanel.ScalePerMeter() / (1000 * v.basePixelsPerMillimeter)
        assert v.SelectionEntries() == []
        main.RefreshProjectDirty()
        assert not main.projectDirty
        scene = copy.deepcopy(main.BuildProjectData()["scene"])
        center = v.WorldToViewport(QtCore.QPointF()).toPoint()
        for outputFormat in ("png", "svg"):
            overlay.outputFormat = outputFormat
            overlay.scale = 150
            v.zoom = 1.7
            anchor = v.ViewportToWorld(QtCore.QPointF(center))
            QtTest.QTest.mouseDClick(v, QtCore.Qt.MouseButton.LeftButton, pos = center)
            assert abs(v.zoom * v.basePixelsPerMillimeter * v.devicePixelRatioF() - .15) < .000001
            assert (v.ViewportToWorld(QtCore.QPointF(center)) - anchor).manhattanLength() < .001
            assert overlay.bounds == baseline
        overlay.outputFormat = "png"
        overlay.scale = 200
        v.zoom = 1.0
        QtTest.QTest.mouseClick(v, QtCore.Qt.MouseButton.LeftButton, pos = center)
        QtTest.QTest.mouseClick(v, QtCore.Qt.MouseButton.RightButton, pos = center)
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_A, QtCore.Qt.KeyboardModifier.ControlModifier)
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_D)
        assert not v.SelectionEntries() and v.openingPlacementMode is None
        assert main.BuildProjectData()["scene"] == scene
        v.SetSelection([(wall, None)])
        assert not v.SelectionEntries()
        v.RestoreState(selectedState)
        assert not v.SelectionEntries(), "History restoration revived selection in Export"
        # Grab the left guide beyond the crop's top: the whole line is a handle.
        v.zoom = .5
        x, y, width, height = baseline
        position = v.WorldToViewport(QtCore.QPointF(x, y + height + 100)).toPoint()
        assert overlay.HitEdge(QtCore.QPointF(position)) == 0
        QtTest.QTest.mouseClick(v, QtCore.Qt.MouseButton.LeftButton, pos = position + QtCore.QPoint(5, 0))
        assert overlay.bounds == baseline, "Clicking a guide without dragging moved the crop"
        QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, pos = position)
        target = position + QtCore.QPoint(100, 0)
        QtTest.QTest.mouseMove(v, target)
        QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, pos = target)
        assert overlay.bounds[0] == x + 1000
        assert overlay.bounds[1] == y and overlay.bounds[3] == height
        assert main.ProjectSettings()["exportSettings"]["bounds"] == list(overlay.bounds)
        saved = copy.deepcopy(main.BuildProjectData())
        QtTest.QTest.mouseDClick(v, QtCore.Qt.MouseButton.LeftButton, pos = target)
        assert overlay.bounds == baseline and "bounds" not in main.exportPanel.overrides
        # All four guide resets restore their original world coordinates.
        for edge, original in enumerate((x, x + width, y, y + height)):
            overlay.MoveEdge(edge, original + 700)
            point = (v.WorldToViewport(QtCore.QPointF(overlay.bounds[0] if edge == 0 else overlay.bounds[0] + overlay.bounds[2], y + height / 2))
                     if edge < 2 else v.WorldToViewport(QtCore.QPointF(x + width / 2, overlay.bounds[1] if edge == 2 else overlay.bounds[1] + overlay.bounds[3])))
            QtTest.QTest.mouseDClick(v, QtCore.Qt.MouseButton.LeftButton, pos = point.toPoint())
            assert overlay.bounds == baseline
        overlay.MoveEdge(0, x + width + 10000)
        assert overlay.bounds[2] == v.GridSteps(overlay.scale / 1000)[1], "Crossing crop guides lost grid alignment"
        overlay.MoveEdge(0, x, reset = True)
        assert overlay.bounds == baseline
        # Use export-scale grid spacing, ignoring viewport zoom and sub-options.
        snapOptions = (v.gridSnapEnabled, v.vertexSnapEnabled, v.midpointSnapEnabled, v.alignmentSnapEnabled)
        v.gridSnapEnabled = v.vertexSnapEnabled = v.midpointSnapEnabled = v.alignmentSnapEnabled = False
        for exportScale, expected in ((50, -1600), (150, -1800), (200, -1700)):
            overlay.scale = exportScale
            for zoom in (.5, 3):
                v.zoom = zoom
                overlay.MoveEdge(0, -1737)
                assert overlay.bounds[0] == expected
            overlay.MoveEdge(0, -1737, modifiers = QtCore.Qt.KeyboardModifier.AltModifier)
            assert overlay.bounds[0] == -1737
            v.snapEnabled = False
            overlay.MoveEdge(0, -1729)
            assert overlay.bounds[0] == -1729
            overlay.MoveEdge(0, -1737, modifiers = QtCore.Qt.KeyboardModifier.AltModifier)
            assert overlay.bounds[0] == expected
            v.snapEnabled = True
            overlay.MoveEdge(0, x, reset = True)
        overlay.scale = 200
        v.zoom = .5
        overlay.dragEdge, overlay.dragOffset = 0, 0
        overlay.hoverPosition = v.WorldToViewport(QtCore.QPointF(-1737, 0))
        overlay.MoveEdge(0, -1737)
        QtTest.QTest.keyPress(v, QtCore.Qt.Key.Key_Alt)
        assert abs(overlay.bounds[0] + 1737) < .000001
        QtTest.QTest.keyRelease(v, QtCore.Qt.Key.Key_Alt)
        assert overlay.bounds[0] == -1700
        overlay.dragEdge = None
        overlay.MoveEdge(0, x, reset = True)
        v.gridSnapEnabled, v.vertexSnapEnabled, v.midpointSnapEnabled, v.alignmentSnapEnabled = snapOptions
        # Shade only the outside and extend vertical/horizontal guides beyond the crop.
        image = QtGui.QImage(v.size(), QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtGui.QColor("white"))
        painter = QtGui.QPainter(image)
        overlay.Draw(painter, v.DrawingRect())
        painter.end()
        assert image.pixelColor(center) == QtGui.QColor("white")
        assert image.pixelColor(40, 40).red() < 255
        previousShade = themeColors["exportOutsideShade"]
        try:
            themeColors["exportOutsideShade"] = "#ff204060"
            image.fill(QtGui.QColor("white"))
            painter = QtGui.QPainter(image)
            overlay.Draw(painter, v.DrawingRect())
            painter.end()
            assert image.pixelColor(40, 40).name() == "#204060"
            assert image.pixelColor(center) == QtGui.QColor("white")
        finally:
            themeColors["exportOutsideShade"] = previousShade
        image.fill(QtGui.QColor("white"))
        painter = QtGui.QPainter(image)
        overlay.Draw(painter, v.DrawingRect())
        painter.end()
        guideX = round(v.WorldToViewport(QtCore.QPointF(x, y)).x())
        assert any(image.pixelColor(guideX, row).red() != image.pixelColor(guideX - 10, row).red() for row in range(40, 100))
        # Pan/zoom change guide positions without changing the world crop.
        v.grab()
        snapshot = overlay.snapshot
        assert snapshot is not None
        originalSize = snapshot.size()
        planPath = Path(folder) / "preview.plan"
        renderData = main.BuildProjectData()
        renderData["settings"].update(main.exportPanel.CaptureView())
        planPath.write_text(json.dumps(renderData), encoding = "utf-8")
        expected = RenderPlan(planPath, overlay.scale, overlay.snapshotBounds)
        assert snapshot == expected, "The source preview differs from the PNG renderer"
        main.exportPanel.borderField.setCurrentText("Ruler")
        v.zoom = .7
        framedPreview = v.grab().toImage()
        outside = v.WorldToViewport(QtCore.QPointF(x - 300, 300)).toPoint()
        outsidePatch = framedPreview.copy(outside.x() - 10, outside.y() - 10, 20, 20)
        assert len({outsidePatch.pixelColor(column, row).rgba() for column in range(20) for row in range(20)}) == 1, "Grid extends beyond the crop ruler"
        v.zoom = 1.0
        assert overlay.drawRuler and len(overlay.rulerStrips) == 4
        assert overlay.snapshot is snapshot, "Toggling the ruler regenerated the scene bitmap"
        expectedFrame = RenderPlan(planPath, overlay.scale, overlay.bounds, ruler = True)
        for offsetX, offsetY, strip in overlay.rulerStrips:
            expectedStrip = expectedFrame.copy(offsetX, offsetY, strip.width(), strip.height())
            if strip != expectedStrip:
                # Text clipped at a strip edge can differ by one channel level
                # from the full opaque surface because of Qt alpha rounding.
                assert all(max(abs(first - second) for first, second in
                               zip(strip.pixelColor(column, row).getRgb(), expectedStrip.pixelColor(column, row).getRgb())) <= 1
                           for row in range(strip.height()) for column in range(strip.width())), "Ruler differs from exported frame"
        rulerStrips = overlay.rulerStrips
        v.ZoomBy(1.1, QtCore.QPointF(center))
        v.grab()
        assert overlay.rulerStrips is rulerStrips, "Viewing zoom regenerated the ruler bitmap"
        v.zoom = 1.0
        main.exportPanel.borderField.setCurrentText("None")
        v.ZoomBy(1.15, QtCore.QPointF(center))
        assert overlay.bounds == baseline and v.zoom == 1.15
        v.grab()
        assert overlay.snapshot is snapshot, "Viewing zoom regenerated the source raster"
        oldPan = QtCore.QPointF(v.panOffset)
        QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.MiddleButton, pos = center)
        QtTest.QTest.mouseMove(v, center + QtCore.QPoint(20, 15))
        QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.MiddleButton, pos = center + QtCore.QPoint(20, 15))
        assert v.panOffset == oldPan + QtCore.QPointF(20, 15) and overlay.bounds == baseline
        v.grab()
        assert overlay.snapshot is snapshot, "Viewing pan regenerated the source raster"
        overlay.MoveEdge(0, baseline[0] + 700)
        v.grab()
        assert overlay.snapshot is snapshot, "A crop edit inside the capture regenerated the raster"
        overlay.MoveEdge(0, baseline[0], reset = True)
        main.sidebarTabs.setCurrentIndex(0)
        assert not overlay.active and v.zoom == 1.7
        v.SetSelection([(wall, None)])
        assert v.SelectionEntries()
        main.sidebarTabs.setCurrentWidget(main.exportPanel)
        main.ApplyProject(DecodeProject(saved, v.furnishingDefinitions), None)
        assert not overlay.active, "Loading a project should return to Build"
        main.sidebarTabs.setCurrentWidget(main.exportPanel)
        assert overlay.bounds == tuple(saved["settings"]["exportSettings"]["bounds"])
        initialZoom = v.zoom
        main.exportPanel.scaleField.setValue(500)
        assert v.zoom == initialZoom and overlay.scale == 500
        v.grab()
        assert overlay.snapshot is not snapshot
        assert overlay.snapshot.width() > originalSize.width()
        snapshot = overlay.snapshot
        anchor = QtCore.QPointF(v.DrawingRect().center())
        wheel = QtGui.QWheelEvent(anchor, QtCore.QPointF(v.mapToGlobal(anchor.toPoint())),
                                 QtCore.QPoint(), QtCore.QPoint(0, 120), QtCore.Qt.MouseButton.NoButton,
                                 QtCore.Qt.KeyboardModifier.NoModifier, QtCore.Qt.ScrollPhase.NoScrollPhase, False)
        app.sendEvent(v, wheel)
        assert v.zoom == initialZoom * 1.15
        v.grab()
        assert overlay.snapshot is snapshot
        v.ResetView()
        assert v.zoom == 2.5
        assert abs(v.WorldToViewport(QtCore.QPointF(1000, 0)).x() - v.WorldToViewport(QtCore.QPointF()).x() - 500) < .000001
        assert main.BuildProjectData()["view"]["zoom"] == 1.7
        assert main.ProjectSettings()["exportSettings"]["scale"] == 500
        main.exportPanel.showGridField.setChecked(False)
        v.grab()
        assert overlay.snapshot is not snapshot, "Export appearance did not regenerate the raster"
        snapshot = overlay.snapshot
        overlay.MoveEdge(1, overlay.snapshotBounds[0] + overlay.snapshotBounds[2] + 1000)
        v.grab()
        assert overlay.snapshot is not snapshot, "Extending the crop did not capture the new area"
        main.ApplyProject(DecodeProject(saved, v.furnishingDefinitions), None)
        main.sidebarTabs.setCurrentWidget(main.exportPanel)
        main.exportPanel.scaleField.setValue(500)
        main.exportPanel.borderField.setCurrentText("Ruler")
        main.exportPanel.sectionButtons["Canvas"].setChecked(True)
        v.ResetView()
        v.ZoomBy(.32, QtCore.QPointF(v.DrawingRect().center()))
        app.processEvents()
        main.grab().save("screenshots/export-bounds-guides.png")
        main.close()
        recovered = MainWindow()
        recovered.show()
        app.processEvents()
        assert recovered.viewport.exportOverlay.active
        assert recovered.viewport.exportOverlay.bounds == tuple(saved["settings"]["exportSettings"]["bounds"])
        assert not recovered.viewport.SelectionEntries()
        assert recovered.viewport.zoom == 2.5 and recovered.exportPanel.scaleField.value() == 500
        assert recovered.exportPanel.borderField.currentText() == "Ruler" and recovered.viewport.exportOverlay.drawRuler
        recovered.sidebarTabs.setCurrentIndex(0)
        assert recovered.viewport.zoom == 1.7
        recovered.close()
        print("PASS: shared auto crop, full-span guides, drag/reset, shading, pan/zoom, saved bounds and read-only selection")


if __name__ == "__main__":
    Main()
