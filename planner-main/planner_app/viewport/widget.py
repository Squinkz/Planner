"""Viewport widget state and world/screen coordinate transforms."""

from collections import deque
import os
from time import perf_counter
from planner_app.preferences import lineworkDefaults, measurementVisibilityDefaults, collisionDefaults
from planner_app.graphics.linework import defaultLineWidths
from PySide6 import QtCore, QtGui, QtWidgets
from .geometry import GeometryMixin
from .angle_guides import AngleGuidesMixin
from .guide_labels import GuideLabelsMixin
from .diagnostics import RenderDiagnostics
from .grouping import GroupingMixin
from .visibility import VisibilityMixin
from .interaction import InteractionMixin
from .placement import PlacementMixin
from .rendering import RenderingMixin
from .scene import SceneEditingMixin
from .snapping import SnappingMixin
from .tools import OpeningToolsMixin
from .context_menu import ContextMenuMixin
from .clipboard import ClipboardMixin
from .furnishing_handles import FurnishingHandlesMixin
from .export_bounds import ExportBoundsOverlay
from .raster_cache import RasterCacheBudget
from planner_app.scene_changes import SceneChanges, SceneList, SceneDict, SceneSet
from planner_app.room_detection import RoomDetection
from planner_app.models import OpenDoorway, Door, SwingingDoor, DoubleDoor, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, Label
from planner_app.catalog import LoadFurnishings, furnishingsFolder
from planner_app.preferences import wallPresetWidths, openingDefaultSizes, miscDefaultSizes, measurementDefaults, stairStepSizeDefaults, railingSpacingDefaults
from planner_app.graphics.furnishings import FurnishingRendererMap
from planner_app.graphics.theme import BuildWallBrush, gridIntensityDefaults, wallMaterials
from planner_app.graphics.palette import themeColors


class PerformanceLabel(QtWidgets.QLabel):
    def showEvent(self, event):
        super().showEvent(event)
        # Restore after stylesheet polishing so label updates do not repaint the scene.
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_OpaquePaintEvent)

    def paintEvent(self, event):
        # An opaque widget must fill every pixel itself. QLabel's stylesheet
        # background can be skipped with that flag, leaving old glyphs behind.
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor(themeColors["canvas"]))
        painter.setFont(self.font())
        painter.setPen(QtGui.QColor(themeColors["performanceText"]))
        painter.drawText(self.rect().adjusted(4, 0, -4, 0), self.alignment(), self.text())


