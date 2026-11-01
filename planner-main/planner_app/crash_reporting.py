"""Keep fatal native faults and unhandled callback exceptions for diagnosis."""
import faulthandler
import sys
import traceback
from datetime import datetime
from pathlib import Path
from PySide6 import QtCore

crashLog = None


def ExceptionDetails(error):
    """Use a nonempty message and bounded traceback for every process boundary."""
    return {"error": str(error) or type(error).__name__, "exceptionType": type(error).__name__,
            "traceback": "".join(traceback.format_exception(type(error), error, error.__traceback__))[-16384:]}


def ReportWorkerFailure(worker, message, diagnostics = ""):
    """Keep bounded worker context in the editor's existing diagnostic log."""
    stream = crashLog if crashLog is not None else sys.stderr
    if stream is not None:
        try:
            stream.write(f"\n{worker}: {message}\n{diagnostics[-16384:]}\n")
            stream.flush()
        except (OSError, ValueError):
            pass


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
