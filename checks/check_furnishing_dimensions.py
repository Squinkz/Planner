"""Catalog dimension readouts follow project units and preserve default sizes."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtWidgets
from planner import MainWindow
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.theme import BuildStyle
from planner_app.ui.settings import SettingsWindow


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    main.sidebarTabs.setCurrentIndex(1)
    settings = SettingsWindow(main)
    definition = main.viewport.furnishingDefinitions["desk"]
    originalWidth, originalLength = definition["width"], definition["length"]
    definition["width"], definition["length"] = 1246, 10
    expected = {
        "Meters": "1.25 × 0.01",
        "Centimeters": "125 × 1",
        "Adaptive Metric": "125 × 1",
        "Millimeters": "1246 × 10",
        "Inches": '50" × 1"',
        "Feet and Inches": '4\' 2" × 1"',
    }
    card = main.furnishingCards["desk"]
    label = main.furnishingDimensionLabels["desk"]
    assert card.layout().itemAt(1).widget() is label
    assert card.layout().itemAt(0).widget() is main.furnishingButtons["desk"]
    assert card.layout().itemAt(2).widget().text() == definition["name"]
    for mode, text in expected.items():
        settings.SetUnitsMode(mode)
        assert label.text() == text, (mode, label.text())
    definition["width"], definition["length"] = 11.6 * 25.4, 12.5 * 25.4
    settings.SetUnitsMode("Inches")
    assert label.text() == '12" × 13"'
    settings.SetUnitsMode("Feet and Inches")
    assert label.text() == '1\' 0" × 1\' 1"'
    definition["width"], definition["length"] = originalWidth, originalLength
    settings.SetUnitsMode("Adaptive Metric")
    main.furnishingSearchField.setText("desk")
    main.UpdateFurnishingSearch()
    assert main.furnishingCards["desk"] is card
    assert main.furnishingDimensionLabels["desk"] is label
    expectedText = label.text()
    main.BuildFurnishTab(refresh = True)
    assert main.furnishingDimensionLabels["desk"].text() == expectedText
    main.furnishingSearchField.clear()
    main.UpdateFurnishingSearch()
    app.processEvents()
    main.furnishScrollArea.grab().save("screenshots/furnishing-dimensions.png")
    settings.SetUnitsMode("Feet and Inches")
    app.processEvents()
    main.furnishScrollArea.grab().save("screenshots/furnishing-dimensions-imperial.png")
    main.close()
    print("PASS: catalog sizes, unit rounding, imperial rollover, search reuse and rebuild.")


if __name__ == "__main__":
    Main()

