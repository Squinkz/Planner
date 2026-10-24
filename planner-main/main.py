import sys

from PySide6 import QtCore, QtWidgets

from planner_app.ui.main_window import MainWindow
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.crash_reporting import ConfigureCrashReporting
from planner_app.ui.session import AcquireSessionLock


def Main():

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Planner")
    if tuple(int(part) for part in QtCore.qVersion().split(".")[:3]) < (6, 11, 2):
        QtWidgets.QMessageBox.warning(None, "Qt Update Required",
            "Planner requires PySide6 6.11.2 or newer. Install requirements.txt in the Python environment used to launch Planner.")
        return 1
    try:
        sessionLock = AcquireSessionLock()
    except OSError as error:
        QtWidgets.QMessageBox.warning(None, "Cannot Start Planner", str(error))
        return 1
    ConfigureCrashReporting()
    app.setStyle("Fusion")
    ApplyApplicationTheme(app)
    window = MainWindow()
    if window.sessionRestored:
        window.show()
    else:
        window.showMaximized()
    try:
        return app.exec()
    finally:
        sessionLock.unlock()


if __name__ == "__main__":
    sys.exit(Main())
