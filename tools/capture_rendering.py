"""Launch an instrumented Planner session; write its bounded report on exit."""
import argparse
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
(root / "diagnostics").mkdir(exist_ok = True)
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtWidgets
from planner import MainWindow
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.crash_reporting import ConfigureCrashReporting


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--output", type = Path, default = root / "diagnostics/render-diagnostics.json")
    args = parser.parse_args()
    app = QtWidgets.QApplication([])
    app.setApplicationName("Planner")
    ConfigureCrashReporting()
    app.setStyle("Fusion")
    ApplyApplicationTheme(app)
    main = MainWindow()
    main.viewport.SetRenderDiagnosticsEnabled(True)
    diagnostics = main.viewport.renderDiagnostics
    if main.sessionRestored or main.startupRestored:
        main.show()
    else:
        main.showMaximized()
    app.exec()
    diagnostics.Stop()
    diagnostics.Write(args.output)
    print(f"Saved {args.output.resolve()}")


if __name__ == "__main__":
    Main()
