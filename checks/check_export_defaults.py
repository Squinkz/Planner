"""Fresh exports start in Print; scale-bar UI and drawing share their defaults."""
import copy
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow
from planner_app.graphics.scale_bar import ScaleBarLayout, DrawScaleBar
from planner_app.project_codec import DecodeProject
from planner_app.print_layout import SelectedPrintPages


def Main():
    with ExampleWindow() as (main, folder):
        panel, view = main.exportPanel, main.viewport
        assert not panel.overrides
        assert [panel.scaleModeTabs.tabText(index) for index in range(3)] == ["Print", "Architectural", "Digital"]
        main.sidebarTabs.setCurrentWidget(panel)
        assert panel.scaleModeTabs.currentIndex() == 0 and panel.overrides["scaleMode"] == "Print"
        overlay = view.exportOverlay
        assert overlay.printMode and len(SelectedPrintPages(overlay.bounds, panel.PrintLayout()["paperTile"], overlay.pageOrigin)) == 1
        assert not panel.exportUndoHistory
        assert panel.scaleBarDivisionMode.currentText() == "Subdivided"
        assert panel.scaleBarStyle.currentText() == "Stepped"
        plot = QtCore.QRectF(0, 0, 1800, 700)
        scale = 300 * 1000 / (25.4 * 100)
        implicit = dict(enabled = True)
        explicit = dict(enabled = True, divisionMode = "Subdivided", style = "Stepped")
        layouts = [ScaleBarLayout(plot, options, scale, "Meters", view.font()) for options in (implicit, explicit)]
        assert layouts[0] == layouts[1] and layouts[0]["distances"] == (0, 1000, 2000, 4000, 6000, 8000, 10000)
        images = []
        for options in (implicit, explicit):
            image = QtGui.QImage(1800, 700, QtGui.QImage.Format.Format_ARGB32)
            image.fill(QtCore.Qt.GlobalColor.transparent)
            with QtGui.QPainter(image) as painter:
                painter.setFont(view.font())
                DrawScaleBar(painter, plot, options, scale, "Meters")
            images.append(image)
        assert images[0] == images[1]
        # Actual tab clicks must retain the chosen mode on returning to Export.
        for index, name in ((1, "Architectural"), (2, "Digital"), (0, "Print")):
            tabBar = panel.scaleModeTabs.tabBar()
            QtTest.QTest.mouseClick(tabBar, QtCore.Qt.MouseButton.LeftButton, pos = tabBar.tabRect(index).center())
            QtWidgets.QApplication.processEvents()
            assert panel.overrides["scaleMode"] == name
            main.sidebarTabs.setCurrentIndex(0)
            main.sidebarTabs.setCurrentWidget(panel)
            assert panel.scaleModeTabs.currentIndex() == index and panel.overrides["scaleMode"] == name
        # Saved explicit choices, including earlier scale-bar appearances, win.
        panel.SetScaleOption("scaleMode", "Digital")
        panel.SetScaleBarOption("divisionMode", "Progressive")
        panel.SetScaleBarOption("style", "Alternating")
        saved = main.BuildProjectData(includeHistory = False)
        main.ApplyProject(DecodeProject(saved, view.furnishingDefinitions), None)
        main.sidebarTabs.setCurrentWidget(panel)
        assert panel.scaleModeTabs.currentIndex() == 2
        assert panel.scaleBarDivisionMode.currentText() == "Progressive" and panel.scaleBarStyle.currentText() == "Alternating"
        legacy = copy.deepcopy(saved)
        legacy["settings"]["exportSettings"] = dict(bounds = [100, 200, 8000, 6000])
        main.ApplyProject(DecodeProject(legacy, view.furnishingDefinitions), None)
        main.sidebarTabs.setCurrentWidget(panel)
        assert panel.scaleModeTabs.currentIndex() == 2 and not overlay.printMode
        assert overlay.bounds == (100, 200, 8000, 6000)
        main.NewProject()
        main.sidebarTabs.setCurrentWidget(panel)
        assert panel.scaleModeTabs.currentIndex() == 0 and overlay.printMode
        assert panel.scaleBarDivisionMode.currentText() == "Subdivided" and panel.scaleBarStyle.currentText() == "Stepped"
    print("PASS: Print default and tab order, matching Subdivided/Stepped drawing defaults, saved choices and new-project reset")


if __name__ == "__main__":
    Main()
