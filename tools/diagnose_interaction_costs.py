"""Diagnostic-only phase timing and deliberately incomplete rendering ablations.

No production source is patched on disk. Bypasses are restored by ExitStack.
Run from the repository root; results are written under diagnostics.
"""
import argparse
from contextlib import ExitStack, contextmanager
import cProfile
import gc
import json
import os
from pathlib import Path
import pstats
from statistics import median
import sys
from time import perf_counter
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / name) for name in ("planner-main", "checks", "tools")]
from PySide6 import QtCore, QtGui, QtWidgets
from benchmark_flat_interactions import PrepareCase
from profile_flat_interactions import BeginEndpoint
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_drag_fitting_preparation import Snapshot
from planner_app.graphics.text import PathTextPainter
from planner_app.graphics.furnishings import FurnishingSvgRenderer
from planner_app.viewport import geometry_cache

folder = root / "diagnostics/performance-interaction-costs-20261101"
cases = ("drag", "drag-wall1", "drag-single", "zoom-out", "zoom-in", "zoom-deep", "zoom-near", "pan", "pan-fractional", "pan-wide")
drawMethods = tuple(name for name in dir(QtGui.QPainter) if name.startswith("draw") and name != "drawText") + ("fillRect", "fillPath", "strokePath", "eraseRect")
phaseMethods = ("SnapStairVertex", "StairSnapTargets", "SnapPosition", "FitWallOpenings",
    "ConnectedWallPath", "TraceWallBoundary", "SceneRenderKey", "SceneRenderValueKey", "EditSceneSnapshot",
    "DrawScene", "DrawOpaqueScene", "DrawSceneMeasurements", "DrawLabels", "DrawGridBackground",
    "RefreshArchitecturalValidation", "WallFits", "ContainedWalls", "DuplicateFurnishings",
    "JoinedObjectsOverlap", "JoinedObjectBounds", "CollisionCategoryGeometry", "BuildWallComponent",
    "HitTest", "UpdateCanvasCursor")


def Prepare(main, case):
    view = PrepareCase(main, "drag" if case.startswith("drag") else case, False)
    if case == "drag-wall1":
        BeginEndpoint(view, next(wall for wall in view.walls if wall.objectId == 1), 0)
    elif case == "drag-single":
        wall = next(wall for wall in view.walls if wall.objectId == 256)
        view.CancelInteraction()
        InstallScene(main, [wall])
        view.ClearGeometryCaches()
        BeginEndpoint(view, wall, 1)
    if case.startswith("pan"):
        if case == "pan-wide":
            for frame in range(8):
                view.ZoomBy(1 / 1.15, view.DrawingRect().center())
        position = view.DrawingRect().center()
        event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonPress, position,
            QtCore.QPointF(view.mapToGlobal(position.toPoint())), QtCore.Qt.MouseButton.MiddleButton,
            QtCore.Qt.MouseButton.MiddleButton, QtCore.Qt.KeyboardModifier.NoModifier)
        view.mousePressEvent(event)
    return view


def Step(view, case, frame, state = None):
    if state is not None:
        state["stage"] = "input"
    view.renderSamples.clear()
    start = perf_counter()
    if case.startswith("drag"):
        view.UpdateInteraction(view.dragStart + QtCore.QPointF(25 + frame * 3, 17 + frame), QtCore.Qt.KeyboardModifier.NoModifier)
    elif case.startswith("pan"):
        delta = QtCore.QPointF(8.25, 5.25) if case == "pan-fractional" else QtCore.QPointF(8, 5)
        delta /= view.devicePixelRatioF()
        position = view.lastPanPosition + delta
        event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, position,
            QtCore.QPointF(view.mapToGlobal(position.toPoint())), QtCore.Qt.MouseButton.NoButton,
            QtCore.Qt.MouseButton.MiddleButton, QtCore.Qt.KeyboardModifier.NoModifier)
        view.mouseMoveEvent(event)
    else:
        position = view.DrawingRect().center()
        event = QtGui.QWheelEvent(position, view.mapToGlobal(position.toPoint()), QtCore.QPoint(),
            QtCore.QPoint(0, 120 if case == "zoom-in" or case == "zoom-near" and frame % 2 == 0 else -120), QtCore.Qt.MouseButton.NoButton,
            QtCore.Qt.KeyboardModifier.NoModifier, QtCore.Qt.ScrollPhase.NoScrollPhase, False)
        view.wheelEvent(event)
    updateMs = (perf_counter() - start) * 1000
    if state is not None:
        state["stage"] = "events"
    start = perf_counter()
    QtWidgets.QApplication.processEvents()
    eventMs = (perf_counter() - start) * 1000
    if state is not None:
        state["stage"] = "paint"
    start = perf_counter()
    view.grab()
    grabMs = (perf_counter() - start) * 1000
    assert len(view.renderSamples) == 1, len(view.renderSamples)
    return dict(updateMs = updateMs, eventMs = eventMs, grabMs = grabMs,
        totalMs = updateMs + eventMs + grabMs, paintEventMs = view.renderSamples[-1][1])


