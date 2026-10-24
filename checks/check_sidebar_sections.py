"""Stacker section headings and shared material swatches in both dropdowns."""
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, SectionHeading, Wall
from theme import BuildStyle, wallMaterials


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    window = MainWindow()
    window.resize(1440, 1300)
    window.show()
    app.processEvents()
    headings = window.buildScrollArea.widget().findChildren(SectionHeading)
    assert [heading.accessibleName() for heading in headings] == ["Wall Tool", "Objects"]
    assert [heading.accessibleName() for heading in window.propertiesPanel.findChildren(SectionHeading)] == ["Object Properties"]
    labels = [label.text() for label in window.buildScrollArea.widget().findChildren(QtWidgets.QLabel)]
    assert "Thickness" not in labels and "New Wall Type" not in labels
    hashes = set()
    for index, material in enumerate(wallMaterials):
        firstIcon = window.newWallMaterialField.itemIcon(index)
        secondIcon = window.materialField.itemIcon(index)
        assert not firstIcon.isNull() and firstIcon.cacheKey() == secondIcon.cacheKey()
        image = firstIcon.pixmap(32, 20).toImage()
        hashes.add(hashlib.sha256(bytes(image.constBits())).hexdigest())
        assert window.newWallMaterialField.itemText(index) == window.materialField.itemText(index) == material
    assert len(hashes) == len(wallMaterials)
    wall = Wall(QtCore.QPointF(), QtCore.QPointF(3000, 0), material = "Wood")
    window.viewport.walls = [wall]
    window.viewport.SetSelection([(wall, None)])
    window.newWallMaterialField.setCurrentText("Ceramic")
    assert wall.material == "Wood" and window.viewport.newWallMaterial == "Ceramic"
    app.processEvents()
    screenshotFolder = Path(__file__).resolve().parent.parent / "screenshots"
    window.sidebarPanel.grab().save(str(screenshotFolder / "sidebar-sections.png"))
    window.newWallMaterialField.showPopup()
    app.processEvents()
    window.newWallMaterialField.view().window().grab().save(str(screenshotFolder / "material-swatch-menu.png"))
    window.newWallMaterialField.hidePopup()
    window.close()
    print("PASS: Walls/Objects/Object Properties sections, no Thickness label, distinct shared swatches and independent new-wall material selection.")


if __name__ == "__main__":
    Main()
