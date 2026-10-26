"""Standalone option checkboxes follow property forms; export trees stay trees."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtWidgets
from fixtures.parity_examples import ExampleWindow


def CheckField(field, root):
    label = None
    for form in root.findChildren(QtWidgets.QFormLayout):
        if form.labelForField(field) is not None:
            label = form.labelForField(field)
            break
    if label is None:
        for grid in root.findChildren(QtWidgets.QGridLayout):
            index = grid.indexOf(field)
            if index >= 0:
                row, column, rowSpan, columnSpan = grid.getItemPosition(index)
                label = grid.itemAtPosition(row, column - 1).widget()
                break
    assert label is not None and label.text() and not field.text(), field.accessibleName()
    labelRect = QtCore.QRect(label.mapTo(root, QtCore.QPoint()), label.size())
    option = QtWidgets.QStyleOptionButton()
    option.initFrom(field)
    option.rect = field.rect()
    indicator = field.style().subElementRect(QtWidgets.QStyle.SubElement.SE_CheckBoxIndicator, option, field)
    indicatorRect = QtCore.QRect(field.mapTo(root, indicator.topLeft()), indicator.size())
    assert labelRect.right() < indicatorRect.left(), (field.accessibleName(), labelRect, indicatorRect)
    assert abs(labelRect.center().y() - indicatorRect.center().y()) <= 1, (labelRect, indicatorRect)
    return label


def Main():
    with ExampleWindow() as (main, folder):
        main.ShowSettings()
        settings = main.settingsWindow
        settings.tabs.setCurrentIndex(1)
        QtWidgets.QApplication.processEvents()
        CheckField(settings.showGridField, settings.measurementPage)
        assert isinstance(settings.measurementVisibilityTree, QtWidgets.QTreeWidget)
        assert settings.drawDimensionsItem.childCount() == 4
        settings.tabs.setCurrentIndex(0)
        QtWidgets.QApplication.processEvents()
        for field in settings.collisionFields.values():
            label = CheckField(field, settings.buildPage)
            before = field.isChecked()
            label.click()
            assert field.isChecked() != before
            field.click()
            assert field.isChecked() == before
        settings.hide()
        export = main.exportPanel
        main.sidebarTabs.setCurrentWidget(export)
        for name in ("Canvas", "Grid", "Composite"):
            export.sectionButtons[name].setChecked(True)
        QtWidgets.QApplication.processEvents()
        for field in (export.solidObjectsField, export.showGridField, export.enableVignetteField):
            CheckField(field, export)
            before = field.isChecked()
            field.click()
            assert field.isChecked() != before
            field.click()
            assert field.isChecked() == before
        assert isinstance(export.measurementVisibilityTree, QtWidgets.QTreeWidget)
        assert export.measurementVisibilityItems["all"].childCount() == 4
        assert isinstance(export.visibilityTree, QtWidgets.QTreeWidget)
    print("PASS: label-left, checkbox-right layout and controls in Dimensions, Build and Export; trees retained")


if __name__ == "__main__":
    Main()
