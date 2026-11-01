"""Exact overlap grouping, redundant-probe omission and editor parity."""
from contextlib import contextmanager
import cProfile
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
from PySide6 import QtCore, QtWidgets
from planner_app.models import Wall, Pillar, Column
from planner_app.viewport.geometry import FootprintGeometry, GeometryMixin
from fixtures.wall_boundary_reference_20261101 import ReferenceGeometry
from check_flat_next import GeometrySnapshot
import check_flat_next
import check_local_paint


@contextmanager
def Baseline(enabled):
    if enabled:
        with patch.object(GeometryMixin, "ConnectedWallPath", ReferenceGeometry.ConnectedWallPath):
            yield
    else:
        yield


def CheckOverlaps():
    point = QtCore.QPointF
    comparisons = 0
    randomizer = random.Random(20261101)
    for case in range(6):
        count = 40 if case == 4 else 12
        offset = point(1e8, -1e8) if case == 5 else point()
        walls = []
        for index in range(count):
            start = offset + point(index % 3 * 40, index // 3 * 3000)
            walls.extend((Wall(start, start + point(1800, 0), 200),
                          Wall(start, start + point(0, 1400), 180)))
        if case == 1:
            walls.append(Pillar(point(800, -250), point(800, 250), 250))
        elif case == 2:
            walls.append(Column(point(3500, -250), point(3500, 250), 250))
        workspaces = [FootprintGeometry(.2), FootprintGeometry(.2)]
        if case == 3:
            workspaces[1].geometryCacheBudget.byteLimit = 16000
            workspaces[1].geometryCacheBudget.pointLimit = 500
        for frame in range(32 if case >= 4 else 64):
            if frame < 8:
                walls[-2].secondVertex += point(.7, .3)
            else:
                moving = walls[frame % 24]
                start = offset + point(randomizer.randrange(count) * 3000, 0)
                # Split/merge an overlap group, acquire/drop endpoint joins,
                # and cross the exact junction and pillar-weld tolerances.
                moving.firstVertex = start + point(randomizer.choice((0, .0099999, .0100001, 800)), 0)
                moving.secondVertex = start + point(randomizer.choice((1800, 3000, 4800)), randomizer.choice((0, 0, 500)))
                moving.width = randomizer.choice((180, 200, 400))
                moving.firstMiter = randomizer.choice((.5, 1, 2))
            members = walls if frame % 13 else walls[2:]
            if frame % 11 == 0:
                members = list(reversed(members))
            trace = frame % 7 != 6
            snapshots = []
            for variant, workspace in enumerate(workspaces):
                workspace.zoom = 1 + frame / 100
                workspace.basePixelsPerMillimeter = .15 if frame % 17 == 0 else .2
                with Baseline(variant == 0):
                    result = workspace.ConnectedWallPath(members, traceContours = trace)
                snapshots.append(GeometrySnapshot(workspace, result))
                budget = workspace.geometryCacheBudget
                assert budget.byteCount <= budget.byteLimit and budget.pointCount <= budget.pointLimit
            assert snapshots[0] == snapshots[1], ("overlap", case, frame)
            comparisons += 1
            if case == 0 and frame == 4:
                walls[-2].secondVertex += point(.7, .3)
                counts = []
                for variant, workspace in enumerate(workspaces):
                    profile = cProfile.Profile()
                    with Baseline(variant == 0):
                        profile.runcall(workspace.ConnectedWallPath, walls)
                    counts.append(sum(entry.callcount for entry in profile.getstats()
                                      if isinstance(entry.code, str) and "intersects" in entry.code and "QRectF" in entry.code))
                assert counts[1] < counts[0], ("Connected components were probed again", counts)
                del profile
            if frame == 31:
                for workspace in workspaces:
                    workspace.geometryCacheBudget.Clear()
        references = [weakref.ref(workspace) for workspace in workspaces]
        del workspaces, workspace
        gc.collect()
        assert all(reference() is None for reference in references)
    return comparisons


def Main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    overlaps = CheckOverlaps()
    with patch.object(check_flat_next, "Baseline", Baseline):
        assemblies = check_flat_next.CheckAssemblies()
    with patch.object(check_local_paint, "Baseline", Baseline):
        frames = check_local_paint.CheckProject()
    print(f"PASS: {overlaps} exact overlap and {assemblies} assembly snapshots, redundant rectangle-probe omission, "
          f"budget eviction/lifetime, and {frames} exact frozen synthetic model/validation/pixel frames.")


if __name__ == "__main__":
    Main()
