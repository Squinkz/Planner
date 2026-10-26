"""Run UI checks in isolated processes, discarding unsaved fixtures at teardown."""
import ctypes
import subprocess
import sys
from time import perf_counter
from pathlib import Path


def Main():
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetErrorMode(3)
    folder = Path(__file__).resolve().parent
    for name in ("diagnostics", "screenshots", "tmp"):
        (folder.parent / name).mkdir(exist_ok = True)
    names = sys.argv[1:]
    checks = [folder / name for name in names] if names else sorted(folder.glob("check_*.py"))
    bootstrap = """import os, runpy, sys, tempfile, threading
from pathlib import Path
from PySide6 import QtWidgets
if not __debug__:
    raise RuntimeError("Checks require Python assertions; disable optimization.")
callbackErrors = []
def ReportCallbackError(errorType, error, errorTraceback):
    callbackErrors.append(error)
    sys.__excepthook__(errorType, error, errorTraceback)
sys.excepthook = ReportCallbackError
threading.excepthook = lambda args: ReportCallbackError(args.exc_type, args.exc_value, args.exc_traceback)
sys.path.insert(0, str(Path(sys.argv[1]).parent))
QtWidgets.QMessageBox.question = lambda *args: QtWidgets.QMessageBox.StandardButton.Discard
QtWidgets.QMessageBox.exec = lambda *args: QtWidgets.QMessageBox.StandardButton.Discard
with tempfile.TemporaryDirectory() as sessionFolder:
    os.environ['PLANNER_SESSION_PATH'] = str(Path(sessionFolder) / 'session.json')
    os.environ['PLANNER_STARTUP_PATH'] = str(Path(sessionFolder) / 'startup.plan')
    os.environ['PLANNER_PREFERENCES_PATH'] = str(Path(sessionFolder) / 'preferences.json')
    try:
        runpy.run_path(sys.argv[1], run_name = '__main__')
    finally:
        if callbackErrors:
            raise RuntimeError(f'{len(callbackErrors)} unhandled callback/thread exceptions occurred during this check.')
"""
    failures = []
    # Full catalog theme changes, repeated session launches and integration renders
    # run substantially slower on hosted Windows workers than locally.
    timeouts = {"check_external_themes.py": 120, "check_furnishings_on_counters.py": 60,
                "check_about_dialog.py": 60, "check_app_preferences.py": 60, "check_canvas_theme_refresh.py": 60,
                "check_export_settings.py": 60, "check_export_solid_objects.py": 60,
                "check_export_cli_settings.py": 120, "check_parity_rendering.py": 60,
                "check_export_bounds.py": 60, "check_export_plan.py": 60,
                "check_furnishing_list_view.py": 60,
                "check_furnishing_quick_search.py": 60, "check_furnishing_sort.py": 60,
                "check_help_typography.py": 60, "check_help_viewer.py": 60,
                "check_linework_settings.py": 60,
                "check_native_paths.py": 60, "check_pan_dpi.py": 60,
                "check_session_recovery.py": 60,
                "check_sparse_history.py": 60,
                "check_viewport_settings.py": 60,
                "check_stairs.py": 60, "check_startup_projects.py": 60, "check_user_furnishings.py": 60,
                "check_export_button.py": 60, "check_export_progress.py": 60, "check_optimized_png.py": 60,
                "check_export_floors.py": 60, "check_exterior_hidden_dimensions.py": 60,
                "check_selection_dimension_overlay.py": 120,
                "check_session_guide_selection.py": 60}
    for check in checks:
        print(f"Checking {check.name}", flush = True)
        timeout = timeouts.get(check.name, 30)
        started = perf_counter()
        try:
            result = subprocess.run([sys.executable, "-c", bootstrap, str(check)], capture_output = True,
                                    text = True, timeout = timeout)
        except subprocess.TimeoutExpired:
            failures.append(check.name)
            print(f"{check.name}: timed out after {timeout} seconds", flush = True)
            continue
        if result.returncode:
            failures.append(check.name)
            print(check.name, result.returncode, result.stdout, result.stderr, flush = True)
        elif perf_counter() - started > 10:
            print(f"{check.name}: passed in {perf_counter() - started:.1f} seconds", flush = True)
    print(f"{len(checks) - len(failures)}/{len(checks)} checks passed", flush = True)
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    Main()
