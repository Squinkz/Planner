"""Collision category switches, opening placement and project persistence."""
import copy
import itertools
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow
from planner_app.models import Wall, Pillar, Stair, Counter, Railing, Arrow, MeasurementGuide, Label, Furnishing, Door, Window
from planner_app.project_codec import DecodeProject
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    main.ShowSettings()
    app.processEvents()
    v = main.viewport
    panel = main.settingsWindow
    panel.tabs.setCurrentIndex(0)
    panel.buildTabs.setCurrentIndex(0)
    app.processEvents()
    point = QtCore.QPointF
    assert all(field.isChecked() for field in panel.collisionFields.values())
    for rowIndex, field in enumerate(panel.collisionFields.values()):
        layout = field.parentWidget().layout()
        assert isinstance(layout, QtWidgets.QFormLayout)
        assert layout.getWidgetPosition(field) == (rowIndex, QtWidgets.QFormLayout.ItemRole.FieldRole)
        label = layout.labelForField(field)
        assert label.accessibleName()
        icon, caption = label.findChildren(QtWidgets.QLabel)
        assert caption.text() == label.accessibleName() and not icon.pixmap().isNull()
        assert icon.size() == QtCore.QSize(18, 18) and label.layout().spacing() == 6
        layout.activate()
        label.layout().activate()
        assert caption.width() >= caption.sizeHint().width(), (caption.text(), caption.width(), caption.sizeHint().width())
        assert caption.geometry().right() < label.width()
        assert label.geometry().right() < field.geometry().left()
        assert abs(label.geometry().center().y() - field.geometry().center().y()) <= 1
        label.click()
        assert not field.isChecked()
        label.click()
        assert field.isChecked()
    assert len({field.x() for field in panel.collisionFields.values()}) == 1
    assert v.collisionSettings == dict.fromkeys(("walls", "architectural", "furnishings"), True)
    for walls, architectural, furnishings in itertools.product((False, True), repeat = 3):
        for key, value in zip(v.collisionSettings, (walls, architectural, furnishings)):
            panel.collisionFields[key].setChecked(value)
        wall = Wall(point(-1000, 0), point(1000, 0), 240)
        stair = Stair(point(-500, 0), point(500, 0), 500)
        counter = Counter(point(-500, 0), point(500, 0), 500)
        railing = Railing(point(-500, 0), point(500, 0))
        furniture = Furnishing(v.furnishingDefinitions["desk"], point())
        pairs = ((wall, stair, walls), (wall, counter, walls), (wall, furniture, walls and furnishings),
                 (stair, counter, architectural), (stair, furniture, architectural and furnishings),
                 (railing, furniture, architectural and furnishings))
        v.walls, v.windows, v.furnishings = [], [], []
        for first, second, expected in pairs:
            assert v.JoinedObjectsOverlap(first, second) == expected, (v.collisionSettings, type(first), type(second))
        v.walls = [wall, stair]
        assert v.StairFits(stair) == (not walls)
        v.walls = [stair, counter]
        assert v.StairFits(stair) == (not architectural)
        assert v.CounterFits(counter) == (not architectural)
        v.walls, v.furnishings = [wall], [furniture]
        assert v.WallFits(wall) == (not (walls and furnishings))
        assert v.FurnishingFits(furniture) == (not (walls and furnishings))
        assert not v.JoinedObjectsOverlap(railing, wall)
        for annotation in (Arrow(point(-500, 0), point(500, 0)), MeasurementGuide(point(-500, 0), point(500, 0)), Label(point())):
            assert not v.JoinedObjectsOverlap(annotation, wall)
    # Opening collision rules stay active even when every category is disabled.
    for field in panel.collisionFields.values():
        field.setChecked(False)
    wall = Wall(point(-1000, 0), point(1000, 0), 240)
    first, second = Door(wall, .2, .7), Window(wall, .4, .9)
    v.walls, v.windows, v.furnishings = [wall], [first, second], []
    assert v.OpeningsOverlap(first, second) and not v.OpeningsValid()
    assert v.FindWindowPlacement(v.WorldToViewport(point()), openingType = Door) is None
    assert v.MinimumOpeningLength(wall) == 2000
    first.centerFraction = 0
    assert not v.OpeningFits(first)
    first.centerFraction = .45
    v.windows = []
    crossing = Wall(point(0, -1000), point(0, 1000), 240)
    v.walls = [wall, crossing]
    assert v.FindWindowPlacement(v.WorldToViewport(point()), openingType = Window) is None
    assert not v.OpeningFits(Window(wall, .3, .7))
    # Disabled collisions allow an actual drag into a wall, with undo intact.
    v.connectedEnabled = v.snapEnabled = False
    stair = Stair(point(-500, 1200), point(500, 1200), 500)
    v.walls, v.windows = [wall, stair], []
    v.SetSelection([(stair, None)])
    before = v.CaptureState()
    start = v.WorldToViewport(point(0, 1200)).toPoint()
    Drag(v, start, v.WorldToViewport(point()).toPoint())
    assert stair.firstVertex == point(-500, 0) and v.StairFits(stair)
    v.Undo()
    assert v.CaptureState()[0] == before[0]
    # Project reload synchronizes existing controls; old projects default on.
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "Collisions.plan"
        assert main.SaveProject(path)
        expected = dict(v.collisionSettings)
        for field in panel.collisionFields.values():
            field.setChecked(True)
        assert main.OpenProject(path)
        assert v.collisionSettings == expected
        assert {key: field.isChecked() for key, field in panel.collisionFields.items()} == expected
    legacy = main.BuildProjectData()
    del legacy["settings"]["collisionSettings"]
    assert all(DecodeProject(legacy, v.furnishingDefinitions)[5]["collisionSettings"].values())
    invalid = copy.deepcopy(legacy)
    invalid["settings"]["collisionSettings"] = {"walls": 0, "architectural": True, "furnishings": True}
    try:
        DecodeProject(invalid, v.furnishingDefinitions)
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid collision switches were accepted")
    main.close()


if __name__ == "__main__":
    Main()
