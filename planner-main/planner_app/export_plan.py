"""Render a .plan crop to PNG or SVG using Planner's existing drawing methods.

Usage: python -m planner_app.export_plan PLAN SCALE [-png | -svg]
       python -m planner_app.export_plan PLAN SCALE X Y WIDTH LENGTH [-png | -svg]
SCALE is pixels/SVG units per meter and overrides the saved scale mode.
Saved export settings supply appearance and crop; missing crops are automatic.
Optional bounds override the saved crop, in millimeters with X/Y at the lower-left.
"""

import argparse
import json
import math
import os
from pathlib import Path
import sys
from functools import wraps
from copy import deepcopy
from xml.etree import ElementTree


def RecolorSvgPreview(data, colors, markers = None):
    """Update named scene paints without rebuilding exported vector geometry."""
    from PySide6 import QtGui
    root = ElementTree.fromstring(data)
    for element in root.iter():
        for attribute in ("fill", "stroke", "stop-color"):
            role = markers.get(element.get(attribute)) if markers is not None else element.get("data-planner-" + attribute)
            if role is not None:
                element.set("data-planner-" + attribute, role)
                element.set(attribute, QtGui.QColor(colors[role]).name())
    return ElementTree.tostring(root, encoding = "utf-8", xml_declaration = True)


def PreviewPaintRoles(render):
    @wraps(render)
    def Render(*args, **kwargs):
        if not (kwargs.get("preview") and kwargs.get("previewScene") and kwargs.get("outputFormat") == "svg"
                and kwargs.get("applyTheme") is False):
            return render(*args, **kwargs)
        from planner_app.graphics import palette
        from PySide6 import QtGui
        original = dict(palette.themeColors)
        roles = ("canvas", "objectOutline", "wallOutline", "grid")
        markers = {}
        for index, role in enumerate(roles):
            marker = f"#02{index + 1:02x}a7"
            while marker in original.values() or marker in markers:
                marker = f"#{int(marker[1:], 16) + 1:06x}"
            markers[marker] = role
            markerColor = QtGui.QColor(marker)
            markerColor.setAlpha(QtGui.QColor(original[role]).alpha())
            # Furnishing paints pass through an SVG reader, which requires RGB
            # hex for opaque colors. Qt's #AARRGGBB form otherwise becomes black.
            palette.themeColors[role] = markerColor.name() if markerColor.alpha() == 255 else markerColor.name(QtGui.QColor.NameFormat.HexArgb)
        try:
            result = render(*args, **kwargs)
        finally:
            palette.themeColors.update(original)
        return RecolorSvgPreview(result, original, markers)
    return Render


