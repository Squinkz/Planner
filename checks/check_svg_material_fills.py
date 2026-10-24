"""Material exports paint a continuous wall base beneath transparent hatches."""
import os
import sys
from pathlib import Path
from xml.etree import ElementTree

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtWidgets
from planner_app.export_plan import VectorizeMaterials
from planner_app.graphics.theme import materialPatternSpacings
from planner_app.graphics.palette import themeColors


def Main():
    app = QtWidgets.QApplication([])
    source = b'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200" viewBox="0 0 400 200">
      <defs><clipPath id="crop"><path fill-rule="evenodd" d="M0 0H400V200H0Z"/></clipPath></defs>
      <g clip-path="url(#crop)"><g fill="#010001" stroke="none" transform="matrix(1.37,0,0,0.83,0.3,0.7)">
        <path fill-rule="evenodd" d="M10 10H280V190H10Z M40 40H80V80H40Z"/>
      </g></g>
    </svg>'''
    namespace = {"s": "http://www.w3.org/2000/svg"}
    for material in materialPatternSpacings:
        root = ElementTree.fromstring(VectorizeMaterials(source, {"#010001": material}))
        pattern = root.find("s:defs/s:pattern", namespace)
        assert pattern is not None
        spacing = materialPatternSpacings[material]
        assert not any(float(rect.get("width", 0)) >= spacing and float(rect.get("height", 0)) >= spacing
                       for rect in pattern.findall(".//s:rect", namespace)), (material, "Background is still tiled")
        group = root.find("s:g", namespace)
        base, hatch = list(group)
        assert base.get("fill") == themeColors["wallFill"]
        assert hatch.get("fill") == "url(#" + pattern.get("id") + ")"
        assert base.get("transform") == hatch.get("transform")
        assert ElementTree.tostring(base[0]) == ElementTree.tostring(hatch[0]), "Wall holes or shape changed"
        assert base.get("stroke") == hatch.get("stroke") == "none"
        assert root.find(".//s:clipPath/s:path", namespace).get("clip-rule") == "evenodd"


if __name__ == "__main__":
    Main()
