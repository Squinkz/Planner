"""Two-point constructions share split/dissolve, retaining class settings and history."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Furnishing, Counter, Stair, Railing, Arrow, MeasurementGuide, BoundaryLine, DashedLine, SolidLine
from check_history import Drag


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        p = QtCore.QPointF
        for cls in (Counter, Stair, Railing, Arrow, MeasurementGuide, BoundaryLine, DashedLine, SolidLine):
            obj = cls(p(-2000, 0), p(2000, 0))
            obj.firstMiter, obj.secondMiter = .2, .4
            if isinstance(obj, DashedLine):
                obj.weightClass = "Furnishings"
            if isinstance(obj, Arrow):
                obj.tipSize, obj.intensity = 123, .6
            if isinstance(obj, Stair):
                obj.directionReversed, obj.autosize, obj.manualStepCount = True, False, 8
                obj.stepSizeBounds = (200, 400)
            if isinstance(obj, Railing):
                obj.autosize, obj.manualPostCount = False, 7
            InstallScene(main, [obj])
            v.SetSelection([(obj, None)])
            v.ShowObjectContextMenu(v.WorldToViewport(p()), v.mapToGlobal(v.WorldToViewport(p()).toPoint()))
            names = [action.defaultWidget().accessibleName() for action in v.objectContextMenu.actions() if not action.isSeparator()]
            assert "Subdivide" in names, (cls, names)
            v.objectContextMenu.hide()
            assert v.SubdivideWalls([obj])
            first, second = v.walls
            assert v.SelectionEntries() == [(first, 1), (second, 0)]
            assert type(first) is cls and type(second) is cls
            assert first.firstVertex == obj.firstVertex and second.secondVertex == obj.secondVertex
            assert first.secondVertex == second.firstVertex == p()
            assert (first.firstMiter, first.secondMiter, second.firstMiter, second.secondMiter) == (.2, 0, 0, .4)
            for field in ("weightClass", "tipSize", "intensity", "autosize", "manualStepCount", "manualPostCount", "directionReversed", "spacingBounds", "stepSizeBounds"):
                if hasattr(obj, field):
                    assert getattr(first, field) == getattr(second, field) == getattr(obj, field), (cls, field)
            v.snapEnabled = False
            v.connectedVerticesEnabled = v.connectedObjectsEnabled = False
            start = v.WorldToViewport(p()).toPoint()
            Drag(v, start, start + QtCore.QPoint(0, -30))
            assert first.secondVertex == second.firstVertex and first.secondVertex != p(), cls
            assert first.firstVertex == obj.firstVertex and second.secondVertex == obj.secondVertex, cls
            v.Undo()
            assert first.secondVertex == second.firstVertex == p()
            v.Undo()
            assert len(v.walls) == 1 and v.walls[0] is obj
            v.Redo()
            assert len(v.walls) == 2
            assert v.SelectionEntries() == [(first, 1), (second, 0)]
            v.ShowObjectContextMenu(v.WorldToViewport(p()), v.mapToGlobal(v.WorldToViewport(p()).toPoint()))
            names = [action.defaultWidget().accessibleName() for action in v.objectContextMenu.actions() if not action.isSeparator()]
            assert "Dissolve Control Point" in names, (cls, names)
            v.objectContextMenu.hide()
            assert v.DissolveWalls(p(), cls)
            merged = v.walls[0]
            assert len(v.walls) == 1 and type(merged) is cls
            assert merged.firstVertex == obj.firstVertex and merged.secondVertex == obj.secondVertex
            assert (merged.firstMiter, merged.secondMiter) == (.2, .4)
            for field in ("weightClass", "tipSize", "intensity", "autosize", "manualStepCount", "manualPostCount", "directionReversed", "spacingBounds", "stepSizeBounds"):
                if hasattr(obj, field):
                    assert getattr(merged, field) == getattr(obj, field), (cls, field)
            v.Undo()
            assert len(v.walls) == 2
            v.Redo()
            assert len(v.walls) == 1
            # Coincident endpoints from another class are never dissolved together.
            other = BoundaryLine(p(), p(0, 2000)) if cls is not BoundaryLine else Arrow(p(), p(0, 2000))
            InstallScene(main, [cls(p(-2000, 0), p()), other])
            assert not v.DissolveWalls(p(), cls)
        # Merging valid construction segments must not create a new collision.
        for cls in (Counter, Stair, Railing):
            first = cls(p(-2000, 0), p(0, 2000), 400)
            second = cls(p(0, 2000), p(2000, 0), 400)
            blocker = Furnishing(v.furnishingDefinitions["desk"], p()) if cls is Railing else Wall(p(0, -1000), p(0, 500), 120)
            InstallScene(main, [first, second, blocker])
            fits = v.CounterFits if cls is Counter else v.StairFits if cls is Stair else v.WallFits
            assert fits(first) and fits(second), cls
            before, history = v.CaptureState(), len(v.undoHistory)
            assert not v.DissolveWalls(p(0, 2000), cls), cls
            assert v.CaptureState() == before and len(v.undoHistory) == history
            # Removing the blocker permits the same operation and its undo/redo.
            InstallScene(main, [first, second])
            assert v.DissolveWalls(p(0, 2000), cls), cls
            assert len(v.walls) == 1 and fits(v.walls[0])
            v.Undo()
            assert v.walls == [first, second]
            v.Redo()
            assert len(v.walls) == 1
    print("PASS: linear subdivision/dissolution menus, style preservation, class separation and undo/redo")


if __name__ == "__main__":
    Main()
