"""Export, paired properties, reference settings and calibration prompt geometry."""
import os
from pathlib import Path
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall
from furnishings import Furnishing
from planner_app.models import Label
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.ui.reference_calibration import CalibrationDistanceDialog
from planner_app.ui.widgets import DragSpinBox, UnitSpinBox


def Rect(widget, ancestor):
    return QtCore.QRect(widget.mapTo(ancestor, QtCore.QPoint()), widget.size())


def CheckPair(first, second, ancestor, link = None):
    left, right = Rect(first, ancestor), Rect(second, ancestor)
    assert left.right() < right.left(), (left, right)
    assert left.top() == right.top() and left.height() == right.height(), (left, right)
    assert abs(left.width() - right.width()) <= 1, (left, right)
    if link is not None:
        middle = Rect(link, ancestor)
        assert left.right() < middle.left() < middle.right() < right.left()
        assert abs(middle.center().y() - left.center().y()) <= 1


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    ApplyApplicationTheme(app)
    main = MainWindow()
    main.resize(1400, 1000)
    main.show()
    v, export = main.viewport, main.exportPanel
    app.processEvents()
    for sidebarWidth in (460, 700):
        main.mainSplitter.setSizes([main.width() - sidebarWidth, sidebarWidth])
        main.sidebarTabs.setCurrentWidget(export)
        for name in export.sectionButtons:
            export.SetSectionExpanded(name, True)
        app.processEvents()
        assert not main.propertiesPanel.isVisible() and main.exportActionPanel.isVisible()
        assert not export.scrollArea.isAncestorOf(main.exportButton)
        assert not export.scrollArea.isAncestorOf(export.scaleModeTabs)
        assert Rect(export.folderField, export).right() < Rect(export.browseButton, export).left()
        assert Rect(export.folderField, export).left() == Rect(export.fileNameField, export).left() == 14
        assert Rect(export.fileNameField, export).right() == Rect(export.browseButton, export).right()
        assert Rect(export.folderField, export).bottom() < Rect(export.fileNameField, export).top()
        assert export.browseButton.size() == QtCore.QSize(44, 32)
        before = [Rect(widget, export) for widget in (export.folderField, export.fileNameField, export.typeField, export.scaleModeTabs)]
        actionBefore = Rect(main.exportButton, main.sidebarContentPanel)
        export.scrollArea.verticalScrollBar().setValue(export.scrollArea.verticalScrollBar().maximum())
        app.processEvents()
        assert before == [Rect(widget, export) for widget in (export.folderField, export.fileNameField, export.typeField, export.scaleModeTabs)]
        assert Rect(main.exportButton, main.sidebarContentPanel) == actionBefore
        for output in ("PNG", "SVG", "PNG_OPTIMIZED"):
            export.typeField.setCurrentIndex(export.typeField.findData(output))
            for mode in (0, 1):
                export.scaleModeTabs.setCurrentIndex(mode)
                app.processEvents()
                raster = output != "SVG"
                assert export.compositeSection.isVisible() == raster
                assert export.resolutionRow.isVisible() == (raster and mode == 0)
                assert export.architecturalResolutionRow.isVisible() == (raster and mode == 1)
                assert export.dpiRow.isVisible() == (raster and mode == 1)
                assert export.digitalScaleRow.isVisible() == (mode == 0)
        export.typeField.setCurrentIndex(export.typeField.findData("PNG"))
        export.scaleModeTabs.setCurrentIndex(0)
        app.processEvents()
        for key, slider in export.gridSliders.items():
            field, reset = export.gridValueFields[key], export.gridResetButtons[key]
            ancestor = slider.parentWidget()
            assert Rect(slider, ancestor).right() < Rect(field, ancestor).left()
            assert Rect(field, ancestor).right() < Rect(reset, ancestor).left()
            assert field.width() == max(80, field.minimumWidth()) and reset.width() == 34
        main.sidebarTabs.setCurrentIndex(0)
        desk = Furnishing(v.furnishingDefinitions["desk"])
        v.furnishings = [desk]
        v.SetSelection([(desk, None)])
        app.processEvents()
        assert main.selectionLabel.isVisible() and main.selectionLabel.text() != "No selection"
        CheckPair(main.objectPositionFields["x"], main.objectPositionFields["y"], main.wallProperties)
        CheckPair(main.propertyFields["width"], main.propertyFields["length"], main.wallProperties, main.sizeLinkButton)
        assert Rect(main.objectPositionRow, main.wallProperties).bottom() < Rect(main.sizeRow, main.wallProperties).top()
        assert main.sizeLinkButton.isChecked()
        wall = Wall(QtCore.QPointF(0, 0), QtCore.QPointF(1000, 0), 200)
        v.walls = [wall]
        v.SetSelection([(wall, 0)])
        app.processEvents()
        assert not main.objectPositionRow.isVisible() and main.vertexProperties.isVisible()
        assert not main.sizeLinkButton.isChecked()
        CheckPair(main.propertyFields["x"], main.propertyFields["y"], main.vertexProperties)
        label = Label(QtCore.QPointF(), "Layout label")
        v.labels = [label]
        v.SetSelection([(label, None)])
        app.processEvents()
        CheckPair(main.labelPositionFields["x"], main.labelPositionFields["y"], main.labelProperties)
        CheckPair(main.labelFields["width"], main.labelFields["length"], main.labelProperties)
        assert not main.sizeLinkButton.isVisible()
        assert main.labelTextField.minimumHeight() == 80 and main.labelTextField.maximumHeight() == 110

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "reference.png"
        image = QtGui.QImage(400, 200, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtGui.QColor("#bc7647"))
        assert image.save(str(path))
        main.sidebarTabs.setCurrentWidget(main.visibilityPage)
        reference = main.referenceImage
        assert reference.Load(path)
        main.SetViewOption("editReferenceImage")
        for sidebarWidth in (460, 700):
            main.mainSplitter.setSizes([main.width() - sidebarWidth, sidebarWidth])
            app.processEvents()
            assert reference.panel.isVisible() and main.selectionLabel.isHidden()
            assert reference.browseButton.size() == QtCore.QSize(44, 32)
            assert Rect(reference.pathField, reference.panel).right() < Rect(reference.browseButton, reference.panel).left()
            CheckPair(reference.fields["x"], reference.fields["y"], reference.panel)
            CheckPair(reference.fields["width"], reference.fields["length"], reference.panel, reference.sizeLinkButton)
            assert Rect(reference.opacitySlider, reference.panel).bottom() < Rect(reference.fields["x"], reference.panel).top()
            assert Rect(reference.fields["angle"], reference.panel).bottom() < Rect(reference.calibrateButton, reference.panel).top()
            assert all(isinstance(field, DragSpinBox) and not field.keyboardTracking() for field in reference.fields.values())
        reference.calibration.Start()
        calibration = reference.calibration
        calibration.points = [QtCore.QPointF(0, 0), QtCore.QPointF(1000, 0)]
        v.unitsMode = "Adaptive Metric"
        dialog = CalibrationDistanceDialog(calibration)
        dialog.show()
        app.processEvents()
        assert not reference.panel.isEnabled()
        assert isinstance(dialog.distanceField, UnitSpinBox) and not isinstance(dialog.distanceField, DragSpinBox)
        assert dialog.distanceField.objectName() == "settingsValue" and dialog.distanceField.decimals() == 6
        assert dialog.distanceField.suffix() == "" and not dialog.distanceField.keyboardTracking()
        assert dialog.unitsField.currentData() == "Meters"
        assert dialog.unitsField.findData("Adaptive Metric") == -1
        assert dialog.windowModality() == QtCore.Qt.WindowModality.WindowModal
        for width in (440, 680):
            dialog.resize(width, dialog.height())
            app.processEvents()
            distance, units = Rect(dialog.distanceField, dialog), Rect(dialog.unitsField, dialog)
            assert distance.right() < units.left() and distance.width() > units.width()
            assert units.left() - distance.right() - 1 == 6
            assert units.right() == Rect(dialog.distanceField.parentWidget(), dialog).right()
        dialog.close()
        calibration.Stop()
        assert reference.panel.isEnabled()
    main.close()
    print("PASS: pinned export regions, format/mode rows, amount groups, paired properties, reference settings and calibration prompt geometry")


if __name__ == "__main__":
    Main()
