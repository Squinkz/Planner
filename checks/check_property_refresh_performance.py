"""Frozen synchronous property state/pixels and metadata reuse/invalidation."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'planner-main'))
from PySide6 import QtCore, QtWidgets
from fixtures.parity_examples import ExampleWindow, CreateObject, InstallScene, objectTypes
from fixtures.qt_properties_reference_20261030 import ReferenceProperties, ReferenceScene
from planner_app import models


def Snapshot(main):
    states = []
    for widget in main.propertiesPanel.findChildren(QtWidgets.QWidget):
        state = [type(widget).__name__, widget.objectName(), widget.isHidden(), widget.isEnabled(), widget.toolTip()]
        visible = widget.isVisibleTo(main.propertiesPanel)
        if isinstance(widget, QtWidgets.QAbstractSpinBox) and visible:
            state += [widget.value(), widget.minimum(), widget.maximum(), widget.singleStep(), widget.suffix(), widget.isReadOnly(),
                      getattr(widget, 'mixedValue', None), getattr(widget, 'mixedEdited', None), getattr(widget, 'commonSuffix', None)]
            if isinstance(widget, QtWidgets.QDoubleSpinBox):
                state += [widget.decimals()]
        if isinstance(widget, (QtWidgets.QLabel, QtWidgets.QLineEdit, QtWidgets.QAbstractButton)) and visible:
            state += [widget.text()]
        if isinstance(widget, QtWidgets.QLineEdit):
            state += [widget.placeholderText()]
        if isinstance(widget, QtWidgets.QPlainTextEdit):
            state += [widget.toPlainText(), widget.placeholderText()]
        if isinstance(widget, QtWidgets.QComboBox):
            state += [widget.currentIndex(), widget.currentText(), widget.placeholderText()]
        if isinstance(widget, QtWidgets.QAbstractButton):
            state += [widget.isChecked()]
        if isinstance(widget, QtWidgets.QCheckBox):
            state += [widget.checkState(), widget.isTristate()]
        states.append(state)
    return states


def Compare(main, label, pixels = False):
    main.RefreshProperties()
    QtWidgets.QApplication.processEvents()
    current = Snapshot(main)
    image = main.propertiesScrollArea.grab().toImage() if pixels else None
    viewportImage = main.viewport.grab().toImage() if pixels else None
    with patch.object(main.viewport, 'EnsureObjectIds', ReferenceScene.EnsureObjectIds.__get__(main.viewport)):
        ReferenceProperties.RefreshProperties(main)
    QtWidgets.QApplication.processEvents()
    expected = Snapshot(main)
    assert current == expected, ('property state', label, [(a, b) for a, b in zip(current, expected) if a != b][:3])
    if pixels:
        assert image == main.propertiesScrollArea.grab().toImage(), ('panel pixels', label)
        assert viewportImage == main.viewport.grab().toImage(), ('editor pixels', label)


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.performanceTimer.stop()
        v.performanceLabel.hide()
        v.showMeasurements = v.showTips = False
        point = QtCore.QPointF
        for index, name in enumerate(objectTypes):
            first, second = CreateObject(v, name), CreateObject(v, name)
            if isinstance(second, models.Window):
                second.length *= .9
            else:
                second.width *= 1.17
                second.secondVertex += point(13, -7)
            if isinstance(second, models.Label):
                second.text = 'Different label'
            objects = [first, second]
            objects += list({id(obj.parentWall): obj.parentWall for obj in objects if isinstance(obj, models.Window)}.values())
            InstallScene(main, objects)
            for units in ('Millimeters', 'Feet and Inches'):
                v.unitsMode = units
                for multi in (False, True):
                    v.SetSelection([(first, None), (second, None)] if multi else [(first, None)])
                    Compare(main, (name, units, multi), pixels = not multi and units == 'Millimeters')
            v.unitsMode = 'Millimeters'
            if isinstance(first, models.Wall):
                v.SetSelection([(first, 0)])
                for frame in range(3):
                    first.firstVertex += point(3, -1)
                    v.selectionChanged.emit()
                    Compare(main, (name, 'vertex', frame))
        # Live editing remains synchronous; every changed value is available
        # immediately after selectionChanged, without waiting for a timer.
        wall = models.Wall(point(), point(2000, 0), 200)
        stair = models.Stair(point(0, 5000), point(0, 8000), 900)
        railing = models.Railing(point(10000, 0), point(14000, 0), 100)
        InstallScene(main, [wall, stair, railing])
        v.SetSelection([(wall, None)])
        metadataKey = v.sceneMetadataKey
        stairs = stair.sceneStairs
        for frame in range(20):
            wall.secondVertex += point(1, 0)
            v.selectionChanged.emit()
            assert main.propertyFields['length'].value() == round(2001 + frame, main.propertyFields['length'].decimals())
            assert v.sceneMetadataKey == metadataKey and stair.sceneStairs is stairs
        # Native chamfer eligibility keeps the original distance predicate at
        # the .01 mm boundary, including representable far-origin positions.
        for offset in (0, 1e8, 1e11):
            for gap in (.009999, .01, .010001):
                horizontal = models.Wall(point(offset, offset), point(offset + 2000, offset), 200)
                vertical = models.Wall(point(offset, offset + gap), point(offset, offset + 2000), 300)
                v.walls = [horizontal, vertical] + [models.Wall(point(offset + 10000 + index * 2000, offset),
                    point(offset + 11000 + index * 2000, offset), 200) for index in range(64)]
                v.SetSelection([(horizontal, 0), (vertical, 0)])
                Compare(main, ('chamfer tolerance', offset, gap))
        v.walls = [wall, stair, railing]
        v.SetSelection([(wall, None)])
        # Insertions, ID resets, derived-data resets and live setting changes
        # must repair metadata on the next synchronous refresh.
        added = models.Stair(point(0, 8000), point(3000, 8000), 900)
        v.walls.append(added)
        main.RefreshProperties()
        assert added.objectId is not None and added in stair.sceneStairs and stair in added.sceneStairs
        wall.objectId = None
        main.RefreshProperties()
        assert wall.objectId is not None
        stair.sceneStairs = []
        stair.stepSizeBounds = (1, 2)
        railing.spacingBounds = (1, 2, 3)
        main.RefreshProperties()
        assert stair.sceneStairs == [stair, added]
        assert stair.stepSizeBounds == tuple(v.AutoSizingLimits('stairs')[key] for key in ('minimum', 'maximum'))
        assert railing.spacingBounds == tuple(v.AutoSizingLimits('railings')[key] for key in ('minimum', 'maximum', 'target'))
        v.stairStepSizes['minimum'] += 1
        v.railingSpacings['target'] += 1
        main.RefreshProperties()
        assert stair.stepSizeBounds[0] == v.AutoSizingLimits('stairs')['minimum']
        assert railing.spacingBounds[2] == v.AutoSizingLimits('railings')['target']
        v.unitsMode = 'Feet and Inches'
        v.imperialAutoSizes['stairs'] = dict(minimum = 250, maximum = 310)
        main.RefreshProperties()
        assert stair.stepSizeBounds == (250, 310)
        v.autoSizingUnitsMode = 'Millimeters'
        main.RefreshProperties()
        assert stair.stepSizeBounds == tuple(v.AutoSizingLimits('stairs')[key] for key in ('minimum', 'maximum'))
        v.walls.remove(added)
        main.RefreshProperties()
        assert stair.sceneStairs == [stair]
        # Explicit maintenance still repairs untracked in-place mutations.
        stair.sceneStairs.clear()
        v.EnsureObjectIds()
        assert stair.sceneStairs == [stair]
        captured = v.CaptureState()
        retired = captured[0][0][0]
        v.walls.remove(retired)
        retired.objectId = None
        v.EnsureObjectIds(captured, reuse = True)
        assert retired.objectId is not None
        # Preserve blocked/reentrant refresh behavior.
        main.bulkPropertyEdit = True
        with patch.object(v, 'EnsureObjectIds', side_effect = AssertionError('Bulk refresh ran')):
            main.RefreshProperties()
        main.bulkPropertyEdit = False
        v.SetSelection([])
        Compare(main, 'no selection')
        with patch.object(main.referenceImage, 'SyncProperties') as sync:
            main.referenceImage.active = True
            main.RefreshProperties()
            assert sync.call_count == 1
            main.referenceImage.active = False
    print('PASS: frozen property state for all object types/units, exact panel/editor pixels, synchronous live values, metadata invalidation and explicit repairs.')


if __name__ == '__main__':
    Main()
