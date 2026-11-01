"""Frozen paint/group parity and prepared SVG process-transport parity."""
import gc
import os
from pathlib import Path
import pickle
import random
import sys
import tempfile
from unittest.mock import patch
import weakref
from xml.etree import ElementTree

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.models import Wall, Furnishing, Label, RoomLabel, NorthArrow
from planner_app.viewport.widget import DrawingViewport
from planner_app.graphics.svg_preview import SvgPreviewRenderer, SvgPreviewDocument
from planner_app.export_preview import LoadPreviewResult
from planner_app.export_preview_worker import WriteSvgPreview
from planner_app import export_preview_worker
from planner_app.geometry.snapping import SnapPoint, PrepareRayTargets, PrepareTargetIndex
from fixtures.point_snapping_reference_20261031 import SnapPoint as ReferencePoint
from fixtures.final_followups_reference_20261031 import ReferenceViewport
from fixtures.svg_reference_20261031 import SvgPreviewRenderer as ReferenceSvg
from check_drag_fitting_preparation import Setup, Snapshot
from shiboken6 import delete


def Paint(view, dirty = None):
    image = QtGui.QImage(view.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QtGui.QColor("white"))
    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    if dirty is not None:
        region = QtGui.QRegion()
        for rect in dirty:
            region |= QtGui.QRegion(rect.toAlignedRect())
        painter.setClipRegion(region)
    drawing = view.DrawingRect()
    ppm = view.basePixelsPerMillimeter * view.zoom
    view.DrawScene(painter, drawing, view.WorldToViewport(QtCore.QPointF()), ppm, dirty)
    view.DrawLabels(painter, ppm, {id(view.labels[0])} if view.labels else (), drawingRect = drawing, dirtyRects = dirty)
    painter.end()
    return image


