"""Drive desktop color popup from framework-independent JSON event traces."""
import json
import os
import sys
from pathlib import Path

workspace = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(workspace / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.ui.color_picker import ColorPickerDialog


def Main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    fixture = json.loads((workspace / "docs" / "parity" / "color-popup-traces.json").read_text(encoding = "utf-8"))
    anchor = QtWidgets.QPushButton("Color")
    anchor.move(500, 100)
    anchor.show()
    eventTypes = {"move": QtCore.QEvent.Type.MouseMove, "press": QtCore.QEvent.Type.MouseButtonPress,
                  "right-press": QtCore.QEvent.Type.MouseButtonPress, "release": QtCore.QEvent.Type.MouseButtonRelease}
    steps = 0
    for trace in fixture["traces"]:
        popup = ColorPickerDialog(QtGui.QColor("red"))
        popup.popupAnchor = anchor
        popup.setWindowFlags(QtCore.Qt.WindowType.Popup | QtCore.Qt.WindowType.FramelessWindowHint)
        popup.show()
        app.processEvents()
        assert popup.isVisible() and not popup.popupArmed, trace["id"]
        for step in trace["steps"]:
            if step["event"] == "escape":
                event = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, QtCore.Qt.Key.Key_Escape,
                                       QtCore.Qt.KeyboardModifier.NoModifier)
            else:
                position = QtCore.QPointF(20, 20) if step["position"] == "inside" else QtCore.QPointF(-20, -20)
                globalPosition = QtCore.QPointF(popup.mapToGlobal(position.toPoint()))
                held = QtCore.Qt.MouseButton.NoButton
                for name in step["heldButtons"]:
                    held |= QtCore.Qt.MouseButton.LeftButton if name == "left" else QtCore.Qt.MouseButton.RightButton
                button = (QtCore.Qt.MouseButton.RightButton if step["event"] == "right-press" else
                          QtCore.Qt.MouseButton.LeftButton if step["event"] in ("press", "release") else
                          QtCore.Qt.MouseButton.NoButton)
                event = QtGui.QMouseEvent(eventTypes[step["event"]], position, globalPosition, button, held,
                                         QtCore.Qt.KeyboardModifier.NoModifier)
            app.sendEvent(popup, event)
            actual = {"armed": popup.popupArmed,
                      "outcome": "open" if popup.isVisible() else "accepted" if popup.result() == QtWidgets.QDialog.DialogCode.Accepted else "cancelled"}
            assert actual == step["expected"], (trace["id"], step, actual)
            steps += 1
        popup.reject()
        popup.deleteLater()
    anchor.close()
    print(f"PASS: {len(fixture['traces'])} portable popup traces, {steps} event transitions")


if __name__ == "__main__":
    Main()
