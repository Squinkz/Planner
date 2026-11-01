"""Portable editor gestures using only the synthetic dense-room fixture."""
import json
from pathlib import Path
from types import MethodType

from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Wall
from planner_app.project_codec import DecodeProject
from fixtures.flat_view_reference_20261031 import ReferenceViewport
from fixtures import flat_renderers_reference_20261031 as oldRenderers


# An isolated oblique wall, a shared room corner and a boundary with openings.
wallCases = ((48, 1), (1, 0), (5, 1))


def PrepareScene(main, case, baseline, width = 1000, height = 800):
    path = Path(__file__).with_name("plans") / "dense_furnishings.plan"
    data = json.loads(path.read_text(encoding = "utf-8"))
    decoded = DecodeProject(data, main.viewport.furnishingDefinitions, validatePlacement = False)
    main.ApplyProject(decoded, path)
    main.hide()
    view = main.viewport
    view.performanceTimer.stop()
    view.setFixedSize(width, height)
    main.resize(width + 450, height + 100)
    wall = Wall(QtCore.QPointF(17000, 1000), QtCore.QPointF(20000, 1800), 180)
    wall.objectId = 48
    assert all(obj.objectId != wall.objectId for obj in view.walls + view.windows + view.furnishings + view.labels)
    view.walls.append(wall)
    view.EnsureObjectIds()
    view.sceneChanged.emit()
    view.zoom = .45
    if baseline:
        for name in ("SceneRenderValueKey", "EditSceneSnapshot", "JoinedObjectBounds", "JoinedObjectsOverlap"):
            setattr(view, name, MethodType(ReferenceViewport.__dict__[name], view))
        for name in ("furnishingRenderers", "selectedFurnishingRenderers"):
            current = getattr(view, name)
            previous = oldRenderers.FurnishingRendererMap(current.definitions, selected = current.selected,
                lineWidth = current.lineWidth, solidBackground = current.solidBackground, colors = current.colors,
                selectionColor = current.selectionColor, excludeErrors = current.excludeErrors)
            previous.changed = current.changed
            object.__setattr__(view, name, previous)
        view.renderChanges.Bump("appearance")
        view.ClearGeometryCaches()
    QtWidgets.QApplication.processEvents()
    if case == "drag":
        BeginEndpoint(view, wall, 1)
    return view


def BeginEndpoint(view, wall, index):
    point = QtCore.QPointF
    view.CancelInteraction()
    # Keep the edited endpoint visible: equality of two offscreen renders is
    # insufficient coverage for paint invalidation during a live wall edit.
    vertex = (wall.firstVertex, wall.secondVertex)[index]
    view.panOffset += view.DrawingRect().center() - view.WorldToViewport(vertex)
    view.SetSelection([(wall, index)])
    view.interactionBefore = view.CaptureState()
    view.dragSource = wall
    view.dragSourceVertex = index
    view.dragVertices = point(wall.firstVertex), point(wall.secondVertex)
    view.dragSourceVertices = tuple(map(point, view.dragVertices))
    view.dragStart = view.WorldToViewport(view.dragVertices[index])
    assert view.DrawingRect().contains(view.dragStart)
    view.isDragging = True
    view.dragAttachments = view.AttachedVertices(wall, captureAll = True)
    view.dragSourceAttachments = list(view.dragAttachments)
    view.dragSourceConstraints = list(view.dragConstraints)


def Step(view, case, frame):
    if case == "drag":
        view.UpdateInteraction(view.dragStart + QtCore.QPointF(25 + frame * 3, 17 + frame),
            QtCore.Qt.KeyboardModifier.NoModifier)
    else:
        position = view.DrawingRect().center()
        event = QtGui.QWheelEvent(position, view.mapToGlobal(position.toPoint()), QtCore.QPoint(),
            QtCore.QPoint(0, 120 if case == "zoom-in" else -120), QtCore.Qt.MouseButton.NoButton,
            QtCore.Qt.KeyboardModifier.NoModifier, QtCore.Qt.ScrollPhase.NoScrollPhase, False)
        view.wheelEvent(event)
    QtWidgets.QApplication.processEvents()
    view.grab()
