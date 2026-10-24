"""Synthetic parity examples only; no production imports this module."""
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from PySide6 import QtCore, QtWidgets
from planner_app import models
from planner_app.graphics import palette
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.project_codec import EncodeScene
from planner_app.ui.main_window import MainWindow

objectTypes = ("Wall", "Counter", "Railing", "Stair", "Pillar", "Column", "Elevator",
               "Door", "SlidingDoor", "PocketDoor", "BarnDoor", "BifoldDoor", "OpenDoorway",
               "Window", "SilledWindow", "CasementWindow", "Fireplace",
               "Furnishing", "Label", "NorthArrow", "Arrow", "MeasurementGuide", "AngleGuide")
openingTypes = ("Door", "SlidingDoor", "PocketDoor", "BarnDoor", "BifoldDoor", "OpenDoorway",
                "Window", "SilledWindow", "CasementWindow", "Fireplace")
workspace = Path(__file__).resolve().parents[2]
referenceDirectory = workspace / "docs" / "parity" / "reference"


@contextmanager
def ExampleWindow():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setStyle("Fusion")
    LoadApplicationFonts(app)
    palette.SetThemes("Dark UI", "Dark Canvas")
    ApplyApplicationTheme(app)
    temporaryRoot = workspace / "tmp"
    temporaryRoot.mkdir(exist_ok = True)
    with tempfile.TemporaryDirectory(prefix = "parity-examples-", dir = temporaryRoot) as folder:
        names = ("PLANNER_SESSION_PATH", "PLANNER_STARTUP_PATH", "PLANNER_PREFERENCES_PATH")
        previous = {name: os.environ.get(name) for name in names}
        for name, filename in zip(names, ("session.json", "startup.plan", "preferences.json")):
            os.environ[name] = str(Path(folder) / filename)
        main = MainWindow()
        main.viewport.setFixedSize(1000, 800)
        main.resize(1480, 900)
        main.show()
        main.viewport.zoom = 1
        main.viewport.panOffset = QtCore.QPointF()
        app.processEvents()
        try:
            yield main, Path(folder)
        finally:
            with patch.object(QtWidgets.QMessageBox, "exec", return_value = QtWidgets.QMessageBox.StandardButton.Discard):
                main.close()
            main.deleteLater()
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


def CreateObject(viewport, name):
    point = QtCore.QPointF
    cls = getattr(models, name)
    if name in openingTypes:
        parent = models.Wall(point(-3000, 0), point(3000, 0))
        size = viewport.miscDefaultSizes["Fireplace"] if name == "Fireplace" else viewport.openingDefaultSizes[name]
        halfFraction = size * 10 / 12000
        return cls(parent, .5 - halfFraction, .5 + halfFraction)
    if name == "AngleGuide":
        return cls(point(1000, 0), point(0, 1000), middleVertex = point())
    if name == "Furnishing":
        return cls(viewport.furnishingDefinitions["desk"])
    if name in ("Label", "NorthArrow"):
        return cls()
    if name in ("Pillar", "Column", "Elevator"):
        size = viewport.miscDefaultSizes[name] * 10
        return cls(point(0, -size / 2), point(0, size / 2), size)
    width = viewport.miscDefaultSizes[name] * 10 if name in viewport.miscDefaultSizes else 240 if name == "Wall" else 0 if name == "MeasurementGuide" else 10
    return cls(point(-1000, 0), point(1000, 0), width)


def InstallScene(main, objects):
    v = main.viewport
    v.CancelInteraction()
    v.SetSelection([])
    v.walls = [obj for obj in objects if isinstance(obj, models.Wall)]
    v.windows = [obj for obj in objects if isinstance(obj, models.Window)]
    v.furnishings = [obj for obj in objects if isinstance(obj, models.Furnishing) and not isinstance(obj, models.Label)]
    v.labels = [obj for obj in objects if isinstance(obj, models.Label)]
    v.objectGroups, v.hiddenObjects = [], []
    v.hiddenObjectIds = set()
    v.undoHistory, v.redoHistory = [], []
    ordered = v.walls + v.windows + v.furnishings + v.labels
    for index, obj in enumerate(ordered, 1):
        obj.objectId = index
    v.EnsureObjectIds()
    v.sceneChanged.emit()
    QtWidgets.QApplication.processEvents()


def WorkflowState(main):
    v = main.viewport
    v.EnsureObjectIds()
    return {"scene": EncodeScene(v),
            "selection": [[obj.objectId, index] for obj, index in v.SelectionEntries()],
            "sceneHistory": {"undo": len(v.undoHistory), "redo": len(v.redoHistory)},
            "camera": {"zoom": v.zoom, "pan": [v.panOffset.x(), v.panOffset.y()],
                       "viewport": [v.width(), v.height()], "pixelsPerMillimeter": v.basePixelsPerMillimeter},
            "export": {"active": v.exportOverlay.active, "overrides": json.loads(json.dumps(main.exportPanel.overrides)),
                       "undo": len(main.exportPanel.exportUndoHistory), "redo": len(main.exportPanel.exportRedoHistory)},
            "projectDirty": main.projectDirty}


def CompareExamples(actual, expected, location = "root"):
    """Compare portable data; retain types/order/keys and allow only numeric roundoff."""
    import math
    if isinstance(expected, dict):
        assert isinstance(actual, dict) and actual.keys() == expected.keys(), (location, "keys", actual, expected)
        for key in expected:
            CompareExamples(actual[key], expected[key], location + "." + key)
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), (location, "length")
        for index, value in enumerate(expected):
            CompareExamples(actual[index], value, f"{location}[{index}]")
    elif type(expected) in (int, float):
        assert type(actual) in (int, float) and math.isclose(actual, expected, abs_tol = 1e-8, rel_tol = 1e-12), (location, actual, expected)
    else:
        assert type(actual) is type(expected) and actual == expected, (location, actual, expected)
