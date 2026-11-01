import sys

from PySide6 import QtCore, QtWidgets

from planner_app.crash_reporting import ConfigureCrashReporting


def Main():
    if len(sys.argv) == 2 and sys.argv[1] == "--preview-worker":
        from planner_app.export_preview_worker import Main as RunPreviewWorker
        return RunPreviewWorker()
    if len(sys.argv) == 3 and sys.argv[1] == "--export-worker":
        from planner_app.export_worker import RunExportWorker
        return RunExportWorker(sys.argv[2])
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Planner")
    ConfigureCrashReporting()
    if tuple(int(part) for part in QtCore.qVersion().split(".")[:3]) < (6, 11, 2):
        QtWidgets.QMessageBox.warning(None, "Qt Update Required",
            "Planner requires PySide6 6.11.2 or newer. Install requirements.txt in the Python environment used to launch Planner.")
        return 1
    try:
        # Editable resources and UI imports belong inside startup reporting.
        from planner_app.graphics import palette
        if palette.themeLoadError is not None:
            palette.InitializeThemes()
        from planner_app.ui.session import AcquireSessionLock
        sessionLock = AcquireSessionLock()
    except (OSError, ValueError, RuntimeError) as error:
        sys.excepthook(type(error), error, error.__traceback__)
        QtWidgets.QMessageBox.warning(None, "Cannot Start Planner", str(error))
        return 1
    try:
        from planner_app.ui.main_window import MainWindow
        from planner_app.graphics.theme import ApplyApplicationTheme
        app.setStyle("Fusion")
        ApplyApplicationTheme(app)
        window = MainWindow()
        if window.sessionRestored:
            window.show()
        else:
            window.showMaximized()
        return app.exec()
    except (OSError, ValueError, RuntimeError) as error:
        sys.excepthook(type(error), error, error.__traceback__)
        QtWidgets.QMessageBox.warning(None, "Cannot Start Planner", str(error))
        return 1
    finally:
        sessionLock.unlock()


if __name__ == "__main__":
    sys.exit(Main())