def CheckPaint():
    point = QtCore.QPointF
    actual, reference = DrawingViewport(), ReferenceViewport()
    for view in (actual, reference):
        view.resize(900, 650)
        view.showMeasurements = view.showTips = False
        view.performanceTimer.stop()
    actual.walls = [Wall(point(-3500, 1200), point(3500, 1200), 200)]
    actual.furnishings = [Furnishing(actual.furnishingDefinitions["desk"], point((index % 10) * 3000, (index // 10) * 2000))
                          for index in range(100)] + [NorthArrow(point(-1800, 0))]
    actual.labels = [Label(point((index % 10) * 3000, -1800 - (index // 10) * 1800), "Áj é 家\nItalic bearings")
                     for index in range(100)] + [RoomLabel(point(0, -800), "ROOM")]
    # Repeated references must retain the original painting multiplicity/order.
    actual.labels += [actual.labels[0]]
    actual.furnishings += [actual.furnishings[0]]
    for name in ("walls", "furnishings", "labels"):
        setattr(reference, name, getattr(actual, name))
    for frame in range(48):
        obj = actual.furnishings[frame % 7]
        obj.firstVertex += point(17, -11)
        obj.secondVertex += point(17, -11)
        obj.flipHorizontal = bool(frame % 2)
        obj.angle += 7
        label = actual.labels[frame % 5]
        label.angle += 13
        if frame % 9 == 0:
            label.text += " é"
        actual.labels[-2].areaSquareMillimeters = frame * 123456789
        dirty = [QtCore.QRectF(40, 30, 430, 370), QtCore.QRectF(650, 480, 200, 130)] if frame % 3 else None
        for view in (actual, reference):
            view.zoom = (.13, .4, 1, 2)[frame % 4]
            view.panOffset = point(frame * 17 - 300, frame * 11)
            view.visibility["Furnishings"] = frame % 13 != 0
            view.hiddenObjectIds = {id(actual.labels[2])} if frame % 4 else set()
        assert Paint(actual, dirty) == Paint(reference, dirty), ("paint", frame)
        if frame % 16 == 0:
            images = []
            for view in (actual, reference):
                image = QtGui.QImage(view.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                view.render(image)
                images.append(image)
            assert images[0] == images[1], ("complete viewport", frame)
    # An unchanged sparse view must not prepare every offscreen object's bounds.
    Paint(actual)
    with patch.object(actual, "PaintObjectBounds", wraps = actual.PaintObjectBounds) as bounds:
        Paint(actual)
        assert bounds.call_count == 0
        actual.furnishings[0].width += 3
        Paint(actual)
        assert bounds.call_count == 1
    actual.renderChanges.Bump("geometry")
    with patch.object(actual, "PaintObjectBounds", wraps = actual.PaintObjectBounds) as bounds:
        Paint(actual)
        assert bounds.call_count > 100
    assert Paint(actual) == Paint(reference)
    # Hidden objects must not force artwork/layout loads.
    actual.hiddenObjectIds = {id(obj) for obj in actual.furnishings + actual.labels}
    with patch.object(actual, "PaintObjectBounds", side_effect = AssertionError("hidden artwork loaded")):
        Paint(actual)
    for view in (actual, reference):
        view.close()
    temporary = DrawingViewport()
    temporary.furnishings = [Furnishing(temporary.furnishingDefinitions["desk"])]
    temporary.PaintObjectCandidates(temporary.DrawingRect(), temporary.basePixelsPerMillimeter * temporary.zoom)
    old = weakref.ref(temporary.furnishings[0])
    temporary.furnishings = []
    temporary.ClearGeometryCaches()
    gc.collect()
    assert old() is None and temporary.renderChanges.paintChanges is None
    temporary.furnishings = [Furnishing(temporary.furnishingDefinitions["desk"], point(index * 5000, 6000)) for index in range(260)]
    temporary.PaintObjectCandidates(temporary.DrawingRect(), temporary.basePixelsPerMillimeter * temporary.zoom)
    for obj in temporary.furnishings:
        obj.firstVertex += point(1, 0)
        obj.secondVertex += point(1, 0)
        temporary.PaintObjectCandidates(temporary.DrawingRect(), temporary.basePixelsPerMillimeter * temporary.zoom)
        assert len(temporary.paintObjectIndex["overlay"]) <= 256
    temporary.close()


def CheckGroups():
    point, modifier = QtCore.QPointF, QtCore.Qt.KeyboardModifier
    actual, reference = DrawingViewport(), ReferenceViewport()
    frames = 0
    for case in range(32):
        for view in (actual, reference):
            view.resize(900, 650)
            view.showMeasurements = view.showTips = False
            Setup(view, case, True)
            view.snapEnabled = True
        for frame in range(8):
            mods = (modifier.NoModifier, modifier.ControlModifier, modifier.ShiftModifier,
                    modifier.AltModifier)[frame % 4]
            for view in (actual, reference):
                if frame == 1:
                    view.walls[-1].secondVertex += point(13, -17)
                    view.labels[-1].text = "outside edit"
                if frame == 4:
                    view.connectedEnabled = not view.connectedEnabled
                view.midpointSnapEnabled = bool((frame + case) % 2)
                view.cornerSnapEnabled = bool((frame + case) % 3)
                view.vertexSnapEnabled = bool((frame + case) % 4)
                view.UpdateGroupDrag(view.dragStart + point(70 + frame * 23, 20 - frame * 3), mods)
            assert Snapshot(actual) == Snapshot(reference), ("group", case, frame)
            frames += 1
    for view in (actual, reference):
        view.CancelInteraction()
        assert view.renderChanges.snapChanges is None and "groupSnapPreparation" not in view.__dict__
        view.walls = [Wall(point(index * 6000, 0), point(index * 6000 + 4000, 0), 200) for index in range(128)]
        view.furnishings = [Furnishing(view.furnishingDefinitions["desk"], point(index * 6000, 6000)) for index in range(128)]
        view.labels = [Label(point(index * 6000, 10000), "Label") for index in range(128)]
        view.snapEnabled = view.vertexSnapEnabled = view.cornerSnapEnabled = True
        view.connectedEnabled = False
        view.SetSelection([(view.furnishings[0], None), (view.labels[0], None)], notify = False)
        view.interactionBefore = view.CaptureState()
        view.dragStart, view.isDragging = point(400, 300), True
        view.StartGroupDrag()
        view.UpdateGroupDrag(point(450, 330), modifier.NoModifier)
    with patch.object(actual, "StairSnapTargets", wraps = actual.StairSnapTargets) as targets, \
            patch.object(actual, "NumericSnapTargets", wraps = actual.NumericSnapTargets) as numeric:
        for frame in range(6):
            for view in (actual, reference):
                view.UpdateGroupDrag(point(460 + frame * 7, 340), modifier.NoModifier)
            assert Snapshot(actual) == Snapshot(reference), ("warm group", frame)
        assert targets.call_count == numeric.call_count == 0
        for view in (actual, reference):
            view.interactionBefore[5][0][1].setX(17.25)
            view.UpdateGroupDrag(point(530, 350), modifier.NoModifier)
        assert targets.call_count > 0
        assert Snapshot(actual) == Snapshot(reference), "mutable baseline snap anchors"
    for view in (actual, reference):
        view.CancelInteraction()
        view.close()
    return frames


def CheckSvg():
    namespace = "http://www.w3.org/2000/svg"
    samples = [f'''<svg xmlns="{namespace}" viewBox="0 0 200 120" {extra}>
        <defs>{style}<clipPath id="clip"><path d="M 5 5 L 150 5 Q 200 60 150 100 L 5 100 Z"/></clipPath>
        <linearGradient id="gradient"><stop offset="0" stop-color="#ff0000" data-planner-stop-color="wallOutline"/>
        <stop offset="1" stop-color="#008800"/></linearGradient></defs>
        <g transform="matrix(1,0,0,1,3,2)"><g clip-path="url(#clip)">
        <rect id="paint" x="0" y="0" width="180" height="110" fill="url(#gradient)"/>
        <g><path d="M 10 80 L 180 10" fill="none" stroke="#ff0000" stroke-width="2" data-planner-stroke="wallOutline"/></g>
        </g></g></svg>''' for extra, style in (("", ""), ('opacity="0.6"', ""),
            ("", "<style>rect {stroke-width: 2}</style>"))]
    for sample in samples:
        source = ElementTree.fromstring(sample)
        before = ReferenceSvg(source)
        preparation = SvgPreviewRenderer(source, prepareOnly = True)
        payload = pickle.loads(pickle.dumps(preparation.PreparedData(), protocol = pickle.HIGHEST_PROTOCOL))
        delete(preparation)
        document = SvgPreviewDocument(payload["root"], 1)
        document.prepared = payload
        with tempfile.TemporaryDirectory(dir = root / "tmp") as directory:
            path = Path(directory) / "prepared.vector"
            with path.open("wb") as output:
                transport = pickle.Pickler(output, protocol = pickle.HIGHEST_PROTOCOL)
                transport.dump(payload["root"])
                logicalSize = output.tell() * 2
                transport.dump(dict(format = "Planner prepared SVG", size = logicalSize, data = payload))
            document = LoadPreviewResult(path, "svg")
            assert document.root is document.prepared["root"] and document.size == logicalSize
            oversized = LoadPreviewResult(path, "svg", QtCore.QCoreApplication.instance().thread(), rendererByteLimit = 0)
            assert oversized.renderer is None and oversized.prepared is None and oversized.size == logicalSize
            with patch.object(SvgPreviewRenderer, "PreparedData", side_effect = MemoryError("preparation probe")):
                WriteSvgPreview(path, source)
            fallback = LoadPreviewResult(path, "svg")
            assert fallback.prepared is None and ElementTree.tostring(fallback.root) == ElementTree.tostring(source)
            originalPickler = pickle.Pickler
            class FailingPickler:
                def __init__(self, destination, **kwargs):
                    self.destination = destination
                    self.writer = originalPickler(destination, **kwargs)
                    self.calls = 0
                def dump(self, value):
                    self.calls += 1
                    if self.calls == 2:
                        self.destination.write(b"partial preparation")
                        raise MemoryError("transport probe")
                    self.writer.dump(value)
                def clear_memo(self):
                    self.writer.clear_memo()
            with patch.object(export_preview_worker.pickle, "Pickler", FailingPickler):
                WriteSvgPreview(path, source)
            fallback = LoadPreviewResult(path, "svg")
            assert fallback.prepared is None and ElementTree.tostring(fallback.root) == ElementTree.tostring(source)
        after = SvgPreviewRenderer(document)
        assert document.prepared is None
        for recolor in (False, True):
            if recolor:
                assert before.Recolor({"wallOutline": "#8855ff"}) == after.Recolor({"wallOutline": "#8855ff"})
            images = []
            for renderer in (before, after):
                image = QtGui.QImage(600, 360, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                image.fill(QtCore.Qt.GlobalColor.transparent)
                painter = QtGui.QPainter(image)
                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                renderer.render(painter)
                painter.end()
                images.append(image)
            assert images[0] == images[1], ("prepared SVG", recolor)
        delete(before)
        delete(after)


def CheckPointQueries():
    randomizer = random.Random(20261031)
    for case in range(2400):
        offset = (0, 1e12, 1e16)[case % 3]
        count = (0, 1, 32, 33, 128, 512)[case % 6]
        targets = [(offset + randomizer.uniform(-2000, 2000), offset if case % 4 else offset + index,
                    bool(index % 3)) for index in range(count)]
        if case % 7 == 0:
            targets += targets[:10]
        if case % 11 == 0:
            # Many distinct coordinates can share one rounded pixel distance.
            targets = [(index * 1e-10, index % 2, True) for index in range(count)]
        position = offset + randomizer.uniform(-1000, 1000), offset + randomizer.uniform(-1000, 1000)
        scale = (1e-15, .03, .3, 1, 100)[case % 5]
        args = position, targets, scale, (0, 14, 20)[case % 3], bool(case % 4), 25.4 if case % 3 else None
        index = PrepareTargetIndex(targets) if len(targets) > 32 else None
        assert SnapPoint(*args, targetIndex = index, rayTargets = PrepareRayTargets(targets)) == ReferencePoint(
            *args, targetIndex = index), ("point query", case)


def Main():
    (root / "tmp").mkdir(exist_ok = True)
    app = QtWidgets.QApplication([])
    app.setStyle("Fusion")
    LoadApplicationFonts(app)
    CheckPaint()
    frames = CheckGroups()
    CheckSvg()
    CheckPointQueries()
    print(f"PASS: 48 exact sparse/rotated/dirty paint comparisons, {frames} frozen group frames, "
          "2,400 point-query matrices, hidden artwork, release, and exact prepared SVG pixels/recoloring/budgets.")


if __name__ == "__main__":
    Main()
