"""Local plan drops use normal project opening across the main window."""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.sessionTimer.stop()
    main.sessionPollTimer.stop()
    main.viewport.performanceTimer.stop()
    main.show()
    app.processEvents()
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "dropped.PLAN"
        path.write_text(json.dumps(main.BuildProjectData()), encoding = "utf-8")
        textPath = Path(directory) / "other.txt"
        textPath.write_text("not a plan", encoding = "utf-8")
        field = main.findChild(QtWidgets.QLineEdit)
        assert field is not None
        for target in (main, main.viewport, main.sidebarPanel, field):
            mime = QtCore.QMimeData()
            mime.setUrls([QtCore.QUrl.fromLocalFile(str(path))])
            with patch.object(main, "OpenProject", return_value = True) as opened:
                for event in (
                    QtGui.QDragEnterEvent(QtCore.QPoint(10, 10), QtCore.Qt.DropAction.CopyAction, mime,
                        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier),
                    QtGui.QDragMoveEvent(QtCore.QPoint(10, 10), QtCore.Qt.DropAction.CopyAction, mime,
                        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier),
                    QtGui.QDropEvent(QtCore.QPointF(10, 10), QtCore.Qt.DropAction.CopyAction, mime,
                        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)):
                    QtWidgets.QApplication.sendEvent(target, event)
                    assert event.isAccepted(), (target, event.type())
                    assert opened.call_count == (1 if event.type() == QtCore.QEvent.Type.Drop else 0)
                opened.assert_called_once_with(path)
        # Reject remote URLs, directories, other file types and multiple projects.
        for urls in ([QtCore.QUrl("https://example.com/test.plan")],
                     [QtCore.QUrl.fromLocalFile(directory)],
                     [QtCore.QUrl.fromLocalFile(str(textPath))],
                     [QtCore.QUrl.fromLocalFile(str(path))] * 2):
            mime.setUrls(urls)
            with patch.object(main, "OpenProject") as opened:
                event = QtGui.QDragEnterEvent(QtCore.QPoint(10, 10), QtCore.Qt.DropAction.CopyAction, mime,
                    QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
                QtWidgets.QApplication.sendEvent(main.viewport, event)
                assert not event.isAccepted()
                opened.assert_not_called()
        mime.setUrls([QtCore.QUrl.fromLocalFile(str(path))])
        previousPath = main.projectPath
        for allow in (False, True):
            with patch.object(main, "ConfirmProjectReplacement", return_value = allow) as confirm:
                enter = QtGui.QDragEnterEvent(QtCore.QPoint(10, 10), QtCore.Qt.DropAction.CopyAction, mime,
                    QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
                QtWidgets.QApplication.sendEvent(main.viewport, enter)
                drop = QtGui.QDropEvent(QtCore.QPointF(10, 10), QtCore.Qt.DropAction.CopyAction, mime,
                    QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
                QtWidgets.QApplication.sendEvent(main.viewport, drop)
                confirm.assert_called_once()
                assert main.projectPath == (path.resolve() if allow else previousPath)
    app.removeEventFilter(main)
    main.hide()
    print("PASS: window/canvas/sidebar/control plan drops, invalid URLs, replacement cancellation and normal project loading")


if __name__ == "__main__":
    Main()
