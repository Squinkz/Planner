"""Exact accounting, collision workspace sharing and snap/render parity."""
from contextlib import ExitStack, contextmanager
import gc
import os
from pathlib import Path
import random
import sys
from unittest.mock import patch
import weakref

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "tools")]
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.viewport import geometry_cache
from planner_app.viewport import geometry
from planner_app.viewport.geometry import GeometryMixin
from planner_app.viewport.widget import DrawingViewport
from planner_app.models import Wall, Pillar, Column, Counter, Stair, Railing
from fixtures.snap_cache_reference_20261101 import GeometryCacheCost as OriginalCost
from fixtures.snap_geometry_reference_20261101 import ReferenceGeometry
from check_native_geometry_budget import Native
import check_local_paint


@contextmanager
def Baseline(enabled, mode = "both"):
    with ExitStack() as stack:
        if enabled:
            if mode in ("both", "accounting"):
                stack.enter_context(patch.object(geometry_cache, "GeometryCacheCost", OriginalCost))
            if mode in ("both", "preparation"):
                stack.enter_context(patch.object(GeometryMixin, "CollisionCategoryGeometry", ReferenceGeometry.CollisionCategoryGeometry))
        yield


def CheckAccounting():
    class CustomFloat(float):
        def __sizeof__(self):
            return 193
    class CustomTuple(tuple):
        pass
    class CustomDict(dict):
        pass
    class CustomPoint(QtCore.QPointF):
        pass
    randomizer = random.Random(20261101)
    shared = [(float(index), float(index + 1)) for index in range(60)]
    cyclic = [shared, shared]
    cyclic.append(cyclic)
    path = QtGui.QPainterPath()
    path.addRect(0, 0, 10, 20)
    polygon = QtGui.QPolygonF([QtCore.QPointF(index, index % 3) for index in range(11)])
    pool = [None, True, False, 0, -1, 2 ** 200, -(2 ** 500), 1.5, float("inf"), float("nan"),
        3j, "label", b"data", bytearray(b"mutable"), CustomFloat(2), CustomTuple(shared),
        CustomDict(value = cyclic), CustomPoint(2, 3), path, polygon, cyclic, set((1, 2)), frozenset((1, 2))]
    comparisons = 0
    for frame in range(150):
        value = [randomizer.choice(pool) for index in range(20)]
        key = geometry_cache.GeometryCacheKey((frame, tuple(shared), tuple(value[:0])))
        for excluded in ((), (id(shared),), (id(value), id(key)), (id(path), id(polygon), id(None))):
            assert geometry_cache.GeometryCacheCost(key, value, excluded) == OriginalCost(key, value, excluded)
            comparisons += 1
        path.lineTo(frame, frame % 7)
        polygon.append(QtCore.QPointF(frame, frame))
    budgets = [geometry_cache.NativeGeometryBudget(byteLimit = 24000, pointLimit = 400) for index in range(2)]
    caches = [[geometry_cache.NativeGeometryCache(budget) for index in range(2)] for budget in budgets]
    for frame in range(80):
        value = (polygon, path, tuple(shared[:frame % 30]))
        for variant in range(2):
            with Baseline(variant == 0, "accounting"):
                target = caches[variant][frame % 2]
                target.Store((frame,), value, shared = (shared,) if frame % 3 == 0 else ())
                target.get((frame - 2,))
                if frame % 7 == 0:
                    caches[variant][1].clear()
        assert (budgets[0].byteCount, budgets[0].pointCount) == (budgets[1].byteCount, budgets[1].pointCount)
        assert [list(cache) for cache in caches[0]] == [list(cache) for cache in caches[1]]
        for budget in budgets:
            assert budget.byteCount <= budget.byteLimit and budget.pointCount <= budget.pointLimit
    for budget in budgets:
        budget.Clear()
        assert not budget.entries and not budget.shared and budget.byteCount == budget.pointCount == 0
    return comparisons


