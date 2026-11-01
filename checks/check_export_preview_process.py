"""Real asynchronous PNG/SVG previews, stale-result rejection and worker cleanup."""
import os
from pathlib import Path
import sys
from time import perf_counter
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Furnishing
from planner_app.export_plan import RenderPlan


def WaitForPreview(viewport, kind):
    overlay = viewport.exportOverlay
    deadline = perf_counter() + 15
    while perf_counter() < deadline:
        QtWidgets.QApplication.processEvents()
        viewport.grab()
        assert not overlay.previewError, overlay.previewError
        worker = overlay.previewProcess
        ready = (worker is not None and worker.current is None and not worker.queue and
                 (overlay.snapshot is not None and overlay.printPageCache and (kind == "png" or overlay.printVectorRenderer is not None)
                  if overlay.printMode else overlay.snapshot is not None if kind == "png" else overlay.svgRenderer is not None))
        if ready:
            return
        QtTest.QTest.qWait(10)
    raise AssertionError(("Preview did not settle", overlay.previewError, worker.current if worker else None,
                          list(worker.queue) if worker else None))


def Main():
    with ExampleWindow() as (main, folder):
        v, panel = main.viewport, main.exportPanel
        points = [QtCore.QPointF(x, y) for x, y in ((0, 0), (7000, 0), (7000, 5000), (0, 5000))]
        InstallScene(main, [*[Wall(points[index], points[(index + 1) % 4], 200) for index in range(4)],
                            Furnishing(v.furnishingDefinitions["washer"], QtCore.QPointF(2000, 2000))])
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("scaleMode", "Print")
        panel.SetScaleOption("dpi", 96)
        panel.SetOverride("titleBlock", dict(enabled = True, logoMode = "None", comments = "Worker preview"))
        panel.SetOverride("scaleBar", dict(enabled = True))
        panel.SetOverride("vignetteEnabled", True)
        overlay = v.exportOverlay
        os.environ.pop("PLANNER_SYNCHRONOUS_PREVIEW", None)
        ticks = []
        timer = QtCore.QTimer()
        timer.setInterval(5)
        timer.timeout.connect(lambda: ticks.append(perf_counter()))
        timer.start()
        with patch.object(overlay, "ConfigureSnapshotViewport", side_effect = AssertionError("Raster adoption rebuilt a local scene")):
            WaitForPreview(v, "png")
        assert len(ticks) > 10, "Rendering blocked the editor event loop"
        worker = overlay.previewProcess
        pid = worker.process.processId()
        assert pid and pid != os.getpid()
        pages = list(overlay.printPageCache)
        jobs = panel.ExportJobs(folder / "page.png", "png")
        assert len(pages) == len(jobs)
        for page, (path, arguments) in zip(sorted(pages), jobs):
            assert overlay.printPageCache[page] == RenderPlan(**arguments), "Worker PNG differs from export"
        for solid in (False, True, False):
            started = perf_counter()
            panel.SetOverride("solidObjects", solid)
            v.grab()
            assert perf_counter() - started < .4, "Appearance change synchronously rebuilt PNG"
        WaitForPreview(v, "png")
        assert worker.process.processId() == pid, "Every edit restarted the renderer"
        for page, (path, arguments) in zip(sorted(overlay.printPageCache), panel.ExportJobs(folder / "latest.png", "png")):
            assert overlay.printPageCache[page] == RenderPlan(**arguments), "An obsolete result replaced the latest settings"
        width, height = panel.PrintLayout()["paperTile"]
        panel.SetOverride("solidRooms", not v.solidRooms)
        v.grab()
        origin = overlay.pageOrigin
        overlay.bounds = (*origin, width, height)
        panel.SetBounds(overlay.bounds)
        v.snapEnabled = False
        panel.BeginExportGesture()
        overlay.dragEdge = 0
        for index in range(1, 9):
            overlay.MoveEdge(0, origin[0] + index * 25)
            v.grab()
            assert len(worker.queue) <= 2, "Dragging queued obsolete full-page renders"
        overlay.dragEdge = None
        panel.EndExportGesture()
        WaitForPreview(v, "png")
        assert "snapshot" in worker.results, "Dragging discarded the pending appearance refresh permanently"
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        WaitForPreview(v, "svg")
        assert overlay.printVectorRenderer.sharedRenderer is not None
        # A worker-side validation failure remains recoverable in the same
        # process and cannot affect the live scene or another preview slot.
        render = panel.RenderArguments("png", preview = True)
        worker.Request("probe", "invalid", lambda: dict(render, scale = -1), "png")
        deadline = perf_counter() + 5
        while worker.current is not None and perf_counter() < deadline:
            QtTest.QTest.qWait(5)
        try:
            worker.Request("probe", "invalid", lambda: render, "png")
        except ValueError:
            pass
        else:
            raise AssertionError("Worker error was not returned")
        worker.Request("crash", "terminated", lambda: render, "png")
        worker.process.kill()
        worker.process.waitForFinished(3000)
        QtWidgets.QApplication.processEvents()
        try:
            worker.Request("crash", "terminated", lambda: render, "png")
        except ValueError:
            pass
        else:
            raise AssertionError("A terminated worker was not reported")
        worker.Request("recovery", "restarted", lambda: render, "png")
        deadline = perf_counter() + 5
        while worker.current is not None and perf_counter() < deadline:
            QtTest.QTest.qWait(5)
        recovered = worker.Request("recovery", "restarted", lambda: render, "png")
        assert isinstance(recovered, QtGui.QImage) and not recovered.isNull()
        assert len(v.walls) == 4 and v.isVisible(), "Worker failure affected the editor"
        # Both non-page scale modes share the background pipeline as well.
        for mode in ("Digital", "Architectural"):
            panel.SetScaleOption("scaleMode", mode)
            for kind, name in (("png", "PNG"), ("svg", "SVG")):
                panel.typeField.setCurrentIndex(panel.typeField.findData(name))
                WaitForPreview(v, kind)
                assert not overlay.previewError
        panel.SetScaleOption("scaleMode", "Print")
        WaitForPreview(v, "svg")
        # New/Open/Build transitions must not leave jobs applying to another
        # project, or a process running after the owning view is closed.
        panel.SetScaleOption("architecturalScale", 75)
        v.grab()
        cleanup = worker.temporary.cleanup
        cleanupAttempts = []

        def FinishCleanup():
            cleanupAttempts.append(True)
            if len(cleanupAttempts) == 1:
                error = PermissionError("Worker transport file is still being released")
                error.winerror = 32
                raise error
            cleanup()

        with patch.object(worker.temporary, "cleanup", side_effect = FinishCleanup):
            panel.SetActive(False)
        assert len(cleanupAttempts) >= 2, "Windows sharing lock was not retried"
        assert worker.current is None and not worker.queue and not worker.results
        assert worker.process.state() == QtCore.QProcess.ProcessState.NotRunning
        panel.SetActive(True)
        v.grab()
        main.close()
        assert worker.process.state() == QtCore.QProcess.ProcessState.NotRunning
        timer.stop()
        os.environ["PLANNER_SYNCHRONOUS_PREVIEW"] = "1"
    print("Asynchronous previews preserve PNG output, coalesce edits, keep UI events running and clean up")


if __name__ == "__main__":
    Main()
