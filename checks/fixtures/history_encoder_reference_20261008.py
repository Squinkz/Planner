"""Persist scene history as validated, detached project scenes, without selection."""
from copy import copy
from types import SimpleNamespace
from PySide6 import QtCore
from .models import Arrow, Railing, Stair
from .project_codec import EncodeScene, DecodeProject


def EncodeHistoryState(state):
    objects = [entry[0] for index in (0, 3, 5, 8) for entry in state[index]]
    clones = {id(obj): copy(obj) for obj in objects}
    walls, windows, furnishings, labels = [], [], [], []
    for obj, firstX, firstY, secondX, secondY, width, firstMiter, secondMiter, material, sizing, extra, measurementHidden in state[0]:
        clone = clones[id(obj)]
        clone.measurementHidden = measurementHidden
        clone.firstVertex, clone.secondVertex = QtCore.QPointF(firstX, firstY), QtCore.QPointF(secondX, secondY)
        clone.width, clone.firstMiter, clone.secondMiter, clone.material = width, firstMiter, secondMiter, material
        if isinstance(clone, Arrow):
            clone.solidTip, clone.tipSize, clone.intensity = extra[:3]
            clone.directionReversed = extra[3] if len(extra) > 3 else False
        if isinstance(clone, Railing):
            clone.autosize, clone.manualPostCount = sizing
        if isinstance(clone, Stair):
            clone.autosize, clone.manualStepCount = sizing
            clone.directionReversed = extra
        walls.append(clone)
    for entry in state[3]:
        obj, parent, center, length, hinge, swing, sill, flipped, measurementHidden = entry[:9]
        clone = clones[id(obj)]
        clone.measurementHidden = measurementHidden
        clone.windowWell, clone.wellDepth, clone.wellDashed = entry[9] if len(entry) > 9 else (False, 600.0, False)
        clone.parentWall, clone.centerFraction, clone.length = clones[id(parent)], center, length
        for attribute, value in (("hingeAtSecond", hinge), ("swingsOutwards", swing), ("panelsFlipped", swing),
                                 ("sillDepth", sill), ("measurementFlipped", flipped)):
            if hasattr(clone, attribute):
                setattr(clone, attribute, value)
        windows.append(clone)
    for index, target in ((5, furnishings), (8, labels)):
        for entry in state[index]:
            clone = clones[id(entry[0])]
            clone.measurementHidden = entry[-1]
            clone.firstVertex, clone.secondVertex, clone.width = QtCore.QPointF(entry[1]), QtCore.QPointF(entry[2]), entry[3]
            if index == 8:
                clone.text, clone.intensity = entry[4:6]
            target.append(clone)
    scene = SimpleNamespace(walls = walls, windows = windows, furnishings = furnishings, labels = labels,
                            objectGroups = [tuple(clones[id(obj)] for obj in group) for group in state[6]],
                            hiddenObjects = [clones[id(obj)] for obj in state[7]])
    return EncodeScene(scene)


def DecodeHistory(history, settings, definitions, validatePlacement = True):
    from .viewport.scene import SceneEditingMixin
    if not isinstance(history, dict) or set(history) != {"undo", "redo"}:
        raise ValueError("Invalid project history.")
    decoded = {}
    objectCount = 0
    for name in ("undo", "redo"):
        edits = history[name]
        if not isinstance(edits, list) or len(edits) > 200:
            raise ValueError("Too many project history entries.")
        decoded[name] = []
        for edit in edits:
            if not isinstance(edit, list) or len(edit) != 2:
                raise ValueError("Invalid project history edit.")
            states = []
            for scene in edit:
                if not isinstance(scene, dict) or not isinstance(scene.get("objects"), list):
                    raise ValueError("Invalid project history scene.")
                objectCount += len(scene["objects"])
                if objectCount > 400000:
                    raise ValueError("Project history is too large.")
                data = {"format": "Planner Project", "version": 1, "scene": scene, "settings": settings}
                walls, windows, furnishings, groups, hidden, flags, view, labels = DecodeProject(data, definitions, validatePlacement = validatePlacement)
                snapshot = SimpleNamespace(walls = walls, windows = windows, furnishings = furnishings, labels = labels,
                                           objectGroups = groups, hiddenObjects = hidden, selectedWall = None, selectedVertex = None,
                                           SelectionEntries = lambda: [])
                states.append(SceneEditingMixin.CaptureState(snapshot))
            decoded[name].append(tuple(states))
    return decoded
