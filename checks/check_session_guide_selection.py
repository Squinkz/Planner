"""Session round-trips for guide handles and object-aware selection validation."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import warnings
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow
from planner_app.models import AngleGuide, MeasurementGuide, BoundaryLine, Wall, Furnishing
from planner_app.project_codec import ValidateEditorUi


def Main():
    app = QtWidgets.QApplication([])
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "PLANNER_SESSION_PATH": str(Path(directory) / "session.json"),
            "PLANNER_STARTUP_PATH": str(Path(directory) / "startup.plan"),
            "PLANNER_PREFERENCES_PATH": str(Path(directory) / "preferences.json")}):
        main = MainWindow()
        main.show()
        app.processEvents()
        v = main.viewport
        point = QtCore.QPointF
        angle = AngleGuide(point(1000, 0), point(0, 1000), middleVertex = point())
        linear = MeasurementGuide(point(3000, 0), point(4000, 0))
        boundary = BoundaryLine(point(6000, 0), point(7000, 0))
        wall = Wall(point(0, -2000), point(1000, -2000))
        furnishing = Furnishing(v.furnishingDefinitions["desk"], point(5000, 3000))
        angle.textOffset, linear.textOffset = point(100, -50), point(200, 80)
        before = v.CaptureState()
        v.walls, v.furnishings = [angle, linear, wall, boundary], [furnishing]
        v.RecordEdit(before)
        ids = angle.objectId, linear.objectId, wall.objectId, furnishing.objectId, boundary.objectId
        selections = [[(ids[0], index)] for index in (0, 1, 2, 3, None)]
        selections += [[(ids[1], 3)], [(ids[0], 2), (ids[1], 3), (ids[2], 0)]]
        selections += [[(ids[4], index)] for index in (0, 1, 3, None)]
        for selection in selections:
            v = main.viewport
            objects = {obj.objectId: obj for obj in v.walls + v.furnishings}
            v.SetSelection([(objects[objectId], index) for objectId, index in selection])
            expectedScene = main.BuildProjectData()["scene"]
            main.close()
            with warnings.catch_warnings(record = True) as caught:
                main = MainWindow()
            main.show()
            app.processEvents()
            assert not caught, [str(warning.message) for warning in caught]
            assert main.sessionRestored
            assert main.SessionUiState()["selection"] == [list(entry) for entry in selection]
            assert main.BuildProjectData()["scene"] == expectedScene
            # Recovered middle/label selections must be usable, not merely stored.
            before = main.viewport.CaptureState()
            main.viewport.NudgeSelection(QtCore.Qt.Key.Key_Right)
            assert main.viewport.CaptureState() != before
            main.viewport.Undo()
            assert main.BuildProjectData()["scene"] == expectedScene
        objects = {obj.objectId: obj for obj in main.viewport.walls + main.viewport.furnishings}
        ui = main.SessionUiState()
        for objectId, index in ((ids[2], 2), (ids[2], 3), (ids[1], 2), (ids[3], 3), (ids[4], 2),
                                (ids[0], -1), (ids[0], 4), (ids[0], True), (ids[0], 1.5)):
            malformed = copy.deepcopy(ui)
            malformed["selection"] = [[objectId, index]]
            try:
                ValidateEditorUi(malformed, recovery = True, tabCount = main.sidebarTabs.count(), objectsById = objects)
            except ValueError:
                pass
            else:
                raise AssertionError((objectId, index, "invalid handle accepted"))
        # Reject an object/index mismatch before applying any incoming scene.
        assert main.WriteSession(wait = True)
        malformed = json.loads(main.sessionPath.read_text(encoding = "utf-8"))
        malformed["ui"]["selection"] = [[ids[2], 2]]
        malformed["project"]["scene"]["objects"][2]["width"] = 900
        invalidPath = Path(directory) / "invalid-session.json"
        invalidPath.write_text(json.dumps(malformed), encoding = "utf-8")
        before = main.BuildProjectData()
        with warnings.catch_warnings(record = True) as caught, patch.object(main, "ApplyProject") as apply, patch.object(main.viewport, "ShowClipboardError") as message:
            main.RestoreSession(invalidPath)
        assert caught and not apply.called and message.called
        assert main.BuildProjectData() == before
        assert list(Path(directory).glob("invalid-session.json.failed-*"))
        main.close()
    print("PASS: endpoint/body/middle/label/mixed session selections, exact scene preservation, usable restored handles and atomic invalid-handle rejection")


if __name__ == "__main__":
    Main()
