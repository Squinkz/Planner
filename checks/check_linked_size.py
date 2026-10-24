"""Linked property sizes, mixed selections, undo/cancel and independent handles."""
import math
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from planner_app.models import Wall, Pillar, Column, Counter, Stair, Railing, Elevator, Furnishing, Fireplace, Label
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.units import PropertyUnit


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    main = MainWindow()
    main.show()
    app.processEvents()
    v, point = main.viewport, QtCore.QPointF
    v.unitsMode = "Millimeters"
    assert main.sizeLinkButton.isChecked()
    parent = Wall(point(), point(10000, 0), 200)
    cases = [Wall(point(), point(0, 2000), 200), Pillar(point(), point(0, 1000)),
             Column(point(), point(0, 1000)), Counter(point(), point(0, 2000)),
             Stair(point(), point(0, 3000)), Railing(point(), point(0, 2000)),
             Elevator(point(), point(0, 1200)), Furnishing(v.furnishingDefinitions["desk"]), Fireplace(parent, .3, .5)]
    for obj in cases:
        v.walls, v.windows, v.furnishings, v.labels = [], [], [], []
        if isinstance(obj, Fireplace):
            v.walls, v.windows = [parent], [obj]
        elif isinstance(obj, Furnishing):
            v.furnishings = [obj]
        else:
            v.walls = [obj]
        v.SetSelection([(obj, None)])
        assert main.sizeLinkButton.isChecked() == isinstance(obj, (Furnishing, Pillar, Fireplace)), type(obj)
        main.sizeLinkButton.setChecked(True)
        main.RefreshProperties()
        assert main.sizeLinkButton.isChecked(), "Refreshing must preserve the user's link choice"
        width = obj.depth if isinstance(obj, Fireplace) else obj.width
        length = QtCore.QLineF(obj.firstVertex, obj.secondVertex).length()
        before = v.CaptureState()
        main.propertyFields["width"].setValue(width * 1.5)
        assert math.isclose(obj.depth if isinstance(obj, Fireplace) else obj.width, width * 1.5), type(obj)
        assert math.isclose(QtCore.QLineF(obj.firstVertex, obj.secondVertex).length(), length * 1.5), type(obj)
        v.Undo()
        assert v.CaptureState() == before, type(obj)
        main.BeginPropertyDrag()
        main.propertyFields["length"].setValue(length * 1.25)
        assert math.isclose(obj.depth if isinstance(obj, Fireplace) else obj.width, width * 1.25), type(obj)
        main.FinishPropertyDrag(True)
        assert v.CaptureState() == before, type(obj)

    # A parent-wall depth limit must reject the whole linked edit, not alter the ratio.
    before = v.CaptureState()
    main.propertyFields["length"].setValue(cases[-1].length / 10)
    assert v.CaptureState() == before
    firstFire = Fireplace(parent, .1, .2)
    secondFire = Fireplace(parent, .6, .9)
    secondFire.depth = parent.width
    v.walls, v.windows = [parent], [firstFire, secondFire]
    v.SetSelection([(firstFire, None), (secondFire, None)])
    before = v.CaptureState()
    main.propertyFields["length"].setValue(1500)
    assert v.CaptureState() == before, "An invalid linked target must roll back the entire selection"

    # Each selected object retains its own aspect ratio, with one atomic undo.
    first = Furnishing(v.furnishingDefinitions["desk"])
    second = Furnishing(dict(v.furnishingDefinitions["desk"], width = 800, length = 1600), point(10000, 0))
    v.walls, v.windows, v.furnishings = [], [], [first, second]
    v.SetSelection([(first, None), (second, None)])
    before = v.CaptureState()
    ratios = [obj.length / obj.width for obj in (first, second)]
    main.propertyFields["width"].setValue(600)
    assert all(obj.width == 600 and math.isclose(obj.length / obj.width, ratio)
               for obj, ratio in zip((first, second), ratios))
    v.Undo()
    assert v.CaptureState() == before
    v.SetSelection([(first, None)])
    v.unitsMode = "Inches"
    main.RefreshProperties()
    divisor, unused = PropertyUnit("width", first, v.unitsMode)
    oldWidth, oldLength = first.width, first.length
    main.propertyFields["width"].setValue(oldWidth * 2 / divisor)
    assert math.isclose(first.width / oldWidth, first.length / oldLength)
    main.sizeLinkButton.setChecked(False)
    oldLength = first.length
    main.propertyFields["width"].setValue(first.width * 1.1 / divisor)
    assert first.length == oldLength
    main.RefreshProperties()
    assert not main.sizeLinkButton.isChecked()
    v.SetSelection([(second, None)])
    assert main.sizeLinkButton.isChecked(), "Another object of the same type must use its default"
    v.SetSelection([(first, None)])
    assert main.sizeLinkButton.isChecked(), "Reselecting must not remember the previous choice"
    v.walls = [cases[0]]
    v.SetSelection([(cases[0], None)])
    assert not main.sizeLinkButton.isChecked()
    main.sizeLinkButton.setChecked(True)
    main.RefreshProperties()
    assert main.sizeLinkButton.isChecked()
    v.SetSelection([])
    v.SetSelection([(cases[0], None)])
    assert not main.sizeLinkButton.isChecked(), "Control-point objects must reset to unlinked"
    v.walls = []

    # Labels always resize proportionally, with no link toggle.
    label = Label(point(), "Linked label")
    v.labels, v.furnishings = [label], []
    v.unitsMode = "Millimeters"
    v.SetSelection([(label, None)])
    assert not hasattr(main, "labelSizeLinkButton")
    ratio = label.width / label.length
    main.labelFields["width"].setValue(label.width * 2)
    assert math.isclose(label.width / label.length, ratio)
    before = v.CaptureState()
    main.labelFields["length"].setValue(label.length * 1.5)
    assert math.isclose(label.width / label.length, ratio)
    v.Undo()
    assert v.CaptureState() == before
    main.BeginPropertyDrag()
    main.labelFields["width"].setValue(label.width * 1.5)
    assert math.isclose(label.width / label.length, ratio)
    main.FinishPropertyDrag(True)
    assert v.CaptureState() == before
    v.SetSelection([])
    v.SetSelection([(label, None)])
    assert math.isclose(label.width / label.length, ratio)

    # Reference sizing shares the control but never changes canvas handle rules.
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "reference.png"
        image = QtGui.QImage(80, 40, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtGui.QColor("red"))
        image.save(str(path))
        main.sidebarTabs.setCurrentWidget(main.visibilityPage)
        reference = main.referenceImage
        assert reference.Load(path)
        main.SetViewOption("editReferenceImage")
        assert reference.active
        assert reference.sizeLinkButton.isChecked()
        width, height = reference.state["width"], reference.state["height"]
        reference.fields["width"].setValue(width * 2)
        assert reference.state["width"] == width * 2 and reference.state["height"] == height * 2
        reference.BeginPropertyDrag()
        reference.fields["length"].setValue(height * 3)
        reference.FinishPropertyDrag(True)
        assert reference.state["width"] == width * 2 and reference.state["height"] == height * 2
        reference.sizeLinkButton.setChecked(False)
        reference.fields["width"].setValue(width)
        assert reference.state["height"] == height * 2
        main.sidebarPanel.grab().save(str(root / "diagnostics/linked-size-properties.png"))
        reference.Hide()
        assert reference.sizeLinkButton.isChecked()
        reference.Show()
        assert reference.sizeLinkButton.isChecked()
    main.MarkProjectClean()
    main.close()


if __name__ == "__main__":
    Main()
