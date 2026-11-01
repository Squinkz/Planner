"""Border display units and text size are independent of export dimensions."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.export_settings import BorderSize
from planner_app.measurement_units import MetricUnit, unitModes
from planner_app.models import Wall
from planner_app.project_codec import DecodeProject


def Main():
    with ExampleWindow() as (main, folder):
        view, panel = main.viewport, main.exportPanel
        InstallScene(main, [Wall(QtCore.QPointF(-2000, 0), QtCore.QPointF(2000, 0), 200)])
        assert panel.borderSizeLabel.text() == "Border"
        assert [panel.borderTextSizeField.itemText(index) for index in range(3)] == ["Small", "Medium", "Large"]
        assert panel.borderTextSizeField.currentText() == "Medium"
        cases = 0
        for units in unitModes:
            main.sidebarTabs.setCurrentWidget(main.buildScrollArea)
            view.unitsMode = units
            main.sidebarTabs.setCurrentWidget(panel)
            for mode in ("Digital", "Architectural", "Print"):
                panel.SetScaleOption("scaleMode", mode)
                panel.SetScaleOption("architecturalScale", 125)
                panel.SetBorder("Plain")
                for kind in ("PNG", "SVG"):
                    panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
                    divisor, suffix = MetricUnit(units)
                    factor = 1 if mode == "Digital" else 1000 / (panel.PreviewScalePerMeter() * divisor)
                    expectedSuffix = " px" if mode == "Digital" else "" if suffix == "ft" else " " + suffix
                    assert panel.borderSizeField.suffix() == expectedSuffix
                    assert panel.borderSizeField.feetAndInches == (mode != "Digital" and suffix == "ft")
                    panel.borderSizeSlider.setValue(80)
                    assert abs(panel.borderSizeField.value() - 80 * factor) <= 10 ** -panel.borderSizeField.decimals()
                    panel.borderSizeField.setValue(63 * factor)
                    assert panel.borderSizeSlider.value() == 63
                    if mode == "Digital":
                        assert panel.overrides["borderSize"] == panel.RenderArguments("png")["borderSize"] == panel.CaptureExportOverrides()["borderSize"] == 63
                    else:
                        expectedWidth = 63 * factor * divisor
                        assert abs(panel.overrides["borderWidth"] - expectedWidth) <= divisor * 10 ** -panel.borderSizeField.decimals()
                        assert panel.RenderArguments("png")["borderWidth"] == panel.CaptureExportOverrides()["borderWidth"] == panel.overrides["borderWidth"]
                    if mode != "Digital":
                        value = panel.borderSizeField.value()
                        panel.SetScaleOption("dpi", 600)
                        assert panel.borderSizeField.value() == value, "PPI changed the physical border input"
                        panel.SetScaleOption("dpi", 96)
                        panel.SetScaleOption("architecturalScale", 50)
                        assert panel.borderSizeField.value() == value, "Scale changed the requested project length"
                        panel.SetScaleOption("architecturalScale", 125)
                    cases += 1
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("scaleMode", "Digital")
        for style in ("None", "Plain", "Frame", "Corner Marks", "Marked", "Ruler", "Reference Zones", "Ruler + Reference Zones"):
            panel.SetBorder(style)
            expected = style in ("Ruler", "Reference Zones", "Ruler + Reference Zones")
            assert panel.borderTextSizeField.isHidden() != expected
            assert panel.borderTextLabel.isHidden() != expected
        panel.SetOverride("borderSize", 1)
        panel.borderTextSizeField.setCurrentText("Small")
        size = view.exportOverlay.borderSize
        panel.measurementSizeField.setCurrentText("Large")
        assert view.exportOverlay.borderSize == size == BorderSize("Ruler + Reference Zones", 1, 1.5)
        assert view.borderTextSize == 1.5 and view.measurementTextSize == 2.5
        panel.ResetExportHistory()
        panel.borderTextSizeField.setCurrentText("Large")
        assert view.borderTextSize == 2.5 and view.measurementTextSize == 2.5
        view.Undo()
        assert panel.borderTextSizeField.currentText() == "Small" and view.borderTextSize == 1.5
        view.Redo()
        assert panel.borderTextSizeField.currentText() == "Large"
        saved = main.BuildProjectData(includeHistory = False)
        assert saved["settings"]["exportSettings"]["borderTextSize"] == 2.5
        assert "borderTextSize" not in saved["settings"]
        width = saved["settings"]["exportSettings"]["borderWidth"]
        main.ApplyProject(DecodeProject(saved, view.furnishingDefinitions), None)
        main.sidebarTabs.setCurrentWidget(panel)
        assert panel.borderTextSizeField.currentText() == "Large" and view.borderTextSize == 2.5
        assert panel.overrides["borderWidth"] == width
    print("PASS:", cases, "border unit/format/mode combinations, density invariance, conditional text controls, independent sizes, undo/redo and persistence")


if __name__ == "__main__":
    Main()