@PreviewPaintRoles
def RenderPlan(planPath, scale, bounds = None, ruler = False, outputFormat = "png", projectData = None, applyTheme = True, border = None,
               dpi = None, architecturalScale = None, borderSize = 28, vignetteStrength = 0, texture = None, textureAngle = 0, textureSettings = None, wallStyle = "Material", solidObjects = True, gridOrigin = (0.0, 0.0), preview = False, previewScene = False, clipCache = None, furnishingDefinitions = None, useExportSettings = False):
    """Return a QImage or SVG bytes, using identical layout and scene drawing.

    projectData accepts an unsaved scene instead of reading planPath. GUI callers
    use applyTheme = False to keep their already active export theme unchanged.
    They also supply their resolved catalog so export uses the editor's assets
    instead of reloading disk definitions on every preview.
    useExportSettings resolves saved Export-tab overrides for the CLI. The scale
    argument remains a digital density and explicit bounds override the saved crop.
    """
    border = border if border is not None else "Ruler" if ruler else "None"
    if border not in ("None", "Plain", "Frame", "Corner Marks", "Reference Zones", "Marked", "Ruler", "Ruler + Reference Zones"):
        raise ValueError("Invalid export border.")
    if type(solidObjects) is not bool:
        raise ValueError("Solid objects must be a boolean.")
    if wallStyle not in ("Material", "Solid", "Outline"):
        raise ValueError("Invalid export wall style.")
    ruler = border in ("Marked", "Ruler")
    previewScene = preview and previewScene and outputFormat == "svg"
    from PySide6 import QtCore, QtGui, QtWidgets, QtSvg
    from planner_app.catalog import LoadFurnishings
    from planner_app.graphics import palette
    from planner_app.graphics.compositing import DrawVignette, DrawNormalTexture
    from planner_app.graphics.export_border import DrawExportBorder, DrawRulerZones
    from planner_app.graphics.furnishings import FurnishingRendererMap
    from planner_app.graphics.fonts import LoadApplicationFonts
    from planner_app.graphics.theme import ApplyApplicationTheme
    from planner_app.paths import fontsDirectory
    from planner_app.project_codec import DecodeProject, ReadProjectBytes
    from planner_app.viewport.widget import DrawingViewport
    from planner_app.export_bounds import AutomaticBounds, BorderSize

    if not math.isfinite(textureAngle) or not 0 <= textureAngle <= 360:
        raise ValueError("Texture angle must be between 0 and 360 degrees.")
    if not math.isfinite(vignetteStrength) or not 0 <= vignetteStrength <= 2:
        raise ValueError("Vignette strength must be between 0 and 2.")
    if outputFormat not in ("png", "svg"):
        raise ValueError("Output format must be png or svg.")
    if type(borderSize) is not int or not 1 <= borderSize <= 128:
        raise ValueError("Border size must be an integer between 1 and 128.")
    if dpi is not None and (type(dpi) is not int or not 1 <= dpi <= 2400):
        raise ValueError("DPI must be an integer between 1 and 2400.")
    if architecturalScale is not None and (not math.isfinite(architecturalScale) or not 1 <= architecturalScale <= 100000):
        raise ValueError("Invalid architectural scale.")
    if not math.isfinite(scale):
        raise ValueError("Scale must be a finite number.")
    if scale <= 0:
        raise ValueError("Scale, width and length must be greater than zero.")
    if bounds is not None:
        if len(bounds) != 4 or not all(math.isfinite(value) for value in bounds):
            raise ValueError("Bounds must contain four finite numbers.")
        if bounds[2] <= 0 or bounds[3] <= 0:
            raise ValueError("Scale, width and length must be greater than zero.")

    # Give the Windows offscreen backend a font directory before startup.
    if sys.platform == "win32" and "QT_QPA_FONTDIR" not in os.environ:
        os.environ["QT_QPA_FONTDIR"] = str(fontsDirectory)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    data = projectData if projectData is not None else json.loads(ReadProjectBytes(planPath).decode("utf-8-sig"))
    # History is irrelevant to rendering and may contain many previous scenes.
    if isinstance(data, dict):
        data = {key: value for key, value in data.items() if key != "history"}
    definitions = (dict(furnishingDefinitions) if furnishingDefinitions is not None else
                   {item["key"]: item for item in LoadFurnishings()})
    walls, windows, furnishings, groups, hidden, settings, savedView, labels = DecodeProject(data, definitions)
    definitions.update(settings["embeddedFurnishings"])
    export = settings["exportSettings"]
    if useExportSettings:
        # Match the Export tab's inherited view and partial option groups. Keep
        # sizing units tied to the editor even when export labels use other units.
        settings["autoSizingUnitsMode"] = settings["unitsMode"]
        settings["unitsMode"] = export.get("unitsMode", "Millimeters")
        for name in ("showGrid", "viewportSettings", "lineworkSettings", "measurementVisibility", "visibility",
                     "wallMeasurementMode", "wallMeasurementReference"):
            if name not in export:
                continue
            if isinstance(export[name], dict):
                if name == "measurementVisibility":
                    settings[name] = {key: enabled and settings["showMeasurements"] for key, enabled in settings[name].items()}
                settings[name].update(export[name])
            else:
                settings[name] = export[name]
        if "measurementVisibility" in export:
            settings["showMeasurements"] = any(settings["measurementVisibility"].values())
        if "visibility" in export:
            settings["visibility"]["World"] = any(value for key, value in settings["visibility"].items() if key != "World")
        bounds = bounds if bounds is not None else export.get("bounds")
        border = export.get("border", "Ruler + Reference Zones" if "ruler" not in export else "Ruler" if export["ruler"] else "None")
        borderSize = export.get("borderSize", 28)
        ruler = border in ("Marked", "Ruler")
        wallStyle = export.get("wallStyle", "Material")
        solidObjects = export.get("solidObjects", True)
        gridOrigin = export.get("gridOrigin", (0.0, 0.0))
        texture = export.get("texture")
        textureAngle = export.get("textureAngle", 0)
        defaults = {"strength": .5, "highlights": 1, "midtones": 1, "shadows": 1}
        if texture is not None:
            from planner_app.graphics.compositing import TextureMapping
            try:
                label, mode, textureScale, defaults = TextureMapping(texture, includeDefaults = True)
            except ValueError:
                pass
        textureSettings = {name.lower(): export.get("texture" + name, defaults[name.lower()])
                           for name in ("Strength", "Highlights", "Midtones", "Shadows")}
        textureSettings["scaleOverride"] = export.get("textureScale")
        vignetteStrength = export.get("vignetteStrength", .25) if export.get("vignetteEnabled", False) else 0
        dpi = architecturalScale = None
    if applyTheme:
        from planner_app.ui.app_preferences import LoadAppPreferences
        preferencesPath, preferences = LoadAppPreferences()
        themes = {}
        for field, themeType in (("uiTheme", "ui"), ("canvasTheme", "canvas")):
            name = preferences.get(field)
            if isinstance(name, str) and palette.themeDefinitions.get(name, {}).get("type") == themeType:
                themes[field] = name
        if "canvasTheme" in settings["exportSettings"]:
            themes["canvasTheme"] = settings["exportSettings"]["canvasTheme"]
        palette.SetThemes(**themes)
        ApplyApplicationTheme(app)
        if useExportSettings:
            for name, role in (("canvasColor", "canvas"), ("linesColor", "objectOutline"),
                               ("linesColor", "wallOutline"), ("borderColor", "rulerBackground"), ("gridColor", "grid")):
                if name in export:
                    palette.themeColors[role] = export[name]
    viewport = DrawingViewport()
    if clipCache is not None:
        viewport.objectClipCache = clipCache
    try:
        # Hidden widgets need polishing explicitly to receive the GUI's stylesheet font.
        viewport.ensurePolished()
        viewport.setMinimumSize(0, 0)
        viewport.walls, viewport.windows, viewport.furnishings = walls, windows, furnishings
        viewport.solidObjects = solidObjects
        viewport.wallStyle = wallStyle
        viewport.labels = labels
        viewport.objectGroups, viewport.hiddenObjects = groups, hidden
        viewport.hiddenObjectIds = {id(obj) for obj in hidden}
        viewport.visibility = dict(settings["visibility"])
        if bounds is None:
            bounds = AutomaticBounds(viewport)
            print("Automatic bounds (mm): " + " ".join(format(value, ".10g") for value in bounds))

        x, y, width, length = bounds
        pixelsPerMillimeter = scale / 1000.0
        pixelWidth = width * pixelsPerMillimeter
        pixelHeight = length * pixelsPerMillimeter
        if not all(math.isfinite(value) for value in (pixelWidth, pixelHeight, x + width, y + length,
                                                      x * pixelsPerMillimeter, (y + length) * pixelsPerMillimeter)):
            raise ValueError("Scale and bounds exceed the supported numeric range.")
        if pixelWidth <= 0 or pixelHeight <= 0:
            raise ValueError("Scale is too small to represent the bounds.")
        rulerSize = BorderSize(border, borderSize)
        # Linked resolution inputs may land a few floating-point bits above an
        # integer. Stabilize the ceiling without rounding away fractional pixels.
        imageWidth = max(1, math.ceil(round(pixelWidth, 8))) + 2 * rulerSize
        imageHeight = max(1, math.ceil(round(pixelHeight, 8))) + 2 * rulerSize
        # Reject excessive allocations explicitly; never silently reduce scale.
        if ((imageWidth > 32767 or imageHeight > 32767) and not (preview and outputFormat == "svg")
                or outputFormat == "png" and imageWidth * imageHeight > 100_000_000):
            raise ValueError("Render exceeds 32,767 pixels per side or 100 million pixels. Choose smaller bounds or scale.")
        if preview and outputFormat == "svg" and max(imageWidth, imageHeight) > 16_777_215:
            raise ValueError("SVG preview exceeds the supported numeric range.")
        viewport.resize(imageWidth, imageHeight)
        viewport.rulerSize = rulerSize
        viewport.zoom = pixelsPerMillimeter / viewport.basePixelsPerMillimeter
        origin = QtCore.QPointF(rulerSize - x * pixelsPerMillimeter,
                               rulerSize + (y + length) * pixelsPerMillimeter)
        viewport.panOffset = origin - QtCore.QPointF((imageWidth + rulerSize) / 2,
                                                    (imageHeight + rulerSize) / 2)
        for name in ("showGrid", "showMeasurements", "measurementPrecision", "measurementVisibility", "measurementSettings", "wallMeasurementMode", "wallMeasurementReference",
                     "collisionSettings", "stairStepSizes", "railingSpacings", "imperialAutoSizes", "autoSizingUnitsMode", "unitsMode", "lineworkSettings"):
            setattr(viewport, name, settings[name])
        viewport.EnsureObjectIds()
        viewport.gridIntensities = dict(settings["viewportSettings"])
        viewport.gridOrigin = tuple(gridOrigin)
        viewport.lineWidths = {key: settings["lineworkSettings"]["baseWidth"] * value
                               for key, value in settings["lineworkSettings"].items() if key != "baseWidth"}
        viewport.furnishingDefinitions = definitions
        viewport.furnishingRenderers = FurnishingRendererMap(definitions,
            lineWidth = viewport.lineWidths["furnishings"], solidBackground = solidObjects)
        from planner_app.export_scene import PrepareExportScene
        PrepareExportScene(viewport)
        if outputFormat == "svg":
            svgBuffer = QtCore.QBuffer()
            svgBuffer.open(QtCore.QIODevice.OpenModeFlag.ReadWrite)
            image = QtSvg.QSvgGenerator(QtSvg.QSvgGenerator.SvgVersion.Svg11)
            image.setOutputDevice(svgBuffer)
            image.setSize(QtCore.QSize(imageWidth, imageHeight))
            image.setViewBox(QtCore.QRect(0, 0, imageWidth, imageHeight))
            image.setResolution(96)
            image.setTitle(Path(planPath).stem)
            # Distinct solid fills identify material regions in the generated SVG.
            # Replace them with vector pattern references after painting; Qt texture
            # brushes otherwise serialize bitmap tiles into the SVG.
            materialMarkers = {}
            for index, material in enumerate(sorted({obj.material for obj in walls if viewport.IsObjectVisible(obj)})):
                if material == "Generic":
                    continue
                marker = QtGui.QColor(1, 0, index + 1).name()
                materialMarkers[marker] = material
                viewport.materialBrushes[(material, False)] = QtGui.QBrush(QtGui.QColor(marker))
        else:
            imageFormat = QtGui.QImage.Format.Format_RGB32 if QtGui.QColor(palette.themeColors["canvas"]).alpha() == 255 else QtGui.QImage.Format.Format_ARGB32
            image = QtGui.QImage(imageWidth, imageHeight, imageFormat)
            if image.isNull():
                raise ValueError("Could not allocate the render image.")
            image.fill(QtCore.Qt.GlobalColor.transparent)
        drawingRect = QtCore.QRectF(rulerSize, rulerSize, pixelWidth, pixelHeight)
        if outputFormat == "svg":
            class SvgPainter(QtGui.QPainter):
                def drawText(self, *args):
                    # Outline exported text so SVG readers cannot substitute fonts.
                    if len(args) == 2 and isinstance(args[0], QtCore.QPointF):
                        position, text = args
                    elif len(args) == 3 and isinstance(args[0], (QtCore.QRect, QtCore.QRectF)):
                        rect, flags, text = args
                        metrics = QtGui.QFontMetricsF(self.font(), self.device())
                        textRect = metrics.boundingRect(QtCore.QRectF(rect), int(flags), text)
                        position = QtCore.QPointF(textRect.left(), textRect.top() + metrics.ascent())
                    else:
                        raise TypeError("Unsupported SVG text drawing arguments.")
                    textPath = QtGui.QPainterPath()
                    textPath.addText(position, self.font(), text)
                    self.fillPath(textPath, self.pen().brush())

                def restore(self):
                    super().restore()
                    # Qt's SVG backend can retain a previous clip definition when
                    # restore() changes the clip without a new explicit clip command.
                    # Reissue the effective restored mask so later symbols do not
                    # inherit holes intended only for wall outlines.
                    if self.hasClipping():
                        self.setClipPath(self.clipPath(), QtCore.Qt.ClipOperation.ReplaceClip)
                    else:
                        self.setClipping(False)

            painter = SvgPainter(image)
        else:
            painter = QtGui.QPainter(image)
        try:
            painter.fillRect(QtCore.QRectF(0, 0, imageWidth, imageHeight), QtGui.QColor(palette.themeColors["canvas"]))
            painter.setFont(viewport.font())
            rulerUnit = viewport.DrawGridBackground(painter, drawingRect, origin, pixelsPerMillimeter,
                                                    gridOnly = previewScene or not ruler, allEdges = ruler, markingsOnly = border == "Marked")
            painter.setClipRect(drawingRect)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            viewport.DrawScene(painter, drawingRect, origin, pixelsPerMillimeter)
            viewport.DrawLabels(painter, pixelsPerMillimeter, drawingRect = drawingRect)
            if ruler and not previewScene:
                painter.setClipping(False)
                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
                viewport.DrawRulerFrame(painter, rulerUnit, allEdges = True, drawUnits = border != "Marked")
            elif border == "Ruler + Reference Zones" and not previewScene:
                painter.setClipping(False)
                DrawRulerZones(painter, drawingRect, rulerSize, viewport, origin, pixelsPerMillimeter)
            elif border != "None" and not previewScene:
                painter.setClipping(False)
                DrawExportBorder(painter, drawingRect, rulerSize, border)
            if outputFormat == "png":
                painter.setClipping(False)
                DrawNormalTexture(painter, QtCore.QRectF(0, 0, imageWidth, imageHeight), texture, textureAngle,
                                  (imageWidth, imageHeight), **(textureSettings or {}))
                DrawVignette(painter, QtCore.QRectF(0, 0, imageWidth, imageHeight), vignetteStrength,
                             (imageWidth, imageHeight))
        finally:
            painter.end()
        if outputFormat == "svg":
            result = VectorizeMaterials(bytes(svgBuffer.data()), materialMarkers)
            if architecturalScale is not None:
                root = ElementTree.fromstring(result)
                # Preserve the renderer's coordinate system while making its world
                # millimeters occupy the requested physical millimeters on paper.
                unitsPerMillimeter = scale * architecturalScale / 1000
                root.set("width", f"{imageWidth / unitsPerMillimeter:.10g}mm")
                root.set("height", f"{imageHeight / unitsPerMillimeter:.10g}mm")
                result = ElementTree.tostring(root, encoding = "utf-8", xml_declaration = True)
            return result
        if dpi is not None:
            dotsPerMeter = round(dpi * 1000 / 25.4)
            image.setDotsPerMeterX(dotsPerMeter)
            image.setDotsPerMeterY(dotsPerMeter)
        return image
    finally:
        viewport.deleteLater()


