"""Cursor event filters tolerate native destruction of dialogs and trees."""
import faulthandler
import os
import sys
from pathlib import Path

faulthandler.enable()
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow

app = QtWidgets.QApplication([])
errors = []
sys.excepthook = lambda kind, error, trace: errors.append(error)
main = MainWindow()
main.show()
for index in range(8):
    main.headerButtons["Settings"].click()
    panel = main.settingsWindow
    panel.tabs.setCurrentIndex(1)
    app.processEvents()
    panel.close()
    panel.deleteLater()
    main.settingsWindow = None
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    app.processEvents()
main.close()
main.deleteLater()
QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
app.processEvents()
assert not errors, errors