@contextmanager
def Measure(view, state):
    active = []
    def Wrap(original, name):
        def Timed(*args, **kwargs):
            entry = [perf_counter(), 0]
            active.append(entry)
            stage = state["stage"]
            try:
                return original(*args, **kwargs)
            finally:
                elapsed = (perf_counter() - entry[0]) * 1000
                active.pop()
                if active:
                    active[-1][1] += elapsed
                row = state["phases"].setdefault(stage + ":" + name, [0, 0, 0])
                row[0] += elapsed
                row[1] += elapsed - entry[1]
                row[2] += 1
        return Timed
    with ExitStack() as stack:
        for name in phaseMethods:
            owner = next(cls for cls in type(view).__mro__ if name in cls.__dict__)
            stack.enter_context(patch.object(owner, name, Wrap(getattr(owner, name), name)))
        for name in ("Check", "Refresh", "UpdateBoundary", "UpdateLabels"):
            stack.enter_context(patch.object(view.roomDetection, name, Wrap(getattr(view.roomDetection, name), "Room." + name)))
        for name in drawMethods:
            stack.enter_context(patch.object(PathTextPainter, name, Wrap(getattr(PathTextPainter, name), "QtDraw")))
        stack.enter_context(patch.object(FurnishingSvgRenderer, "render", Wrap(FurnishingSvgRenderer.render, "FurnishingSvg.render")))
        stack.enter_context(patch.object(geometry_cache, "GeometryCacheCost", Wrap(geometry_cache.GeometryCacheCost, "GeometryCacheCost")))
        yield


@contextmanager
def Bypass(view, mode):
    def NoDraw(*args, **kwargs):
        return None
    def NoSnap(position, opposite, stair, modifiers):
        view.alignmentGuides = []
        view.snapApplied = False
        return position
    def FrozenRoom():
        return view.roomDetection.revision, view.roomDetection.labelRevision
    with ExitStack() as stack:
        if mode == "no-snap":
            stack.enter_context(patch.object(view, "SnapStairVertex", NoSnap))
        elif mode == "frozen-rooms":
            stack.enter_context(patch.object(view.roomDetection, "Check", FrozenRoom))
        elif mode == "no-qt-draw":
            for name in drawMethods:
                stack.enter_context(patch.object(PathTextPainter, name, NoDraw))
        elif mode == "no-artwork":
            stack.enter_context(patch.object(FurnishingSvgRenderer, "render", NoDraw))
        elif mode == "no-measurements":
            stack.enter_context(patch.object(view, "DrawSceneMeasurements", NoDraw))
        elif mode == "no-edit-cache":
            stack.enter_context(patch.object(view, "CanCacheEditScene", lambda: False))
        yield


def Phases(case, run):
    with ExampleWindow() as (main, temporary):
        view = Prepare(main, case)
        warmups = [Step(view, case, frame) for frame in range(2)]
        rows = []
        state = dict(stage = "input", phases = {})
        with Measure(view, state):
            for frame in range(2, 17):
                state["phases"] = {}
                row = Step(view, case, frame, state)
                row["phases"] = state["phases"]
                rows.append(row)
        profile = cProfile.Profile()
        profile.runcall(Step, view, case, 17)
        profile.dump_stats(str(folder / f"profile-{case}-{run}.pstats"))
        stats = pstats.Stats(profile)
        functions = sorted((dict(file = key[0], line = key[1], name = key[2], calls = value[1],
            selfMs = value[2] * 1000, cumulativeMs = value[3] * 1000) for key, value in stats.stats.items()),
            key = lambda row: row["cumulativeMs"], reverse = True)
        view.CancelInteraction()
        return dict(case = case, run = run, warmups = warmups, samples = rows, profile = functions[:120],
            devicePixelRatio = view.devicePixelRatioF(), finalZoom = view.zoom)


