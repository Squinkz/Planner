"""Multiple palette categories inherit, search once and travel with projects."""
import json
import os
import shutil
import sys
import tempfile
import warnings
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtWidgets
from planner import MainWindow
from planner_app.catalog import LoadFurnishings
from planner_app.furnishing_search import FindFurnishings
from planner_app.models import Furnishing
from planner_app.paths import furnishingsDirectory
from planner_app.project_codec import DecodeProject
from planner_app.ui.widgets import FurnishingButton


def Main():
    app = QtWidgets.QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        (folder / "definitions").mkdir()
        (folder / "definitions_user").mkdir()
        shutil.copytree(furnishingsDirectory / "images", folder / "images")
        for key in ("null", "desk", "chair_dining"):
            shutil.copyfile(furnishingsDirectory / f"definitions/{key}.json", folder / f"definitions/{key}.json")
        fixtures = {
            "multi": {"inherits": "desk", "name": json.loads((folder / "definitions/desk.json").read_text())["name"],
                      "category": ["Office", "Study", " office ", ""]},
            "inherited": {"inherits": "multi", "name": "Inherited Desk"},
            "changed": {"inherits": "multi", "name": "Changed Desk", "category": "Bedroom"},
            "bad": {"category": ["Office", 4]},
        }
        for key, record in fixtures.items():
            (folder / f"definitions_user/{key}.json").write_text(json.dumps(record), encoding = "utf-8")
        with warnings.catch_warnings(record = True) as messages:
            catalog = {item["key"]: item for item in LoadFurnishings(folder)}
        assert "bad" not in catalog and messages
        assert catalog["multi"]["categories"] == catalog["inherited"]["categories"] == ["Office", "Study"]
        assert catalog["changed"]["categories"] == ["Bedroom"]
        assert catalog["multi"]["name"] == catalog["desk"]["name"]
        uncached = dict(catalog["multi"])
        uncached.pop("searchText")
        assert FindFurnishings([uncached], "Study", "Millimeters") == [uncached]
        main = MainWindow()
        main.show()
        v = main.viewport
        v.furnishingsFolder = folder
        v.furnishingDefinitions = v.localFurnishingDefinitions = catalog
        main.BuildFurnishTab(refresh = True)
        main.sidebarTabs.setCurrentIndex(1)
        app.processEvents()
        cards = [main.furnishingCategoryCards[("multi", category)] for category in ("Office", "Study")]
        assert cards[0] is not cards[1]
        assert all(card.isVisible() and card.findChild(FurnishingButton).definition is catalog["multi"] for card in cards)
        for query in ("Study", "Office", "*"):
            main.furnishingSearchField.setText(query)
            main.UpdateFurnishingSearch()
            results = [main.furnishingResultsLayout.itemAt(index).widget().findChild(FurnishingButton).definition["key"]
                       for index in range(main.furnishingResultsLayout.count())]
            assert results.count("multi") == 1 and len(results) == len(set(results))
        main.furnishingSearchField.clear()
        v.unitsMode = "Millimeters"
        main.UpdateFurnishingSearch()
        assert all(card.isVisible() for card in cards)
        labels = [main.furnishingCategoryDimensionLabels[("multi", category)] for category in ("Office", "Study")]
        assert labels[0].text() == labels[1].text()
        children = [{"furnishing": "desk", "x": -600}, {"furnishing": "chair_dining", "x": 600}]
        with patch.object(main, "ShowAppMessage") as dialogs, warnings.catch_warnings(record = True):
            saved = main.SaveUserFurnishing("Desk", "Office, Study, office", children)
            duplicate = main.SaveUserFurnishing("Desk", ["Bedroom", "Study"], children)
            assert saved and duplicate and not dialogs.called
        assert saved["key"] != duplicate["key"] != "desk"
        assert saved["categories"] == ["Office", "Study"]
        assert json.loads(saved["sourcePath"].read_text())["category"] == ["Office", "Study"]
        v.furnishings = [Furnishing(saved), Furnishing(duplicate)]
        data = main.BuildProjectData(includeHistory = False)
        localOnly = {key: definition for key, definition in catalog.items() if not definition["isUser"]}
        decoded = DecodeProject(data, localOnly)
        assert [obj.definition["categories"] for obj in decoded[2]] == [["Office", "Study"], ["Bedroom", "Study"]]
        assert all(obj.definition["name"] == "Desk" for obj in decoded[2])
        main.ApplyProject(decoded, None)
        assert main.BuildProjectData(includeHistory = False)["furnishingDefinitions"] == data["furnishingDefinitions"]
        main.close()
    print("PASS: multi-category inheritance/palette/search, duplicate names, unique keys and embedded project round trips")


if __name__ == "__main__":
    Main()
