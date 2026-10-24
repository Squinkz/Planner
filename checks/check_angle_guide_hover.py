"""Muted angle hover overlays reveal handles without modifying selection or exports."""
import math
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from planner_app.models import AngleGuide, ObjectControlPoints
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.export_plan import RenderPlan


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    point = QtCore.QPointF
    guide = AngleGuide(point(900, 0), point(0, 900), middleVertex = point())
    v.walls = [guide]
    v.SetSelection([])
    v.hoverPosition = v.WorldToViewport(point(-1800, -1500))
    compact = v.grab().toImage()
    before = v.CaptureState()
    revision = v.sceneRevision
    sceneRaster = v.viewportScene.cacheKey()
    middle = v.WorldToViewport(guide.middleVertex)
    radius = QtCore.QLineF(middle, v.WorldToViewport(guide.firstVertex)).length() - 8
    arcPoint = middle + point(12, -6)
    armPoint = middle + point(radius * .4, 0)
    patch = QtCore.QRect(armPoint.toPoint() - QtCore.QPoint(4, 4), QtCore.QSize(9, 9))
    labelRect = v.AngleLayout(guide)[1]
    data = main.BuildProjectData()
    exportBefore = RenderPlan("Angles.plan", 150, (-1500, -1500, 4000, 4000), projectData = data, applyTheme = False)
    for position in [arcPoint, labelRect.center()] + [v.WorldToViewport(vertex) for vertex in ObjectControlPoints(guide)]:
        v.hoveredAngleGuide = None
        v.hoverPosition = position
        hover = v.grab().toImage()
        assert v.hoveredAngleGuide is guide, position
        assert hover.copy(patch) != compact.copy(patch), "Hover failed to reveal the arms"
        for vertex in ObjectControlPoints(guide):
            center = v.WorldToViewport(vertex).toPoint()
            handleRect = QtCore.QRect(center - QtCore.QPoint(8, 8), QtCore.QSize(17, 17))
            assert hover.copy(handleRect) != compact.copy(handleRect), "Hover failed to reveal all three handles"
        assert v.CaptureState() == before and v.sceneRevision == revision and not v.undoHistory
        assert v.viewportScene.cacheKey() == sceneRaster, "Hover was baked into the retained physical scene"
    # Revealed arms remain interactive while hovering them, then disappear on leave.
    v.hoverPosition = armPoint
    v.grab()
    assert v.hoveredAngleGuide is guide and v.HitTest(armPoint) == (guide, None)
    assert v.AngleHoverColor() != QtGui.QColor(v.SelectionColor(guide))
    main.grab().save(str(root / "diagnostics/angle-guide-hover.png"))
    exportAfter = RenderPlan("Angles.plan", 150, (-1500, -1500, 4000, 4000), projectData = main.BuildProjectData(), applyTheme = False)
    assert exportBefore == exportAfter, "A hover preview leaked into export"
    v.leaveEvent(QtCore.QEvent(QtCore.QEvent.Type.Leave))
    after = v.grab().toImage()
    assert v.hoveredAngleGuide is None and after.copy(patch) == compact.copy(patch)
    assert v.HitTest(armPoint)[0] is None
    # Actual selection supersedes the muted preview.
    v.SetSelection([(guide, None)])
    v.hoverPosition = arcPoint
    selected = v.grab().toImage()
    assert selected.copy(patch) != hover.copy(patch)
    # The hover color remains distinct and visible on both light and dark canvases.
    main.SetThemes(uiTheme = "Dark UI")
    v.SetSelection([])
    v.hoverPosition = arcPoint
    assert not v.grab().isNull() and v.hoveredAngleGuide is guide
    main.MarkProjectClean()
    main.close()
    print("PASS: muted arc/label/control hover, all handles, interactive preview arms, cache isolation, leave, selection and export")


if __name__ == "__main__":
    Main()
