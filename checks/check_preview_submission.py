"""Deferred snapshot ownership, lossless private transport and real-worker pixels."""
import json
import os
from pathlib import Path
import pickle
import sys
import weakref
from time import perf_counter
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app import export_preview
from planner_app.export_worker import ExportJobEncoder, DecodeExportValue
from planner_app.export_plan import RenderPlan
from planner_app.models import Wall, Furnishing, Label


def Wait(worker):
    deadline = perf_counter() + 10
    while (worker.current is not None or worker.queue) and perf_counter() < deadline:
        QtTest.QTest.qWait(5)
    assert worker.current is None and not worker.queue, "Worker did not settle"


def Main():
    with ExampleWindow() as (main, folder):
        v, panel = main.viewport, main.exportPanel
        InstallScene(main, [Wall(QtCore.QPointF(0, 0), QtCore.QPointF(4000, 0), 200),
            Furnishing(v.furnishingDefinitions["washer"], QtCore.QPointF(1800, 1200)), Label(text = "Unicode \u00e9 \u5bb6")])
        render = panel.RenderArguments("png", preview = True)
        render.update(bounds = (-500, -1000, 6000, 4000), scale = 60, pageSize = None, architecturalScale = None,
                      dpi = None, border = "None", titleBlock = {}, scaleBar = {})
        worker = export_preview.ExportPreviewProcess(v.exportOverlay)
        try:
            # Keep the process deliberately busy while replacing one queued
            # slot. Only the final factory should encode its scene.
            with patch.object(worker.process, "state", return_value = QtCore.QProcess.ProcessState.Running), \
                    patch.object(worker.process, "write", return_value = 1), \
                    patch.object(main, "BuildProjectData", wraps = main.BuildProjectData) as builds:
                worker.current = dict(slot = "occupied", key = 0)
                for index in range(16):
                    worker.Request("snapshot", index, lambda: panel.RenderArguments("png", preview = True), "png", isCurrent = lambda: True)
                assert builds.call_count == 0 and len(worker.queue) == 1
                worker.current = None
                worker.StartNext()
                assert builds.call_count == 1 and worker.current["key"] == 15
                path = Path(worker.temporary.name) / "job.pickle"
                with path.open("rb") as source:
                    job = pickle.load(source)
                expected = panel.RenderArguments("png", preview = True)
                assert json.dumps(job["render"], cls = ExportJobEncoder) == json.dumps(expected, cls = ExportJobEncoder)
                # A changed source without a new paint cannot evaluate an old
                # callback under an obsolete key. Schedule a fresh paint instead.
                worker.current = dict(slot = "occupied", key = 0)
                worker.Request("snapshot", "stale", lambda: (_ for _ in ()).throw(AssertionError("Stale factory ran")), "png", isCurrent = lambda: False)
                worker.current = None
                worker.StartNext()
                assert worker.current is None and not worker.queue
                # A new generation and closing release closures without work.
                worker.current = dict(slot = "occupied", key = 0)
                worker.Request("snapshot", "cancelled", lambda: (_ for _ in ()).throw(AssertionError("Cancelled factory ran")), "png", isCurrent = lambda: True)
                worker.BeginFrame("another scene")
                worker.current = None
                worker.StartNext()
                assert not worker.queue
                worker.current = dict(slot = "occupied", key = 0)
                before = builds.call_count
                worker.Request("eager", 1, lambda: panel.RenderArguments("png", preview = True), "png")
                assert builds.call_count == before + 1, "Unguarded API stopped snapshotting at request time"
                worker.BeginFrame("clear eager snapshot")
                class Payload:
                    pass
                payload = Payload()
                retained = weakref.ref(payload)
                worker.Request("payload", 1, lambda payload = payload: render, "png", isCurrent = lambda: True)
                del payload
                assert retained() is not None
                worker.BeginFrame("release queued snapshot")
                assert retained() is None, "Generation change retained a discarded factory closure"
                worker.current = None
                # Errors during dispatch are reported through the normal slot
                # result, not an unhandled process-completion callback.
                worker.Request("fault", "factory", lambda: (_ for _ in ()).throw(ValueError("Injected snapshot failure")), "png", isCurrent = lambda: True)
                assert worker.current is None
                try:
                    worker.Request("fault", "factory", lambda: render, "png")
                except ValueError as error:
                    assert str(error) == "Injected snapshot failure"
                else:
                    raise AssertionError("Deferred failure was not returned")
                # A callback may cancel its owner; dispatch must stop cleanly.
                worker.Request("closing", 1, lambda: worker.Close(), "png", isCurrent = lambda: True)
                assert worker.current is None and worker.temporary is None
            # The ordinary public API still snapshots unguarded factories at
            # request time. Binary round trips preserve old JSON value semantics.
            for kind in ("png", "svg"):
                for index, options in enumerate(({}, dict(solidObjects = False), dict(wallStyle = "Outline", rasterSampling = .75))):
                    arguments = dict(render, outputFormat = kind, **options)
                    legacy = json.loads(json.dumps(arguments, ensure_ascii = False, cls = ExportJobEncoder), object_hook = DecodeExportValue)
                    worker.Request("pixels", (kind, index), lambda: arguments, kind)
                    Wait(worker)
                    actual = worker.Request("pixels", (kind, index), lambda: arguments, kind)
                    expected = RenderPlan(**legacy)
                    if kind == "png":
                        assert actual == expected, (kind, index, "worker pixels")
                    else:
                        from planner_app.graphics.svg_preview import SvgPreviewRenderer
                        native = SvgPreviewRenderer(actual)
                        reference = SvgPreviewRenderer(expected)
                        images = []
                        for renderer in (native, reference):
                            image = QtGui.QImage(450, 320, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                            image.fill(QtCore.Qt.GlobalColor.transparent)
                            with QtGui.QPainter(image) as painter:
                                renderer.render(painter)
                            images.append(image)
                        assert images[0] == images[1], (kind, index, "SVG pixels")
                        native.deleteLater()
                        reference.deleteLater()
            # Check the real CaptureRaster caller defers its expensive snapshot,
            # and rejects it after a geometry change even before the next paint.
            worker.Close()
            overlay = v.exportOverlay
            with patch.object(export_preview, "PreviewProcess", return_value = worker), \
                    patch.object(panel, "RenderArguments", wraps = panel.RenderArguments) as arguments:
                worker.current = dict(slot = "occupied", key = 0)
                assert overlay.CaptureRaster(QtCore.QRectF(-500, -1000, 6000, 4000), .5, "snapshot") is None
                assert arguments.call_count == 0
                v.walls[0].secondVertex += QtCore.QPointF(1, 0)
                worker.current = None
                worker.StartNext()
                assert arguments.call_count == 0 and worker.current is None
        finally:
            worker.Close()
        assert worker.temporary is None and not worker.queue and not worker.results
    print("PASS: 16-to-1 snapshot coalescing, stale/generation/close rejection, dispatch errors, binary/legacy PNG-SVG pixel parity and real caller invalidation.")


if __name__ == "__main__":
    Main()
