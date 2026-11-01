"""PDF material strokes stay vector, including points/curves and wall holes."""
import os
from pathlib import Path
import re
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
import numpy as np
from PySide6 import QtCore, QtGui, QtPdf
from shiboken6 import delete
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.export_plan import RenderPlan
from planner_app.graphics import palette
from planner_app.graphics.svg_preview import SvgPreviewRenderer
from planner_app.graphics.theme import wallMaterials
from planner_app.models import Wall
from planner_app.pdf_export import PdfExporter
from planner_app.print_layout import PrintPageLayout, printPaperSizes


def Main():
    with ExampleWindow() as (main, folder):
        points = [(1000, 1000), (20000, 2700), (19000, 16000), (0, 14300)]
        walls = [Wall(QtCore.QPointF(*first), QtCore.QPointF(*second), 500)
                 for first, second in zip(points, points[1:] + points[:1])]
        InstallScene(main, walls)
        palette.SetThemes(canvasTheme = "Light Canvas")
        palette.themeColors["materialPattern"] = "#ff0000"
        layout = PrintPageLayout({}, 0, {})
        pdf = PdfExporter(folder / "materials.pdf")
        references = []
        for material in wallMaterials:
            for wall in walls:
                wall.material = material
            data = main.BuildProjectData(includeHistory = False)
            data["settings"].update(showGrid = False, showMeasurements = False)
            svg = RenderPlan(folder / "material.plan", 100, (0, 0, *layout["tile"]), projectData = data,
                outputFormat = "svg", applyTheme = False, architecturalScale = 100, border = "None", pageSize = layout["paper"])
            pdf.AddPage(svg, layout["paper"])
            references.append(svg)
        pdf.Close()
        content = (folder / "materials.pdf").read_bytes()
        assert not re.search(rb"/Subtype\s*/Image\b", content)
        document = QtPdf.QPdfDocument()
        assert document.load(str(folder / "materials.pdf")).value == 0
        assert document.pageCount() == len(wallMaterials)
        failures = []
        for index, svg in enumerate(references):
            renderer = SvgPreviewRenderer(svg)
            reference = QtGui.QImage(3508, 2480, QtGui.QImage.Format.Format_RGBA8888)
            reference.fill(QtCore.Qt.GlobalColor.white)
            with QtGui.QPainter(reference) as painter:
                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
                renderer.render(painter)
            delete(renderer)
            actual = document.render(index, reference.size()).convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
            arrays = [np.frombuffer(image.constBits(), dtype = np.uint8).reshape(image.height(), image.width(), 4).astype(np.int16)
                      for image in (actual, reference)]
            difference = np.abs(arrays[0] - arrays[1])
            if difference.mean() >= 3:
                failures.append((wallMaterials[index], difference.mean()))
            counts = [int(np.count_nonzero((array[:, :, 0] > array[:, :, 1] + 40) & (array[:, :, 0] > array[:, :, 2] + 40)))
                      for array in arrays]
            if wallMaterials[index] not in ("Generic", "Lumber"):
                weights = [int(np.maximum(0, array[:, :, 0] - array[:, :, 1]).sum()) for array in arrays]
                if counts[1] <= 10 or not .55 < weights[0] / weights[1] < 1.5:
                    failures.append((wallMaterials[index], counts, weights))
        document.close()
        delete(document)
        assert not failures, failures
        # A single writer must preserve every paper size in both orientations,
        # even when changing the page layout after painting an earlier page.
        pdf = PdfExporter(folder / "paper-sizes.pdf")
        papers = [paper for size in printPaperSizes.values() for paper in (size, tuple(reversed(size)))]
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100"><path fill="#0088ff" d="M0 0 H200 V100 H0Z"/></svg>'
        for paper in papers:
            pdf.AddPage(svg, paper)
        pdf.Close()
        document = QtPdf.QPdfDocument()
        assert document.load(str(folder / "paper-sizes.pdf")).value == 0
        assert document.pageCount() == len(papers)
        failures = []
        for index, paper in enumerate(papers):
            points = document.pagePointSize(index)
            actual = (points.width() * 25.4 / 72, points.height() * 25.4 / 72)
            # Qt's page backend rounds MediaBox extents to the nearest point.
            if any(abs(first - second) > 25.4 / 144 + 1e-8 for first, second in zip(actual, paper)):
                failures.append((index, paper, actual))
            image = document.render(index, QtCore.QSize(200, 100))
            assert image.pixelColor(100, 50) == QtGui.QColor("#0088ff")
        document.close()
        delete(document)
        assert not failures, failures
    print("PASS: vector PDF hatches for every material, angled wall holes, point/curve patterns and all paper sizes/orientations")


if __name__ == "__main__":
    Main()
