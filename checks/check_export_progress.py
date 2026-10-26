"""Process export parity, event-loop responsiveness, cancellation and atomic failure."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Furnishing
from planner_app.ui.export_progress import ExportProgressDialog
from planner_app.export_plan import RenderPlan


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        InstallScene(main, [Wall(QtCore.QPointF(-900, 0), QtCore.QPointF(900, 0), 200),
                            Furnishing(v.furnishingDefinitions["desk"], QtCore.QPointF(0, 600))])
        panel = main.exportPanel
        main.sidebarTabs.setCurrentWidget(panel)
        expectedState = main.BuildProjectData(includeHistory = False)
        for outputFormat, optimized in (("png", False), ("svg", False), ("png", True)):
            arguments = panel.RenderArguments(outputFormat)
            arguments.update(bounds = [-1000, -1000, 2000, 2000], scale = 60)
            expected = RenderPlan(**arguments)
            path = folder / ("optimized.png" if optimized else "result." + outputFormat)
            ticks = []
            dialog = ExportProgressDialog(panel, path, outputFormat, optimized)
            timer = QtCore.QTimer(dialog)
            timer.timeout.connect(lambda: ticks.append(dialog.statusLabel.text()))
            timer.start(5)
            with patch.object(panel, "RenderArguments", return_value = arguments):
                assert dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted, dialog.error
            timer.stop()
            assert len(ticks) > 3, "GUI event loop did not remain responsive"
            assert dialog.process.state() == QtCore.QProcess.ProcessState.NotRunning
            assert not list(folder.glob(".planner-export-*"))
            if optimized:
                # UPNG's palette solver uses random initial vectors, so exact
                # bytes are not stable between engines even for identical pixels.
                encoded = path.read_bytes()
                decoded = QtGui.QImage(str(path))
                assert encoded[25] == 3 and decoded.size() == expected.size()
                assert decoded.colorCount() <= 256
                assert decoded.dotsPerMeterX() == expected.dotsPerMeterX()
                assert "Optimizing PNG" in ticks
            elif outputFormat == "png":
                assert QtGui.QImage(str(path)) == expected
            else:
                assert path.read_bytes() == expected
            assert main.BuildProjectData(includeHistory = False) == expectedState
            dialog.deleteLater()

            # Stop a running process for every format. Closing the window and
            # Escape follow the same cancellation path as the Cancel button.
            contents = path.read_bytes()
            cancelled = ExportProgressDialog(panel, path, outputFormat, optimized)
            cancelled.process.started.connect(cancelled.close)
            with patch.object(panel, "RenderArguments", return_value = arguments):
                assert cancelled.exec() == QtWidgets.QDialog.DialogCode.Rejected
            assert cancelled.cancelled and not cancelled.error
            assert cancelled.process.state() == QtCore.QProcess.ProcessState.NotRunning
            assert path.read_bytes() == contents
            assert not list(folder.glob(".planner-export-*"))
            cancelled.deleteLater()

        # Render errors travel back from the worker and cannot overwrite a file.
        path = folder / "result.png"
        contents = path.read_bytes()
        arguments = panel.RenderArguments("png")
        arguments["scale"] = -1
        failed = ExportProgressDialog(panel, path, "png", False)
        with patch.object(panel, "RenderArguments", return_value = arguments):
            assert failed.exec() == QtWidgets.QDialog.DialogCode.Rejected
        assert "greater than zero" in failed.error and path.read_bytes() == contents
        assert not list(folder.glob(".planner-export-*"))
        failed.deleteLater()

        # Interrupt the JavaScript encoder itself, rather than merely cancelling
        # startup. The timer must keep firing while that work is in progress.
        arguments = panel.RenderArguments("png")
        arguments.update(bounds = [-2560, -2560, 5120, 5120], scale = 100)
        encoding = ExportProgressDialog(panel, path, "png", True)
        timer = QtCore.QTimer(encoding)
        timer.setInterval(5)
        stages = []
        def CancelEncoding():
            stages.append(encoding.statusLabel.text())
            if stages[-1] == "Optimizing PNG":
                encoding.grab().save(str(Path(__file__).resolve().parents[1] / "diagnostics/export-progress.png"))
                encoding.reject()
        timer.timeout.connect(CancelEncoding)
        timer.start()
        with patch.object(panel, "RenderArguments", return_value = arguments):
            assert encoding.exec() == QtWidgets.QDialog.DialogCode.Rejected
        timer.stop()
        assert "Optimizing PNG" in stages and encoding.cancelled
        assert path.read_bytes() == contents and not list(folder.glob(".planner-export-*"))
        encoding.deleteLater()

        # Failed startup is handled without waiting forever for a finished signal.
        missing = ExportProgressDialog(panel, path, "png", False)
        with patch("planner_app.ui.export_progress.sys.executable", str(folder / "missing-python.exe")):
            assert missing.exec() == QtWidgets.QDialog.DialogCode.Rejected
        assert "Could not start" in missing.error and path.read_bytes() == contents
        assert not list(folder.glob(".planner-export-*"))
        missing.deleteLater()

        # A fatal worker exit must close progress and return an error instead of
        # leaving the parent waiting behind an unreachable worker error window.
        crashed = ExportProgressDialog(panel, path, "png", True)
        crashed.process.started.connect(crashed.process.kill)
        assert crashed.exec() == QtWidgets.QDialog.DialogCode.Rejected
        assert "stopped unexpectedly" in crashed.error
        assert path.read_bytes() == contents and not list(folder.glob(".planner-export-*"))
        crashed.deleteLater()

        # Cancellation before the queued start does not launch a child.
        early = ExportProgressDialog(panel, folder / "cancelled.png", "png", False)
        early.reject()
        QtWidgets.QApplication.processEvents()
        assert early.completed and early.process.processId() == 0
        assert not (folder / "cancelled.png").exists()
        early.deleteLater()

        # The bundled executable dispatches the worker before session locking.
        import main as entry
        with patch.object(sys, "argv", ["Planner.exe", "--export-worker", "job.json"]), \
                patch("planner_app.export_worker.RunExportWorker", return_value = 0) as worker, \
                patch.object(entry, "AcquireSessionLock", side_effect = AssertionError("Export must not acquire a session lock")):
            assert entry.Main() == 0
            worker.assert_called_once_with("job.json")

        frozen = ExportProgressDialog(panel, path, "svg", False)
        with patch.object(sys, "frozen", True, create = True), \
                patch.object(frozen.process, "start") as start:
            frozen.Start()
            assert start.call_args.args[0] == sys.executable
            assert start.call_args.args[1][0] == "--export-worker"
            assert len(start.call_args.args[1]) == 2
        frozen.reject()
        assert frozen.completed and not list(folder.glob(".planner-export-*"))
        frozen.deleteLater()
    print("PASS: all export formats match, remain responsive, cancel safely and preserve destinations on failure")


if __name__ == "__main__":
    Main()
