"""Physical backgrounds, grid visibility and persistence for Solid Objects."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from planner_app.models import Wall, Counter, Stair, Railing, Window, SilledWindow, CasementWindow, BifoldDoor, SlidingDoor, PocketDoor, BarnDoor, MeasurementGuide, Arrow, Label
from planner_app.project_codec import DecodeProject
from planner_app.graphics.svg_preview import SvgPreviewRenderer
from planner_app.models import Elevator


def Main():
    app = QtWidgets.QApplication([])
    messages = []
    oldHandler = QtCore.qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    main = MainWindow()
    main.show()
    v = main.viewport
    panel = main.exportPanel
    main.sidebarTabs.setCurrentWidget(panel)
    assert panel.solidObjectsField.text() == "Solid Objects"
    panel.borderField.setCurrentText("None")
    panel.scaleField.setValue(100)
    panel.showGridField.setChecked(True)
    panel.SetOverride("measurementVisibility", {key: False for key in v.measurementVisibility})
    v.exportOverlay.bounds = (-3000, -2000, 6000, 4000)
    for kind in (Counter, Stair, Railing, Elevator, Window, SilledWindow, CasementWindow, BifoldDoor, SlidingDoor, PocketDoor, BarnDoor):
        parent = Wall(QtCore.QPointF(-2000, 0), QtCore.QPointF(2000, 0), 400)
        if kind in (Counter, Stair, Railing, Elevator):
            v.walls = [kind(QtCore.QPointF(-1000, 0), QtCore.QPointF(1000, 0), 600)]
            v.windows = []
        else:
            v.walls = [parent]
            v.windows = [kind(parent, .25, .75)]
        v.furnishings = []
        v.EnsureObjectIds()
        v.sceneRevision += 1
        panel.solidObjectsField.setChecked(True)
        solid = panel.Render("png")
        panel.solidObjectsField.setChecked(False)
        transparent = panel.Render("png")
        assert transparent != solid, f"{kind.__name__} still draws its background"
        assert transparent.pixelColor(20, 20) == solid.pixelColor(20, 20), "Canvas/grid changed outside physical objects"
        panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
        v.grab()
        assert not v.exportOverlay.previewError
        assert not v.exportOverlay.snapshotViewport.solidObjects
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        svg = panel.Render("svg")
        renderer = SvgPreviewRenderer(svg)
        assert renderer.isValid()
        image = QtGui.QImage(transparent.size(), QtGui.QImage.Format.Format_ARGB32)
        with QtGui.QPainter(image) as painter:
            renderer.render(painter)
        assert image.pixelColor(23, 23) == transparent.pixelColor(23, 23), kind.__name__
        v.grab()
        assert not v.exportOverlay.previewError
    v.walls = [MeasurementGuide(QtCore.QPointF(-1000, 0), QtCore.QPointF(1000, 0)),
               Arrow(QtCore.QPointF(-500, -500), QtCore.QPointF(500, -500))]
    v.windows = []
    v.labels = [Label(QtCore.QPointF(0, 500), "Annotation")]
    v.EnsureObjectIds()
    v.sceneRevision += 1
    panel.solidObjectsField.setChecked(True)
    annotations = panel.Render("png")
    panel.solidObjectsField.setChecked(False)
    assert panel.Render("png") == annotations, "Transparency changed measurements, arrows or labels"
    saved = main.BuildProjectData(includeHistory = False)
    assert saved["settings"]["exportSettings"]["solidObjects"] is False
    assert "solidFurnishings" not in saved["settings"]["exportSettings"]
    saved["settings"]["exportSettings"]["solidFurnishings"] = saved["settings"]["exportSettings"].pop("solidObjects")
    assert DecodeProject(saved, v.furnishingDefinitions)[5]["exportSettings"]["solidObjects"] is False
    main.sidebarTabs.setCurrentIndex(0)
    assert v.solidObjects, "Export object transparency leaked into the normal viewport"
    main.close()
    QtCore.qInstallMessageHandler(oldHandler)
    assert not any("QPainter" in message or "paint device" in message for message in messages), messages
    print("PASS: Solid Objects covers counters, stairs, railings, windows and filled door panels in PNG/SVG")


if __name__ == "__main__":
    Main()
