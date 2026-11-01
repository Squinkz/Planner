"""Synthetic scene parity, bounded wall assemblies and early collision policy."""
from contextlib import ExitStack, contextmanager
import gc
import os
from pathlib import Path
import sys
from unittest.mock import patch
import weakref

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "tools")]
from PySide6 import QtCore, QtWidgets
from fixtures.editor_interactions import PrepareScene, BeginEndpoint, wallCases
from fixtures.flat_next_reference_20261031 import ReferenceGeometry, ReferenceSnapping, ReferencePlacement
from planner_app.viewport.geometry import GeometryMixin
from planner_app.viewport.snapping import SnappingMixin
from planner_app.viewport.placement import PlacementMixin
from fixtures.parity_examples import ExampleWindow
from check_drag_fitting_preparation import Snapshot
from check_native_geometry_budget import Native
from planner_app.models import Wall, Pillar, Column
from planner_app.viewport.geometry import FootprintGeometry


@contextmanager
def Baseline(enabled):
    with ExitStack() as stack:
        if enabled:
            stack.enter_context(patch.object(GeometryMixin, "ConnectedWallPath", ReferenceGeometry.ConnectedWallPath))
            stack.enter_context(patch.object(SnappingMixin, "SnapStairVertex", ReferenceSnapping.SnapStairVertex))
            stack.enter_context(patch.object(PlacementMixin, "PlacementBlockers", ReferencePlacement.PlacementBlockers))
        yield


def GeometrySnapshot(workspace, result):
    return (Native(result), Native(workspace.wallGeometryPath),
        tuple((id(owner), tuple((p.x().hex(), p.y().hex()) for p in polygon))
              for owner, polygon in workspace.wallFillPolygons), workspace.wallFootprintCuts,
        tuple((key, tuple(id(obj) for obj in members), Native(path))
              for key, members, path in workspace.wallGeometryComponents),
        tuple((Native(path), Native(occluders)) for path, occluders in workspace.columnOutlinePaths),
        tuple((key, Native(path)) for key, path in workspace.columnMaterialPaths.items()))


def CheckAssemblies():
    point = QtCore.QPointF
    comparisons = 0
    for case in range(4):
        walls = [Wall(point(index * 400, index % 2 * 100), point((index + 1) * 400, (index + 1) % 2 * 100),
                      160, material = "Brick" if index % 3 else "Concrete") for index in range(20)]
        if case == 1:
            walls += [Pillar(point(500, -200), point(500, 200), 300)]
        elif case == 2:
            walls += [Column(point(800, 400), point(800, 900), 400)]
        workspaces = [FootprintGeometry(.2), FootprintGeometry(.2)]
        if case == 3:
            workspaces[1].geometryCacheBudget.byteLimit = 16000
            workspaces[1].geometryCacheBudget.pointLimit = 500
        for frame in range(24):
            members = walls if frame % 3 != 1 else walls[2:]
            trace = frame < 12
            if frame % 6 == 5:
                walls[-1].secondVertex += point(.7, .3)
                walls[1].firstMiter = 1.2 if frame % 12 == 5 else 1
            snapshots = []
            for variant, workspace in enumerate(workspaces):
                workspace.zoom = 1 + frame / 20
                with Baseline(variant == 0):
                    result = workspace.ConnectedWallPath(members, traceContours = trace)
                snapshots.append(GeometrySnapshot(workspace, result))
                budget = workspace.geometryCacheBudget
                assert budget.byteCount <= budget.byteLimit and budget.pointCount <= budget.pointLimit
                assert len(workspace.__dict__.get("wallAssemblyCache", ())) <= 4
                assert len(workspace.__dict__.get("wallAssemblyCandidates", ())) <= 16
            assert snapshots[0] == snapshots[1], ("assembly", case, frame)
            comparisons += 1
        if case == 0:
            workspace = workspaces[1]
            workspace.ConnectedWallPath(walls)
            workspace.ConnectedWallPath(walls[2:])
            with patch.object(workspace, "BuildWallComponent", side_effect = AssertionError("Rebuilt a cached assembly")), \
                    patch.object(workspace, "TraceWallBoundary", side_effect = AssertionError("Retraced a cached assembly")):
                workspace.ConnectedWallPath(walls)
            assert len(workspace.wallAssemblyCache) > 0
            budget = workspace.geometryCacheBudget
            budget.Clear()
            assert not workspace.wallAssemblyCache and budget.byteCount == budget.pointCount == 0
        references = [weakref.ref(workspace) for workspace in workspaces]
        del workspaces, workspace
        gc.collect()
        assert all(reference() is None for reference in references), "Assembly history retained its workspace"
    workspace = FootprintGeometry(.2)
    walls = [Wall(point(index * 500, 0), point(index * 500, 400), 160) for index in range(20)]
    for frame in range(32):
        walls[-1].secondVertex += point(.7, .3)
        workspace.ConnectedWallPath(walls)
        assert not workspace.wallAssemblyCache, "One-use drag positions were admitted to the assembly cache"
        assert len(workspace.wallAssemblyCandidates) <= 16
    return comparisons


