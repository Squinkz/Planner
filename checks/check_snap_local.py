"""Exact ordered clipping and snapping/render parity for fragment-local work."""
from contextlib import ExitStack, contextmanager
import math
import os
from pathlib import Path
import random
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "tools")]
from PySide6 import QtWidgets
from planner_app.geometry import polygons
from planner_app.viewport import geometry, polygon_clipping
from fixtures.snap_local_reference_20261101 import ReferenceGeometry
from fixtures.snap_subtraction_reference_20261101 import SubtractConvexPolygon as OriginalSubtract
import check_local_paint
import check_snap_preparation


@contextmanager
def Baseline(enabled, mode = None):
    with ExitStack() as stack:
        if enabled:
            stack.enter_context(patch.object(geometry.GeometryMixin, "BuildWallComponent", ReferenceGeometry.BuildWallComponent))
            stack.enter_context(patch.object(polygon_clipping, "SubtractCoordinates", OriginalSubtract))
            stack.enter_context(patch.object(polygons, "SubtractConvexPolygon", OriginalSubtract))
        yield


def CheckClipping():
    randomizer = random.Random(20261102)
    comparisons = 0
    for case in range(1000):
        offset = (0, 1e8, -1e8, 1e15, -1e15)[case % 5]
        scale = (1e-5, .01, 1, 1000, 1e6)[case // 5 % 5]
        inputs = []
        for index in range(12):
            angle = randomizer.random() * math.tau
            cosine, sine = math.cos(angle), math.sin(angle)
            x, y = randomizer.uniform(-2, 2), randomizer.uniform(-2, 2)
            width, height = randomizer.uniform(.1, 3), randomizer.uniform(.1, 3)
            points = [(offset + (x + a * cosine - b * sine) * scale,
                       offset + (y + a * sine + b * cosine) * scale)
                      for a, b in ((0, 0), (width, 0), (width, height), (0, height))]
            if index % 3 == 0:
                points.reverse()
            if case % 7 == 0:
                points = points[:index % 5]
            if case % 11 == 0 and points:
                points.append(points[-1])
            inputs.append(points)
        # Prefix comparisons include deletion, insertion and order changes,
        # touching/degenerate rectangles, distant origins and both windings.
        for order in (inputs[1:], list(reversed(inputs[1:]))):
            expected = [inputs[0]]
            for index, cutter in enumerate(order):
                expected = [piece for fragment in expected for piece in OriginalSubtract(fragment, cutter)]
                actual = polygons.SubtractConvexPolygons(inputs[0], order[:index + 1])
                expectedHex = [[(float(x).hex(), float(y).hex()) for x, y in piece] for piece in expected]
                actualHex = [[(float(x).hex(), float(y).hex()) for x, y in piece] for piece in actual]
                assert actualHex == expectedHex, (case, index)
                assert polygons.SubtractConvexPolygon(inputs[0], cutter) == OriginalSubtract(inputs[0], cutter)
                comparisons += 1
    # Explicit bounds-edge rounding and uncertain values must retain the old
    # result or old exception, rather than silently pruning a possible overlap.
    shapes = [[], [(0., 0.)], [(0., 0.), (1., 0.), (1., 1.), (0., 1.)],
              [(-0., 0.), (1., 0.), (1., 1e-10)],
              [(1., 0.), (2., 0.), (2., 1.), (1., 1.)],
              [(math.nextafter(1., 0.), 0.), (2., 0.), (2., 1.), (math.nextafter(1., 0.), 1.)],
              [(math.nextafter(1., 2.), 0.), (2., 0.), (2., 1.), (math.nextafter(1., 2.), 1.)],
              [(1e100, -1e100), (1e100 + 1e85, -1e100), (1e100, -1e100 + 1e85)]]
    for value in (float("nan"), float("inf"), -float("inf")):
        shapes.append([(value, 0.), (1., 0.), (1., 1.)])
    for source in shapes:
        for cutter in shapes:
            results = []
            for variant in range(2):
                try:
                    pieces = (OriginalSubtract(source, cutter) if variant == 0 else
                              polygons.SubtractConvexPolygons(source, [cutter]))
                    result = [[(float(x).hex(), float(y).hex()) for x, y in piece] for piece in pieces]
                except (ValueError, OverflowError) as error:
                    result = type(error)
                results.append(result)
            assert results[0] == results[1], (source, cutter, results)
            comparisons += 1
    return comparisons


def Main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    clipping = CheckClipping()
    with patch.object(check_snap_preparation, "Baseline", Baseline):
        snapshots = check_snap_preparation.CheckSharing()
    with patch.object(check_local_paint, "Baseline", Baseline):
        frames = check_local_paint.CheckProject()
    print(f"PASS: {clipping} exact clipping comparisons, {snapshots} collision snapshots with bounded/disabled "
          f"budgets and cleanup, {frames} exact model/snap/validation/pixel frames.")


if __name__ == "__main__":
    Main()
