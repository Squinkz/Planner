"""Synthetic scene drag/zoom parity and allocated SVG budget invariants."""
from contextlib import ExitStack
import gc
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
import weakref

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "tools")]
from PySide6 import QtCore, QtGui, QtWidgets
from fixtures.editor_interactions import PrepareScene, Step, BeginEndpoint, wallCases
from fixtures.parity_examples import ExampleWindow
from check_drag_fitting_preparation import Snapshot
from planner_app.graphics import furnishings
from planner_app.models import Furnishing
from planner_app.graphics.furnishings import FurnishingRendererMap, FurnishingRetainedBytes
from fixtures import flat_renderers_reference_20261031 as oldRenderers


def Draw(renderer, width):
    image = QtGui.QImage(220, 160, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QtCore.QRectF(5, 5, width, 120), worldSize = (1000, 600))
    painter.end()
    return image


def CheckBudgets():
    source = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 60">
        <rect x="1" y="1" width="98" height="58" fill="white" stroke="black"/>
        <text x="50" y="35" font-size="18" text-anchor="middle">TEST</text></svg>'''
    definitions = {key: dict(key = key, graphicData = source, width = 1000, length = 600) for key in ("a", "b", "c")}
    cache = FurnishingRendererMap(definitions)
    renderers = [cache[key] for key in definitions]
    baseBytes = sum(FurnishingRetainedBytes(renderer) for renderer in renderers)
    cache.byteLimit = baseBytes + min(renderer.nativeBaseBytes for renderer in renderers) * 2
    reference = oldRenderers.FurnishingRenderer(source, nominalSize = (1000, 600))
    tokens = [cache.RenderToken(key) for key in definitions]
    for frame in range(24):
        for key, renderer in zip(definitions, renderers):
            assert Draw(renderer, 130 + frame) == Draw(reference, 130 + frame), ("budget pixels", frame)
            assert len(cache) == 3, "Variant pressure evicted base artwork that fits"
            assert cache.byteCount <= cache.byteLimit
            assert cache.byteCount == sum(cache.costs.values())
            assert set(cache.identities) == set(cache)
    assert [cache.RenderToken(key) for key in definitions] == tokens
    assert any(len(renderer.letteringVariants) < 16 for renderer in renderers)
    # A borrowed solid's variants are charged to its transparent parent too.
    transparent = FurnishingRendererMap(definitions, solidBackground = False)
    parent = transparent["a"]
    transparent.byteLimit = FurnishingRetainedBytes(parent) + parent.solidRenderer.nativeBaseBytes
    for frame in range(20):
        Draw(parent.solidRenderer, 130 + frame)
        assert transparent.byteCount <= transparent.byteLimit
        assert transparent.byteCount == FurnishingRetainedBytes(parent)
    referenceCache = weakref.ref(cache)
    del cache
    gc.collect()
    assert referenceCache() is None, "Native cost callbacks retained their owning cache"
    Draw(renderers[0], 180)
    assert not renderers[0].cacheEntries


def CheckProject():
    with ExitStack() as stack:
        windows = [stack.enter_context(ExampleWindow())[0] for variant in range(2)]
        for main in windows:
            main.hide()
        views = [PrepareScene(main, "drag", variant == 0, 1000, 800) for variant, main in enumerate(windows)]
        comparisons = 0
        for wallId, vertex in wallCases:
            for view in views:
                view.CancelInteraction()
                wall = next(wall for wall in view.walls if wall.objectId == wallId)
                BeginEndpoint(view, wall, vertex)
            for frame in range(5):
                for view in views:
                    Step(view, "drag", frame)
                assert Snapshot(views[0]) == Snapshot(views[1]), ("wall state", wallId, frame)
                assert views[0].grab().toImage() == views[1].grab().toImage(), ("wall pixels", wallId, frame)
                comparisons += 1
        for view in views:
            view.CancelInteraction()
        for frame in range(16):
            case = "zoom-out" if frame < 12 else "zoom-in"
            anchors = [view.ViewportToWorld(view.DrawingRect().center()) for view in views]
            for view in views:
                Step(view, case, frame)
            assert views[0].zoom == views[1].zoom
            assert views[0].panOffset == views[1].panOffset
            for view, anchor in zip(views, anchors):
                assert QtCore.QLineF(anchor, view.ViewportToWorld(view.DrawingRect().center())).length() < 1e-7
                assert view.furnishingRenderers.byteCount <= view.furnishingRenderers.byteLimit
            assert views[0].grab().toImage() == views[1].grab().toImage(), ("zoom pixels", frame)
            comparisons += 1
        for mask in range(8):
            results = []
            for view in views:
                for index, name in enumerate(("walls", "architectural", "furnishings")):
                    view.collisionSettings[name] = bool(mask & (1 << index))
                invalid = view.InvalidArchitecturalObjects()
                results.append({obj.objectId for obj in view.walls + view.windows if id(obj) in invalid})
            assert results[0] == results[1], ("collision policy", mask)
        current = views[1]
        # Validity inspection must neither realize native artwork nor change LRU.
        normal, selected = current.furnishingRenderers, current.selectedFurnishingRenderers
        key = current.SceneRenderValueKey(None)
        appearance = current.renderChanges.appearance
        selected.clear()
        selectedKey = current.SceneRenderValueKey(None)
        order = tuple(normal.costs)
        with patch.object(furnishings, "FurnishingRenderer", side_effect = AssertionError("Validity key constructed artwork")):
            assert current.SceneRenderValueKey(None) == selectedKey
        assert tuple(normal.costs) == order
        assert len(selected) == 0
        assert key != selectedKey and current.renderChanges.appearance > appearance
        color = normal.colors["outline"]
        normal.colors["outline"] = "#123456"
        with patch.object(furnishings, "FurnishingRenderer", side_effect = AssertionError("Style key constructed artwork")):
            assert current.SceneRenderValueKey(None) != selectedKey
        normal.colors["outline"] = color
        oldLimit = normal.entryLimit
        normal.entryLimit = 1
        stable = current.SceneRenderValueKey(None)
        objects = [obj for obj in current.furnishings if type(obj) is Furnishing]
        for definition in objects[:8]:
            normal[definition.definition["key"]]
        assert current.SceneRenderValueKey(None) == stable, "Eviction changed semantic scene identity"
        normal.entryLimit = oldLimit
        definitionKey = objects[0].definition["key"]
        sourceFor = objects[0].definition.get("graphicData") or objects[0].definition["imagePath"]
        replacement = furnishings.FurnishingRenderer(sourceFor, selectionColor = "#ff0000")
        normal[definitionKey] = replacement
        changed = current.SceneRenderValueKey(None)
        assert changed != stable
        # Defensive value checks also see a direct dictionary replacement.
        direct = furnishings.FurnishingRenderer(sourceFor, selectionColor = "#00ff00")
        dict.__setitem__(normal, definitionKey, direct)
        assert current.SceneRenderValueKey(None) != changed
        CheckBudgets()
    return comparisons


def Main():
    count = CheckProject()
    print(f"PASS: {count} exact synthetic drag/zoom frames and model states, stable nonrealizing tokens, "
          "16 MiB estimated budget enforcement, variant/base reuse, borrowed solids and weak cache ownership.")


if __name__ == "__main__":
    Main()
