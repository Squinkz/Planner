"""Bounded alternating timings for the final editor audit follow-ups."""
import argparse
import gc
import json
import os
from pathlib import Path
import platform
from statistics import median
import sys
from time import perf_counter
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.models import Wall, Furnishing, Label
from planner_app.viewport.widget import DrawingViewport
from fixtures.final_followups_reference_20261031 import ReferenceViewport
from fixtures.paint_preparation_reference_20261031 import ReferenceViewport as OriginalPlacementViewport
from fixtures.svg_reference_20261031 import SvgPreviewRenderer as ReferenceSvg
from fixtures.parity_examples import ExampleWindow
from planner_app.export_preview import ExportPreviewProcess
from planner_app.graphics import svg_preview
from planner_app.graphics.svg_preview import SvgPreviewRenderer
from shiboken6 import delete

folder = root / "diagnostics/performance-final-followups-20261031"


def CreateViewport(cls, count, selected = 0, dense = False):
    view = cls()
    point = QtCore.QPointF
    view.resize(1200, 800)
    view.showMeasurements = view.showTips = False
    view.performanceTimer.stop()
    view.walls = [Wall(point(index * 6000, 0), point(index * 6000 + 4000, 0), 200) for index in range(count)]
    view.furnishings = [Furnishing(view.furnishingDefinitions["desk"], point(index * 6000 + 2000, 10000)) for index in range(count)]
    view.labels = [Label(point(index * 6000, 15000), "Label é 家") for index in range(count)]
    if dense:
        view.walls = []
        for index, obj in enumerate(view.furnishings + view.labels):
            delta = point(index % 16 * 1800, index // 16 * 1400) - (obj.firstVertex + obj.secondVertex) / 2
            obj.firstVertex += delta
            obj.secondVertex += delta
        view.zoom = .02
        view.panOffset = point(-200, -200)
    view.snapEnabled = view.connectedEnabled = False
    view.dragStart, view.isDragging = point(400, 300), True
    view.selectedWall = view.furnishings[0]
    if selected:
        view.snapEnabled = True
        view.SetSelection([(obj, None) for obj in view.furnishings[:selected // 2] + view.labels[:selected - selected // 2]], notify = False)
        view.interactionBefore = view.CaptureState()
        view.StartGroupDrag()
    return view


def MeasureEditor(case):
    result = []
    configurations = ({"paint": [(128, 0, False), (1024, 0, False), (128, 0, True)],
                       "snap": [(128, 2, False), (1024, 2, False), (1024, 128, False)],
                       "wall": [(1024, 0, False)]})[case]
    for count, selected, dense in configurations:
        classes = (OriginalPlacementViewport, ReferenceViewport, DrawingViewport) if case == "wall" else (ReferenceViewport, DrawingViewport)
        views = [CreateViewport(cls, count, selected, dense) for cls in classes]
        images = [QtGui.QImage(view.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied) for view in views]
        workloads = (("warm", "preparation-miss") if case == "paint" else
                     ("warm", "target-preparation-miss") if case == "snap" else ("warm",))
        for workload in workloads:
            samples = [[] for view in views]
            for iteration in range(11):
                for variant in (range(len(views)) if iteration % 2 == 0 else reversed(range(len(views)))):
                    view = views[variant]
                    if workload == "preparation-miss":
                        view.__dict__.pop("paintObjectIndex", None)
                        view.renderChanges.paintChanges = None
                    elif workload == "target-preparation-miss":
                        view.__dict__.pop("groupSnapPreparation", None)
                        view.renderChanges.snapChanges = None
                        view.numericSnapPreparation = view.footprintSnapTargetsKey = None
                    started = perf_counter()
                    if case == "snap":
                        view.UpdateGroupDrag(view.dragStart + QtCore.QPointF(70 + iteration * 3, 50), QtCore.Qt.KeyboardModifier.NoModifier)
                    else:
                        for update in range(3 if case == "wall" or case == "paint" and workload == "warm" else 1):
                            obj = view.walls[0] if case == "wall" else view.furnishings[0]
                            step = 1 if iteration % 2 else -1
                            obj.firstVertex.setX(obj.firstVertex.x() + step)
                            obj.secondVertex.setX(obj.secondVertex.x() + step)
                            if case == "wall":
                                view.InvalidArchitecturalObjects()
                            else:
                                view.render(images[variant])
                    elapsed = (perf_counter() - started) * 1000
                    if case == "wall" or case == "paint" and workload == "warm":
                        elapsed /= 3
                    if iteration >= 2:
                        samples[variant].append(elapsed)
            row = dict(case = case, objectsPerCategory = count, selected = selected, dense = dense,
                       workload = workload, medianMs = [median(values) for values in samples], samplesMs = samples)
            result.append(row)
            print(json.dumps({key: value for key, value in row.items() if key != "samplesMs"}), flush = True)
            if case == "paint":
                assert images[0] == images[1], ("Benchmark pixels differ", count, dense, workload)
        for view in views:
            view.CancelInteraction()
            view.close()
            delete(view)
    return result


class ReferenceAdoptionSvg(ReferenceSvg):
    def __init__(self, value, *args, **kwargs):
        super().__init__(value.root if hasattr(value, "root") else value, *args, **kwargs)


def MeasureSvg():
    with ExampleWindow() as (main, temporary):
        main.hide()
        view = main.viewport
        point = QtCore.QPointF
        count = 64
        view.walls = [Wall(point(index % 16 * 2000, index // 16 * 2000), point(index % 16 * 2000 + 1500, index // 16 * 2000), 200)
                      for index in range(count)]
        view.furnishings = [Furnishing(view.furnishingDefinitions["washer"], point(index % 16 * 2000 + 500, index // 16 * 2000 + 800))
                            for index in range(count)]
        view.EnsureObjectIds()
        render = main.exportPanel.RenderArguments("svg", preview = True)
        render.update(bounds = (-1000, -1000, 34000, 10000), scale = 20, border = "None", titleBlock = {})
        workers = [ExportPreviewProcess(view.exportOverlay) for variant in range(2)]
        sources = [folder / "export_preview_worker.py", root / "planner-main/planner_app/export_preview_worker.py"]
        samples, gaps, sizes, producers, adoptions = [[], []], [[], []], [[], []], [[], []], [[], []]
        try:
            for worker, source in zip(workers, sources):
                environment = QtCore.QProcessEnvironment.systemEnvironment()
                environment.insert("QT_QPA_PLATFORM", "offscreen")
                environment.insert("PYTHONPATH", str(root / "planner-main"))
                worker.process.setProcessEnvironment(environment)
                worker.process.setWorkingDirectory(str(root / "planner-main"))
                worker.process.start(sys.executable, [str(source)])
                assert worker.process.waitForStarted(5000)
            for iteration in range(9):
                for variant in ((0, 1) if iteration % 2 == 0 else (1, 0)):
                    worker = workers[variant]
                    ticks = [perf_counter()]
                    timer = QtCore.QTimer()
                    timer.setInterval(1)
                    timer.timeout.connect(lambda: ticks.append(perf_counter()))
                    producerReady = []
                    def ReadResult():
                        if not producerReady:
                            producerReady.append(perf_counter())
                        worker.ReadOutput()
                    worker.process.readyReadStandardOutput.disconnect(worker.ReadOutput)
                    worker.process.readyReadStandardOutput.connect(ReadResult)
                    loop = QtCore.QEventLoop()
                    poll = QtCore.QTimer()
                    poll.setInterval(2)
                    poll.timeout.connect(lambda: loop.quit() if worker.current is None else None)
                    deadline = QtCore.QTimer()
                    deadline.setSingleShot(True)
                    deadline.timeout.connect(loop.quit)
                    rendererClass = ReferenceAdoptionSvg if variant == 0 else SvgPreviewRenderer
                    with patch.object(svg_preview, "SvgPreviewRenderer", rendererClass):
                        timer.start()
                        started = perf_counter()
                        key = ("svg", iteration)
                        worker.Request("benchmark", key, lambda: render, "svg")
                        poll.start()
                        deadline.start(15000)
                        loop.exec()
                        elapsed = (perf_counter() - started) * 1000
                    timer.stop()
                    worker.process.readyReadStandardOutput.disconnect(ReadResult)
                    worker.process.readyReadStandardOutput.connect(worker.ReadOutput)
                    poll.stop()
                    deadline.stop()
                    ticks.append(perf_counter())
                    assert worker.current is None, "Preview timed out"
                    value = worker.Request("benchmark", key, lambda: render, "svg")
                    assert value is not None and value.renderer is not None, view.exportOverlay.previewError
                    if iteration >= 2:
                        samples[variant].append(elapsed)
                        gaps[variant].append(max(second - first for first, second in zip(ticks, ticks[1:])) * 1000)
                        sizes[variant].append(worker.results["benchmark"][1].stat().st_size)
                        producers[variant].append((producerReady[0] - started) * 1000)
                        adoptions[variant].append(elapsed - producers[variant][-1])
                    delete(value.renderer)
                    value.renderer = None
            return [dict(case = "svg", walls = count, washerFurnishings = count, medianMs = [median(values) for values in samples],
                         samplesMs = samples, heartbeatGapMs = [median(values) for values in gaps], heartbeatSamplesMs = gaps,
                         transportBytes = [median(values) for values in sizes], producerMs = [median(values) for values in producers],
                         producerSamplesMs = producers, adoptionMs = [median(values) for values in adoptions], adoptionSamplesMs = adoptions)]
        finally:
            for worker in workers:
                worker.Close()
                delete(worker)


def Main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required = True, choices = ("paint", "snap", "wall", "svg"))
    args = parser.parse_args()
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setStyle("Fusion")
    LoadApplicationFonts(app)
    gcWasEnabled = gc.isenabled()
    gc.disable()
    try:
        cases = MeasureSvg() if args.case == "svg" else MeasureEditor(args.case)
        report = dict(python = platform.python_version(), qt = QtCore.qVersion(), platform = platform.platform(),
            qtPlatform = QtWidgets.QApplication.platformName(), devicePixelRatio = app.primaryScreen().devicePixelRatio(),
            methodology = "Independent frozen/current offscreen 1200x800 viewports; explicit model movement plus synchronous QWidget.render for paint; "
                "group updates include fitting and snapping but exclude paint. N walls, N furnishings and N labels, except dense paint has no walls. "
                "Two warmups then nine alternating samples; three updates per sample for wall validation/warm paint, one otherwise. Paint misses discard only the new paint index outside the timer. "
                "Wall variants are pre-paint-preparation, previous pass, current. Shared current model observers. "
                "SVG uses real persistent before/current render processes, two warmups plus seven alternating samples, from request through native result adoption. "
                "Its 1ms GUI heartbeat measures maximum callback gaps, not display latency. Cyclic GC disabled equally in the benchmark parent. Jobs run sequentially.", cases = cases)
        destination = folder / f"benchmark-{args.case}.json"
        destination.write_text(json.dumps(report, indent = 2), encoding = "utf-8")
        print(json.dumps([{key: value for key, value in case.items() if key not in ("samplesMs", "heartbeatSamplesMs", "producerSamplesMs", "adoptionSamplesMs")}
                          for case in cases], indent = 2), flush = True)
    finally:
        if gcWasEnabled:
            gc.enable()


if __name__ == "__main__":
    Main()
