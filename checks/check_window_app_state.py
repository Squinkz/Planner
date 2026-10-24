"""Project loading preserves window placement; session recovery owns it."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow


def Main():
    app = QtWidgets.QApplication([])
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "PLANNER_SESSION_PATH": str(Path(directory) / "session.json"),
            "PLANNER_STARTUP_PATH": str(Path(directory) / "startup.plan")}):
        main = MainWindow()
        main.resize(900, 700)
        main.move(20, 30)
        main.show()
        app.processEvents()
        legacy = main.BuildProjectData()
        assert not {"geometry", "size", "maximized"} & legacy["ui"].keys()
        legacy["ui"].update(geometry = bytes(main.saveGeometry().toBase64()).decode("ascii"),
                            size = [900, 700], maximized = True)
        legacyPath = Path(directory) / "legacy.plan"
        legacyPath.write_text(json.dumps(legacy), encoding = "utf-8")
        for maximized in (False, True):
            main.showNormal()
            main.resize(1100, 780)
            main.move(160, 120)
            if maximized:
                main.showMaximized()
            app.processEvents()
            geometry, state = main.geometry(), main.windowState()
            with patch.object(main, "restoreGeometry", wraps = main.restoreGeometry) as restore:
                assert main.OpenProject(legacyPath)
                app.processEvents()
                assert main.geometry() == geometry and main.windowState() == state
                assert main.NewProject()
                app.processEvents()
                assert main.geometry() == geometry and main.windowState() == state
                restore.assert_not_called()
        # Obsolete placement metadata cannot cause a project recovery warning.
        legacy["ui"].update(geometry = "invalid base64!", size = "obsolete", maximized = "obsolete")
        legacyPath.write_text(json.dumps(legacy), encoding = "utf-8")
        with patch.object(main, "ShowAppMessage", side_effect = AssertionError("Unexpected project notice")):
            assert main.OpenProject(legacyPath)
        output = Path(directory) / "saved.plan"
        assert main.SaveProject(output)
        assert not {"geometry", "size", "maximized"} & json.loads(output.read_text())["ui"].keys()
        # App state survives relaunch, independently of the saved project.
        main.showNormal()
        main.resize(1100, 780)
        main.move(140, 100)
        app.processEvents()
        position, size = main.pos(), main.size()
        savedGeometry = bytes(main.saveGeometry().toBase64()).decode("ascii")
        frame = main.frameGeometry()
        assert main.close()
        session = json.loads((Path(directory) / "session.json").read_text())
        assert session["ui"]["geometry"] and session["ui"]["maximized"] is False
        assert session["ui"]["geometry"] == savedGeometry
        assert not {"geometry", "size", "maximized"} & session["project"]["ui"].keys()
        restored = MainWindow()
        restored.show()
        app.processEvents()
        assert restored.sessionRestored and restored.size() == size
        # Qt clamps placement if the offscreen test display is smaller than the window.
        available = restored.screen().availableGeometry()
        if available.contains(frame):
            assert restored.pos() == position
        else:
            assert available.contains(restored.frameGeometry().topLeft())
        restored.showMaximized()
        app.processEvents()
        assert restored.close()
        maximized = MainWindow()
        maximized.show()
        app.processEvents()
        assert maximized.sessionRestored and maximized.isMaximized()
        maximized.close()
    print("PASS: projects preserve placement, ignore legacy geometry and save only panels; sessions restore normal/maximized windows.")


if __name__ == "__main__":
    Main()
