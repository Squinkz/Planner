"""Composite sliders repaint while held without queuing complete Print pages."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_export_preview_process import WaitForPreview
from planner_app.models import Wall
from planner_app.graphics import compositing
from planner_app.export_plan import RenderPlan


def Main():
    with ExampleWindow() as (main, folder):
        panel, v = main.exportPanel, main.viewport
        InstallScene(main, [Wall(QtCore.QPointF(1000, 1000), QtCore.QPointF(5000, 3500), 200)])
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("scaleMode", "Print")
        panel.SetScaleOption("dpi", 96)
        panel.SetOverride("titleBlock", dict(enabled = True, logoMode = "None", projectName = "Live effects"))
        panel.SetOverride("canvasColor", "#cccccc")
        panel.SetOverride("vignetteEnabled", True)
        panel.SetSectionExpanded("Composite", True)
        overlay = v.exportOverlay
        width, height = panel.PrintLayout()["paperTile"]
        overlay.bounds = (0, 0, width, height)
        panel.SetBounds(overlay.bounds)
        v.zoom = min(v.DrawingRect().width() / width, v.DrawingRect().height() / height) * .8 / v.basePixelsPerMillimeter
        v.panOffset += v.DrawingRect().center() - v.WorldToViewport(QtCore.QPointF(width / 2, height / 2))
        overlay.printPreviewTimer.stop()
        os.environ.pop("PLANNER_SYNCHRONOUS_PREVIEW", None)
        WaitForPreview(v, "png")
        context = overlay.snapshot
        slider = panel.vignetteStrengthSlider
        panel.scrollArea.ensureWidgetVisible(slider)
        QtTest.QTest.qWait(20)
        option = QtWidgets.QStyleOptionSlider()
        slider.initStyleOption(option)
        handle = slider.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_Slider, option,
                                               QtWidgets.QStyle.SubControl.SC_SliderHandle, slider)
        start = handle.center()
        beforeHistory = len(panel.exportUndoHistory)
        QtTest.QTest.mousePress(slider, QtCore.Qt.MouseButton.LeftButton, pos = start)
        assert overlay.compositeGesture, "Application mouse filter hid the composite slider source"
        images = []
        with patch.object(overlay, "renderPrintPage", wraps = overlay.renderPrintPage) as renders, \
                patch.object(overlay, "DrawPrintDrag", wraps = overlay.DrawPrintDrag) as paints:
            for delta in (10, 45, 25):
                count = paints.call_count
                position = QtCore.QPointF(start + QtCore.QPoint(delta, 0))
                event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, position,
                    QtCore.QPointF(slider.mapToGlobal(position.toPoint())), QtCore.Qt.MouseButton.NoButton,
                    QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
                QtWidgets.QApplication.sendEvent(slider, event)
                QtTest.QTest.qWait(40)
                assert paints.call_count > count, "Real held mouse drag did not repaint through the event loop"
                assert slider.isSliderDown() and overlay.previewGesture and overlay.compositeGesture
                images.append(v.grab().toImage())
                assert not overlay.previewError, overlay.previewError
                assert overlay.snapshot is context, "Composite drag rebuilt plan context"
            assert all(call.kwargs.get("decorationsOnly") for call in renders.call_args_list), "Slider drag queued complete page renders"
            assert renders.call_count == 1, "Composite values rebuilt unchanged decorations"
        assert images[0] != images[1] and images[1] != images[2], "Composite preview waited for slider release"
        finalStrength = slider.value() / 1000
        QtTest.QTest.mouseRelease(slider, QtCore.Qt.MouseButton.LeftButton, pos = position.toPoint())
        assert not overlay.compositeGesture
        assert len(panel.exportUndoHistory) == beforeHistory + 1, "Drag was split into multiple undo entries"
        WaitForPreview(v, "png")
        finalPreview = v.grab().toImage()
        pageRect = overlay.PrintPageRect(next(iter(overlay.printPageCache)))
        sample = (pageRect.topLeft() + QtCore.QPointF(pageRect.width() * .95, pageRect.height() * .65)) * v.devicePixelRatioF()
        liveColor = images[-1].pixelColor(sample.toPoint())
        finalColor = finalPreview.pixelColor(sample.toPoint())
        assert max(abs(a - b) for a, b in zip(liveColor.getRgb(), finalColor.getRgb())) <= 5, "Live effects omitted or doubled the title block"
        for page, (path, args) in zip(sorted(overlay.printPageCache), panel.ExportJobs(folder / "final.png", "png")):
            assert overlay.printPageCache[page] == RenderPlan(**args), "Final composite page differs from export"
        panel.UndoExport()
        assert panel.overrides.get("vignetteStrength", .125) == .125
        panel.RedoExport()
        assert panel.overrides["vignetteStrength"] == finalStrength
        overlay.previewProcess.Close()
        os.environ["PLANNER_SYNCHRONOUS_PREVIEW"] = "1"
        normal = QtGui.QImage(8, 8, QtGui.QImage.Format.Format_RGB32)
        for y in range(8):
            for x in range(8):
                normal.setPixelColor(x, y, QtGui.QColor(40 + x * 25, 40 + y * 25, 255))
        assert normal.save(str(folder / "live_t1.png"))
        with patch.object(compositing, "texturesDirectory", folder):
            panel.SetOverride("texture", "live_t1.png")
            for mode in ("Print", "Digital", "Architectural"):
                panel.SetScaleOption("scaleMode", mode)
                overlay.printPreviewTimer.stop()
                v.grab()
                for name, slider in panel.textureSliders.items():
                    values = (30, 140) if name == "Angle" else (250, 750)
                    slider.setSliderDown(True)
                    images = []
                    context = overlay.snapshot
                    with patch.object(overlay, "renderPrintPage", wraps = overlay.renderPrintPage) as renders:
                        for value in values:
                            slider.setSliderPosition(value)
                            images.append(v.grab().toImage())
                            assert not overlay.previewError, overlay.previewError
                            assert overlay.snapshot is context
                        if mode == "Print":
                            assert all(call.kwargs.get("decorationsOnly") for call in renders.call_args_list)
                    assert images[0] != images[1], (mode, name, "Held slider did not update preview")
                    slider.setSliderDown(False)
                    v.grab()
                    assert not overlay.previewError, overlay.previewError
                    assert v.rasterCacheBudget.RetainedBytes() <= v.viewportRasterByteLimit
            panel.SetOverride("texture", None)
        panel.borderSizeSlider.setSliderDown(True)
        assert not overlay.compositeGesture, "Unrelated sliders entered composite-only preview handling"
        panel.borderSizeSlider.setSliderDown(False)
    print("Held composite sliders update across scale modes; Print reuses context/decorations and final pages match export")


if __name__ == "__main__":
    Main()
