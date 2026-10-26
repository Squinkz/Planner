"""Furnishings cannot trim any architectural measurement category."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Stair, Counter, Railing, Furnishing


def Dimensions(viewport, obj):
    if type(obj) is Stair:
        return viewport.StairDimensions([obj])
    if type(obj) is Counter:
        return viewport.ConnectedCounterPath([obj])[1]
    if type(obj) is Railing:
        return viewport.ConnectedRailingPath([obj])[1]
    path = viewport.ConnectedWallPath([obj])
    return viewport.WallDimensions([obj], path, [], cachedBoundary = True)


def Main():
    p = QtCore.QPointF
    with ExampleWindow() as (main, folder):
        v = main.viewport
        for cls in (Wall, Stair, Counter, Railing):
            obj = cls(p(-1000, 0), p(1000, 0), 600)
            InstallScene(main, [obj])
            baseline = Dimensions(v, obj)
            for key in ("desk", "table_dining_round_6"):
                furnishing = Furnishing(v.furnishingDefinitions[key], p(0, 600))
                furnishing.width = 4000
                furnishing.firstVertex, furnishing.secondVertex = p(0, -2000), p(0, 2000)
                v.furnishings = [furnishing]
                assert Dimensions(v, obj) == baseline, (cls, key)
                furnishing.firstVertex += p(100, -500)
                furnishing.secondVertex += p(100, -500)
                assert Dimensions(v, obj) == baseline, (cls, key)
            if cls in (Stair, Counter):
                v.walls.append(Wall(p(-1000, 420), p(1000, 420), 240))
                assert len(Dimensions(v, obj)) == 3
    print("PASS: ordinary/compound furnishings never block wall, stair, counter or railing dimensions")


if __name__ == "__main__":
    Main()
