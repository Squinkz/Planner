"""Stacker status icons, message styling and prompt defaults."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setFont(QtGui.QFont("Segoe UI", 9))
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.SetThemes(uiTheme = "Dark UI", canvasTheme = "Dark Canvas")  # Fixed palette for pixel assertions.
    observed = []

    def InspectDialog(message):
        message.show()
        app.processEvents()
        assert not message.windowIcon().isNull()
        assert message.iconPixmap().size() == QtCore.QSize(48, 48)
        colors = {message.iconPixmap().toImage().pixelColor(x, y).name()
                  for x in range(48) for y in range(48)
                  if message.iconPixmap().toImage().pixelColor(x, y).alpha() == 255}
        assert colors == {"#d5a24a" if message.windowTitle() in ("Unsaved Project", "Replace Export") else "#ff5c5c"}
        assert message.textFormat() == QtCore.Qt.TextFormat.PlainText
        if message.windowTitle() == "Unsaved Project":
            assert message.text() == "Save changes to New Project before continuing?"
            assert message.defaultButton() is message.button(QtWidgets.QMessageBox.StandardButton.Save)
            assert {button.text().replace("&", "") for button in message.buttons()} == {"Save", "Discard", "Cancel"}
            target = Path(__file__).resolve().parent.parent / "screenshots" / "unsaved-project-dialog.png"
            message.grab().save(str(target))
        elif message.windowTitle() == "Replace Export":
            label = message.findChild(QtWidgets.QLabel, "qt_msgbox_informativelabel")
            assert not label.wordWrap()
            assert label.contentsRect().width() >= label.fontMetrics().horizontalAdvance(message.informativeText())
            assert message.defaultButton() is message.button(QtWidgets.QMessageBox.StandardButton.No)
            message.grab().save(str(Path(__file__).resolve().parent.parent / "diagnostics" / "replace-export-dialog.png"))
        else:
            assert message.informativeText() == "Test error detail"
        observed.append(message.windowTitle())
        message.hide()
        return QtWidgets.QMessageBox.StandardButton.Cancel

    with patch.object(QtWidgets.QMessageBox, "exec", InspectDialog):
        main.newWallMaterialField.setCurrentText("Brick")
        assert not main.NewProject()
        main.ShowAppMessage("Cannot Save Project", "Could not save <House>.plan.", "error", informativeText = "Test error detail")
        main.ShowAppMessage("Replace Export", "Replace the existing file?", "warning",
                            informativeText = r"C:\Users\Dieter\Drawer\PythonProjects\Planner\bunk_room_3.png",
                            standardButtons = QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                            defaultButton = QtWidgets.QMessageBox.StandardButton.No, wrapInformativeText = False)
    assert observed == ["Unsaved Project", "Cannot Save Project", "Replace Export"]
    main.close()
    print("PASS: Stacker warning/error icons, status colors, prompt text, buttons and save default.")


if __name__ == "__main__":
    Main()
