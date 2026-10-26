"""Manual measurement annotations: editing, visibility, collisions and persistence."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, MeasurementGuide, Wall, Counter, Stair, Arrow
from planner_app.models import Furnishing, Label
from planner_app.project_codec import DecodeProject
from theme import BuildStyle
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    v.unitsMode = "Meters"
    point = QtCore.QPointF
    main.snapButton.setChecked(False)
    assert not main.measurementGuideButton.icon().isNull()
    assert main.buildObjectLayouts["Annotations"].count() == 9
    mime = QtCore.QMimeData()
    mime.setData("application/x-planner-measurement-guide", b"measurement-guide")
    position = v.WorldToViewport(point())
    enter = QtGui.QDragEnterEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                 QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    app.sendEvent(v, enter)
    move = QtGui.QDragMoveEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                               QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    app.sendEvent(v, move)
    assert enter.isAccepted() and isinstance(v.arrowPreview, MeasurementGuide)
    v.grab()
    drop = QtGui.QDropEvent(position, QtCore.Qt.DropAction.CopyAction, mime,
                           QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    app.sendEvent(v, drop)
    assert drop.isAccepted() and len(v.walls) == 1 and v.arrowPreview is None
    guide = v.walls[0]
    assert guide.width == 0 and guide.objectId is not None
    assert "Dimension guide" in main.selectionLabel.text()
    assert main.arrowFields["length"].isVisible()
    assert not main.arrowFields["width"].isVisible() and not main.arrowFields["solidTip"].isVisible()
    main.EditArrowProperty("length", 2)
    assert QtCore.QLineF(guide.firstVertex, guide.secondVertex).length() == 2000
    v.Undo()
    assert QtCore.QLineF(guide.firstVertex, guide.secondVertex).length() == 1000
    main.SetViewOption("showMeasurements")
    assert v.IsObjectVisible(guide)
    v.SetSelection([])
    # The guide text is still drawn when automatic dimensions are disabled.
    from planner_app.viewport import rendering
    originalFormat = rendering.FormatLength
    lengths = []

    def RecordLength(value, *args, **kwargs):
        lengths.append(value)
        assert kwargs.get("includeUnit") is False, "Canvas dimensions still include unit suffixes"
        return originalFormat(value, *args, **kwargs)

    rendering.FormatLength = RecordLength
    v.grab()
    assert 1000 in lengths
    v.visibility["Measurement guides"] = False
    lengths.clear()
    v.grab()
    assert not lengths and not v.IsObjectVisible(guide)
    v.visibility["Measurement guides"] = True
    rendering.FormatLength = originalFormat
    assert v.HitTest(v.WorldToViewport(point()))[0] is guide
    for obj in (Wall(point(-1000, 0), point(1000, 0)), Counter(point(-1000, 0), point(1000, 0)),
                Stair(point(-1000, 0), point(1000, 0)), Arrow(point(-1000, 0), point(1000, 0)),
                Furnishing({"width": 1000, "length": 1000}, point()), Label(point())):
        assert not v.ObjectsOverlap(guide, obj) and not v.JoinedObjectsOverlap(guide, obj)
    v.SetSelection([(guide, None)])
    before = QtCore.QPointF(guide.secondVertex)
    Drag(v, v.WorldToViewport(guide.secondVertex).toPoint(), v.WorldToViewport(before + point(0, 500)).toPoint())
    assert QtCore.QLineF(guide.secondVertex, before + point(0, 500)).length() < 10
    v.Undo()
    assert guide.secondVertex == before
    otherGuide = MeasurementGuide(point(800, 600), point(1200, 600))
    wall = Wall(point(800, 600), point(800, 1600))
    v.walls.extend([otherGuide, wall])
    v.snapEnabled = True
    snapped = v.SnapStairVertex(point(805, 603), guide.firstVertex, guide, QtCore.Qt.KeyboardModifier.NoModifier)
    assert snapped == otherGuide.firstVertex
    v.SetSelection([(guide, 1)])
    assert all(isinstance(obj, MeasurementGuide) for obj, index, position in v.AttachedVertices(guide))
    v.walls = [guide]
    v.snapEnabled = False
    v.SetSelection([(guide, None)])
    assert v.CopySelection()
    assert v.ReadClipboardSelection()["objects"][0]["type"] == "MeasurementGuide"
    assert v.PasteSelection(v.WorldToViewport(point(0, 1000)))
    assert len(v.walls) == 2 and all(obj.width == 0 for obj in v.walls)
    data = main.BuildProjectData()
    decoded = DecodeProject(data, v.furnishingDefinitions)
    assert all(isinstance(obj, MeasurementGuide) for obj in decoded[0])
    del data["settings"]["visibility"]["Measurement guides"]
    assert DecodeProject(data, v.furnishingDefinitions)[5]["visibility"]["Measurement guides"]
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "Guides.plan"
        assert main.SaveProject(path)
        assert main.NewProject() and main.OpenProject(path)
        assert len(v.walls) == 2 and all(isinstance(obj, MeasurementGuide) for obj in v.walls)
    v.SetSelection([(v.walls[0], None)])
    main.resize(1500, 950)
    main.mainSplitter.setSizes([1000, 500])
    app.processEvents()
    main.buildScrollArea.verticalScrollBar().setValue(main.buildScrollArea.verticalScrollBar().maximum())
    app.processEvents()
    main.grab().save("screenshots/measurement-guides.png")
    main.close()
    restored = MainWindow()
    assert len(restored.viewport.walls) == 2 and all(isinstance(obj, MeasurementGuide) for obj in restored.viewport.walls)
    restored.close()
    app.clipboard().clear()
    app.processEvents()


if __name__ == "__main__":
    Main()
