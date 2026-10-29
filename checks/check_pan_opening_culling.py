"""Opening clip culling and prepared endpoints preserve native pan pixels."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
os.environ["QT_QPA_PLATFORM"] = "offscreen"


def Child():
    from PySide6 import QtCore, QtWidgets
    from planner_app.models import Wall
    from planner_app.object_schema import openingClasses
    from planner_app.viewport.widget import DrawingViewport
    from check_pan_dpi import CompareDirect
    app = QtWidgets.QApplication([])
    view = DrawingViewport()
    view.resize(1001, 701)
    view.showTips = view.showMeasurements = False
    view.performanceTimer.stop()
    point = QtCore.QPointF
    for index, kind in enumerate(openingClasses.values()):
        center = point((index % 7 - 3) * 2000, (index // 7 - .5) * 2800)
        axis = point(0, 800) if index % 2 else point(800, 0)
        wall = Wall(center - axis, center + axis, 240)
        opening = kind(wall, .2, .8)
        if hasattr(opening, "windowWell"):
            opening.windowWell, opening.wellDepth, opening.wellDashed = True, 450, True
        if hasattr(opening, "hingeAtSecond"): opening.hingeAtSecond = True
        if hasattr(opening, "swingsOutwards"): opening.swingsOutwards = True
        view.walls.append(wall)
        view.windows.append(opening)
    view.zoom = .25
    view.show()
    app.processEvents()
    view.performanceLabel.hide()
    ratio = view.devicePixelRatioF()
    frames = 0
    for style in ("Material", "Outline", "Solid"):
        view.wallStyle = style
        view.panOffset = point(.3, -.7)
        view.viewportPanRaster = None
        view.isPanning = True
        view.grab()
        for delta in (point(7, 3), point(-7, -3), point(3, -7), point(-3, 7)):
            for frame in range(4):
                view.panOffset += delta / ratio
                CompareDirect(view)
                frames += 1
        view.panOffset += point(.31, .43) / ratio
        CompareDirect(view)
    # Camera-only movement keeps detached world endpoints. Model and parent
    # changes rebuild them before drawing, including selection/undo pathways.
    prepared = view.scenePreparation[1]["openingPositions"]
    view.panOffset += point(3, 1) / ratio
    CompareDirect(view)
    assert view.scenePreparation[1]["openingPositions"] is prepared
    for change in ("opening", "parent", "visibility", "well", "hinge"):
        previous = view.scenePreparation[1]["openingPositions"]
        if change == "opening": view.windows[1].centerFraction += .01
        elif change == "parent": view.walls[1].secondVertex.setY(view.walls[1].secondVertex.y() + 50)
        elif change == "visibility": view.visibility["Windows"] = False
        elif change == "well":
            obj = next(obj for obj in view.windows if type(obj).__name__ == "Window")
            obj.wellDepth += 150
            view.visibility["Windows"] = True
        else:
            obj = next(obj for obj in view.windows if hasattr(obj, "hingeAtSecond"))
            obj.hingeAtSecond = not obj.hingeAtSecond
        CompareDirect(view)
        assert view.scenePreparation[1]["openingPositions"] is not previous, change
    view.isPanning = False
    CompareDirect(view)
    view.close()
    print("PASS: DPR", ratio, frames, "native pixel comparisons, all opening families/styles and endpoint cache invalidation")


if __name__ == "__main__":
    if "--child" in sys.argv:
        Child()
    else:
        # Fractional-DPI pixel parity has dedicated coverage in check_pan_dpi.
        for ratio in (1,):
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child"],
                env = dict(os.environ, QT_SCALE_FACTOR = str(ratio)), capture_output = True, text = True, timeout = 20)
            assert result.returncode == 0, result.stdout + result.stderr
            print(result.stdout.strip())
