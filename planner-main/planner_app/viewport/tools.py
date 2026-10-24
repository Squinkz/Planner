"""Held-key opening placement and type cycling, using sidebar drag previews."""

from PySide6 import QtCore, QtGui, QtWidgets

class OpeningToolsMixin:
    def BeginOpeningMode(self, mode):
        if self.exportOverlay.active:
            return
        if self.dragStart is not None or self.pendingWall is not None or self.isPanning:
            return
        self.openingPlacementMode = mode
        self.openingPlacementPressed = False
        self.windowDropPreview = None
        self.inactiveOpeningPreview = None
        self.doorOrientationLocked = False
        self.UpdateMode(QtWidgets.QApplication.keyboardModifiers())
        self.openingToolChanged.emit(self.openingPlacementTypes[mode][self.openingPlacementIndices[mode]])
        position = QtCore.QPointF(self.mapFromGlobal(QtGui.QCursor.pos()))
        self.UpdateOpeningMode(position, QtWidgets.QApplication.keyboardModifiers())

    def EndOpeningMode(self):
        self.openingPlacementMode = None
        self.openingPlacementPressed = False
        self.windowDropPreview = None
        self.inactiveOpeningPreview = None
        self.doorOrientationLocked = False
        self.alignmentGuides = []
        self.UpdateMode(QtWidgets.QApplication.keyboardModifiers())
        self.openingToolChanged.emit(None)
        self.update()

    def CycleOpeningType(self, delta):
        mode = self.openingPlacementMode
        types = self.openingPlacementTypes[mode]
        self.openingPlacementIndices[mode] = (self.openingPlacementIndices[mode] + delta) % len(types)
        self.settingsChanged.emit()
        self.windowDropPreview = None
        self.inactiveOpeningPreview = None
        self.doorOrientationLocked = False
        self.openingToolChanged.emit(types[self.openingPlacementIndices[mode]])
        if self.lastInteractionPosition is not None:
            self.UpdateOpeningMode(self.lastInteractionPosition, QtWidgets.QApplication.keyboardModifiers())

    def UpdateOpeningMode(self, position, modifiers):
        self.hoverPosition = position
        self.lastInteractionPosition = position
        mode = self.openingPlacementMode
        openingType = self.openingPlacementTypes[mode][self.openingPlacementIndices[mode]]
        self.UpdateOpeningPreview(position, openingType, modifiers)
