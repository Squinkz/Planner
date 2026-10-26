"""Snap indicator and persisted preference stay consistent across dialog focus changes."""
import os
import json
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        point = QtCore.QPointF
        none = QtCore.Qt.KeyboardModifier.NoModifier
        alt = QtCore.Qt.KeyboardModifier.AltModifier
        for name, button in main.snapOptions.items():
            button.setChecked(name == "grid")
        raw, snapped = point(47, 33), point(0, 0)
        for baseState in (True, False):
            main.snapButton.setChecked(baseState)
            QtTest.QTest.keyPress(v, QtCore.Qt.Key.Key_Alt)
            assert main.altHeld and main.snapButton.isChecked() != baseState
            main.ShowSettings()
            options = main.settingsWindow
            field = options.precisionField
            field.setFocus()
            QtTest.QTest.keyRelease(field, QtCore.Qt.Key.Key_Alt)
            assert not main.altHeld, "Alt release in Options left the snap indicator inverted"
            assert main.snapButton.isChecked() == v.snapEnabled == baseState
            assert v.SnapPosition(raw, none) == (snapped if baseState else raw)

            # The inverse focus route and a keyboard activation of the toolbar.
            QtTest.QTest.keyPress(field, QtCore.Qt.Key.Key_Alt)
            assert main.altHeld and main.snapButton.isChecked() != baseState
            assert main.ProjectSettings()["snapEnabled"] == baseState
            saved = folder / f"snapping-{baseState}.plan"
            assert main.SaveProject(saved)
            assert json.loads(saved.read_text(encoding = "utf-8"))["settings"]["snapEnabled"] == baseState
            main.WriteSession(wait = True)
            session = json.loads(main.sessionPath.read_text(encoding = "utf-8"))
            assert session["project"]["settings"]["snapEnabled"] == baseState
            repeat = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyRelease, QtCore.Qt.Key.Key_Alt, alt, "", True)
            QtWidgets.QApplication.sendEvent(field, repeat)
            assert main.altHeld, "Auto-repeat release must not end the temporary override"
            QtTest.QTest.keyRelease(v, QtCore.Qt.Key.Key_Alt)
            QtTest.QTest.keyClick(main.snapButton, QtCore.Qt.Key.Key_Space)
            assert main.snapButton.isChecked() == v.snapEnabled == (not baseState)
            assert v.SnapPosition(raw, none) == (raw if baseState else snapped)

            # Clicking while Alt is held changes the saved preference once.
            QtTest.QTest.keyPress(field, QtCore.Qt.Key.Key_Alt)
            before = v.snapEnabled
            QtTest.QTest.mouseClick(main.snapButton, QtCore.Qt.MouseButton.LeftButton, alt)
            assert v.snapEnabled != before
            assert main.ProjectSettings()["snapEnabled"] == v.snapEnabled
            QtTest.QTest.keyRelease(field, QtCore.Qt.Key.Key_Alt)
            assert main.snapButton.isChecked() == v.snapEnabled
            options.hide()

        # Recover if a native dialog/window consumed the modifier release.
        QtTest.QTest.keyPress(v, QtCore.Qt.Key.Key_Alt)
        assert main.altHeld
        move = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, point(100, 100), point(100, 100),
                                QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.NoButton, none)
        QtWidgets.QApplication.sendEvent(v, move)
        assert not main.altHeld and main.snapButton.isChecked() == v.snapEnabled
        QtTest.QTest.keyRelease(v, QtCore.Qt.Key.Key_Alt)

        # With no target types, Alt cannot make snapping effective.
        QtTest.QTest.keyPress(v, QtCore.Qt.Key.Key_Alt)
        for button in main.snapOptions.values():
            button.setChecked(False)
        assert not main.snapButton.isChecked() and not main.ProjectSettings()["snapEnabled"]
        assert v.SnapPosition(raw, alt) == raw
        QtTest.QTest.keyRelease(v, QtCore.Qt.Key.Key_Alt)
    print("PASS: Alt across Options, keyboard/mouse toggles, saved preference and lost-release recovery")


if __name__ == "__main__":
    Main()