def CheckProject():
    comparisons = 0
    with ExitStack() as stack:
        windows = [stack.enter_context(ExampleWindow())[0] for variant in range(2)]
        views = []
        for variant, main in enumerate(windows):
            with Baseline(variant == 0):
                views.append(PrepareScene(main, "drag", False, 1000, 800))
        modifier = QtCore.Qt.KeyboardModifier
        for wallId, vertex in wallCases:
            for modifiers in (modifier.NoModifier, modifier.ControlModifier, modifier.AltModifier,
                              modifier.ControlModifier | modifier.AltModifier):
                for variant, view in enumerate(views):
                    with Baseline(variant == 0):
                        wall = next(wall for wall in view.walls if wall.objectId == wallId)
                        BeginEndpoint(view, wall, vertex)
                for frame in range(4):
                    images, invalid = [], []
                    for variant, view in enumerate(views):
                        with Baseline(variant == 0):
                            view.UpdateInteraction(view.dragStart + QtCore.QPointF(25 + frame * 7, 17 - frame * 11), modifiers)
                            QtWidgets.QApplication.processEvents()
                            images.append(view.grab().toImage())
                            bad = view.InvalidArchitecturalObjects()
                            invalid.append({obj.objectId for obj in view.walls + view.windows if id(obj) in bad})
                    assert Snapshot(views[0]) == Snapshot(views[1]), ("drag state", wallId, modifiers, frame)
                    assert invalid[0] == invalid[1], ("drag validation", wallId, modifiers, frame)
                    assert images[0] == images[1], ("drag pixels", wallId, modifiers, frame)
                    comparisons += 1
        for mask in range(8):
            for variant, view in enumerate(views):
                with Baseline(variant == 0):
                    view.CancelInteraction()
                    for index, name in enumerate(("walls", "architectural", "furnishings")):
                        view.collisionSettings[name] = bool(mask & (1 << index))
                    BeginEndpoint(view, next(wall for wall in view.walls if wall.objectId == wallCases[0][0]), 1)
            for frame in range(3):
                images, invalid = [], []
                for variant, view in enumerate(views):
                    with Baseline(variant == 0):
                        view.UpdateInteraction(view.dragStart + QtCore.QPointF(30 + frame * 4, -20 + frame * 7), modifier.NoModifier)
                        images.append(view.grab().toImage())
                        bad = view.InvalidArchitecturalObjects()
                        invalid.append({obj.objectId for obj in view.walls + view.windows if id(obj) in bad})
                assert Snapshot(views[0]) == Snapshot(views[1]), ("policy state", mask, frame)
                assert invalid[0] == invalid[1] and images[0] == images[1], ("policy paint", mask, frame)
                comparisons += 1
        for view in views:
            view.CancelInteraction()
            view.ClearGeometryCaches()
            assert not view.__dict__.get("wallAssemblyCache")
    return comparisons


def Main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    assemblies = CheckAssemblies()
    frames = CheckProject()
    print(f"PASS: {assemblies} exact native assembly comparisons with eviction, columns, pillars, miter changes, zoom "
          f"and weak lifetime; {frames} exact synthetic drag frames/state/validation with modifier and collision policies.")


if __name__ == "__main__":
    Main()