class DrawingViewport(GuideLabelsMixin, AngleGuidesMixin, VisibilityMixin, GroupingMixin, SceneEditingMixin, GeometryMixin, SnappingMixin, PlacementMixin,
                      InteractionMixin, RenderingMixin, OpeningToolsMixin, ContextMenuMixin, ClipboardMixin, FurnishingHandlesMixin, QtWidgets.QWidget):
    """Unbounded metric drawing plane. World coordinates are millimeters."""

    selectionChanged = QtCore.Signal()
    sceneChanged = QtCore.Signal()
    settingsChanged = QtCore.Signal()
    openingToolChanged = QtCore.Signal(object)
    clipboardMessage = QtCore.Signal(str)

    def __setattr__(self, name, value):
        changes = self.__dict__.get("renderChanges")
        if changes is not None:
            if name in ("walls", "windows", "furnishings", "labels", "objectGroups"):
                if not isinstance(value, SceneList) or value.changes is not changes:
                    value = SceneList(value, changes, nested = name == "objectGroups")
                    changes.Bump("topology")
            elif name in ("furnishingRenderers", "selectedFurnishingRenderers"):
                value = (value.Copy(changed = lambda: changes.Bump("appearance")) if isinstance(value, FurnishingRendererMap)
                         else SceneDict(value, lambda: changes.Bump("appearance")))
                changes.Bump("appearance")
            elif name == "hiddenObjectIds":
                if not isinstance(value, SceneSet) or value.changes is not changes:
                    value = SceneSet(value, changes)
                    changes.Bump("visibility")
        super().__setattr__(name, value)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.renderChanges = SceneChanges()
        self.verifyRenderRevisions = os.environ.get("PLANNER_VERIFY_RENDER_REVISIONS") == "1"
        self.renderRevisionReference = None
        self.renderSamples = deque(maxlen = 512)
        self.renderDiagnostics = None
        self.panFrameTimer = QtCore.QTimer(self)
        self.panFrameTimer.setSingleShot(True)
        self.panFrameTimer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self.panFrameTimer.timeout.connect(self.PaintPanFrame)
        self.dragPanTimer = QtCore.QTimer(self)
        self.dragPanTimer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self.dragPanTimer.setInterval(16)
        self.dragPanTimer.timeout.connect(self.AdvanceDragPan)
        self.dragPanPosition = None
        self.dragPanButtons = QtCore.Qt.MouseButton.NoButton
        self.dragPanVelocity = QtCore.QPointF()
        self.dragPanLastTime = None
        self.dragPanMimeData = None
        self.dragPanActions = QtCore.Qt.DropAction.IgnoreAction
        self.panFrameDeadline = None
        self.panFrameInterval = 1 / 60
        self.lastRenderMilliseconds = 0.0
        self.viewportBackgroundKey = None
        self.viewportBackground = None
        self.referenceFocusBackground = self.referenceFocusKey = None
        self.viewportSceneKey = None
        self.viewportScene = None
        self.viewportSceneState = None
        self.viewportSceneByteLimit = 128 * 1024 * 1024
        self.viewportRasterByteLimit = 128 * 1024 * 1024
        self.rasterCacheBudget = RasterCacheBudget(self)
        self.viewportPanKey = None
        self.viewportPanRaster = None
        self.viewportPanOrigin = None
        self.viewportPanState = None
        self.performanceLabel = PerformanceLabel("FPS: Idle | Render: -- ms", self)
        self.performanceLabel.setObjectName("viewportPerformance")
        self.performanceLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.performanceLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.performanceLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.performanceLabel.setFixedSize(240, self.fontMetrics().height() + 8)
        self.showFpsCounter = False
        self.performanceLabel.hide()
        self.performanceTimer = QtCore.QTimer(self)
        self.performanceTimer.setInterval(250)
        self.performanceTimer.timeout.connect(self.RefreshPerformance)
        self.visibility = dict.fromkeys(("World", "Walls", "Doors", "Windows", "Fireplaces", "Elevators", "Stairs", "Counters", "Railings", "Furnishings", "Labels", "Arrows", "Measurement guides", "Boundary lines", "Dashed lines", "Solid lines", "North arrows"), True)
        self.objectGroups = []
        self.hiddenObjects = []
        self.hiddenObjectIds = set()
        self.problemObjects = ()
        self.potentialProblemObjects = ()
        self.ignoredPotentialIssues = []
        self.groupModeEnabled = True
        self.clipboardError = ""
        self.clipboardErrorTimer = QtCore.QTimer(self)
        self.clipboardErrorTimer.setSingleShot(True)
        self.clipboardErrorTimer.timeout.connect(lambda: self.ShowClipboardError(""))
        self.clipboardMessage.connect(self.ShowClipboardError)
        self.zoom = 1.0
        self.panOffset = QtCore.QPointF()
        self.isPanning = False
        self.lastPanPosition = QtCore.QPointF()
        self.rulerSize = 28
        self.basePixelsPerMillimeter = 0.2
        self.showGrid = True
        self.showTips = True
        self.showMeasurements = True
        self.measurementVisibility = dict(measurementVisibilityDefaults)
        self.collisionSettings = dict(collisionDefaults)
        self.gridIntensities = dict(gridIntensityDefaults)
        self.gridOrigin = (0.0, 0.0)
        self.lineworkSettings = dict(lineworkDefaults)
        self.lineWidths = dict(defaultLineWidths)
        self.measurementSettings = dict(measurementDefaults)
        self.wallMeasurementMode = "Exterior stacked"
        self.wallMeasurementReference = "Wall faces"
        self.stairStepSizes = dict(stairStepSizeDefaults)
        self.railingSpacings = dict(railingSpacingDefaults)
        self.imperialAutoSizes = {}
        self.autoSizingUnitsMode = None
        self.unitsMode = "Millimeters"
        self.measurementPrecision = "Medium"
        self.vertexSnapRange = 10.0
        self.vertexHoverRange = 50.0
        self.hoverPosition = None
        self.alignmentGuides = []
        self.snapApplied = False
        self.controlHeld = False
        self.axisConstraintOrigin = None
        self.axisConstraintDirection = None
        self.vertexAxisFromDragged = False
        self.vertexAxisWheelDelta = 0
        self.localTransforms = False
        self.guiDragActive = False
        self.guiDragCancelled = False
        self.guiDragKind = None
        self.snapEnabled = True
        self.gridSnapEnabled = True
        self.vertexSnapEnabled = True
        self.cornerSnapEnabled = True
        self.midpointSnapEnabled = True
        self.alignmentSnapEnabled = True
        self.connectedEnabled = True
        self.connectedVerticesEnabled = True
        self.connectedObjectsEnabled = False
        self.newWallWidth = wallPresetWidths[2] * 10.0
        self.wallPresetWidths = list(wallPresetWidths)
        self.openingDefaultSizes = dict(openingDefaultSizes)
        self.miscDefaultSizes = dict(miscDefaultSizes)
        self.imperialDefaultSizes = {}
        self.referenceImage = None
        self.newWallMaterial = "Generic"
        self.dragAttachments = []
        self.dragConstraints = []
        self.dragObjectAttachmentKeys = set()
        self.lastInteractionPosition = None
        self.walls = []
        self.windows = []
        self.furnishings = []
        self.labels = []
        self.labelPreview = None
        self.counterPreview = None
        self.arrowPreview = None
        self.objectContextMenu = QtWidgets.QMenu(self)
        self.objectContextMenu.setObjectName("viewportContextMenu")
        self.furnishingContextMenu = self.objectContextMenu
        self.rightClickStart = None
        self.furnishingsFolder = furnishingsFolder
        self.furnishingDefinitions = {item["key"]: item for item in LoadFurnishings(self.furnishingsFolder)}
        self.localFurnishingDefinitions = dict(self.furnishingDefinitions)
        self.projectFurnishingDefinitions = {}
        self.furnishingRenderers = FurnishingRendererMap(self.furnishingDefinitions)
        self.selectedFurnishingRenderers = FurnishingRendererMap(self.furnishingDefinitions, selected = True)
        self.groupedFurnishingRenderers = {}
        self.objectClipCache = {}
        self.furnishingPreview = None
        self.furnishingHandleDrag = None
        self.furnishingRotationObject = None
        self.rotationPivot = None
        self.furnishingSelectionBox = None
        self.furnishingSelectionBoxKey = None
        self.pendingFurnishingHandleToggle = None
        self.furnishingValidationKey = None
        self.furnishingValidationCache = {}
        self.windowDropPreview = None
        self.inactiveOpeningPreview = None
        self.groupOpeningPreviews = []
        self.dragWindowState = None
        self.dragSourceVertex = None
        self.dragSourceVertices = None
        self.dragSource = None
        self.dragCopies = []
        self.dragSourceAttachments = []
        self.dragSourceConstraints = []
        self.doorOrientationLocked = False
        self.mode = "Select"
        self.openingPlacementMode = None
        self.openingPlacementPressed = False
        self.openingPlacementTypes = {"Door": (Door, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway, SwingingDoor, DoubleDoor), "Window": (Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow)}
        self.openingPlacementIndices = {"Door": 0, "Window": 0}
        self.selectedWall = None
        self.selectedVertex = None
        self.selection = []
        self.boxStart = None
        self.boxEnd = None
        self.boxSelectionBefore = []
        self.boxSelectionRemove = False
        self.pendingShiftSelection = None
        self.groupDrag = False
        self.groupEntries = []
        self.groupSourceEntries = []
        self.groupOpeningStates = []
        self.groupMovedVertices = []
        self.groupMovedOpenings = []
        self.pendingWall = None
        self.pendingShapeWalls = []
        self.wallShape = "line"
        self.wallDrawShape = "line"
        self.circleSegments = 8
        self.circleWheelDelta = 0
        self.wallStartPosition = None
        self.wallDrawButton = None
        self.dragStart = None
        self.dragVertices = None
        self.isDragging = False
        self.interactionBefore = None
        self.sceneRevision = 0
        self.historyLimit = 200
        self.historyByteBudget = 16 * 1024 * 1024
        self.undoHistory = []
        self.redoHistory = []
        self.wallGeometryKey = None
        self.counterGeometryCache = {}
        self.footprintSnapTargetsKey = None
        self.footprintSnapTargets = []
        self.containedWallKey = None
        self.containedWallCache = []
        self.wallGeometryPath = QtGui.QPainterPath()
        self.viewportEditRaster = self.viewportEditKey = self.viewportEditState = self.viewportEditSnapshot = None
        self.viewportEditFrameKey = self.viewportEditBackgroundKey = self.viewportEditSuppressedGesture = None
        self.viewportEditDirtyRects = []
        self.wallBoundaryCache = {}
        self.wallBoundaryEdgeCache = {}
        self.wallTraceState = None
        self.wallTraceContexts = {}
        self.wallTraceContextPoints = 0
        self.wallContourCache = {}
        self.wallContourCachePoints = 0
        self.wallComponentCache = {}
        self.wallBodyCache = {}
        self.wallJunctionCache = {}
        self.wallSectorCache = {}
        self.wallOwnershipCache = {}
        self.wallPolygonCache = {}
        self.wallPolygonPointCount = 0
        self.dimensionOwnerCache = {}
        self.dimensionSpanCache = {}
        self.dimensionSpanCachePoints = 0
        self.dimensionOwnerState = None
        self.wallMaterialPathCache = {}
        self.wallGeometryComponents = []
        self.wallDimensionComponentCache = {}
        self.dimensionCacheKey = None
        self.dimensionCache = []
        self.dimensionBoundaryKey = None
        self.dimensionBoundaryValues = ()
        self.solidObjects = True
        self.wallStyle = "Material"
        self.materialBrushes = {(material, selected): BuildWallBrush(selected = selected, material = material)
                                for material in wallMaterials for selected in (False, True)}
        self.warningMaterialBrushes = {material: BuildWallBrush(material = material, warning = True) for material in wallMaterials}
        self.groupedMaterialBrushes = {material: BuildWallBrush(selected = True, material = material, grouped = True)
                                      for material in wallMaterials}
        self.materialGeometryKey = None
        self.materialPaths = {}
        self.wallMaterialPaths = {}
        self.wallFillPolygons = []
        self.stairGeometryKey = None
        self.stairGeometryComponents = []
        self.stairGeometryPath = QtGui.QPainterPath()
        self.stairOutlinePath = QtGui.QPainterPath()
        self.stairLandingCache = {}
        self.setMinimumSize(320, 240)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.WheelFocus)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.exportOverlay = ExportBoundsOverlay(self)
        self.roomDetection = RoomDetection(self)
        if os.environ.get("PLANNER_RENDER_DIAGNOSTICS") == "1":
            self.SetRenderDiagnosticsEnabled(True)

    def SetRenderDiagnosticsEnabled(self, enabled):
        if enabled:
            if self.renderDiagnostics is None:
                self.renderDiagnostics = RenderDiagnostics(self)
            self.renderDiagnostics.Start()
        elif self.renderDiagnostics is not None:
            self.renderDiagnostics.Stop()

    def event(self, event):
        if (getattr(self, "dragPanTimer", None) is not None and event.type() in
                (QtCore.QEvent.Type.MouseButtonRelease, QtCore.QEvent.Type.Drop, QtCore.QEvent.Type.DragLeave, QtCore.QEvent.Type.UngrabMouse,
                 QtCore.QEvent.Type.WindowDeactivate, QtCore.QEvent.Type.Hide)):
            self.StopDragPan()
        if event.type() == QtCore.QEvent.Type.UngrabMouse and getattr(self, "isPanning", False):
            self.EndPan()
        diagnostics = getattr(self, "renderDiagnostics", None)
        if diagnostics is not None and diagnostics.enabled and event.type() in (
                QtCore.QEvent.Type.MouseMove, QtCore.QEvent.Type.MouseButtonPress,
                QtCore.QEvent.Type.MouseButtonRelease, QtCore.QEvent.Type.Wheel,
                QtCore.QEvent.Type.KeyPress):
            diagnostics.RecordInput(event)
        handled = super().event(event)
        if event.type() == QtCore.QEvent.Type.MouseMove:
            self.UpdateDragPan(event.position(), event.buttons())
        elif event.type() == QtCore.QEvent.Type.DragMove:
            self.dragPanMimeData = event.mimeData()
            self.dragPanActions = event.possibleActions()
            self.UpdateDragPan(event.position(), event.buttons())
        return handled

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.performanceLabel.move(self.rulerSize + 12, max(0, self.height() - self.performanceLabel.height() - 12))
        self.performanceLabel.raise_()

    def RefreshPerformance(self):
        if not self.showFpsCounter or not self.isVisible():
            self.renderSamples.clear()
            return
        now = perf_counter()
        while self.renderSamples and now - self.renderSamples[0][0] > 1.0:
            self.renderSamples.popleft()
        if len(self.renderSamples) >= 2:
            span = self.renderSamples[-1][0] - self.renderSamples[0][0]
            fps = f"{(len(self.renderSamples) - 1) / span:.1f}" if span > 0 else "--"
        else:
            fps = "--" if self.renderSamples else "Idle"
        if self.renderSamples:
            self.lastRenderMilliseconds = sum(duration for timestamp, duration in self.renderSamples) / len(self.renderSamples)
        duration = f"{self.lastRenderMilliseconds:.1f}" if self.lastRenderMilliseconds else "--"
        text = f"FPS: {fps} | Render: {duration} ms"
        if self.performanceLabel.text() != text:
            # An opaque child updates its text without requesting another scene redraw.
            self.performanceLabel.setText(text)

    def SetFpsCounterVisible(self, visible):
        self.showFpsCounter = visible
        self.performanceLabel.setVisible(visible)
        if visible:
            self.RefreshPerformance()
            self.performanceLabel.raise_()
            self.performanceTimer.start()
        else:
            self.performanceTimer.stop()

    def ResetView(self):
        self.zoom = (self.exportOverlay.scale / (1000 * self.basePixelsPerMillimeter)
                     if self.exportOverlay.active else 1.0)
        self.panOffset = QtCore.QPointF()
        self.isPanning = False
        self.UpdateCanvasCursor()
        self.update()

    def ZoomBy(self, factor, anchor):
        self.exportOverlay.StartVectorNavigation()
        oldZoom = self.zoom
        self.zoom = max(0.02, min(100.0, self.zoom * factor))
        center = self.DrawingRect().center()
        self.panOffset = anchor - center - (anchor - center - self.panOffset) * (self.zoom / oldZoom)
        self.update()

    def DrawingRect(self):
        return QtCore.QRectF(self.rulerSize, self.rulerSize,
                            self.width() - self.rulerSize, self.height() - self.rulerSize)

    def WorldToViewport(self, worldPosition):
        scale = self.basePixelsPerMillimeter * self.zoom
        return QtCore.QPointF((self.width() + self.rulerSize) / 2 + self.panOffset.x() + worldPosition.x() * scale,
                             (self.height() + self.rulerSize) / 2 + self.panOffset.y() - worldPosition.y() * scale)

    def ViewportToWorld(self, viewportPosition):
        scale = self.basePixelsPerMillimeter * self.zoom
        return QtCore.QPointF((viewportPosition.x() - ((self.width() + self.rulerSize) / 2 + self.panOffset.x())) / scale,
                             ((self.height() + self.rulerSize) / 2 + self.panOffset.y() - viewportPosition.y()) / scale)
