"""Keep fatal native faults and unhandled callback exceptions for diagnosis."""
import faulthandler
import sys
import traceback
from datetime import datetime
from pathlib import Path
from PySide6 import QtCore

crashLog = None


def ConfigureCrashReporting(directory = None):
    global crashLog
    try:
        folder = Path(directory) if directory is not None else Path(QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.AppLocalDataLocation))
        folder.mkdir(parents = True, exist_ok = True)
        crashLog = (folder / "crash.log").open("a", encoding = "utf-8", buffering = 1)
        crashLog.write(f"\nPlanner started {datetime.now().isoformat(timespec = 'seconds')}\nPython {sys.version}\nQt {QtCore.qVersion()}\n")
        faulthandler.enable(file = crashLog, all_threads = True)
    except (OSError, RuntimeError) as error:
        if sys.stderr is not None:
            print(f"Could not initialize crash reporting: {error}", file = sys.stderr)
        return

    def ReportException(errorType, error, errorTraceback):
        traceback.print_exception(errorType, error, errorTraceback, file = crashLog)
        crashLog.flush()
        if sys.stderr is not None:
            sys.__excepthook__(errorType, error, errorTraceback)

    sys.excepthook = ReportException
