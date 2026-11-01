"""Startup resource failures and worker faults retain useful diagnostics."""
import io
import json
import os
from pathlib import Path
import pickle
import subprocess
import sys
from time import perf_counter
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtTest
from fixtures.parity_examples import ExampleWindow
from planner_app.export_preview import ExportPreviewProcess
from planner_app.graphics import palette


def Main():
    with ExampleWindow() as (main, folder):
        startupProbe = '''
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from planner_app import paths
paths.themesDirectory = Path(sys.argv[2])
import main
assert 'planner_app.graphics.palette' not in sys.modules
with patch.object(main, 'ConfigureCrashReporting') as reporting, patch.object(sys, 'excepthook') as failure, \
        patch.object(main.QtWidgets.QMessageBox, 'warning') as warning:
    assert main.Main() == 1
    assert reporting.call_count == failure.call_count == warning.call_count == 1
    assert sys.argv[2] in warning.call_args.args[2]
    from planner_app.graphics.palette import LoadThemes, themeLoadError
    assert themeLoadError is not None
'''
        startup = subprocess.run([sys.executable, "-B", "-c", startupProbe, str(root / "planner-main"),
                                  str(folder / "missing-themes")], capture_output = True, text = True, timeout = 15)
        assert startup.returncode == 0, startup.stderr
        # Failed reloads leave the active, valid resource collection intact.
        definitions, colors = dict(palette.themeDefinitions), dict(palette.themeColors)
        try:
            palette.InitializeThemes(folder / "missing-themes")
        except ValueError as error:
            assert str(folder / "missing-themes") in str(error)
        else:
            raise AssertionError("Missing resource collection was accepted")
        assert palette.themeDefinitions == definitions and palette.themeColors == colors

        job = folder / "bad-job.json"
        job.write_text("{invalid", encoding = "utf-8")
        exported = subprocess.run([sys.executable, str(root / "planner-main/main.py"), "--export-worker", str(job)],
                                  capture_output = True, text = True, timeout = 15)
        message = next(json.loads(line.removeprefix("PLANNER_EXPORT:")) for line in exported.stdout.splitlines()
                       if line.startswith("PLANNER_EXPORT:") and "error" in json.loads(line.removeprefix("PLANNER_EXPORT:")))
        assert exported.returncode == 1 and message["exceptionType"] == "JSONDecodeError"
        assert "export_worker.py" in message["traceback"] and len(message["traceback"]) <= 16384

        job = folder / "bad-preview.pickle"
        job.write_bytes(pickle.dumps({}))
        request = dict(id = 1, job = str(job), output = str(folder / "unused.frame"))
        preview = subprocess.run([sys.executable, str(root / "planner-main/main.py"), "--preview-worker"],
                                 input = json.dumps(request) + "\n", capture_output = True, text = True, timeout = 15)
        messages = [json.loads(line.removeprefix("PLANNER_PREVIEW:")) for line in preview.stdout.splitlines()
                    if line.startswith("PLANNER_PREVIEW:")]
        assert preview.returncode == 0 and len(messages) == 1, (preview.stdout, preview.stderr)
        assert messages[0]["exceptionType"] == "KeyError" and "export_preview_worker.py" in messages[0]["traceback"]

        # Native/initialization faults without a protocol result retain stderr
        # in both the result and the editor's existing diagnostic destination.
        worker = ExportPreviewProcess(main.viewport.exportOverlay)
        worker.current = dict(id = 1, slot = "fault", key = "fault", path = folder / "fault.frame", kind = "png")
        worker.requests["fault"] = "fault"
        diagnostic = io.StringIO()
        try:
            with patch("planner_app.crash_reporting.crashLog", diagnostic):
                worker.process.start(sys.executable, ["-c", "import sys; sys.stderr.write('native initialization marker\\n'); sys.exit(2)"])
                deadline = perf_counter() + 5
                while worker.current is not None and perf_counter() < deadline:
                    QtTest.QTest.qWait(5)
                assert worker.current is None
                assert "native initialization marker" in worker.results["fault"][2]
                assert "native initialization marker" in diagnostic.getvalue()
                assert len(worker.diagnostics) <= 16384
        finally:
            worker.Close()
            worker.deleteLater()
    print("PASS: protected startup, atomic theme reload, worker tracebacks and bounded retained stderr")


if __name__ == "__main__":
    Main()
