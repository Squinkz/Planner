"""Wheel presets across the icon area and separate material defaults for new walls."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall, DownwardComboBox
from theme import BuildStyle, wallMaterials
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    window = MainWindow()
    window.show()
    app.processEvents()
    selector = window.wallWidthSelector
    assert selector.widths == (10, 15, 20, 30)
    assert selector.slider.value() == 2 and window.viewport.newWallWidth == 200
    for index, width in enumerate(selector.widths):
        selector.slider.setValue(index)
        assert window.viewport.newWallWidth == width * 10
    results = []
    for widget, position in ((selector.slider, selector.slider.rect().center()),
                             (selector, QtCore.QPoint(round(selector.PresetCenters()[1]), 15))):
        selector.slider.setValue(1)
        event = QtGui.QWheelEvent(QtCore.QPointF(position), QtCore.QPointF(widget.mapToGlobal(position)),
                                 QtCore.QPoint(), QtCore.QPoint(0, 120), QtCore.Qt.MouseButton.NoButton,
                                 QtCore.Qt.KeyboardModifier.NoModifier, QtCore.Qt.ScrollPhase.NoScrollPhase, False)
        QtWidgets.QApplication.sendEvent(widget, event)
        results.append(selector.slider.value())
        assert event.isAccepted()
    assert results[0] == results[1] and results[0] > 1
    viewport = window.viewport
    field = window.newWallMaterialField
    assert isinstance(field, DownwardComboBox)
    forms = window.buildScrollArea.widget().findChildren(QtWidgets.QFormLayout)
    assert any(form.labelForField(field) is not None and form.labelForField(field).text() == "Material" for form in forms)
    assert [field.itemText(index) for index in range(field.count())] == list(wallMaterials)
    assert field.currentText() == viewport.newWallMaterial == "Generic"
    existing = Wall(QtCore.QPointF(-1500, -1000), QtCore.QPointF(1500, -1000))
    viewport.walls = [existing]
    viewport.SetSelection([(existing, None)])
    field.setCurrentText("Ceramic")
    assert existing.material == "Generic" and viewport.newWallMaterial == "Ceramic"
    window.materialField.setCurrentText("Wood")
    assert existing.material == "Wood" and field.currentText() == "Ceramic"
    viewport.snapEnabled = False
    Drag(viewport, QtCore.QPoint(150, 250), QtCore.QPoint(450, 250), button = QtCore.Qt.MouseButton.RightButton)
    assert len(viewport.walls) == 2 and viewport.walls[-1].material == "Ceramic"
    viewport.Undo()
    assert len(viewport.walls) == 1 and field.currentText() == "Ceramic"
    viewport.Redo()
    assert viewport.walls[-1].material == "Ceramic"
    app.processEvents()
    window.close()
    print("PASS: icon/slider wheel parity, matching material dropdowns, independent defaults and new-wall material history.")


if __name__ == "__main__":
    Main()
