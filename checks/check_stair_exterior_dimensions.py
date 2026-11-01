"""Stair room boundaries preserve outward exterior/stacked dimension directions."""
import json
import math
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_room_detection import Rectangle
from planner_app.models import Wall, Stair
from planner_app.export_plan import RenderPlan
from planner_app.viewport.rendering import RenderingMixin


def AssertOutward(envelope, spans):
    assert spans
    for first, second, owners, *tier in spans:
        direction = second - first
        length = math.hypot(direction.x(), direction.y())
        if length < .001:
            continue
        # The renderer offsets toward the left of a directed world span.
        normal = QtCore.QPointF(-direction.y(), direction.x()) / length
        midpoint = (first + second) / 2
        distance = max(owner.width for owner in owners) + 1
        assert not envelope.contains(midpoint + normal * distance), ("Dimension points inward", first, second, tier)
        assert envelope.contains(midpoint - normal * distance), ("Opposite side is not inside", first, second, tier)


def Main():
    with ExampleWindow() as (main, folder):
        view = main.viewport
        point = QtCore.QPointF
        view.showMeasurements = True
        view.measurementVisibility = dict.fromkeys(view.measurementVisibility, False)
        view.measurementVisibility["walls"] = True
        view.zoom = .3
        view.showTips = False
        for mode in ("Exterior", "Exterior stacked"):
            view.wallMeasurementMode = mode
            for reference in ("Wall faces", "Centerline"):
                view.wallMeasurementReference = reference
                walls = Rectangle(-2000, -2000, 4000, 4000)
                InstallScene(main, walls)
                view.grab()
                baseline = [(first, second, tuple(owners), *tier)
                            for first, second, owners, *tier in view.sceneMeasurements[1] + view.sceneMeasurements[2]]
                view.walls.append(Stair(point(-1000, -1000), point(1000, -1000), 600))
                view.grab()
                spans = view.sceneMeasurements[1] + view.sceneMeasurements[2]
                assert {(a.toTuple(), b.toTuple(), tuple(id(owner) for owner in owners), tuple(tier))
                        for a, b, owners, *tier in spans} == {
                    (a.toTuple(), b.toTuple(), tuple(id(owner) for owner in owners), tuple(tier))
                    for a, b, owners, *tier in baseline}, (mode, reference)
                AssertOutward(view.roomDetection.exteriorPath, spans)
                try:
                    AssertOutward(view.roomDetection.exteriorPath, [(second, first, owners, *tier) for first, second, owners, *tier in spans])
                except AssertionError:
                    pass
                else:
                    raise AssertionError("Direction regression check accepted reversed dimensions")
        # Structural coordinates from scissor_med, the reported mirrored duplex.
        records = json.loads((Path(__file__).parent / "fixtures/scissor_stair_dimensions.json").read_text(encoding = "utf-8"))
        objects = []
        for record in records:
            obj = (Stair if record["type"] == "Stair" else Wall)(point(*record["first"]), point(*record["second"]), record["width"])
            obj.firstMiter, obj.secondMiter = record["firstMiter"], record["secondMiter"]
            obj.objectId = record["id"]
            objects.append(obj)
        InstallScene(main, objects)
        for mode in ("Exterior", "Exterior stacked"):
            view.wallMeasurementMode = mode
            for reference in ("Wall faces", "Centerline"):
                view.wallMeasurementReference = reference
                for zoom in (.2, .7):
                    view.zoom = zoom
                    view.panOffset += point(13, -7)
                    view.grab()
                    AssertOutward(view.roomDetection.exteriorPath, view.sceneMeasurements[1] + view.sceneMeasurements[2])
                data = main.BuildProjectData(includeHistory = False)
                observed = []
                draw = RenderingMixin.DrawSceneMeasurements

                def Observe(viewport, *args, **kwargs):
                    result = draw(viewport, *args, **kwargs)
                    observed.append((QtGui.QPainterPath(viewport.roomDetection.exteriorPath),
                                     viewport.sceneMeasurements[1] + viewport.sceneMeasurements[2]))
                    return result

                with patch.object(RenderingMixin, "DrawSceneMeasurements", Observe):
                    for kind in ("png", "svg"):
                        image = RenderPlan(folder / "directions.plan", 80, bounds = (-10000, -7000, 20000, 14000),
                                           projectData = data, outputFormat = kind, applyTheme = False)
                        assert image if kind == "png" else QtSvg.QSvgRenderer(image).isValid()
                assert len(observed) == 2
                for envelope, spans in observed:
                    AssertOutward(envelope, spans)
    print("Stairs preserve outward wall/centreline dimension spans, stacked tiers, camera changes and PNG/SVG directions")


if __name__ == "__main__":
    Main()
