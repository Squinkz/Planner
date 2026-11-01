"""Native path/owner parity under eviction, aggregate limits and scene cleanup."""
import gc
import os
from pathlib import Path
import sys
import weakref

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from fixtures.parity_examples import ExampleWindow
from fixtures.native_geometry_budget_reference_20261031 import ReferenceViewport
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.models import Wall, Pillar, Column, Counter, Stair, Railing
from planner_app.project_codec import DecodeProject
from planner_app.viewport.geometry import FootprintGeometry
from planner_app.viewport.geometry_cache import NativeGeometryBudget, NativeGeometryCache, GeometryCacheCost
from planner_app.viewport.widget import DrawingViewport
from check_connections_opening_jambs import SceneImage


def Native(path):
    return path.fillRule(), tuple((element.type, element.x.hex(), element.y.hex()) for index in range(path.elementCount())
                                for element in (path.elementAt(index),))


def Main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    point = QtCore.QPointF
    path = QtGui.QPainterPath()
    for index in range(300):
        path.lineTo(point(index, index % 7))
    size, points = GeometryCacheCost(("fixture", 1), path)
    budget = NativeGeometryBudget(byteLimit = size * 2 + 1000, pointLimit = points * 2)
    first, second = NativeGeometryCache(budget), NativeGeometryCache(budget)
    first[1], second[2] = path, QtGui.QPainterPath(path)
    first[1] = first.get(1)
    second[3] = QtGui.QPainterPath(path)
    assert 1 in first and 2 not in second and 3 in second, "Aggregate LRU did not honor reuse across caches"
    assert budget.byteCount <= budget.byteLimit and budget.pointCount <= budget.pointLimit
    second.pop(3)
    assert budget.pointCount == points
    first.clear()
    assert budget.byteCount == budget.pointCount == 0 and not budget.entries
    budget.pointLimit = 1
    first["oversized"] = path
    assert not first and not budget.entries, "Oversized history should bypass caching"
    budget.pointLimit = points * 2
    second["temporary"] = path
    del second
    gc.collect()
    assert budget.byteCount == budget.pointCount == 0, "Destroyed cache left accounting/keys behind"

    class Owner:
        pass
    def StoreOwner():
        owner = Owner()
        first["owner"] = (path, owner)
        return weakref.ref(owner)
    retained = StoreOwner()
    assert retained() is not None
    budget.Clear()
    assert retained() is None, "Clearing a history retained its owner"
    # Dimension keys share complete blocker/cutter data across components.
    # Charging each copy would cause needless eviction and repeated rescanning.
    shared = tuple(float(index) for index in range(1024))
    sharedBudget = NativeGeometryBudget(byteLimit = 65000, pointLimit = 1000)
    sharedCache = NativeGeometryCache(sharedBudget)
    sharedCache.Store((1, shared), path, shared = (shared,))
    sharedCache.Store((2, shared), QtGui.QPainterPath(path), shared = (shared,))
    assert len(sharedCache) == 2 and len(sharedBudget.shared) == 1
    sharedCache.pop((1, shared))
    assert len(sharedBudget.shared) == 1
    sharedCache.clear()
    assert sharedBudget.byteCount == sharedBudget.pointCount == 0 and not sharedBudget.shared

    view, reference = DrawingViewport(furnishingDefinitions = {}), ReferenceViewport(furnishingDefinitions = {})
    for viewport in (view, reference):
        viewport.resize(900, 650)
        viewport.showMeasurements = viewport.showTips = False
    view.geometryCacheBudget.byteLimit, view.geometryCacheBudget.pointLimit = 32768, 1024
    reference.geometryCacheBudget.byteLimit = reference.geometryCacheBudget.pointLimit = 1 << 60
    matrices = 0
    for case in range(4):
        walls = [Wall(point(index * 400, index % 2 * 100), point((index + 1) * 400, (index + 1) % 2 * 100),
                      160, material = "Brick" if index % 3 else "Concrete") for index in range(16)]
        if case == 1:
            walls += [Pillar(point(500, -200), point(500, 200), 300)]
        elif case == 2:
            walls += [Column(point(index * 600, 400), point(index * 600, 900), 400) for index in range(33)]
        elif case == 3:
            walls = [Wall(point(index * 800, 0), point(index * 800, 500), 180) for index in range(48)]
        for viewport in (view, reference):
            viewport.walls = walls
        originalEnd = QtCore.QPointF(walls[-1].secondVertex)
        for frame in range(6):
            walls[-1].secondVertex += point(.7, .3)
            for viewport in (view, reference):
                viewport.ConnectedWallPath(viewport.walls)
            assert Native(view.wallGeometryPath) == Native(reference.wallGeometryPath), (case, frame, "native path")
            assert [(id(owner), tuple((p.x().hex(), p.y().hex()) for p in polygon)) for owner, polygon in view.wallFillPolygons] == [
                (id(owner), tuple((p.x().hex(), p.y().hex()) for p in polygon)) for owner, polygon in reference.wallFillPolygons], (case, frame, "owned polygons")
            assert view.geometryCacheBudget.byteCount <= view.geometryCacheBudget.byteLimit
            assert view.geometryCacheBudget.pointCount <= view.geometryCacheBudget.pointLimit
            matrices += 1
        for svg in (False, True):
            assert SceneImage(view, svg) == SceneImage(reference, svg), (case, svg, "raster/SVG")
        before = Native(view.wallGeometryPath)
        view.ClearGeometryCaches()
        view.ConnectedWallPath(view.walls)
        assert Native(view.wallGeometryPath) == before, (case, "rebuild after clearing")
        walls[-1].secondVertex = originalEnd
        for viewport in (view, reference):
            viewport.ConnectedWallPath(viewport.walls)
        assert Native(view.wallGeometryPath) == Native(reference.wallGeometryPath), (case, "return to evicted history")
        matrices += 1
    for kind, method in ((Counter, "ConnectedCounterPath"), (Stair, "ConnectedStairPath"), (Railing, "ConnectedRailingPath")):
        objects = [kind(point(0, 0), point(1200, 0), 300), kind(point(1200, 0), point(1200, 1200), 300)]
        for viewport in (view, reference):
            viewport.walls = objects
        for frame in range(2):
            objects[-1].secondVertex += point(.7, .3)
            paths = [getattr(viewport, method)(viewport.walls) for viewport in (view, reference)]
            if kind is not Stair:
                paths = [result[0] for result in paths]
            assert Native(paths[0]) == Native(paths[1]), (kind, frame, "workspace path")
            matrices += 1
        for svg in (False, True):
            assert SceneImage(view, svg) == SceneImage(reference, svg), (kind, svg, "workspace raster/SVG")
    workspace = FootprintGeometry(.1, view)
    assert workspace.geometryCacheBudget is view.geometryCacheBudget
    child = DrawingViewport(view, furnishingDefinitions = {})
    assert child.geometryCacheBudget is view.geometryCacheBudget
    child.deleteLater()
    for viewport in (view, reference):
        viewport.close()
        viewport.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.walls = [Wall(point(0, 0), point(2000, 0), 200)]
        v.ConnectedWallPath(v.walls)
        v.columnWallWorkspace = FootprintGeometry(.1, v)
        v.columnWallWorkspace.ConnectedWallPath(v.walls)
        v.preparedCounterMembers = list(v.walls)
        v.FindWindowPlacement(v.WorldToViewport(point(1000, 0)), modifiers = QtCore.Qt.KeyboardModifier.NoModifier)
        assert v.openingFootprintWorkspace.geometryCacheBudget is v.geometryCacheBudget
        assert v.openingFootprints
        assert v.geometryCacheBudget.entries
        decoded = DecodeProject(main.defaultProjectData, v.furnishingDefinitions)
        main.ApplyProject(decoded, None)
        assert not v.geometryCacheBudget.entries and v.geometryCacheBudget.byteCount == 0
        assert "columnWallWorkspace" not in v.__dict__ and not v.wallFillPolygons
        assert all(name not in v.__dict__ for name in ("openingFootprintWorkspace", "openingFootprintKey", "openingFootprints",
                                                      "openingPlacementPolygons", "preparedWallMembers", "preparedWallValueKey", "preparedCounterMembers"))
    print(f"PASS: {matrices} frozen native geometry matrices, exact PNG/SVG, aggregate limits/LRU, oversized bypass, weak ownership and project cleanup.")


if __name__ == "__main__":
    Main()
