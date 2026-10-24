"""Frozen scene/component orchestration, numeric opening policies and bounded caches."""
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))


def CheckWithoutQt():
    from check_footprint_measurement_core import CheckWithoutQt as CheckExisting
    CheckExisting()
    from planner_app.geometry.measurements import (MeasurementOpening, PlanMeasurementComponents,
        BuildOpeningDimensions, BuildMeasurementSpan, OpeningProjection, CoveredMeasurementSpans,
        OpeningOnMeasuredSide)
    rng = random.Random(220658)
    for case in range(800):
        parents = [rng.randrange(30) for i in range(case % 70)]
        groups = [[rng.randrange(30) for i in range(case % 13)] for j in range(5)]
        selected = set(rng.sample(range(30), case % 20))
        expected = [([i for i, parent in enumerate(parents) if parent in set(members)],
                     frozenset(member for member in members if member in selected)) for members in groups]
        assert PlanMeasurementComponents(groups, parents, selected) == expected
    for case in range(1000):
        angle = case * .113
        direction = math.cos(angle), math.sin(angle)
        first = (1e8 if case % 2 else 0, -1e8 if case % 2 else 0)
        second = first[0] + direction[0] * 10000, first[1] + direction[1] * 10000
        midpoint = (first[0] + second[0]) / 2, (first[1] + second[1]) / 2
        records = []
        for i in range(case % 12):
            low, high = i * 700 - 100, i * 700 + 400
            start = first[0] + direction[0] * low, first[1] + direction[1] * low
            end = first[0] + direction[0] * high, first[1] + direction[1] * high
            normal = -direction[1], direction[0]
            fireplace = (*normal, *midpoint, 800, 100) if (case + i) % 7 == 0 else None
            records.append(MeasurementOpening(i, start, end, first, second, (case + i) % 3,
                bool(i % 2), bool(case % 2), bool(i % 3), bool(case % 3), fireplace))
        interruptions = []
        projections, fireplaces = [], []
        for opening in records:
            low, high = OpeningProjection(first, direction, opening.first, opening.second)
            projections.append((opening.key, low, high))
            if opening.fireplace is not None:
                fireplaces.append((low, high, *opening.fireplace))
        for opening in records:
            if opening.mode == 2 and opening.fireplace is None:
                continue
            if opening.mode == 1 and opening.fireplace is None and opening.oneSided:
                if not OpeningOnMeasuredSide(midpoint, first, second, opening.flipped):
                    continue
            low, high = OpeningProjection(first, direction, opening.first, opening.second, opening.pocket, opening.hingeAtSecond)
            start, end = max(0.0, low), min(10000, high)
            if end - start > .0001:
                interruptions.append((start, end))
        owners = ["wall"]
        expected = BuildMeasurementSpan(first, second, direction, owners, interruptions, projections, fireplaces)
        assert BuildOpeningDimensions(first, second, direction, 10000, midpoint, owners, records, []) == expected
    print("PASS: 800 ordered component plans and 1000 numeric opening policies without Qt/site packages")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"], capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import QtCore, QtGui, QtWidgets
    from planner_app.models import (Wall, Pillar, Column, Stair, Counter, Door, Window, SilledWindow,
        CasementWindow, PocketDoor, SlidingDoor, BarnDoor, BifoldDoor, Fireplace, OpenDoorway)
    from planner_app.viewport.widget import DrawingViewport
    from planner_app.catalog import LoadFurnishings
    from planner_app.project_codec import DecodeProject
    from fixtures.qt_measurement_orchestration_reference_20261016 import ReferenceMeasurements

    class ReferenceViewport(DrawingViewport):
        WallDimensions = ReferenceMeasurements.WallDimensions
        BuildWallDimensions = ReferenceMeasurements.BuildWallDimensions

    def Values(dimensions):
        return [(first.x(), first.y(), second.x(), second.y(), tuple(id(owner) for owner in owners))
                for first, second, owners in dimensions]

    app = QtWidgets.QApplication([])
    p = QtCore.QPointF
    views = [DrawingViewport(), ReferenceViewport()]
    definitions = {entry["key"]: entry for entry in LoadFurnishings()}
    cases = []
    for name in ("rectangular_rooms", "angled_rooms", "dense_furnishings"):
        data = json.loads((root / "checks/fixtures/plans" / (name + ".plan")).read_text(encoding = "utf-8-sig"))
        decoded = DecodeProject(data, definitions)
        cases.append((name, decoded[0], decoded[1]))
    kinds = (Door, Window, SilledWindow, CasementWindow, PocketDoor, SlidingDoor, BarnDoor, BifoldDoor, Fireplace, OpenDoorway)
    for case in range(32):
        transform = QtGui.QTransform().translate(1e8 if case % 2 else 0, -1e8 if case % 2 else 0).rotate(case * 7.3)
        walls = [Wall(transform.map(p(i * 2500, 0)), transform.map(p(i * 2500 + 1800, 0)), 240) for i in range(12)]
        walls += [Pillar(transform.map(p(0, 3000)), transform.map(p(0, 3600)), 400),
                  Column(transform.map(p(2500, 3000)), transform.map(p(2500, 3600)), 600),
                  Stair(transform.map(p(0, 0)), transform.map(p(0, 3000)), 700),
                  Counter(transform.map(p(2500, 0)), transform.map(p(2500, 3000)), 600)]
        openings = [kind(walls[i], .2, .6) for i, kind in enumerate(kinds)]
        if case % 4 == 0:
            openings.reverse()
        if case % 7 == 0:
            openings.append(openings[0])
        cases.append((str(case), walls, openings))
    count = 0
    for case, (name, objects, openings) in enumerate(cases):
        walls = [obj for obj in objects if type(obj) in (Wall, Pillar, Column)]
        original = p(walls[0].firstVertex)
        for frame in range(6):
            walls[0].firstVertex = original + p(frame * 7, frame * 11)
            for opening in openings:
                opening.measurementFlipped = bool(frame % 2)
                if isinstance(opening, Fireplace):
                    opening.depth, opening.depthOffset = 800, (frame % 3 - 1) * 150
                if hasattr(opening, "hingeAtSecond"):
                    opening.hingeAtSecond = bool(frame % 2)
                if hasattr(opening, "swingsOutwards"):
                    opening.swingsOutwards = bool(frame % 3)
            results = []
            direct = []
            for view in views:
                view.walls, view.windows = objects, openings
                view.zoom = (.003, .2, 1.5)[frame % 3]
                view.panOffset = p(.37 + frame * .13, .71)
                for key in ("doors", "windows", "stairs", "counters"):
                    view.measurementSettings[key] = (case + frame) % 3
                view.SetSelection([(walls[0], None)] if frame == 2 else [(openings[0], None)] if openings and frame == 3 else [])
                view.hiddenObjects = objects[-1:] if frame == 4 else []
                view.hiddenObjectIds = {id(obj) for obj in view.hiddenObjects}
                path = view.ConnectedWallPath(walls)
                # Both connected-component caches and direct arbitrary-boundary paths.
                result = view.WallDimensions(walls, path, openings, cachedBoundary = True, measureCaps = bool(frame % 2))
                results.append(Values(result))
                assert Values(view.WallDimensions(walls, path, openings, cachedBoundary = True, measureCaps = bool(frame % 2))) == results[-1]
                blocker = QtGui.QPolygonF([p(-500, -500), p(500, -500), p(500, 500), p(-500, 500)])
                direct.append(Values(view.BuildWallDimensions(walls, path, openings, blockers = [blocker], cutters = [blocker], measureCaps = bool(frame % 2))))
                assert view.dimensionSpanCachePoints == sum(size for spans, size in view.dimensionSpanCache.values())
                assert view.dimensionSpanCachePoints <= 32768
                assert len(view.wallDimensionComponentCache) <= max(128, len(view.wallGeometryComponents) * 2)
            assert results[0] == results[1], ("component", name, frame)
            assert direct[0] == direct[1], ("direct", name, frame)
            count += 1
    # A warm disconnected pass collects selection once, rather than once per
    # component. Neither planning nor its records survive as a new scene cache.
    actual = views[0]
    walls = [Wall(p(i * 2500, 0), p(i * 2500 + 1800, 0), 240) for i in range(60)]
    actual.walls, actual.windows = walls, [Door(wall, .2, .4) for wall in walls]
    actual.SetSelection([])
    path = actual.ConnectedWallPath(walls)
    actual.WallDimensions(walls, path, cachedBoundary = True)
    from unittest.mock import patch
    with patch.object(actual, "SelectionEntries", wraps = actual.SelectionEntries) as reads:
        actual.WallDimensions(walls, path, cachedBoundary = True)
        assert reads.call_count == 1, reads.call_count
    for view in views:
        view.close()
    print(f"PASS: {count} frozen saved/mixed scene frames, warm/direct measurements, owner order and cache bounds")


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