def VectorizeMaterials(svgData, materialMarkers):
    """Replace marked wall fills with fixed-size vector tiles, sharing GUI commands."""
    from PySide6 import QtCore, QtGui, QtSvg
    from planner_app.graphics.palette import themeColors
    from planner_app.graphics.theme import DrawMaterialPattern, materialPatternSpacings

    svgNamespace = "http://www.w3.org/2000/svg"
    ElementTree.register_namespace("", svgNamespace)
    ElementTree.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    root = ElementTree.fromstring(svgData)
    # SVG uses clip-rule, not fill-rule, to determine holes in clipping paths.
    # Qt emits only fill-rule; stricter viewers can interpret the masks differently.
    for clipPath in root.findall(f".//{{{svgNamespace}}}clipPath"):
        clipPath.set("clipPathUnits", "userSpaceOnUse")
        for shape in clipPath.iter():
            if shape is not clipPath:
                shape.set("clip-rule", shape.get("fill-rule", "nonzero"))
    definitions = root.find(f"{{{svgNamespace}}}defs")
    if definitions is None:
        definitions = ElementTree.SubElement(root, f"{{{svgNamespace}}}defs")
    for index, (marker, material) in enumerate(materialMarkers.items()):
        patternId = f"plannerMaterial{index}"
        spacing = materialPatternSpacings[material]
        pattern = ElementTree.SubElement(definitions, f"{{{svgNamespace}}}pattern", {
            "id": patternId, "patternUnits": "userSpaceOnUse", "width": str(spacing),
            "height": str(spacing), "x": "0", "y": "0"})
        tileBuffer = QtCore.QBuffer()
        tileBuffer.open(QtCore.QIODevice.OpenModeFlag.ReadWrite)
        tileGenerator = QtSvg.QSvgGenerator(QtSvg.QSvgGenerator.SvgVersion.Svg11)
        tileGenerator.setOutputDevice(tileBuffer)
        tileGenerator.setSize(QtCore.QSize(spacing, spacing))
        tileGenerator.setViewBox(QtCore.QRect(0, 0, spacing, spacing))
        tileGenerator.setResolution(96)
        tilePainter = QtGui.QPainter(tileGenerator)
        try:
            # The base wall color is painted once over its complete silhouette.
            # Repeating background rectangles produce antialias seams in viewers.
            tilePainter.setPen(QtGui.QPen(QtGui.QColor(themeColors["materialPattern"]), 1))
            DrawMaterialPattern(tilePainter, material, spacing)
        finally:
            tilePainter.end()
        tileRoot = ElementTree.fromstring(bytes(tileBuffer.data()))
        for child in tileRoot:
            if child.tag in (f"{{{svgNamespace}}}g", f"{{{svgNamespace}}}defs"):
                pattern.append(child)
        parents = {child: parent for parent in root.iter() for child in parent}
        for element in list(root.iter()):
            if element.get("fill") == marker:
                element.set("fill", themeColors["wallFill"])
                hatch = deepcopy(element)
                hatch.set("fill", f"url(#{patternId})")
                hatch.set("stroke", "none")
                parent = parents[element]
                parent.insert(list(parent).index(element) + 1, hatch)
    # Use CSS pixels for the nominal digital size, rather than Qt's mm dimensions.
    root.set("width", root.get("viewBox").split()[2])
    root.set("height", root.get("viewBox").split()[3])
    return ElementTree.tostring(root, encoding = "utf-8", xml_declaration = True)


