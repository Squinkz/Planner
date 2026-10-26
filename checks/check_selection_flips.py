"""Shared global reflections, individual local flips and attachment-safe history."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow, InstallScene, CompareExamples
from planner_app.models import (Furnishing, Wall, Counter, Stair, Railing, Pillar, Column, Elevator,
    Arrow, MeasurementGuide, BoundaryLine, DashedLine, SolidLine, AngleGuide, Label, NorthArrow,
    Door, Window, Fireplace, ObjectControlPoints)
from planner_app.project_codec import EncodeScene


def ArtworkPoint(obj):
    center = (obj.firstVertex + obj.secondVertex) / 2
    north = (obj.secondVertex - obj.firstVertex) / obj.length
    east = QtCore.QPointF(north.y(), -north.x())
    return (center + east * (obj.width * .23 * (-1 if obj.flipHorizontal else 1))
            + north * (obj.length * -.17 * (-1 if obj.flipVertical else 1)))


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        p = QtCore.QPointF
        for local in (False, True):
            for horizontal in (True, False):
                first = Furnishing(v.furnishingDefinitions["desk"], p(-1500, -500))
                second = Furnishing(v.furnishingDefinitions["desk"], p(2500, 900))
                first.angle, second.angle = 37, 123
                InstallScene(main, [first, second])
                v.localTransforms = local
                v.SetSelection([(first, None), (second, None)])
                centers = [(obj.firstVertex + obj.secondVertex) / 2 for obj in (first, second)]
                points = [ArtworkPoint(obj) for obj in (first, second)]
                box = v.ObjectFootprint(first)[0].united(v.ObjectFootprint(second)[0])
                before = EncodeScene(v)
                command = "flipHorizontal" if horizontal else "flipVertical"
                main.furnishingFlipFields[command].click()
                assert len(v.undoHistory) == 1
                for index, obj in enumerate((first, second)):
                    origin = centers[index] if local else box.center()
                    transform = QtGui.QTransform().translate(origin.x(), origin.y())
                    angle = (37, 123)[index] if local else 0
                    transform.rotate(angle).scale(-1 if horizontal else 1, 1 if horizontal else -1).rotate(-angle)
                    transform.translate(-origin.x(), -origin.y())
                    assert QtCore.QLineF(ArtworkPoint(obj), transform.map(points[index])).length() < 1e-8
                    if local:
                        assert (obj.firstVertex + obj.secondVertex) / 2 == centers[index]
                        assert abs(obj.angle - angle) < 1e-8
                after = EncodeScene(v)
                v.Undo()
                CompareExamples(EncodeScene(v), before)
                v.Redo()
                CompareExamples(EncodeScene(v), after)
                v.ApplyObjectContextAction([first, second], command)
                CompareExamples(EncodeScene(v), before)
        v.localTransforms = False
        objects = [Wall(p(-3000, -1000), p(-1000, -1000), 200),
                   Wall(p(-1000, -1000), p(-1000, 1000), 200),
                   Counter(p(1000, -1000), p(3000, -1000), 500),
                   Stair(p(1000, 1500), p(3000, 1500), 700),
                   Railing(p(4500, 1000), p(4500, 2500), 80),
                   Pillar(p(0, -4500), p(0, -4000), 300),
                   Column(p(-3000, 4500), p(-3000, 4900), 300),
                   Elevator(p(4000, 4500), p(4000, 5500), 1000),
                   Furnishing(v.furnishingDefinitions["desk"], p(5000, -3000)),
                   Label(p(-5000, -3000), "Readable"), NorthArrow(p(-5000, 4000)),
                   Arrow(p(-4000, 2000), p(-3000, 2500)),
                   AngleGuide(p(-1000, 4000), p(-2000, 3000), middleVertex = p(-2000, 4000))]
        for index, cls in enumerate((MeasurementGuide, BoundaryLine, DashedLine, SolidLine)):
            objects.append(cls(p(-4500, -5500 - index * 300), p(-3000, -5500 - index * 300)))
        objects[9].angle = 23
        for obj in objects:
            if isinstance(obj, MeasurementGuide):
                obj.textOffset = p(75, 125)
        for horizontal in (True, False):
            InstallScene(main, objects)
            v.SetSelection([(obj, None) for obj in objects])
            before = EncodeScene(v)
            bounds = v.ObjectFootprint(objects[0])[0]
            for obj in objects[1:]:
                bounds = bounds.united(v.ObjectFootprint(obj)[0])
            transform = QtGui.QTransform().translate(bounds.center().x(), bounds.center().y())
            transform.scale(-1 if horizontal else 1, 1 if horizontal else -1).translate(-bounds.center().x(), -bounds.center().y())
            original = {id(obj): [p(point) for point in ObjectControlPoints(obj)] for obj in objects}
            offsets = {id(obj): p(obj.textOffset) for obj in objects if isinstance(obj, MeasurementGuide)}
            assert v.FlipObjects(objects, horizontal)
            for obj in objects:
                if type(obj) is Furnishing or isinstance(obj, Label):
                    continue
                for old, point in zip(original[id(obj)], ObjectControlPoints(obj)):
                    assert QtCore.QLineF(point, transform.map(old)).length() < 1e-8, type(obj)
                if isinstance(obj, MeasurementGuide):
                    assert QtCore.QLineF(obj.textOffset, transform.map(offsets[id(obj)]) - transform.map(p())).length() < 1e-8
            assert objects[0].secondVertex == objects[1].firstVertex
            assert objects[9].text == "Readable"
            assert not objects[9].flipHorizontal and not objects[9].flipVertical
            v.Undo()
            CompareExamples(EncodeScene(v), before)
        # Parent reflections carry unselected openings, including facing and wells.
        for horizontal in (True, False):
            rotation = QtGui.QTransform().rotate(37)
            wall = Wall(rotation.map(p(-3000, 0)), rotation.map(p(3000, 0)), 200)
            door, window, fireplace = Door(wall, .1, .23), Window(wall, .7, .83), Fireplace(wall, .4, .55)
            window.windowWell = True
            fireplace.depth, fireplace.depthOffset = 500, 75
            desk = Furnishing(v.furnishingDefinitions["desk"], p(7000, 5000))
            InstallScene(main, [wall, door, window, fireplace, desk])
            v.SetSelection([(wall, None), (desk, None)])
            original = EncodeScene(v)
            if horizontal:
                main.furnishingFlipFields["flipHorizontal"].click()
            else:
                position = v.WorldToViewport((desk.firstVertex + desk.secondVertex) / 2)
                v.ShowObjectContextMenu(position, v.mapToGlobal(position.toPoint()))
                button = next(action.defaultWidget() for action in v.objectContextMenu.actions()
                              if not action.isSeparator() and action.defaultWidget().accessibleName() == "Flip Vertical")
                button.click()
            assert len(v.undoHistory) == 1
            assert all(obj.parentWall is wall for obj in (door, window, fireplace))
            assert all(obj.swingsOutwards for obj in (door, window, fireplace))
            assert fireplace.depthOffset == -75 and not door.hingeAtSecond
            after = EncodeScene(v)
            path = folder / "mirrored.plan"
            assert main.SaveProject(path) and main.OpenProject(path)
            CompareExamples(EncodeScene(v), after)
            v.Undo()
            CompareExamples(EncodeScene(v), original)
        # An unsupported off-wall reflection is atomic and does not detach doors.
        wall = Wall(p(-2000, 0), p(2000, 0))
        door = Door(wall, .2, .4)
        desk = Furnishing(v.furnishingDefinitions["desk"], p(5000, 4000))
        InstallScene(main, [wall, door, desk])
        v.SetSelection([(door, None), (desk, None)])
        before = EncodeScene(v)
        assert not v.FlipObjects([door, desk], False)
        CompareExamples(EncodeScene(v), before)
        assert not v.undoHistory and door.parentWall is wall
    print("PASS: shared/global and individual/local mirrors, mixed geometry, joined endpoints, attachments, readable text and history")


if __name__ == "__main__":
    Main()
