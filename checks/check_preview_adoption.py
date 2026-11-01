"""Asynchronous result ownership, exact native SVG pixels and cancellation."""
import json
import os
from pathlib import Path
import pickle
import sys
import weakref
from threading import Event
from time import perf_counter
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from xml.etree import ElementTree

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Door, Furnishing, Label
from planner_app import export_preview
from planner_app.graphics.svg_preview import SvgPreviewRenderer
from planner_app.graphics import svg_preview
from planner_app.export_plan import RenderPlan
from shiboken6 import isValid


def Wait(worker):
    deadline = perf_counter() + 10
    while (worker.current is not None or worker.queue) and perf_counter() < deadline:
        QtTest.QTest.qWait(2)
    assert worker.current is None and not worker.queue and worker.adoption is None


def Main():
    with ExampleWindow() as (main, folder):
        point = QtCore.QPointF
        wall = Wall(point(0, 0), point(4000, 0), 200)
        InstallScene(main, [wall, Door(wall, .2, .4), Furnishing(main.viewport.furnishingDefinitions["washer"], point(1500, 1500)),
                            Label(point(2000, 2500), "Unicode é 家")])
        worker = export_preview.ExportPreviewProcess(main.viewport.exportOverlay)
        worker.temporary = __import__("tempfile").TemporaryDirectory(prefix = "planner-adoption-")
        directory = Path(worker.temporary.name)
        image = QtGui.QImage(160, 100, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtGui.QColor(10, 30, 80, 137))
        image.setDotsPerMeterX(11811)
        image.setDotsPerMeterY(11000)
        frame = directory / "frame.raw"
        with frame.open("wb") as output:
            output.write((json.dumps(dict(width = image.width(), height = image.height(), stride = image.bytesPerLine(),
                format = image.format().value, dpiX = image.dotsPerMeterX(), dpiY = image.dotsPerMeterY())) + "\n").encode())
            output.write(image.constBits())
        frameBytes = frame.read_bytes()
        render = main.exportPanel.RenderArguments("svg", preview = True)
        render.update(bounds = (-500, -1000, 6000, 4000), scale = 60, border = "None", titleBlock = {})
        root = RenderPlan(**render, previewDocument = True)
        vector = directory / "vector.pickle"
        vector.write_bytes(pickle.dumps(root))
        loadedOn = []
        tasks = []
        load = export_preview.LoadPreviewResult
        # Shared cache paths are copied; only short metadata operations lock.
        shapes = [ElementTree.Element("path", d = f"M {index} 0 L {index + 10} 20 L 0 30 Z") for index in range(64)]
        with ThreadPoolExecutor(max_workers = 2) as pool:
            futures = [pool.submit(svg_preview.SvgClipPath, shape) for shape in shapes * 2]
            expected = [svg_preview.SvgClipPath(shape) for shape in shapes * 2]
            assert [future.result() for future in futures] == expected
        assert svg_preview.clipPathCacheElements == sum(path.elementCount() for path in svg_preview.clipPathCache.values())
        assert svg_preview.clipPathCacheBytes == sum(len(key[0]) * 2 for key in svg_preview.clipPathCache)
        def Load(*args):
            loadedOn.append(QtCore.QThread.currentThread())
            return load(*args)
        try:
            with patch.object(export_preview, "LoadPreviewResult", side_effect = Load):
                for kind, path in (("png", frame), ("svg", vector)):
                    key = kind, "fixture"
                    worker.requests[kind] = key
                    worker.current = dict(id = 1, slot = kind, key = key, path = path, kind = kind)
                    worker.Complete()
                    assert worker.adoption is not None
                    tasks.append(weakref.ref(worker.adoption))
                    Wait(worker)
                    actual = worker.Request(kind, key, lambda: {}, kind)
                    assert actual is not None
                    if kind == "png":
                        assert actual == image and actual.dotsPerMeterX() == image.dotsPerMeterX() and actual.dotsPerMeterY() == image.dotsPerMeterY()
                    else:
                        assert actual.renderer is not None
                        native = SvgPreviewRenderer.FromDocument(actual, worker)
                        reference = SvgPreviewRenderer(root)
                        assert native.thread() == main.thread()
                        assert all(child.thread() == main.thread() for child in native.findChildren(QtCore.QObject))
                        images = []
                        for renderer in (native, reference):
                            bitmap = QtGui.QImage(400, 280, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                            bitmap.fill(QtCore.Qt.GlobalColor.transparent)
                            with QtGui.QPainter(bitmap) as painter:
                                renderer.render(painter)
                            images.append(bitmap)
                        assert images[0] == images[1]
                        native.deleteLater()
                        reference.deleteLater()
                    # A second request reloads the same disk result off-thread.
                    assert worker.Request(kind, key, lambda: {}, kind) is None
                    Wait(worker)
                    again = worker.Request(kind, key, lambda: {}, kind)
                    assert again is not None
                    if kind == "svg":
                        again.renderer.deleteLater()
                        again.renderer = None
                assert loadedOn and all(thread != main.thread() for thread in loadedOn)
                savedLimit = main.viewport.viewportRasterByteLimit
                lowLimit = max(8192, vector.stat().st_size * 2)
                main.viewport.viewportRasterByteLimit = lowLimit
                try:
                    assert worker.Request("svg", ("svg", "fixture"), lambda: {}, "svg") is None
                    Wait(worker)
                    oversized = worker.Request("svg", ("svg", "fixture"), lambda: {}, "svg")
                    assert oversized is not None and oversized.size > max(4096, lowLimit // 2) and oversized.renderer is None, "Oversized vectors bypassed caller budget checks"
                finally:
                    main.viewport.viewportRasterByteLimit = savedLimit
                loadedOn.clear()
                QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
                assert all(reference() is None or not isValid(reference()) and reference().value is None for reference in tasks), "Finished task retained native resources or its result"
            # Hold the loader while changing generations: no stale adoption.
            entered, release = Event(), Event()
            def Delayed(*args):
                entered.set()
                assert release.wait(3)
                return load(*args)
            worker.requests["stale"] = "old"
            worker.current = dict(id = 7, slot = "stale", key = "old", path = vector, kind = "svg")
            with patch.object(export_preview, "LoadPreviewResult", side_effect = Delayed):
                worker.Complete()
                assert entered.wait(2)
                worker.BeginFrame("new generation")
                release.set()
                Wait(worker)
            assert "stale" not in worker.results and worker.readyResult is None
            # Corrupt files become recoverable slot errors rather than paint errors.
            broken = directory / "broken.frame"
            broken.write_bytes(b"not JSON\n")
            worker.requests["broken"] = 1
            worker.current = dict(id = 8, slot = "broken", key = 1, path = broken, kind = "png")
            worker.Complete()
            Wait(worker)
            try:
                worker.Request("broken", 1, lambda: {}, "png")
            except ValueError:
                pass
            else:
                raise AssertionError("Corrupt image was accepted")
            # Empty-message exceptions (notably MemoryError) must be errors,
            # never successful disk results that repeatedly try adoption.
            frame.write_bytes(frameBytes)  # The stale-generation test retired the old result.
            worker.requests["memory"] = 1
            worker.current = dict(id = 10, slot = "memory", key = 1, path = frame, kind = "png")
            with patch.object(export_preview, "LoadPreviewResult", side_effect = MemoryError()):
                worker.Complete()
                Wait(worker)
            assert worker.results["memory"][2] == "MemoryError"
            assert worker.workerFailure["exceptionType"] == "MemoryError"
            assert "MemoryError" in worker.diagnostics
            try:
                worker.Request("memory", 1, lambda: {}, "png")
            except ValueError as error:
                assert str(error) == "MemoryError"
            else:
                raise AssertionError("Empty-message adoption failure was cached as success")

            def BrokenSnapshot():
                raise MemoryError()

            worker.Request("factory", 1, BrokenSnapshot, "png", isCurrent = lambda: True)
            assert worker.results["factory"][2] == "MemoryError" and worker.current is None
            try:
                worker.Request("eager", 1, BrokenSnapshot, "png")
            except ValueError as error:
                assert str(error) == "MemoryError" and isinstance(error.__cause__, MemoryError)
            else:
                raise AssertionError("Eager snapshot failure lost its diagnostic")
            worker.requests["memory"] = 2
            worker.current = dict(id = 11, slot = "memory", key = 2, path = frame, kind = "png")
            worker.Complete()
            Wait(worker)
            assert worker.Request("memory", 2, lambda: {}, "png") is not None
            # Close joins an active task and drops GUI-owned native preparation.
            worker.requests["close"] = 1
            worker.current = dict(id = 9, slot = "close", key = 1, path = frame, kind = "png")
            worker.Complete()
            worker.Close()
            assert worker.adoption is worker.readyResult is worker.current is worker.temporary is None
        finally:
            worker.Close()
    print("PASS: off-GUI image/SVG loading, exact pixels/DPI, native child-thread ownership, disk revisits, stale generation, malformed data and in-flight close.")


if __name__ == "__main__":
    Main()