def WriteExportFile(path, result, outputFormat):
    from PySide6 import QtCore
    output = QtCore.QSaveFile(str(path))
    try:
        if not output.open(QtCore.QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(output.errorString())
        if outputFormat == "png":
            if not result.save(output, "PNG"):
                raise OSError("Could not encode the PNG image.")
        elif output.write(result) != len(result):
            raise OSError(output.errorString())
        if not output.commit():
            raise OSError(output.errorString())
    except Exception:
        output.cancelWriting()
        raise


def Main():
    parser = argparse.ArgumentParser(description = __doc__, formatter_class = argparse.RawDescriptionHelpFormatter)
    parser.add_argument("plan", type = Path, help = "Input .plan file")
    parser.add_argument("scale", type = float, help = "Pixels/SVG units per meter, overriding saved scale mode (e.g. 200)")
    parser.add_argument("bounds", nargs = "*", type = float, metavar = "BOUND",
                        help = "Override saved crop: X Y WIDTH LENGTH in millimeters; X/Y is the lower-left corner")
    formats = parser.add_mutually_exclusive_group()
    formats.add_argument("-png", "--png", dest = "outputFormat", action = "store_const", const = "png",
                         help = "Export a PNG bitmap (default)")
    formats.add_argument("-svg", "--svg", dest = "outputFormat", action = "store_const", const = "svg",
                         help = "Export an SVG vector drawing")
    parser.set_defaults(outputFormat = "png")
    args = parser.parse_args()
    if len(args.bounds) not in (0, 4):
        parser.error("Provide all four bounds: X Y WIDTH LENGTH, or omit them to use the saved or automatic crop.")
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    try:
        if args.plan.suffix.lower() != ".plan":
            raise ValueError("Input must be a .plan file.")
        result = RenderPlan(args.plan, args.scale, args.bounds or None,
                            outputFormat = args.outputFormat, useExportSettings = True)
        outputDirectory = args.plan.resolve().parent / "renders"
        outputDirectory.mkdir(exist_ok = True)
        outputPath = outputDirectory / f"{args.plan.stem}_{args.scale:.15g}p.{args.outputFormat}"
        WriteExportFile(outputPath, result, args.outputFormat)
    except (OSError, ValueError, KeyError, TypeError, IndexError, OverflowError, RecursionError, RuntimeError) as error:
        parser.exit(1, f"Export failed: {error}\n")
    if args.outputFormat == "png":
        print(f"Saved {outputPath} ({result.width()} x {result.height()} pixels)")
    else:
        print(f"Saved {outputPath} (vector SVG)")
    return 0


if __name__ == "__main__":
    sys.exit(Main())
