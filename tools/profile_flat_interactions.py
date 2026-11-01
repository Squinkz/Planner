"""Profile actual flat.plan wall endpoint edits and wheel zoom without saving it."""
import argparse
import cProfile
import json
import os
from pathlib import Path
import pstats
from statistics import median
import sys
from time import perf_counter

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
from PySide6 import QtCore, QtGui, QtWidgets
from fixtures.parity_examples import ExampleWindow
from planner_app.models import Wall
from planner_app.project_codec import DecodeProject

folder = root / "diagnostics/performance-flat-20261031"


def LoadFlat(main):
    path = root / "plans/flat.plan"
    data = json.loads(path.read_text(encoding = "utf-8"))
    decoded = DecodeProject(data, main.viewport.furnishingDefinitions, validatePlacement = False)
    main.ApplyProject(decoded, path)
    main.viewport.performanceTimer.stop()
    QtWidgets.QApplication.processEvents()
    return main.viewport


def BeginEndpoint(view, wall, index):
    point = QtCore.QPointF
    view.CancelInteraction()
    view.SetSelection([(wall, index)])
    view.interactionBefore = view.CaptureState()
    view.dragSource = wall
    view.dragSourceVertex = index
    view.dragVertices = point(wall.firstVertex), point(wall.secondVertex)
    view.dragSourceVertices = tuple(map(point, view.dragVertices))
    view.dragStart = view.WorldToViewport(view.dragVertices[index])
    view.isDragging = True
    view.dragAttachments = view.AttachedVertices(wall, captureAll = True)
    view.dragSourceAttachments = list(view.dragAttachments)
    view.dragSourceConstraints = list(view.dragConstraints)


def Step(view, case, frame):
    start = perf_counter()
    if case == "drag":
        view.UpdateInteraction(view.dragStart + QtCore.QPointF(25 + frame * 3, 17 + frame), QtCore.Qt.KeyboardModifier.NoModifier)
    else:
        position = view.DrawingRect().center()
        zoomIn = frame % 2 == 0 if case == "zoom" else case == "zoom-in"
        event = QtGui.QWheelEvent(position, view.mapToGlobal(position.toPoint()), QtCore.QPoint(),
            QtCore.QPoint(0, 120 if zoomIn else -120), QtCore.Qt.MouseButton.NoButton,
            QtCore.Qt.KeyboardModifier.NoModifier, QtCore.Qt.ScrollPhase.NoScrollPhase, False)
        view.wheelEvent(event)
    updateMs = (perf_counter() - start) * 1000
    start = perf_counter()
    QtWidgets.QApplication.processEvents()
    eventMs = (perf_counter() - start) * 1000
    start = perf_counter()
    image = view.grab()
    paintMs = (perf_counter() - start) * 1000
    return dict(updateMs = updateMs, eventMs = eventMs, grabMs = paintMs, totalMs = updateMs + eventMs + paintMs)


def Main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default = "baseline")
    parser.add_argument("--width", type = int, default = 1000)
    parser.add_argument("--height", type = int, default = 800)
    parser.add_argument("--cases", nargs = "+", default = ["drag", "zoom"], choices = ("drag", "zoom", "zoom-in", "zoom-out"))
    args = parser.parse_args()
    folder.mkdir(exist_ok = True)
    rows = []
    with ExampleWindow() as (main, temporary):
        main.viewport.setFixedSize(args.width, args.height)
        main.resize(args.width + 450, args.height + 100)
        for case in args.cases:
            view = LoadFlat(main)
            if case == "drag":
                center = view.DrawingRect().center()
                candidates = [(QtCore.QLineF(center, view.WorldToViewport(vertex)).length(), wall, index)
                              for wall in view.walls if type(wall) is Wall
                              for index, vertex in enumerate((wall.firstVertex, wall.secondVertex))
                              if view.DrawingRect().contains(view.WorldToViewport(vertex))]
                distance, wall, index = min(candidates, key = lambda item: item[0])
                BeginEndpoint(view, wall, index)
                print("Selected wall", wall.objectId, "vertex", index, "at zoom", view.zoom, flush = True)
            for frame in range(2):
                Step(view, case, frame)
            samples = [Step(view, case, frame) for frame in range(2, 5)]
            profile = cProfile.Profile()
            profile.runcall(Step, view, case, 5)
            profile.dump_stats(str(folder / f"{args.output}-{case}.pstats"))
            stats = pstats.Stats(profile)
            functions = sorted(((key[0], key[1], key[2], value[0], value[2] * 1000, value[3] * 1000)
                                for key, value in stats.stats.items()), key = lambda item: item[-1], reverse = True)
            row = dict(case = case, samples = samples, medians = {key: median(sample[key] for sample in samples) for key in samples[0]},
                       topCumulativeMs = functions[:45])
            if case == "drag":
                row.update(wallId = wall.objectId, vertex = index)
            rows.append(row)
            print(case, row["medians"], flush = True)
            print(json.dumps(functions[:18], indent = 2), flush = True)
            view.CancelInteraction()
    (folder / f"{args.output}.json").write_text(json.dumps(dict(viewportSize = [args.width, args.height], methodology =
        "Real MainWindow at 1000x800 viewport, saved project settings, endpoint UpdateInteraction or wheelEvent, processEvents then synchronous grab. "
        "Two warmups, three unprofiled samples, one separate cProfile step. Events and grab may both paint. Not display latency. Original project is never saved.",
        cases = rows), indent = 2), encoding = "utf-8")


if __name__ == "__main__":
    Main()
