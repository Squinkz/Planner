"""Unit/precision and export transitions tolerate collapsed scene footprints."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Wall, Column
from planner_app.ui.settings import SettingsWindow
from planner_app.units import unitModes
from check_selected_measurements import RenderLabels


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    settings = SettingsWindow(main)
    collapsed = Wall(QtCore.QPointF(), QtCore.QPointF(), 240)
    column = Column(QtCore.QPointF(500, 0), QtCore.QPointF(500, 0), 300)
    valid = Wall(QtCore.QPointF(-1000, -500), QtCore.QPointF(1000, -500), 240)
    v.walls = [collapsed, column, valid]
    v.SetSelection([(collapsed, None)])
    v.showMeasurements = True
    v.measurementVisibility = dict.fromkeys(v.measurementVisibility, True)
    errors = []
    originalHook = sys.excepthook
    originalHandler = QtCore.qInstallMessageHandler(lambda kind, context, message: errors.append(message)
        if "QPainter" in message or "Python override" in message else None)
    sys.excepthook = lambda exceptionType, exception, traceback: errors.append(str(exception))
    try:
        for mode in unitModes:
            settings.SetUnitsMode(mode)
            for precision in ("High", "Medium", "Low"):
                settings.SetMeasurementPrecision(precision)
                for index in (0, 3, 0):
                    main.sidebarTabs.setCurrentIndex(index)
                    app.processEvents()
                    RenderLabels(v)  # Fractional imperial text is drawn as glyph paths.
                    assert not v.grab().isNull()
                    assert any(valid in owners for first, second, owners in
                        v.WallDimensions([valid], v.ConnectedWallPath([valid]))), (mode, precision, index)
        assert not errors, errors
    finally:
        sys.excepthook = originalHook
        QtCore.qInstallMessageHandler(originalHandler)
        main.close()
    print("PASS: all unit/precision modes, repeated export transitions, valid measurements and clean painting.")


if __name__ == "__main__":
    Main()
