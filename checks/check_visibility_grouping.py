"""World/export grouping is presentation-only and preserves cascading visibility."""
import copy
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Stair, Furnishing, Label, Door
from planner_app.project_codec import DecodeProject


def Main():
    checked, unchecked, partial = QtCore.Qt.CheckState.Checked, QtCore.Qt.CheckState.Unchecked, QtCore.Qt.CheckState.PartiallyChecked
    with ExampleWindow() as (main, folder):
        v, export = main.viewport, main.exportPanel
        p = QtCore.QPointF
        wall = Wall(p(-2000, 0), p(2000, 0), 200)
        stair = Stair(p(0, 1500), p(0, 3000), 1000)
        furnishing = Furnishing(v.furnishingDefinitions["desk"], p(2000, 2000))
        label = Label(p(-2000, 2000), "Label")
        door = Door(wall, .2, .4)
        InstallScene(main, [wall, stair, furnishing, label, door])
        originalKeys = set(v.visibility)
        for owner in (main, export):
            assert owner.visibilityItems["North arrows"].text(0) == "North markers (0 objects)"
            root = owner.visibilityItems["World"]
            assert [root.child(i).text(0).split(" (")[0] for i in range(root.childCount())] == ["Walls", "Objects", "Annotations"]
            for name, names in (("Objects", ["Elevators", "Stairs", "Counters", "Railings", "Furnishings"]),
                                ("Annotations", ["Labels", "Arrows", "Measurement guides", "Boundary lines", "Dashed lines", "Solid lines", "North arrows"])):
                group = owner.visibilityGroups[name]
                assert group.parent() is root and group.isExpanded()
                assert group.flags() & QtCore.Qt.ItemFlag.ItemIsUserCheckable
                assert group.checkState(0) == checked
                count = 2 if name == "Objects" else 1
                assert group.text(0) == f"{name} ({count} {'object' if count == 1 else 'objects'})"
                assert [group.child(i) for i in range(group.childCount())] == [owner.visibilityItems[key] for key in names]
        assert main.referenceImageItem.parent() is None
        assert main.visibilityTree.topLevelItem(0) is main.referenceImageItem
        v.labels.remove(label)
        main.RefreshVisibilityCounts()
        export.RefreshControls()
        for owner in (main, export):
            assert owner.visibilityGroups["Annotations"].text(0) == "Annotations (0 objects)"
        v.labels.append(label)
        main.RefreshVisibilityCounts()
        export.RefreshControls()
        for owner in (main, export):
            assert owner.visibilityGroups["Annotations"].text(0) == "Annotations (1 object)"
        assert export.visibilityTree.topLevelItemCount() == 1
        # Folding a heading changes only presentation, not any visibility flags.
        snapshot = copy.deepcopy(main.ProjectSettings())
        main.visibilityGroups["Objects"].setExpanded(False)
        assert main.ProjectSettings() == snapshot
        assert not main.SessionUiState()["expanded"]["Objects"]
        main.visibilityItems["World"].setCheckState(0, unchecked)
        assert not any(v.visibility.values())
        main.visibilityItems["Labels"].setCheckState(0, checked)
        assert v.IsObjectVisible(label) and not v.IsObjectVisible(stair)
        assert main.visibilityItems["World"].checkState(0) == partial
        assert main.visibilityGroups["Annotations"].checkState(0) == partial
        main.visibilityItems["World"].setCheckState(0, checked)
        assert all(v.visibility.values()) and set(v.visibility) == originalKeys
        main.visibilityGroups["Objects"].setCheckState(0, unchecked)
        assert not v.IsObjectVisible(stair) and not v.IsObjectVisible(furnishing)
        assert v.IsObjectVisible(wall) and v.IsObjectVisible(label)
        main.visibilityItems["Stairs"].setCheckState(0, checked)
        assert main.visibilityGroups["Objects"].checkState(0) == partial
        main.visibilityTree.setCurrentItem(main.visibilityGroups["Objects"])
        QtTest.QTest.keyClick(main.visibilityTree, QtCore.Qt.Key.Key_Space)
        assert main.visibilityGroups["Objects"].checkState(0) == unchecked
        assert not v.IsObjectVisible(stair)
        main.visibilityGroups["Objects"].setCheckState(0, checked)
        assert all(v.visibility.values())
        assert not main.visibilityGroups["Objects"].isExpanded()
        main.visibilityItems["Doors"].setCheckState(0, unchecked)
        assert main.visibilityItems["Walls"].checkState(0) == partial
        assert main.visibilityItems["World"].checkState(0) == partial
        main.sidebarTabs.setCurrentWidget(export)
        export.sectionButtons["Visibility"].setChecked(True)
        assert export.visibilityTree.height() == 19 * 32
        export.visibilityGroups["Objects"].setExpanded(False)
        assert export.visibilityTree.height() == 14 * 32
        export.visibilityGroups["Annotations"].setExpanded(False)
        assert export.visibilityTree.height() == 7 * 32
        project = copy.deepcopy(export.projectView["visibility"])
        export.visibilityGroups["Objects"].setCheckState(0, unchecked)
        assert not v.IsObjectVisible(stair) and not v.IsObjectVisible(furnishing)
        assert v.IsObjectVisible(wall) and v.IsObjectVisible(label)
        export.visibilityItems["Stairs"].setCheckState(0, checked)
        assert export.visibilityGroups["Objects"].checkState(0) == partial
        assert export.projectView["visibility"] == project
        assert set(export.overrides["visibility"]).issubset(originalKeys)
        export.visibilityItems["World"].setCheckState(0, unchecked)
        assert not any(v.visibility.values())
        assert export.projectView["visibility"] == project
        assert set(export.overrides["visibility"]) == originalKeys
        export.visibilityItems["Labels"].setCheckState(0, checked)
        assert v.IsObjectVisible(label) and not v.IsObjectVisible(stair)
        assert export.visibilityItems["World"].checkState(0) == partial
        assert export.visibilityGroups["Annotations"].checkState(0) == partial
        export.visibilityItems["World"].setCheckState(0, checked)
        assert all(v.visibility.values())
        assert not export.visibilityGroups["Objects"].isExpanded()
        export.visibilityTree.grab().save(str(Path(__file__).resolve().parents[1] / "diagnostics/export-visibility-groups.png"))
        saved = main.BuildProjectData()
        assert set(DecodeProject(saved, v.furnishingDefinitions)[5]["visibility"]) == originalKeys
        main.sidebarTabs.setCurrentIndex(2)
        assert v.visibility == project
        assert not main.visibilityGroups["Objects"].isExpanded()
        main.visibilityTree.grab().save(str(Path(__file__).resolve().parents[1] / "diagnostics/world-visibility-groups.png"))
        # Keyboard activation toggles every category in the focused group only.
        main.visibilityTree.setCurrentItem(main.visibilityGroups["Annotations"])
        QtTest.QTest.keyClick(main.visibilityTree, QtCore.Qt.Key.Key_Space)
        assert not v.IsObjectVisible(label) and v.IsObjectVisible(stair)
        assert main.visibilityGroups["Annotations"].checkState(0) == unchecked
        QtTest.QTest.keyClick(main.visibilityTree, QtCore.Qt.Key.Key_Space)
        assert v.IsObjectVisible(label)
        assert main.visibilityGroups["Annotations"].checkState(0) == checked
        main.visibilityGroups["Annotations"].setExpanded(False)
        main.WriteSession(wait = True)
        main.visibilityGroups["Annotations"].setExpanded(True)
        main.RestoreSession(main.sessionPath)
        assert not main.visibilityGroups["Objects"].isExpanded()
        assert not main.visibilityGroups["Annotations"].isExpanded()
    print("PASS: matching grouped trees, category counts/visibility, export isolation and session expansion state")


if __name__ == "__main__":
    Main()
