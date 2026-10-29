"""Sizing limits, annotation rotation and atomic reference-image replacement."""
import copy
import json
import math
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Railing, Stair, MeasurementGuide, AngleGuide, sizingCountLimit
from planner_app.project_codec import DecodeProject
from check_rotation_pivots import Mouse
from check_wall_selection_rotation import RotatePoint


def Main():
    p = QtCore.QPointF
    none = QtCore.Qt.KeyboardModifier.NoModifier
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.connectedEnabled = v.snapEnabled = False
        v.unitsMode = "Adaptive Metric"
        for cls in (Railing, Stair):
            obj = cls(p(), p(20000, 0))
            obj.autosize = False
            InstallScene(main, [obj])
            v.SetSelection([(obj, None)])
            oldCount = obj.postCount if cls is Railing else obj.stepCount
            main.EditProperty("stepSize", main.propertyFields["stepSize"].minimum())
            assert (obj.postCount if cls is Railing else obj.stepCount) == sizingCountLimit
            path = folder / (cls.__name__ + ".plan")
            assert main.SaveProject(path)
            loaded = DecodeProject(json.loads(path.read_text(encoding = "utf-8")), v.furnishingDefinitions)
            assert (loaded[0][0].postCount if cls is Railing else loaded[0][0].stepCount) == sizingCountLimit
            v.Undo()
            assert (obj.postCount if cls is Railing else obj.stepCount) == oldCount
            v.Redo()
            assert (obj.postCount if cls is Railing else obj.stepCount) == sizingCountLimit
            InstallScene(main, [])  # Do not paint excessive-count fixtures.

        first = Stair(p(-20000, 0), p())
        second = Stair(p(), p(0, 20000))
        first.sceneStairs = second.sceneStairs = [first, second]
        first.autosize = False
        first.SetStepSize(.1)
        assert first.stepCount == sizingCountLimit
        assert first.StepLayout()[2] == 1
        for cls in (Railing, Stair):
            obj = cls(p(), p(1e9, 0))
            obj.SetAutosize(False)
            assert (obj.manualPostCount if cls is Railing else obj.manualStepCount) == sizingCountLimit

        for cls in (MeasurementGuide, AngleGuide):
            for local in (False, True):
                guide = cls(p(-1000, 0), p(1000, 0))
                guide.textOffset = p(0, 400)
                InstallScene(main, [guide])
                v.SetSelection([(guide, None)])
                v.rotationPivot = p(200, 300)
                assert v.MoveSpecial(50, 70, 90, localOrigins = local) is None
                assert QtCore.QLineF(guide.textOffset, p(-400, 0)).length() < 1e-6
                v.Undo()
                assert guide.textOffset == p(0, 400)
                v.Redo()
                assert QtCore.QLineF(guide.textOffset, p(-400, 0)).length() < 1e-6
                assert v.MoveSpecial(50, 70, 0, localOrigins = local) is None
                assert QtCore.QLineF(guide.textOffset, p(-400, 0)).length() < 1e-6

        guides = [MeasurementGuide(p(-1000, 0), p(1000, 0)), AngleGuide(p(-1000, 1000), p(1000, 1000))]
        for guide in guides:
            guide.textOffset = p(0, 400)
        InstallScene(main, guides)
        v.SetSelection([(guide, None) for guide in guides])
        box, handles = v.VisibleFurnishingHandles()[0]
        handle = next(handle for handle in handles if handle[0] == "rotate")
        Mouse(v, QtCore.QEvent.Type.MouseButtonPress, handle[3])
        state = v.furnishingHandleDrag
        pivot = p(state["pivot"])
        start = v.ViewportToWorld(handle[3])
        for degrees, modifiers in ((90, none), (45, none), (90, shift), (90, none)):
            end = v.WorldToViewport(RotatePoint(start, pivot, degrees))
            v.UpdateFurnishingHandleDrag(end, modifiers)
            expected = p(-400 * math.sin(math.radians(degrees)), 400 * math.cos(math.radians(degrees)))
            for guide in guides:
                target = next(obj for obj in state["copies"] if type(obj) is type(guide)) if modifiers == shift else guide
                assert QtCore.QLineF(target.textOffset, expected).length() < 1e-6
                if modifiers == shift:
                    assert guide.textOffset == p(0, 400)
        v.CancelInteraction()
        assert all(guide.textOffset == p(0, 400) for guide in guides)
        InstallScene(main, [])

        ref = main.referenceImage
        for name, height in (("square", 2), ("portrait", 4)):
            image = QtGui.QImage(2, height, QtGui.QImage.Format.Format_ARGB32)
            image.fill(QtCore.Qt.GlobalColor.white)
            assert image.save(str(folder / (name + ".png")))
        assert ref.Load(folder / "square.png")
        ref.sizeLinkButton.setChecked(False)
        ref.fields["width"].setValue(ref.fields["width"].maximum())
        before = ref.Snapshot()
        imageKey = ref.image.cacheKey()
        history = list(v.undoHistory), list(v.redoHistory), copy.deepcopy(ref.historyState)
        with patch.object(main, "ShowAppMessage") as message, patch.object(main, "RememberBrowseFolder") as remember:
            assert not ref.Load(folder / "portrait.png")
            assert message.call_count == 1 and not remember.called
        assert ref.Snapshot() == before and ref.image.cacheKey() == imageKey
        assert (list(v.undoHistory), list(v.redoHistory), ref.historyState) == history
        assert main.SaveProject(folder / "reference.plan")
        DecodeProject(json.loads((folder / "reference.plan").read_text(encoding = "utf-8")), v.furnishingDefinitions)
        ref.fields["width"].setValue(100)
        before = ref.Snapshot()
        assert ref.Load(folder / "portrait.png") and ref.state["height"] == ref.state["width"] * 2
        v.Undo()
        assert ref.Snapshot() == before
        v.Redo()
        assert ref.state["path"].endswith("portrait.png") and ref.image.height() == 4
        ref.Restore(None)
        main.MarkProjectClean()


if __name__ == "__main__":
    Main()
