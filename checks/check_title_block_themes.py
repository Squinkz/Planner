"""Every canvas theme supplies title-block colours, independently of the UI theme."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics import palette
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.title_block import TitleBlockLayout, TitleBlockCells, RenderTitleBlockBitmap, TitleBlockUnitScale
from fixtures.parity_examples import ExampleWindow


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    themes = sorted(name for name, definition in palette.themeDefinitions.items() if definition["type"] == "canvas")
    options = dict(enabled = True, logoMode = "None", projectName = "Planner House", drawingTitle = "Ground Floor Plan",
                   address = "12 Oak Street\nCape Town", comments = "Proposed layout", sheetNumber = "0001")
    gallery = QtGui.QImage(1120, ((len(themes) + 3) // 4) * 270, QtGui.QImage.Format.Format_RGB32)
    gallery.fill(QtGui.QColor("#eeeeee"))
    galleryPainter = QtGui.QPainter(gallery)
    for index, name in enumerate(themes):
        palette.SetThemes("Dark UI", name)
        for position in ("Right", "Bottom"):
            options["position"] = position
            width, height, block = TitleBlockLayout(1200, 700, options)
            image = RenderTitleBlockBitmap(block, options, 100)
            factor = TitleBlockUnitScale(100)
            margin = int(7 * factor)
            assert image.pixelColor(image.width() - margin, image.height() - margin) == QtGui.QColor(palette.themeColors["canvas"]), name
            assert image.pixelColor(0, 0) == QtGui.QColor(palette.themeColors["rulerMajorTick"]), name
            ink = QtGui.QColor(palette.themeColors["objectOutline"]).rgb()
            assert any(image.pixel(x, y) == ink for y in range(int(25 * factor), int(55 * factor))
                       for x in range(int(10 * factor), min(int(210 * factor), image.width() - margin))), name
            palette.SetThemes("Light UI", name)
            assert RenderTitleBlockBitmap(block, options, 100) == image, "UI colours leaked into the title block"
            palette.SetThemes("Dark UI", name)
            if position == "Right":
                x, y = (index % 4) * 280, (index // 4) * 270
                galleryPainter.setPen(QtGui.QColor("#222222"))
                galleryPainter.setFont(QtGui.QFont("Arial", 10))
                galleryPainter.drawText(QtCore.QPointF(x + 12, y + 20), name)
                sampleHeight = int(sum(cell.height() for field, label, value, cell in TitleBlockCells(block, options, 100)[:3]))
                galleryPainter.drawImage(QtCore.QRectF(x + 12, y + 30, 253, sampleHeight * 253 / image.width()),
                                         image.copy(0, 0, image.width(), sampleHeight))
    galleryPainter.end()
    diagnostics = root / "diagnostics" / "title-block"
    diagnostics.mkdir(parents = True, exist_ok = True)
    gallery.save(str(diagnostics / "themes.png"))
    with ExampleWindow() as (main, folder):
        panel, v = main.exportPanel, main.viewport
        main.sidebarTabs.setCurrentWidget(panel)
        panel.titleBlockEnabled.setChecked(True)
        panel.SetBorder("None")
        panel.canvasThemeField.setCurrentText("Light Canvas")
        v.grab()
        previousImage = v.exportOverlay.titleBlockImage
        previousFont = palette.labelFont
        panel.canvasThemeField.setCurrentText("Dark Canvas")
        v.grab()
        assert palette.labelFont == previousFont
        assert v.exportOverlay.titleBlockImage is not previousImage
        assert previousImage != v.exportOverlay.titleBlockImage
        panel.SetOverride("linesColor", "#ffeedd")
        v.grab()
        previousImage = v.exportOverlay.titleBlockImage
        palette.themeColors["rulerMajorTick"] = "#bbccdd"
        v.grab()
        assert v.exportOverlay.titleBlockImage is not previousImage
        assert v.exportOverlay.titleBlockImage.pixelColor(0, 0) == QtGui.QColor("#bbccdd")
        panel.SetOverride("canvasColor", "#80406080")
        v.grab()
        cached = v.exportOverlay.titleBlockImage
        sampleX, sampleY = cached.width() - 30, 100
        assert cached.pixelColor(sampleX, sampleY).alpha() == 128
        exported = panel.Render("png")
        block = v.exportOverlay.titleBlockLayout[2]
        assert exported.pixelColor(int(block[0]) + sampleX, sampleY) == cached.pixelColor(sampleX, sampleY), "Title background was composited twice"
    print(f"Title block colours verified for {len(themes)} canvas themes")


if __name__ == "__main__":
    Main()
