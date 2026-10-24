"""Explicit geometry choices, precise repairs, persistent highlights and cancellation."""
import copy
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Wall, Window
from planner_app.project_recovery import RecoverProject
from planner_app.project_codec import DecodeProject
from planner_app.geometry_recovery import ActiveGeometryIssues, GeometryLoadCancelled
from planner_app.graphics.palette import themeColors
from planner_app.viewport import rendering


def Main():
    app = QtWidgets.QApplication([])
    app.setQuitOnLastWindowClosed(False)
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    parent = Wall(QtCore.QPointF(0, 0), QtCore.QPointF(2000, 0), 240)
    opening = Window(parent, .35, .65)
    v.walls, v.windows, v.furnishings, v.labels = [parent], [opening], [], []
    v.objectGroups, v.hiddenObjects = [], []
    v.EnsureObjectIds()
    template = main.BuildProjectData(includeHistory = False)
    definitions = dict(v.furnishingDefinitions)
    defaults = main.defaultProjectData
    issues = []
    def Repair(issue):
        issues.append(issue)
        assert issue['repair'] is not None
        return 'repair'
    data = copy.deepcopy(template)
    data['scene']['objects'][0].update(second = [0, 0], width = 0, first = [float('nan'), 0])
    decoded, notices = RecoverProject(data, definitions, defaults, Repair)
    assert not issues[0]['highlight'] and issues[0]['code'] == 'dimensions'
    assert decoded[0][0].width > 0 and decoded[0][0].secondVertex.x() == 1000 and notices
    data = copy.deepcopy(template)
    data['scene']['objects'][1]['parent'] = 999
    def Remove(issue):
        issues.append(issue)
        return 'remove'
    decoded, notices = RecoverProject(data, definitions, defaults, Remove)
    assert not decoded[1] and issues[-1]['repair'] is None and not issues[-1]['highlight']
    data = copy.deepcopy(template)
    data['scene']['objects'][0]['type'] = 'Unknown Object'
    decoded, notices = RecoverProject(data, definitions, defaults, Remove)
    assert not decoded[0] and not decoded[1]  # Removing the parent also removes its opening.
    for unknownType in (None, []):
        data['scene']['objects'][0]['type'] = unknownType
        decoded, notices = RecoverProject(data, definitions, defaults, Remove)
        assert not decoded[0] and not decoded[1]
    data = copy.deepcopy(template)
    data['scene']['objects'][1]['center'] = 1.05
    decoded, notices = RecoverProject(data, definitions, defaults, Repair)
    assert abs(decoded[1][0].centerFraction - .85) < 1e-8 and abs(decoded[1][0].length - 600) < 1e-8
    def Highlight(issue):
        issues.append(issue)
        assert issue['highlight']
        return 'highlight'
    decoded, notices = RecoverProject(data, definitions, defaults, Highlight)
    main.ApplyProject(decoded, None)
    highlighted = v.windows[0]
    assert highlighted.centerFraction == 1.05 and abs(highlighted.secondVertex.x() - 2400) < 1e-8
    assert ActiveGeometryIssues(highlighted, v) == ['opening_bounds']
    for canvasTheme in ('Dark Canvas', 'Light Canvas', 'Blueprint Canvas'):
        main.SetThemes(canvasTheme = canvasTheme)
        with patch.object(rendering, 'DrawOpeningSymbol', wraps = rendering.DrawOpeningSymbol) as draw:
            v.grab()
            assert any(call.args[7] == themeColors['warningOutline'] for call in draw.call_args_list), canvasTheme
    saved = main.BuildProjectData(includeHistory = False)
    assert saved['scene']['objects'][1]['geometryIssues'] == ['opening_bounds']
    assert DecodeProject(saved, definitions)[1][0].centerFraction == 1.05
    before = v.CaptureState()
    highlighted.centerFraction = .5
    v.RecordEdit(before)
    assert not ActiveGeometryIssues(highlighted, v)
    v.Undo()
    assert ActiveGeometryIssues(highlighted, v)
    v.Redo()
    assert not ActiveGeometryIssues(highlighted, v)
    # Overlap repair searches a genuinely unoccupied interval.
    data = copy.deepcopy(template)
    other = copy.deepcopy(data['scene']['objects'][1])
    other.update(id = 999, center = .6)
    data['scene']['objects'].append(other)
    decoded, notices = RecoverProject(data, definitions, defaults, Repair)
    assert decoded[1][0].secondFraction <= decoded[1][1].firstFraction + 1e-8
    # A fully occupied wall has no usable repair.
    other.update(center = .5, length = 2000)
    data['scene']['objects'][2] = other
    def NoGap(issue):
        assert issue['code'] == 'opening_overlap' and issue['repair'] is None and issue['highlight']
        return 'remove'
    decoded, notices = RecoverProject(data, definitions, defaults, NoGap)
    assert len(decoded[1]) == 1
    # Obstruction repair moves the opening out of the crossing wall's footprint.
    data = copy.deepcopy(template)
    blocker = copy.deepcopy(data['scene']['objects'][0])
    blocker.update(id = 999, first = [1000, -1000], second = [1000, 1000])
    data['scene']['objects'].append(blocker)
    decoded, notices = RecoverProject(data, definitions, defaults, Repair)
    assert decoded[1][0].secondVertex.x() <= 880 + 1e-8
    data = copy.deepcopy(template)
    fire = data['scene']['objects'][1]
    fire.update(type = 'Fireplace', depth = 100, depthOffset = 80, material = 'Generic')
    decoded, notices = RecoverProject(data, definitions, defaults, Repair)
    assert decoded[1][0].depth == 240 and decoded[1][0].depthOffset == 0
    decoded, notices = RecoverProject(data, definitions, defaults, Highlight)
    main.ApplyProject(decoded, None)
    fire = v.windows[0]
    assert fire.depth == 100 and fire.depthOffset == 80 and ActiveGeometryIssues(fire, v)
    fire.depth = 240
    fire.depthOffset = 0
    assert not ActiveGeometryIssues(fire, v)
    # Closing a later dialog discards earlier staged choices.
    data = copy.deepcopy(template)
    data['scene']['objects'][0]['second'] = [0, 0]
    data['scene']['objects'].append({'type': 'Unknown Object'})
    original = copy.deepcopy(data)
    answers = iter(('repair', None))
    try:
        RecoverProject(data, definitions, defaults, lambda issue: next(answers))
    except GeometryLoadCancelled:
        pass
    else:
        raise AssertionError('Cancelled load completed')
    assert data == original
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        main.sessionPath = folder / 'session.json'
        path = folder / 'Geometry.plan'
        path.write_text(json.dumps(data))
        main.showMaximized()
        app.processEvents()
        previousWindowState = main.windowState()
        previousWindowGeometry = main.geometry()
        before = main.BuildProjectData()
        with patch.object(main, 'ConfirmProjectReplacement', return_value = False), patch.object(main, 'ShowGeometryIssue') as issueDialog:
            assert not main.OpenProject(path)
            issueDialog.assert_not_called()
        assert main.BuildProjectData() == before
        order = []

        def ConfirmClose():
            order.append('close')
            assert main.BuildProjectData() == before
            return True

        def CancelIncomingIssue(issue):
            order.append('incoming issue')
            assert not v.walls and not v.windows and not v.furnishings and not v.labels
            assert main.projectPath is None and getattr(main, 'recoveryWindow', None) is None
            assert main.windowState() == previousWindowState
            assert main.geometry() == previousWindowGeometry
            return None

        with patch.object(main, 'ConfirmProjectReplacement', side_effect = ConfirmClose), patch.object(main, 'ShowGeometryIssue', side_effect = CancelIncomingIssue):
            assert not main.OpenProject(path)
        assert order == ['close', 'incoming issue']
        assert main.BuildProjectData() == before, {key: (before[key], value) for key, value in main.BuildProjectData().items() if value != before[key]}
        assert not (folder / 'project-recovery').exists()
        main.showNormal()
        main.resize(1100, 760)
        app.processEvents()
        previousWindowState = main.windowState()
        previousWindowGeometry = main.geometry()
        before = main.BuildProjectData()
        previousStartup = main.startupPath
        main.startupPath = path
        order.clear()
        with patch.object(main, 'ConfirmProjectReplacement', side_effect = ConfirmClose), patch.object(main, 'ShowGeometryIssue', side_effect = CancelIncomingIssue):
            assert not main.NewProject()
        assert order == ['close', 'incoming issue']
        assert main.BuildProjectData() == before
        main.startupPath = previousStartup
        # Completing a choice installs an unsaved copy after preserving original bytes.
        data = copy.deepcopy(template)
        data['scene']['objects'][1]['center'] = 1.05
        originalBytes = json.dumps(data).encode('utf-8')
        path.write_bytes(originalBytes)
        with patch.object(main, 'ShowGeometryIssue', side_effect = Highlight), patch.object(main, 'ShowAppMessage', return_value = QtWidgets.QMessageBox.StandardButton.Discard):
            assert main.OpenProject(path)
        assert main.projectPath is None and main.projectDirty
        assert main.recoveryBackupPath.read_bytes() == originalBytes and path.read_bytes() == originalBytes
        assert v.windows[0].centerFraction == 1.05
    # Inspect real buttons and verify the window close button cancels.
    def CloseDialog():
        dialog = app.activeModalWidget()
        buttons = {button.text(): button for button in dialog.buttons() if button.isVisible()}
        assert set(buttons) == {'Remove', 'Highlight', 'Repair'}
        assert not buttons['Highlight'].isEnabled() and buttons['Repair'].isEnabled()
        assert dialog.width() >= 440 and dialog.height() >= 180
        dialog.close()
    issue = next(issue for issue in issues if issue['code'] == 'dimensions')
    QtCore.QTimer.singleShot(0, CloseDialog)
    with patch.object(QtWidgets.QMessageBox, 'exec', QtWidgets.QDialog.exec):
        assert main.ShowGeometryIssue(issue) is None
    issue = next(issue for issue in issues if issue['code'] == 'opening_bounds')
    for action in ('Highlight', 'Repair'):
        def ClickAction():
            dialog = app.activeModalWidget()
            button = next(button for button in dialog.buttons() if button.text() == action)
            assert button.isEnabled(), (action, issue)
            button.click()
        QtCore.QTimer.singleShot(0, ClickAction)
        with patch.object(QtWidgets.QMessageBox, 'exec', QtWidgets.QDialog.exec):
            actual = main.ShowGeometryIssue(issue)
        assert actual == action.lower(), (action, actual)
    main.close()
    print('PASS: geometry choices, dimensions/attachments/unknowns, opening gaps/obstructions, fireplace clamps, highlights, history and cancellation.')


if __name__ == '__main__':
    Main()
