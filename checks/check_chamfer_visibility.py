"""Chamfer appears only when every selected vertex is a usable two-wall corner."""
import os
from pathlib import Path
import sys

workspace = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(workspace / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore
from planner_app.models import Wall, Counter, Railing, Stair, Pillar
from fixtures.parity_examples import ExampleWindow, InstallScene


def Main():
    with ExampleWindow() as (main, folder):
        v, point = main.viewport, QtCore.QPointF
        field = main.propertyFields["miter"]
        form = main.vertexProperties.layout()
        cases = [
            ("solo", [Wall(point(), point(1000, 0), firstMiter = .4)], False),
            ("corner", [Wall(point(), point(1000, 0)), Wall(point(), point(0, 1000))], True),
            ("unequal", [Wall(point(), point(1000, 0), 120), Wall(point(), point(0, 1000), 240)], True),
            ("straight", [Wall(point(), point(1000, 0)), Wall(point(), point(-1000, 0))], False),
            ("duplicate", [Wall(point(), point(1000, 0)), Wall(point(), point(2000, 0))], False),
            ("three", [Wall(point(), point(1000, 0)), Wall(point(), point(0, 1000)), Wall(point(), point(-1000, 0))], False),
            ("four", [Wall(point(), point(1000, 0)), Wall(point(), point(0, 1000)), Wall(point(), point(-1000, 0)), Wall(point(), point(0, -1000))], False),
            ("three-with-duplicate", [Wall(point(), point(1000, 0)), Wall(point(), point(0, 1000)), Wall(point(), point(2000, 0))], False),
            ("counter", [Counter(point(), point(1000, 0)), Counter(point(), point(0, 1000))], True),
            ("railing", [Railing(point(), point(1000, 0)), Railing(point(), point(0, 1000))], False),
            ("stair", [Stair(point(), point(1000, 0)), Stair(point(), point(0, 1000))], True),
            ("solo-stair", [Stair(point(), point(1000, 0))], False),
            ("straight-stairs", [Stair(point(), point(1000, 0)), Stair(point(), point(-1000, 0))], False),
            ("three-stairs", [Stair(point(), point(1000, 0)), Stair(point(), point(0, 1000)), Stair(point(), point(-1000, 0))], False),
            ("unequal-stairs", [Stair(point(), point(4000, 0), 600), Stair(point(), point(0, 4000), 1000)], True),
            ("pillar", [Pillar(point(), point(1000, 0)), Wall(point(), point(0, 1000))], False),
            ("local-transition", [Wall(point(), point(1000, 0), 80), Wall(point(), point(-1000, 1), 600)], False),
            ("weld-tolerance", [Wall(point(), point(1000, 0)), Wall(point(.005, 0), point(.005, 1000))], True),
        ]
        for name, objects, expected in cases:
            InstallScene(main, objects)
            before = [(obj.firstMiter, obj.secondMiter) for obj in objects]
            v.SetSelection([(objects[0], 0)])
            main.RefreshProperties()
            assert form.isRowVisible(field) is expected, name
            assert main.vertexProperties.isVisible(), name
            assert [(obj.firstMiter, obj.secondMiter) for obj in objects] == before, (name, "visibility changed stored amounts")
            # A whole-object selection never exposes the vertex-only parameter.
            v.SetSelection([(objects[0], None)])
            main.RefreshProperties()
            assert not field.isVisibleTo(main.propertiesPanel), name
        # Topology changes hide/show immediately; hidden amounts survive.
        first = Wall(point(), point(1000, 0), firstMiter = .4)
        second = Wall(point(), point(0, 1000), firstMiter = .4)
        third = Wall(point(), point(-1000, 0), firstMiter = .4)
        InstallScene(main, [first, second])
        v.SetSelection([(first, 0), (second, 0)])
        main.RefreshProperties()
        assert form.isRowVisible(field)
        v.walls.append(third)
        main.RefreshProperties()
        assert not form.isRowVisible(field) and first.firstMiter == .4
        v.walls.remove(third)
        main.RefreshProperties()
        assert form.isRowVisible(field) and field.value() == .4
        # An eligible corner combined with an ineligible endpoint hides the row.
        v.SetSelection([(first, 0), (second, 1)])
        main.RefreshProperties()
        assert not form.isRowVisible(field)

        # Stair junction edits propagate across either endpoint, stay isolated
        # from other object classes, affect geometry, and form one undo edit.
        first = Stair(point(-5000, 0), point(), 1000)
        second = Stair(point(), point(0, 5000), 1000)
        wall = Wall(point(), point(2000, 2000), firstMiter = .2)
        counter = Counter(point(), point(2000, -2000), firstMiter = .3)
        InstallScene(main, [first, second, wall, counter])
        v.collisionSettings = {name: False for name in v.collisionSettings}
        v.SetSelection([(first, 1)])
        main.RefreshProperties()
        assert form.isRowVisible(field)
        sample = v.WorldToViewport(point(450, -450))
        assert v.ConnectedStairPath([first, second]).contains(sample)
        main.EditProperty("miter", .5)
        assert first.secondMiter == second.firstMiter == .5
        assert wall.firstMiter == .2 and counter.firstMiter == .3
        assert not v.ConnectedStairPath([first, second]).contains(sample)
        assert len(v.undoHistory) == 1
        v.grab()
        v.Undo()
        assert first.secondMiter == second.firstMiter == 0
        assert v.ConnectedStairPath([first, second]).contains(sample)
        v.Redo()
        assert first.secondMiter == second.firstMiter == .5
    print("PASS: chamfer visibility, stair propagation/geometry/history, topology refresh and preserved internal amounts")


if __name__ == "__main__":
    Main()
