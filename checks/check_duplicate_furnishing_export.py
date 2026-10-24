"""Coincident furnishing warnings are advisory and excluded from every export path."""
import copy
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from planner import MainWindow, Wall
from planner_app.models import Furnishing
from planner_app.graphics.palette import themeColors
from planner_app.graphics.furnishings import CompoundFurnishingSvg, FurnishingRenderer
from planner_app.export_plan import RenderPlan
from check_pan_dpi import CompareDirect


def ImageBytes(image):
    return bytes(image.convertToFormat(QtGui.QImage.Format.Format_ARGB32).constBits())


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.resize(1400, 900)
    main.show()
    app.processEvents()
    v = main.viewport
    point = QtCore.QPointF
    v.walls, v.windows, v.labels, v.objectGroups, v.hiddenObjects = [], [], [], [], []
    v.showMeasurements = v.showGrid = v.showTips = False
    first = Furnishing(v.furnishingDefinitions["desk"], point())
    second = Furnishing(first.definition, point())
    third = Furnishing(first.definition, point())
    v.furnishings = [first, second, third]
    v.EnsureObjectIds()
    assert v.DuplicateFurnishings() == [second, third]
    assert all(v.FurnishingFits(obj) for obj in v.furnishings), 'Coincidence must remain a nonblocking advisory'
    v.SetSelection([(second, None)])
    assert v.CanCopySelection(), 'Duplicate warnings are not missing-asset errors'
    v.SetSelection([])
    v.furnishings = [third, second, first]
    assert v.DuplicateFurnishings() == [second, first]
    first.behindCounters = True
    assert v.DuplicateFurnishings() == [third, second], 'Actual paint layers determine which copy is in front'
    first.behindCounters = False
    v.hiddenObjects, v.hiddenObjectIds = [third, second], {id(third), id(second)}
    assert not v.DuplicateFurnishings()
    v.hiddenObjects, v.hiddenObjectIds = [], set()
    v.furnishings = [first, second]
    for field, value in (("width", second.width + 1), ("flipHorizontal", True), ("flipVertical", True)):
        old = getattr(second, field)
        setattr(second, field, value)
        assert not v.DuplicateFurnishings()
        setattr(second, field, old)
    second.firstVertex += point(.001, 0)
    second.secondVertex += point(.001, 0)
    assert not v.DuplicateFurnishings(), 'Near coincidence is not exact coincidence'
    second.firstVertex, second.secondVertex = point(first.firstVertex), point(first.secondVertex)
    second.definitionKey = "Other type"
    assert not v.DuplicateFurnishings()
    second.definitionKey = first.definition["key"]
    v.SetSelection([])
    v.sceneChanged.emit()
    image = v.grab().toImage()
    warning = QtGui.QColor(themeColors["warningOutline"])
    assert any(image.pixelColor(x, y) == warning for x in range(image.width()) for y in range(image.height()))
    # Moving the rear member clears the stationary front member's warning in
    # dirty-region rendering as well as a full redraw; undo restores it.
    before = v.CaptureState()
    first.firstVertex += point(1800, 0)
    first.secondVertex += point(1800, 0)
    v.RecordEdit(before)
    assert not v.DuplicateFurnishings()
    CompareDirect(v)
    v.Undo()
    assert v.DuplicateFurnishings() == [second]
    CompareDirect(v)

    outer = Wall(point(-1500, -2000), point(1500, -2000), 600)
    inner = Wall(point(-500, -2000), point(500, -2000), 120)
    null = Furnishing(v.furnishingDefinitions["null"], point(2500, 0))
    v.walls = [outer, inner]
    v.furnishings = [first, second, null]
    v.EnsureObjectIds()
    v.sceneChanged.emit()
    data = main.BuildProjectData(includeHistory = False)
    # Compare against an explicitly clean scene, using the same crop, scale and
    # settings. Both formats must produce the same artwork as removing warnings.
    baseline = copy.deepcopy(data)
    excluded = {inner.objectId, second.objectId, null.objectId}
    baseline["scene"]["objects"] = [record for record in baseline["scene"]["objects"] if record["id"] not in excluded]
    baseline["scene"]["groups"], baseline["scene"]["hidden"] = [], []
    bounds = (-2500, -3000, 6500, 4500)
    original = v.CaptureState()
    for solid in (True, False):
        for outputFormat in ("png", "svg"):
            options = dict(bounds = bounds, outputFormat = outputFormat, applyTheme = False, solidObjects = solid,
                           furnishingDefinitions = v.furnishingDefinitions)
            actual = RenderPlan("Warnings.plan", 80, projectData = data, **options)
            expected = RenderPlan("Warnings.plan", 80, projectData = baseline, **options)
            if outputFormat == "png":
                assert ImageBytes(actual) == ImageBytes(expected)
            else:
                rendered = []
                for source in (actual, expected):
                    image = QtGui.QImage(520, 360, QtGui.QImage.Format.Format_ARGB32)
                    image.fill(QtCore.Qt.GlobalColor.transparent)
                    with QtGui.QPainter(image) as painter:
                        QtSvg.QSvgRenderer(source).render(painter)
                    rendered.append(image)
                assert ImageBytes(rendered[0]) == ImageBytes(rendered[1])
                assert not any(rendered[0].pixelColor(x, y).name() in (themeColors["warningOutline"], themeColors["missing"])
                               for x in range(520) for y in range(360))
    assert v.CaptureState() == original
    # Bounded PNG overview/detail rendering uses a separate snapshot viewport.
    main.exportPanel.SetActive(True)
    overlay = v.exportOverlay
    from planner_app.viewport.widget import DrawingViewport
    snapshot = DrawingViewport()
    overlay.ConfigureSnapshotViewport(snapshot)
    assert snapshot.walls == [outer] and snapshot.furnishings == [first]
    assert v.walls == [outer, inner] and v.furnishings == [first, second, null]
    snapshot.close()
    main.exportPanel.SetActive(False)

    # A missing child paints nothing while its healthy sibling remains present.
    good = v.furnishingDefinitions["desk"]
    components = [{"definition": definition, "x": x, "y": 0, "width": definition["width"],
                   "length": definition["length"], "angle": 0, "zIndex": index}
                  for index, (definition, x) in enumerate(((good, 0), (null.definition, 2000)))]
    graphic, width, length, center = CompoundFurnishingSvg(components)
    renderer = FurnishingRenderer(graphic, excludeErrors = True)
    image = QtGui.QImage(400, 200, QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    with QtGui.QPainter(image) as painter:
        renderer.render(painter, QtCore.QRectF(0, 0, 400, 200))
    assert image.pixelColor(350, 100).alpha() == 0
    assert any(image.pixelColor(x, 100).alpha() for x in range(150))
    main.projectDirty = False
    main.close()
    print("PASS: exact duplicate front-order warnings, nonblocking placement, dirty-region undo and clean PNG/SVG/snapshot exports")


if __name__ == "__main__":
    Main()
