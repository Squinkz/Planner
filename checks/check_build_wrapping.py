"""Build palette uses the furnishing flow layout as the sidebar resizes."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtGui, QtWidgets
from planner import MainWindow
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.resize(1500, 1100)
    main.show()
    app.processEvents()
    doors = main.buildObjectLayouts["Doors"]
    assert doors.hasHeightForWidth() and doors.count() == 8
    assert main.buildObjectLayouts["Windows"].count() == 5
    assert main.buildObjectLayouts["Miscellaneous"].count() == 7
    assert main.buildObjectLayouts["Annotations"].count() == 9
    main.mainSplitter.setSizes([800, 700])
    app.processEvents()
    wideRows = {doors.itemAt(index).geometry().y() for index in range(doors.count())}
    assert len(wideRows) == 1
    main.mainSplitter.setSizes([1200, 300])
    app.processEvents()
    narrowRows = {doors.itemAt(index).geometry().y() for index in range(doors.count())}
    assert len(narrowRows) > 1
    for layout in main.buildObjectLayouts.values():
        for index in range(layout.count()):
            rect = layout.itemAt(index).geometry()
            assert layout.geometry().contains(rect)
            for other in range(index):
                assert not rect.intersects(layout.itemAt(other).geometry())
    main.sidebarPanel.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "build-wrapping.png"))
    main.mainSplitter.setSizes([800, 700])
    app.processEvents()
    assert len({doors.itemAt(index).geometry().y() for index in range(doors.count())}) == 1
    main.close()
    print("PASS: Build categories wrap and unwrap on real sidebar resizing, without clipped or overlapping icons.")


if __name__ == "__main__":
    Main()
