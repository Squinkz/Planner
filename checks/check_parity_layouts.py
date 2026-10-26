"""Specialized Settings measurement rows and Wall Tool composition geometry."""
import json
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    main.ShowSettings()
    panel = main.settingsWindow
    # The Measurements page is hosted by a scroll area, rather than being a tab itself.
    for index in range(panel.tabs.count()):
        if panel.tabs.tabText(index) == "Dimensions":
            panel.tabs.setCurrentIndex(index)
    app.processEvents()
    page = panel.measurementPage
    panel.wallMeasurementModeField.setCurrentText("All")
    app.processEvents()
    observations = []
    for width, height in ((980, 540), (980, 900), (1200, 900)):
        panel.resize(width, height)
        app.processEvents()
        observations.append({"requestedDialogSize": [width, height], "actualDialogSize": [panel.width(), panel.height()],
                             "selectorHeights": {key: slider.height() for key, slider in panel.measurementSliders.items()}})
        sliderXs, resetXs = [], []
        headingBottom = panel.wallMeasurementHeading.mapTo(page, panel.wallMeasurementHeading.rect().bottomLeft()).y()
        modeTop = panel.wallMeasurementModeField.mapTo(page, QtCore.QPoint()).y()
        modeBottom = panel.wallMeasurementModeField.mapTo(page, panel.wallMeasurementModeField.rect().bottomLeft()).y()
        assert headingBottom < modeTop
        modeLabel = next(form.labelForField(panel.wallMeasurementModeField)
                         for form in page.findChildren(QtWidgets.QFormLayout)
                         if form.labelForField(panel.wallMeasurementModeField) is not None)
        assert modeLabel.text() == "Mode"
        for tabIndex, (key, slider) in enumerate(panel.measurementSliders.items()):
            panel.measurementSplitTabs.setCurrentIndex(tabIndex)
            app.processEvents()
            sliderRect = QtCore.QRect(slider.mapTo(page, QtCore.QPoint()), slider.size())
            assert modeBottom < sliderRect.top()
            reset = panel.measurementResetButtons[key]
            resetRect = QtCore.QRect(reset.mapTo(page, QtCore.QPoint()), reset.size())
            labels = [label for label in page.findChildren(QtWidgets.QLabel) if label.property("measurementKey") == key]
            labelRects = [QtCore.QRect(label.mapTo(page, QtCore.QPoint()), label.size()) for label in labels]
            assert sliderRect.right() < min(rect.left() for rect in labelRects)
            assert max(rect.right() for rect in labelRects) < resetRect.left()
            assert abs(resetRect.center().y() - sliderRect.center().y()) <= 2
            assert panel.measurementHeading.mapTo(page, panel.measurementHeading.rect().topRight()).x() < sliderRect.left()
            option = QtWidgets.QStyleOptionSlider()
            slider.initStyleOption(option)
            for index, rect in enumerate(labelRects):
                option.sliderPosition = option.sliderValue = index
                handle = slider.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_Slider, option,
                                                       QtWidgets.QStyle.SubControl.SC_SliderHandle, slider)
                detentY = slider.mapTo(page, handle.center()).y()
                assert abs(rect.center().y() - detentY) <= 4, (key, index, rect, detentY)
            sliderXs.append(sliderRect.center().x())
            resetXs.append(resetRect.left())
        assert max(sliderXs) - min(sliderXs) <= 1
        assert max(resetXs) - min(resetXs) <= 1
        assert panel.precisionField.mapTo(page, panel.precisionField.rect().bottomLeft()).y() < panel.measurementVisibilityTree.mapTo(page, QtCore.QPoint()).y()
        assert panel.measurementVisibilityTree.mapTo(page, panel.measurementVisibilityTree.rect().bottomLeft()).y() < panel.showGridField.mapTo(page, QtCore.QPoint()).y()
    panel.close()
    main.sidebarTabs.setCurrentIndex(0)
    for width in (320, 700):
        main.mainSplitter.setSizes([main.width() - width, width])
        app.processEvents()
        page = main.buildScrollArea.widget()
        selector = main.wallWidthSelector
        selectorRect = QtCore.QRect(selector.mapTo(page, QtCore.QPoint()), selector.size())
        divider = page.findChild(QtWidgets.QFrame, "wallToolDivider")
        dividerRect = QtCore.QRect(divider.mapTo(page, QtCore.QPoint()), divider.size())
        shapes = [main.wallToolButtons[key] for key in ("line", "square", "circle")]
        rects = [QtCore.QRect(button.mapTo(page, QtCore.QPoint()), button.size()) for button in shapes]
        assert len({rect.x() for rect in rects}) == 1
        assert all(rects[index].bottom() < rects[index + 1].top() for index in range(2))
        assert max(rect.right() for rect in rects) < dividerRect.left()
        assert dividerRect.right() < selectorRect.left()
        field = main.newWallMaterialField
        fieldRect = QtCore.QRect(field.mapTo(page, QtCore.QPoint()), field.size())
        assert fieldRect.top() > selectorRect.bottom()
        assert fieldRect.left() >= selectorRect.left() and fieldRect.right() <= selectorRect.right()
        assert main.wallToolButtonGroup.exclusive() and sum(button.isChecked() for button in shapes) == 1
    (Path(__file__).resolve().parent.parent / "diagnostics/parity-special-layout-metrics-20261022.json").write_text(
        json.dumps(observations, indent = 2), encoding = "utf-8")
    main.close()
    print("PASS: measurement label/detent alignment, shared slider/reset columns, separate settings columns and Wall Tool shape/divider/preset/material composition at multiple sizes")


if __name__ == "__main__":
    Main()
