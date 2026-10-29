"""Room topology, stable area plans and indexed assignment without Qt."""
import copy
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.geometry.room_regions import ClassifyRoomContours, ContourArea, PlanRoomRegions, FindContainingRegion
    from planner_app.geometry.spatial_index import BoundsIndex
    bounds = [(0, 0, 100, 100), (10, 10, 90, 90), (30, 30, 70, 70), (40, 40, 60, 60),
              (200, 0, 300, 100), (210, 10, 290, 90)]
    contours = [[(left, top), (right, top), (right, bottom), (left, bottom), (left, top)] for left, top, right, bottom in bounds]
    before = copy.deepcopy((bounds, contours))
    def Contains(index, point):
        left, top, right, bottom = bounds[index]
        return left < point[0] < right and top < point[1] < bottom
    depths, children = ClassifyRoomContours(contours, bounds, Contains)
    assert depths == {0: 0, 1: 1, 2: 2, 3: 3, 4: 0, 5: 1}
    assert children == {0: [1], 1: [2], 2: [3], 4: [5]}
    assert list(PlanRoomRegions(contours, depths, children)) == [((1, 2), 4800), ((3,), 400), ((5,), 6400)]
    assert ClassifyRoomContours([polygon[::-1] for polygon in contours], bounds, Contains) == (depths, children)
    for x, y in ((1e8, -1e8), (-1e12, 1e12)):
        moved = [[(first + x, second + y) for first, second in polygon] for polygon in contours]
        movedBounds = [(left + x, top + y, right + x, bottom + y) for left, top, right, bottom in bounds]
        def MovedContains(index, point):
            left, top, right, bottom = movedBounds[index]
            return left < point[0] < right and top < point[1] < bottom
        assert ClassifyRoomContours(moved, movedBounds, MovedContains) == (depths, children)
        assert [area for boundaries, area in PlanRoomRegions(moved, depths, children)] == [4800, 400, 6400]
    assert ContourArea([(0, 0), (100, 0), (100, 100), (0, 100)]) == 10000
    assert ClassifyRoomContours([], [], Contains) == ({}, {})
    assert (bounds, contours) == before
    regions = [dict(key = "first", bounds = (0, 0, 100, 100)), dict(key = "second", bounds = (10, 10, 90, 90))]
    index = BoundsIndex(100)
    for region in regions:
        index.Insert(region["bounds"], region)
    assert FindContainingRegion((50, 50), index, lambda region: True) is regions[0]
    assert FindContainingRegion((50, 50), index, lambda region: region["key"] == "second") is regions[1]
    assert FindContainingRegion((500, 500), index, lambda region: True) is None
    assert FindContainingRegion((50, 50), index, lambda region: False) is None
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: nested rooms/islands, winding, distant areas and ordered room assignment without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
