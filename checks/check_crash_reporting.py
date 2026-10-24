"""Boot diagnostics persist Python callback errors without touching real logs."""
import faulthandler
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from planner_app import crash_reporting


with tempfile.TemporaryDirectory() as folder:
    previousHook = sys.excepthook
    crash_reporting.ConfigureCrashReporting(folder)
    assert faulthandler.is_enabled()
    try:
        raise ValueError("Callback diagnostic fixture")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    text = (Path(folder) / "crash.log").read_text(encoding = "utf-8")
    assert "Planner started" in text and "Callback diagnostic fixture" in text and "Traceback" in text
    faulthandler.disable()
    sys.excepthook = previousHook
    crash_reporting.crashLog.close()