def Trial(case, mode, run):
    with ExitStack() as stack:
        order = (0, 1) if run % 2 == 0 else (1, 0)
        views = [None, None]
        for index in order:
            main, temporary = stack.enter_context(ExampleWindow())
            views[index] = Prepare(main, case)
        samples, warmups = [[], []], [[], []]
        for frame in range(17):
            for index in ((0, 1) if (frame + run) % 2 == 0 else (1, 0)):
                with Bypass(views[index], mode if index == 1 else "normal"):
                    row = Step(views[index], case, frame)
                (warmups if frame < 2 else samples)[index].append(row)
            assert views[0].zoom == views[1].zoom and views[0].panOffset == views[1].panOffset
            if mode not in ("no-snap", "frozen-rooms"):
                assert Snapshot(views[0]) == Snapshot(views[1]), (case, mode, frame, "model")
        # Both normal windows must agree exactly; deliberately incomplete ablations need not.
        if mode == "normal":
            assert views[0].grab().toImage() == views[1].grab().toImage(), (case, "control pixels")
        releaseSamples = []
        if mode == "normal" and case.startswith("pan"):
            for view in views:
                view.renderSamples.clear()
                position = view.lastPanPosition
                event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonRelease, position,
                    QtCore.QPointF(view.mapToGlobal(position.toPoint())), QtCore.Qt.MouseButton.MiddleButton,
                    QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier)
                started = perf_counter()
                view.mouseReleaseEvent(event)
                QtWidgets.QApplication.processEvents()
                view.grab()
                releaseSamples.append(dict(totalMs = (perf_counter() - started) * 1000,
                    paintEventMs = sum(row[1] for row in view.renderSamples), paints = len(view.renderSamples)))
                assert not view.isPanning
            assert views[0].grab().toImage() == views[1].grab().toImage(), (case, "released control pixels")
        for view in views:
            view.CancelInteraction()
        return dict(case = case, mode = mode, run = run, samples = samples, warmups = warmups, releaseSamples = releaseSamples,
            devicePixelRatio = views[0].devicePixelRatioF(), finalZoom = views[0].zoom,
            medians = [{name: median(row[name] for row in rows) for name in rows[0]} for rows in samples],
            pairedMedianDeltaMs = {name: median(b[name] - a[name] for a, b in zip(*samples)) for name in samples[0][0]})


def Transitions(case, run):
    assert case.startswith("pan")
    with ExampleWindow() as (main, temporary):
        view = Prepare(main, case)
        view.EndPan()
        # Finish the initial project load and render an idle scene at the final camera.
        # The main matrix's first warmup deliberately has no such pre-render.
        QtWidgets.QApplication.processEvents()
        view.grab()
        view.grab()
        rows = []
        for transition in ("start", "release"):
            position = view.DrawingRect().center() if transition == "start" else view.lastPanPosition
            event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonPress if transition == "start" else QtCore.QEvent.Type.MouseButtonRelease,
                position, QtCore.QPointF(view.mapToGlobal(position.toPoint())), QtCore.Qt.MouseButton.MiddleButton,
                QtCore.Qt.MouseButton.MiddleButton if transition == "start" else QtCore.Qt.MouseButton.NoButton,
                QtCore.Qt.KeyboardModifier.NoModifier)
            state = dict(stage = "input", phases = {})
            view.renderSamples.clear()
            with Measure(view, state):
                started = perf_counter()
                if transition == "start":
                    view.mousePressEvent(event)
                else:
                    view.mouseReleaseEvent(event)
                updateMs = (perf_counter() - started) * 1000
                state["stage"] = "events"
                started = perf_counter()
                QtWidgets.QApplication.processEvents()
                eventMs = (perf_counter() - started) * 1000
                state["stage"] = "paint"
                started = perf_counter()
                view.grab()
                grabMs = (perf_counter() - started) * 1000
            rows.append(dict(transition = transition, updateMs = updateMs, eventMs = eventMs, grabMs = grabMs,
                totalMs = updateMs + eventMs + grabMs, phases = state["phases"], paints = len(view.renderSamples)))
            if transition == "start":
                for frame in range(17):
                    Step(view, case, frame)
        assert not view.isPanning
        return dict(case = case, run = run, transitions = rows, devicePixelRatio = view.devicePixelRatioF())


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--case", choices = cases, required = True)
    parser.add_argument("--mode", choices = ("phases", "transitions", "normal", "no-snap", "frozen-rooms", "no-qt-draw", "no-artwork", "no-measurements", "no-edit-cache"), default = "phases")
    parser.add_argument("--run", type = int, default = 0)
    args = parser.parse_args()
    folder.mkdir(exist_ok = True)
    gc.disable()
    try:
        result = (Phases(args.case, args.run) if args.mode == "phases" else Transitions(args.case, args.run)
                  if args.mode == "transitions" else Trial(args.case, args.mode, args.run))
    finally:
        gc.enable()
    (folder / f"{args.case}-{args.mode}-{args.run}.json").write_text(json.dumps(result, indent = 2), encoding = "utf-8")
    print(args.case, args.mode, args.run, result.get("medians", "phases recorded"), flush = True)


if __name__ == "__main__":
    Main()
