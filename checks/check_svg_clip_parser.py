"""Exact frozen clip geometry for absolute, relative and implicit SVG commands."""
import os
from pathlib import Path
import sys
from xml.etree import ElementTree

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from fixtures.svg_preview_reference_20261019 import SvgClipPath as ReferenceSvgClipPath
from planner_app.graphics.svg_preview import SvgClipPath


def Main():
    sources = (
        "M10 20 30 40 50 60Z",
        "m10 20 30 40 -10 -20z",
        "M10 20 H70 90 V100 120 H10 Z",
        "m10 20 h70 -20 v100 -40 h-10 z",
        "M10 20 Q30 40 50 60 70 80 90 100Z",
        "m10 20 q30 40 50 60 -20 -10 30 40z",
        "M10 20 C30 40 50 60 70 80 90 100 110 120 130 140Z",
        "m10 20 c30 40 50 60 70 80 -20 -30 40 50 60 70z",
        "M10 20 l30 40 H90 v-15 Q40 30 20 10 c5 10 15 20 25 30 Z m5 7 l3 4z",
        "M.5-.25L1e2-2e1 3E+1,+4e-2Z",
        "M0 0 L0 0 M10 10 L10 10Z m5 5 2 3 4 5z",
        "M0 0L100 0L100 100L0 100ZM20 20L80 20L80 80L20 80Z",
        "",
    )
    for source in sources:
        for rule in (None, "evenodd", "nonzero"):
            element = ElementTree.Element("path", d = source)
            if rule is not None:
                element.set("clip-rule", rule)
            actual, expected = SvgClipPath(element), ReferenceSvgClipPath(element)
            assert actual == expected, (source, rule)
            assert actual.elementCount() == expected.elementCount()
            for index in range(actual.elementCount()):
                first, second = actual.elementAt(index), expected.elementAt(index)
                assert (first.x, first.y, first.type) == (second.x, second.y, second.type)
            actual.translate(5, 7)
            assert SvgClipPath(element) == expected, "Caller mutated cached clip geometry"
            assert expected.fillRule() == (QtCore.Qt.FillRule.OddEvenFill if rule == "evenodd" else QtCore.Qt.FillRule.WindingFill)
    print("39 exact frozen clip-path cases passed, including implicit/relative commands and independent cache values")


if __name__ == "__main__":
    Main()
