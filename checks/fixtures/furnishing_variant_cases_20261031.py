"""Shared real artwork and nested SVGs for variant parity and timing probes."""
from pathlib import Path
from unittest.mock import patch
from planner_app.graphics import furnishings
from fixtures.furnishing_svg_reference_20261031 import FurnishingSvgRenderer as ReferenceRenderer


def MakeRenderer(source, nominalSize, reference = False, **options):
    if reference:
        with patch.object(furnishings, "FurnishingSvgRenderer", ReferenceRenderer):
            return furnishings.FurnishingRenderer(source, nominalSize = nominalSize, **options)
    return furnishings.FurnishingRenderer(source, nominalSize = nominalSize, **options)


def VariantCases():
    folder = Path(__file__).resolve().parents[2] / "planner-main/furnishings/images"
    washer = (folder / "washer.svg").read_bytes()
    table = (folder / "coffee_table.svg").read_bytes()
    cases = [("washer", washer, (600, 600)), ("coffee_table", table, (1200, 600))]
    for count in (12, 48):
        components = [{"definition": {"graphicData": washer if index % 2 else table},
                       "x": index % 4 * 1300, "y": index // 4 * 900,
                       "width": 600 if index % 2 else 1200, "length": 600,
                       "angle": index * 13, "flipHorizontal": index % 3 == 0, "zIndex": index}
                      for index in range(count)]
        source, width, length, center = furnishings.CompoundFurnishingSvg(components)
        cases.append(("compound" + str(count), source, (width, length)))
    return cases


def EdgeSource():
    return b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="-10 -5 120 90" preserveAspectRatio="none">
      <title>plannerSvgTransformSlot0_ &amp; unchanged artwork</title>
      <defs><linearGradient id="ink"><stop stop-color="#123456"/><stop offset="1" stop-color="#abcdef"/></linearGradient>
        <clipPath id="clip"><rect x="-5" y="0" width="100" height="70" rx="10"/></clipPath></defs>
      <g transform="translate(2 3) rotate(17 50 30)" opacity=".6" clip-path="url(#clip)">
        <rect x="5" y="5" width="80" height="50" fill="url(#ink)"/>
        <g data-planner-fixed="true" data-planner-fixed-anchor="61 21"><circle cx="61" cy="21" r="8" fill="red"/></g>
        <text id="caption" x="20" y="35" transform="translate(1 2) scale(.8)" font-size="14" fill="black">A &amp; B<tspan dy="2">!</tspan></text>
        <rect x="30" y="25" width="20" height="10" fill="white" opacity=".7"/>
      </g></svg>'''
