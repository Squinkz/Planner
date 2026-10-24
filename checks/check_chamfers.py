"""Analytic chamfer planes, unequal-width body clipping and desktop consistency."""
import itertools
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

workspace = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(workspace / "planner-main"))
from planner_app.geometry.junctions import BuildWallJunction
from planner_app.geometry.polygons import ClipHalfPlane


def CheckNumeric():
    count = 0
    fixture = json.loads((workspace / "docs/parity/chamfer-examples.json").read_text(encoding = "utf-8"))
    for case in fixture["cases"]:
        firstHalf, secondHalf = (width / 2 for width in case["widths"])
        result = BuildWallJunction((0, 0), [((1, 0), firstHalf, "a"), ((0, 1), secondHalf, "b")],
                                   [case["amount"]] * 2, .0001)
        assert all(abs(x + y - case["xPlusY"]) < 1e-10 for x, y in case["endpoints"])
        if case["amount"] == 0:
            assert len(result[4]["a"]) == int(firstHalf != secondHalf)
            assert all(math.dist(point, (-secondHalf, -firstHalf)) < 1e-10 for point in case["endpoints"])
        else:
            origin, normal = result[4]["a"][-1]
            assert abs(sum(origin) - case["xPlusY"]) < 1e-10
            for x, y in case["endpoints"]:
                assert abs((x - origin[0]) * normal[0] + (y - origin[1]) * normal[1]) < 1e-10
                assert abs(x + secondHalf) < 1e-10 or abs(y + firstHalf) < 1e-10
    for degrees, widths, amount in itertools.product((5, 15, 30, 60, 90, 120, 150),
                                                      ((120, 120), (120, 240), (80, 600)), (.25, .5, .75, 1)):
        angle = math.radians(degrees)
        cosine, sine = math.cos(angle), math.sin(angle)
        firstHalf, secondHalf = widths[0] / 2, widths[1] / 2
        rays = [((1, 0), firstHalf, "a"), ((cosine, sine), secondHalf, "b")]
        polygons, joins, transitions, sectors, cuts = BuildWallJunction((0, 0), rays, [amount, amount], .0001)
        assert len(cuts["a"]) == len(cuts["b"]) == 1 + int(firstHalf != secondHalf)
        origin, normal = cuts["a"][-1]
        assert cuts["a"][-1] == cuts["b"][-1]
        tip = ((-secondHalf - firstHalf * cosine) / sine, -firstHalf)
        midpoint = (-sine * secondHalf / 2, (cosine * secondHalf - firstHalf) / 2)
        expected = tuple(tip[index] + (midpoint[index] - tip[index]) * amount for index in (0, 1))
        assert math.dist(origin, expected) < 1e-8, (degrees, widths, amount, origin, expected)
        assert abs(math.hypot(*normal) - 1) < 1e-12
        assert abs(normal[0] * sine - normal[1] * (1 + cosine)) < 1e-12
        assert normal[0] < 0 and normal[1] < 0
        # No residual point may protrude beyond the plane in either owner patch.
        for owner, polygon in joins:
            assert all((x - origin[0]) * normal[0] + (y - origin[1]) * normal[1] <= 1e-8 for x, y in polygon)
        count += 1
    # Explicit right-angle result: halfway is a face, not the old single peak.
    polygons, joins, transitions, sectors, cuts = BuildWallJunction((0, 0),
        [((1, 0), 120, "a"), ((0, 1), 120, "b")], [.5, .5], .0001)
    outer = polygons[-1]
    assert all(any(math.dist(point, expected) < 1e-10 for point in outer) for expected in ((-60, -120), (-120, -60))), outer
    assert (-90, -90) not in outer, outer
    original = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert ClipHalfPlane(original, (5, 0), (1, 0)) == [(0, 0), (5, 0), (5, 10), (0, 10)]
    assert original == [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert ClipHalfPlane([], (0, 0), (1, 0)) == []
    assert BuildWallJunction((0, 0), [], [], .0001) == ([], [], [], {}, {})
    for offset in ((1e8, -1e8), (-1e8, 1e8)):
        result = BuildWallJunction(offset, [((1, 0), 120, "a"), ((0, 1), 120, "b")], [.5, .5], .0001)
        origin, normal = result[4]["a"][0]
        assert math.dist(origin, (offset[0] - 90, offset[1] - 90)) < 1e-6
    # Straight, duplicate and guarded near-straight unequal rays remain finite.
    for angle in (0, math.pi, math.pi - 1e-8, math.pi - .001):
        result = BuildWallJunction((0, 0), [((1, 0), 40, "a"), ((math.cos(angle), math.sin(angle)), 300, "b")], [1, 1], .0001)
        assert all(math.isfinite(coordinate) for polygon in result[0] for point in polygon for coordinate in point)
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print(f"PASS: {count} analytic chamfers, explicit flat face, clipping, straight/near-straight stability without Qt")


def CheckRaster(actual, expected, caseId):
    from PySide6 import QtGui
    assert not actual.isNull() and not expected.isNull(), (caseId, "missing image")
    assert actual.size() == expected.size(), (caseId, "image dimensions changed")
    actualRgba = actual.convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
    expectedRgba = expected.convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
    actualBytes = bytes(actualRgba.constBits())
    expectedBytes = bytes(expectedRgba.constBits())
    differentPixels = 0
    for offset in range(0, len(actualBytes), 4):
        actualPixel, expectedPixel = actualBytes[offset:offset + 4], expectedBytes[offset:offset + 4]
        if actualPixel == expectedPixel:
            continue
        differentPixels += 1
        pixel = offset // 4
        position = (pixel % actual.width(), pixel // actual.width())
        assert all(abs(a - e) <= 1 for a, e in zip(actualPixel, expectedPixel)), (caseId, position, "channel difference exceeds 1")
        assert differentPixels <= 5, (caseId, "more than 5 pixels differ")


def Main():
    result = subprocess.run([sys.executable, "-S", __file__, "--numeric-only"], capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import QtCore, QtGui, QtWidgets
    from planner_app.models import Wall
    from planner_app.viewport.geometry import FootprintGeometry
    app = QtWidgets.QApplication([])
    count = 0
    for degrees, widths, amount, rotation, scale in itertools.product((5, 30, 90, 150),
            ((120, 120), (120, 240), (80, 600)), (.5, 1), (0, 37), (.02, .2, 2)):
        angle = math.radians(degrees)
        transform = QtGui.QTransform().rotate(rotation)
        firstHalf, secondHalf = widths[0] / 2, widths[1] / 2
        direction = QtCore.QPointF(math.cos(angle), math.sin(angle))
        tip = QtCore.QPointF((-secondHalf - firstHalf * math.cos(angle)) / math.sin(angle), -firstHalf)
        midpoint = QtCore.QPointF(-math.sin(angle) * secondHalf / 2, (math.cos(angle) * secondHalf - firstHalf) / 2)
        cutPoint = transform.map(tip + (midpoint - tip) * amount)
        normal = -(QtCore.QPointF(1, 0) + direction)
        normal /= math.hypot(normal.x(), normal.y())
        normal = transform.map(normal)
        # The plane origin need not lie on the physical face for unequal,
        # obtuse joins. Sample between its actual offset-edge intersections.
        firstOffset = transform.map(QtCore.QPointF(0, -firstHalf))
        secondOffset = transform.map(QtCore.QPointF(-math.sin(angle) * secondHalf, math.cos(angle) * secondHalf))
        endpoints = []
        for offset, axis in ((firstOffset, transform.map(QtCore.QPointF(1, 0))), (secondOffset, transform.map(direction))):
            delta = cutPoint - offset
            distance = (delta.x() * normal.x() + delta.y() * normal.y()) / (axis.x() * normal.x() + axis.y() * normal.y())
            endpoints.append(offset + axis * distance)
        sample = (endpoints[0] + endpoints[1]) / 2
        walls = [Wall(QtCore.QPointF(), transform.map(QtCore.QPointF(5000, 0)), widths[0], amount, 0),
                 Wall(QtCore.QPointF(), transform.map(direction * 5000), widths[1], amount, 0)]
        original = None
        for reverseOrder, reverseEndpoints in itertools.product((False, True), repeat = 2):
            ordered = list(reversed(walls)) if reverseOrder else list(walls)
            if reverseEndpoints:
                ordered = [Wall(wall.secondVertex, wall.firstVertex, wall.width, 0, amount) for wall in ordered]
            geometry = FootprintGeometry(scale)
            path = geometry.ConnectedWallPath(ordered)
            assert not path.contains(geometry.WorldToViewport(sample + normal * 1)), (degrees, widths, amount, "outside")
            assert path.contains(geometry.WorldToViewport(sample - normal * 1)), (degrees, widths, amount, "inside")
            for owner, polygon in geometry.wallFillPolygons:
                for point in polygon:
                    world = QtCore.QPointF(point.x() / scale, -point.y() / scale)
                    delta = world - cutPoint
                    assert delta.x() * normal.x() + delta.y() * normal.y() <= 1e-6, (degrees, widths, amount, world)
            samples = [path.contains(geometry.WorldToViewport(sample + normal * distance)) for distance in (-5, -1, 1, 5)]
            if original is None:
                original = samples
            assert samples == original
            warm = geometry.wallGeometryPath
            geometry.ConnectedWallPath(ordered)
            assert geometry.wallGeometryPath is warm, "warm geometry should be reused"
        count += 1
    print(f"PASS: {count} angle/width/amount/rotation/scale cases, each with order/endpoint reversal, clipped materials and cache reuse")
    from planner_app.graphics import palette
    from planner_app.export_plan import RenderPlan
    directory = workspace / "docs/parity/reference/chamfers"
    manifest = json.loads((directory / "manifest.json").read_text(encoding = "utf-8"))
    palette.SetThemes(canvasTheme = "Light Canvas")
    # Exercise both tolerance boundaries independently of the saved renders.
    reference = QtGui.QImage(8, 2, QtGui.QImage.Format.Format_RGBA8888)
    reference.fill(QtGui.QColor(100, 100, 100, 255))
    CheckRaster(reference, reference, "identical")
    withinLimit = reference.copy()
    for x in range(5):
        withinLimit.setPixelColor(x, 0, QtGui.QColor(101, 99, 100, 254))
    CheckRaster(withinLimit, reference, "five pixels, channel differences of one")
    sixPixels = withinLimit.copy()
    sixPixels.setPixelColor(5, 0, QtGui.QColor(101, 100, 100, 255))
    for invalid, reason in ((sixPixels, "six pixels"),
                            (QtGui.QImage(7, 2, QtGui.QImage.Format.Format_RGBA8888), "different dimensions")):
        try:
            CheckRaster(invalid, reference, reason)
        except AssertionError:
            pass
        else:
            raise AssertionError("Raster comparison accepted " + reason)
    for channel in range(4):
        invalid = reference.copy()
        color = [100, 100, 100, 255]
        color[channel] += -2 if channel == 3 else 2
        invalid.setPixelColor(0, 0, QtGui.QColor(*color))
        try:
            CheckRaster(invalid, reference, "channel " + str(channel))
        except AssertionError:
            pass
        else:
            raise AssertionError("Raster comparison accepted a channel difference of two")
    for case in manifest["cases"]:
        image = RenderPlan(directory / case["plan"], case["scalePixelsPerMeter"],
                           bounds = case["boundsMillimeters"], applyTheme = False)
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        reference = QtGui.QImage(str(directory / case["image"])).convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
        assert not reference.isNull(), (case["id"], "missing reference image")
        assert hashlib.sha256(bytes(reference.constBits())).hexdigest() == case["rgbaSha256"], (case["id"], "reference changed")
        CheckRaster(image, reference, case["id"])
    print(f"PASS: {len(manifest['cases'])} frozen chamfer material renders")


if __name__ == "__main__":
    if "--numeric-only" in sys.argv:
        CheckNumeric()
    else:
        Main()