def CheckSharing():
    point = QtCore.QPointF
    comparisons = 0
    for case in range(5):
        views = [DrawingViewport(furnishingDefinitions = {}) for index in range(2)]
        offset = point(1e8, -1e8) if case == 3 else point()
        walls = [Wall(offset + point(index * 1500, index % 2 * 300),
                      offset + point((index + 1) * 1500, (index + 1) % 2 * 300), 150 + index % 3 * 20) for index in range(8)]
        walls += [Pillar(offset + point(1600, 100), offset + point(1600, 700), 400),
                  Column(offset + point(2400, -200), offset + point(2400, 500), 500)]
        for kind in (Counter, Stair, Railing):
            walls += [kind(offset + point(0, 3000), offset + point(2000, 3000), 200),
                      kind(offset + point(2000, 3000), offset + point(2000, 4500), 200)]
        for view in views:
            view.walls = walls
            if case == 1:
                view.geometryCacheBudget.byteLimit = 16000
                view.geometryCacheBudget.pointLimit = 400
            elif case == 2:
                view.geometryCacheBudget.byteLimit = 0
        for frame in range(14):
            walls[0].secondVertex += point(.2, -.1)
            if frame % 3 == 0:
                walls[1].firstMiter = .5 + frame / 10
                walls[2].width += 7
            if frame == 6:
                for view in views:
                    view.ClearGeometryCaches()
            members = walls if frame % 4 else list(reversed(walls))
            for view in views:
                view.walls = members
                view.ConnectedWallPath([wall for wall in members if type(wall) in (Wall, Pillar, Column)])
                view.collisionPassCache = {}
            candidates = [walls[0], Wall(offset, walls[0].secondVertex + point(1, 2), 200)]
            candidates += [kind(offset + point(0, 3000), offset + point(2000, 3000.0099999), 200) for kind in (Counter, Stair, Railing)]
            for candidate in candidates:
                for excluded in (frozenset(), frozenset((id(walls[1]),))):
                    results = []
                    for variant, view in enumerate(views):
                        with Baseline(variant == 0):
                            result = view.CollisionCategoryGeometry(candidate, excluded)
                            results.append((result[0], tuple((identity, Native(path)) for identity, path in result[1].items()), result[2]))
                        if variant == 1:
                            workspace = view.collisionWorkspaces.get(type(candidate))
                            if workspace is not None:
                                for name in ("wallBodyCache", "wallJunctionCache", "wallSectorCache", "wallOwnershipCache"):
                                    assert (getattr(workspace, name) is getattr(view, name)) == (type(candidate) in (Wall, Pillar, Column))
                        budget = view.geometryCacheBudget
                        assert budget.byteCount <= budget.byteLimit and budget.pointCount <= budget.pointLimit
                    assert results[0] == results[1], (case, frame, type(candidate), excluded)
                    comparisons += 1
            for view in views:
                view.collisionPassCache = None
        references = [weakref.ref(workspace) for view in views for workspace in view.collisionWorkspaces.values()]
        workspace = None
        for view in views:
            view.ClearGeometryCaches()
            assert not view.geometryCacheBudget.entries
            view.close()
            view.deleteLater()
        gc.collect()
        assert all(reference() is None for reference in references), "Clearing retained collision workspaces"
    return comparisons


def CheckSharedReuse():
    point = QtCore.QPointF
    walls = [Wall(point(index * 1200, index % 2 * 200), point((index + 1) * 1200, (index + 1) % 2 * 200), 180)
             for index in range(8)]
    candidate = Wall(point(20000, 5000), point(22000, 5000), 180)
    counts, results = [], []
    for variant in range(2):
        view = DrawingViewport(furnishingDefinitions = {})
        view.walls = walls
        before = Native(view.ConnectedWallPath(walls))
        with Baseline(variant == 0):
            with patch.object(geometry, "SubtractConvexPolygons", wraps = geometry.SubtractConvexPolygons) as subtract:
                result = view.CollisionCategoryGeometry(candidate, frozenset())
            counts.append(subtract.call_count)
            results.append(tuple((identity, Native(path)) for identity, path in result[1].items()))
        assert Native(view.ConnectedWallPath(walls)) == before, "Candidate preparation changed the live wall outline"
        view.ClearGeometryCaches()
        view.close()
        view.deleteLater()
    assert results[0] == results[1]
    assert counts[1] < counts[0], ("Unchanged clipping preparation was repeated", counts)
    return counts


def Main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    accounting = CheckAccounting()
    sharing = CheckSharing()
    counts = CheckSharedReuse()
    with patch.object(check_local_paint, "Baseline", Baseline):
        frames = check_local_paint.CheckProject()
    print(f"PASS: {accounting} exact accounting comparisons, identical budget/eviction sequences, {sharing} shared/private "
          f"collision snapshots, clipping operations {counts}, workspace cleanup, {frames} exact model/validation/pixel frames.")


if __name__ == "__main__":
    Main()
