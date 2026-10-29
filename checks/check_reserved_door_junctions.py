"""CPU-only pocket/barn-door placement, collisions and persistence; no application."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from planner_app.models import Wall, Door, BarnDoor, PocketDoor, Pillar
from planner_app.project_codec import DecodeProject, EncodeScene
from planner_app.geometry_recovery import OpeningProblem, PrepareGeometryValidation
from planner_app.viewport.placement import PlacementMixin
from planner_app.viewport.geometry import FootprintGeometry
from planner_app.viewport.scene import SceneEditingMixin
from planner_app.graphics.symbols import WallOpeningPolygons


class GeometryViewport(PlacementMixin, FootprintGeometry):
    CaptureOpeningStates = SceneEditingMixin.CaptureOpeningStates

    def __init__(self, walls):
        super().__init__(.2)
        self.walls = walls
        self.windows, self.furnishings, self.labels = [], [], []
        self.objectGroups, self.hiddenObjects = [], []
        self.connectedEnabled = self.connectedObjectsEnabled = self.snapEnabled = False
        self.selectedWall = self.selectedVertex = None

    def ViewportToWorld(self, point):
        return QtCore.QPointF(point.x(), -point.y()) / self.basePixelsPerMillimeter

    def IsObjectVisible(self, obj):
        return True

    def SnapPosition(self, position, *args, **kwargs):
        self.snapApplied = False
        return position

    def SelectionEntries(self):
        return []


def Main():
    p = QtCore.QPointF
    none = QtCore.Qt.KeyboardModifier.NoModifier
    root = Path(__file__).resolve().parents[1]
    template = json.loads((root / "docs/parity/reference/rendering/wall.plan").read_text(encoding = "utf-8"))
    for angle in (0, 37):
        for reverse in (False, True):
            for kind in (BarnDoor, PocketDoor):
                transform = QtGui.QTransform().rotate(angle)
                parent = Wall(p(-2000, 0), p(), 200)
                continuation = Wall(p(), p(2000, 0), 200)
                branch = Wall(p(), p(0, 2000), 150)
                walls = [parent, continuation, branch]
                for wall in walls:
                    wall.firstVertex, wall.secondVertex = transform.map(wall.firstVertex), transform.map(wall.secondVertex)
                    if reverse:
                        wall.firstVertex, wall.secondVertex = wall.secondVertex, wall.firstVertex
                v = GeometryViewport(walls)
                source = kind(parent, -.4 if reverse else .5, .5 if reverse else 1.4, hingeAtSecond = reverse)
                opening = v.FindWindowPlacement(v.WorldToViewport(transform.map(p(-100, 0))), 1800, parent, kind,
                    exclude = source, modifiers = none)
                assert opening is not None and opening.parentWall is parent, (angle, reverse, kind)
                assert abs(opening.length - 1800) < .01
                assert QtCore.QLineF((opening.firstVertex + opening.secondVertex) / 2, transform.map(p(-100, 0))).length() < .01
                v.windows = [opening]
                assert v.OpeningFits(opening) and v.WallFits(branch)
                assert v.FitWallOpenings() and abs(opening.length - 1800) < .01
                before = SceneEditingMixin.CaptureState(v)
                clone = SceneEditingMixin.CloneOpening(v, opening, parent)
                assert clone.length == opening.length and clone.centerFraction == opening.centerFraction
                opening.length = 1000
                SceneEditingMixin.RestoreOpeningStates(v, before[3])
                assert abs(opening.length - 1800) < .01
                parkedIndex = 0 if reverse else 1
                target = transform.map(p(600, 0))
                v.SetOpeningVertex(opening, parkedIndex, target)
                endpoint = opening.firstVertex if reverse else opening.secondVertex
                assert QtCore.QLineF(endpoint, target).length() < .01 and v.OpeningFits(opening)
                SceneEditingMixin.RestoreOpeningStates(v, before[3])
                v.SetOpeningVertex(opening, parkedIndex, target, fromCenter = True)
                assert abs(opening.length - 1400) < .01 and v.OpeningFits(opening)
                SceneEditingMixin.RestoreOpeningStates(v, before[3])
                data = dict(template, scene = EncodeScene(v))
                data.pop("history", None)
                decoded = DecodeProject(data, {})
                assert abs(decoded[1][0].length - 1800) < .01 and len(decoded[0]) == 3
                assert OpeningProblem(3, data, prepared = PrepareGeometryValidation(data)) is None
                # The branch is allowed only in the reserved half, not the doorway.
                branch.firstVertex, branch.secondVertex = transform.map(p(-500, 0)), transform.map(p(-500, 2000))
                assert not v.OpeningFits(opening)
                branch.firstVertex, branch.secondVertex = transform.map(p(0, -2000)), transform.map(p(0, 2000))
                assert not v.OpeningFits(opening)  # Full crossing in parking space.
                branch.firstVertex = p()
                pillar = Pillar(transform.map(p(400, -150)), transform.map(p(400, 150)), 300)
                v.walls.append(pillar)
                assert not v.OpeningFits(opening)
                v.walls.remove(pillar)
                offset = transform.map(p(30, 0))
                continuation.firstVertex += offset
                continuation.secondVertex += offset
                assert not v.OpeningFits(opening)
                assert not v.OpeningsValid(before = before)
                continuation.firstVertex -= offset
                continuation.secondVertex -= offset
                assert v.OpeningFits(opening)
                normal = Door(parent, -.4 if reverse else .5, .5 if reverse else 1.4)
                normal.centerFraction, normal.length = opening.centerFraction, opening.length
                assert not v.OpeningFits(normal)  # No relaxed bounds for actual full-span openings.
                cuts = WallOpeningPolygons(opening, opening.firstVertex, opening.secondVertex, 1, 0)
                assert len(cuts) == (1 if kind is BarnDoor else 2)
                assert len(v.walls) == 3
    print("PASS: pocket/barn parking across controls/Ts, aperture/crossing/pillar/gap rejection, rotation/reversal, clone/history restore, save/load/recovery; no app/rendering")


if __name__ == "__main__":
    Main()
