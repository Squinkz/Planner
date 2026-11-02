"""Title-block edits preserve valid saved text and cancelled logo selections."""
import base64
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))

from fixtures.parity_examples import ExampleWindow
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.project_codec import DecodeProject


def Main():
    with ExampleWindow() as (main, folder):
        panel = main.exportPanel
        # Leave the block disabled: its text is still saved in the project.
        for name in ("address", "comments"):
            field = panel.titleBlockFields[name]
            for text in ("A" * 10001, "Plan\n\U0001f3e0" * 2000):
                field.setPlainText(text)
                expected = text[:10000]
                assert field.toPlainText() == expected
                assert panel.overrides["titleBlock"][name] == expected
                path = folder / "long-title-text.plan"
                assert main.SaveProject(path)
                decoded = DecodeProject(json.loads(path.read_bytes()), main.viewport.furnishingDefinitions)
                assert decoded[5]["exportSettings"]["titleBlock"][name] == expected
                assert main.OpenProject(path)
                assert main.recoverySourcePath is None, "Normal UI input must not require recovery"
                assert panel.titleBlockFields[name].toPlainText() == expected
                assert main.WriteSession(wait = True)
                checkpoint = json.loads(main.sessionPath.read_bytes())
                DecodeProject(checkpoint["project"], main.viewport.furnishingDefinitions)
        # Normal editing continues after limiting a large paste.
        field.setPlainText("Revised notes")
        assert panel.overrides["titleBlock"]["comments"] == "Revised notes"
        # Cancelling a replacement logo must preserve the existing selection.
        image = QtGui.QImage(8, 8, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.red)
        buffer = QtCore.QBuffer()
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        assert image.save(buffer, "PNG")
        logo = base64.b64encode(bytes(buffer.data())).decode("ascii")
        for mode in ("Custom", "None", "Planner"):
            panel.SetOverride("titleBlock", dict(enabled = False, logoMode = mode, logo = logo, logoName = "Original.png"))
            expected = dict(panel.overrides["titleBlock"])
            with patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value = ("", "")):
                panel.titleBlockLogoMode.setCurrentText("Custom")
                panel.ChooseTitleBlockLogo()
            assert panel.overrides["titleBlock"] == expected, "Cancel changed the selected logo"
            assert panel.titleBlockLogoMode.currentText() == mode
            with patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value = (str(folder / "missing.png"), "")), \
                    patch.object(main, "ShowAppMessage") as message:
                panel.ChooseTitleBlockLogo()
            assert message.called
            assert panel.overrides["titleBlock"] == expected, "Failed image loading changed the selected logo"
            assert panel.titleBlockLogoMode.currentText() == mode
    print("Title-block input limits, save/open, checkpoints and cancelled/failed logo replacements passed")


if __name__ == "__main__":
    Main()
