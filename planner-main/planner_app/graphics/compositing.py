"""Raster export effects shared by the file renderer and viewport preview."""
import math
import random
import re
from functools import lru_cache
from pathlib import Path
from PySide6 import QtCore, QtGui
from planner_app.paths import appDirectory

vignetteNoise = None


def TextureMapping(name, includeDefaults = False):
    stem = Path(name).stem
    if stem.lower().endswith("_ao"):
        raise ValueError("Ambient occlusion maps are companions, not selectable normal textures.")
    defaults = {"strength": .5, "highlights": 1.0, "midtones": 1.0, "shadows": 1.0}
    numberPattern = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
    parts = stem.rsplit("_", 5)
    if len(parts) == 6 and parts[1] and re.fullmatch(r"s|t?(?:" + numberPattern + r")?", parts[1], re.IGNORECASE):
        try:
            # Decimal filenames use the old format, including bare endpoint 1.
            # Compact filenames imply 0., except 10 denotes the endpoint 1.0.
            legacyFormat = any("." in value for value in parts[2:])
            values = [float(value) if legacyFormat or not re.fullmatch(r"[0-9]+", value)
                      else 1.0 if value == "10" else float("0." + value) for value in parts[2:]]
        except ValueError as error:
            raise ValueError("Texture lighting defaults must be four numbers between 0 and 1.") from error
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in values):
            raise ValueError("Texture lighting defaults must be between 0 and 1.")
        defaults.update(zip(defaults, values))
        stem = "_".join(parts[:2])
    prefix, separator, suffix = stem.rpartition("_")
    label, mode, scale = stem, "tile", 1.0
    if separator and suffix:
        if suffix.lower() == "s":
            label, mode = prefix, "stretch"
        else:
            # Only a complete trailing hint is metadata; other underscores and
            # words remain part of the display name.
            match = re.fullmatch(r"t?([+-]?(?:\d+(?:\.\d*)?|\.\d+))?", suffix, re.IGNORECASE)
            if match is not None:
                label = prefix
                scale = float(match.group(1)) if match.group(1) is not None else 1.0
                if not math.isfinite(scale) or scale <= 0:
                    raise ValueError("Texture tiling scale must be greater than zero.")
    label = " ".join(word[0].upper() + word[1:] for word in label.replace("_", " ").split())
    return (label, mode, scale, defaults) if includeDefaults else (label, mode, scale)


def CompactTextureName(name):
    path = Path(name)
    parts = path.stem.rsplit("_", 5)
    if len(parts) != 6 or not re.fullmatch(r"s|t?(?:[+-]?(?:\d+(?:\.\d*)?|\.\d+))?", parts[1], re.IGNORECASE):
        return name
    if not any("." in value for value in parts[2:]):
        return name
    for index in range(2, 6):
        value = parts[index]
        if re.fullmatch(r"1(?:\.0+)?", value):
            parts[index] = "10"
        elif re.fullmatch(r"0\.[0-9]+", value):
            digits = value[2:]
            parts[index] = "1" if digits == "10" else digits
    return "_".join(parts) + path.suffix


@lru_cache(maxsize = 1)
def LoadNormalTexture(path, stamp):
    reader = QtGui.QImageReader(str(path))
    size = reader.size()
    if size.isValid() and size.width() * size.height() > 4_194_304:
        raise ValueError("Composite textures are limited to 4 million pixels.")
    image = reader.read()
    if image.isNull():
        raise ValueError(f"Could not read composite texture: {path.name}")
    return image.convertToFormat(QtGui.QImage.Format.Format_RGBA8888)


@lru_cache(maxsize = 1)
def NormalLightingTile(path, stamp, angle, highlights = 1, midtones = 1, shadows = 1):
    normal = LoadNormalTexture(path, stamp)
    source = normal.constBits()
    pixels = bytearray(normal.width() * normal.height() * 4)
    cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    colors = {}
    for offset in range(0, len(pixels), 4):
        red, green = source[offset], source[offset + 1]
        key = red * 256 + green
        color = colors.get(key)
        if color is None:
            nx, ny = red / 127.5 - 1, green / 127.5 - 1
            rotatedX = nx * cosine - ny * sine
            rotatedY = nx * sine + ny * cosine
            up, down = min(1, max(0, -rotatedY)), min(1, max(0, rotatedY))
            side = min(1, abs(rotatedX))
            up *= highlights
            down *= shadows
            midtone = 1 - .5 * side * midtones
            # Black multiply, white screen, then half-gray multiply. Fuse
            # C' = C * factor + highlight into one source-over
            # tile; no full-render masks or per-frame pixel loops are needed.
            factor = (1 - down) * (1 - up) * midtone
            highlight = up * midtone
            alpha = 1 - factor
            value = round(255 * highlight / alpha) if alpha > 0 else 0
            color = bytes((value, value, value, round(255 * alpha)))
            colors[key] = color
        pixels[offset:offset + 4] = color
    return QtGui.QImage(bytes(pixels), normal.width(), normal.height(), normal.width() * 4,
                       QtGui.QImage.Format.Format_RGBA8888).copy()


def DrawNormalTexture(painter, rect, name, angle, pixelSize, scaleOverride = None, strength = 1,
                      highlights = 1, midtones = 1, shadows = 1):
    if name is None or rect.isEmpty():
        return
    for value in (strength, highlights, midtones, shadows):
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Texture lighting strengths must be between 0 and 1.")
    if scaleOverride is not None and (not math.isfinite(scaleOverride) or not 0 <= scaleOverride <= 4):
        raise ValueError("Texture scale override must be between 0 and 4.")
    if not isinstance(name, str) or "/" in name or "\\" in name or name in ("", ".", ".."):
        raise ValueError("Invalid composite texture name.")
    path = appDirectory / "textures" / name
    if not path.is_file():
        # Saved projects may still refer to the shipped files' decimal names.
        path = appDirectory / "textures" / CompactTextureName(name)
    label, mode, scale = TextureMapping(name)
    if mode == "tile" and scaleOverride is not None:
        scale = scaleOverride
    if strength == 0 or mode == "tile" and scale == 0:
        return
    stamp = path.stat()
    layers = []
    if strength > 0:
        tile = NormalLightingTile(path, (stamp.st_mtime_ns, stamp.st_size), angle, highlights, midtones, shadows)
        layers.append((tile, QtGui.QPainter.CompositionMode.CompositionMode_SourceOver, strength))
    # AO companions use the texture's name without mapping/lighting metadata.
    stem = path.stem
    numberPattern = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
    baseStem = re.sub(r"_(?:s|t?(?:" + numberPattern + r")?)(?:_" + numberPattern + r"){4}$", "", stem, flags = re.IGNORECASE)
    stem = (re.sub(r"_(?:s|t?(?:" + numberPattern + r")?)$", "", stem, flags = re.IGNORECASE)
            if baseStem == stem else baseStem)
    aoPath = path.with_name(stem + "_ao" + path.suffix)
    if aoPath.is_file():
        aoStamp = aoPath.stat()
        normalSize = LoadNormalTexture(path, (stamp.st_mtime_ns, stamp.st_size)).size()
        ao = AmbientOcclusionTile(aoPath, (aoStamp.st_mtime_ns, aoStamp.st_size), normalSize.width(), normalSize.height())
        layers.append((ao, QtGui.QPainter.CompositionMode.CompositionMode_Multiply, strength))
    painter.save()
    try:
        painter.setClipRect(rect, QtCore.Qt.ClipOperation.IntersectClip)
        # Blend the completed lighting result with the original albedo. Overall
        # strength and mapping changes reuse the already processed normal tile.
        for tile, composition, opacity in layers:
            painter.setCompositionMode(composition)
            painter.setOpacity(opacity)
            if mode == "stretch":
                painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
                painter.drawImage(rect, tile)
                continue
            # Filter the cached lighting tile when scaling rather than rerunning
            # the normal-map calculation for each output resolution.
            painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, scale != 1)
            painter.setBrushOrigin(rect.topLeft())
            brush = QtGui.QBrush(tile)
            brush.setTransform(QtGui.QTransform().scale(rect.width() / (pixelSize[0] * scale),
                                                       rect.height() / (pixelSize[1] * scale)))
            painter.fillRect(rect, brush)
    finally:
        painter.restore()


@lru_cache(maxsize = 1)
def AmbientOcclusionTile(path, stamp, width, height):
    # Normalize resolution once so AO shares the normal's tile period and UVs.
    image = LoadNormalTexture(path, stamp).convertToFormat(QtGui.QImage.Format.Format_RGB32)
    if image.width() != width or image.height() != height:
        image = image.scaled(width, height, QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                             QtCore.Qt.TransformationMode.SmoothTransformation)
    return image


def DrawVignette(painter, rect, strength, pixelSize = None):
    global vignetteNoise
    if strength <= 0 or rect.isEmpty():
        return
    # Normalize each axis independently: the vignette follows the crop's aspect
    # ratio, with identical falloff at matching relative positions on each axis.
    gradient = QtGui.QRadialGradient(QtCore.QPointF(), math.sqrt(2))
    # Keep the inner 30% of the center-to-corner radius clear, then ease into
    # shading with fifth-order smootherstep. Both ends of the transition have
    # zero first and second derivatives, so the clear area has no hard seam.
    # Sample more stops to preserve that curve in Qt's linear interpolation.
    for index in range(65):
        position = index / 64
        transition = max(0, (position - .3) / .7)
        falloff = transition ** 3 * (transition * (6 * transition - 15) + 10)
        value = round(255 * max(0, 1 - strength * falloff))
        gradient.setColorAt(position, QtGui.QColor(value, value, value))
    painter.save()
    try:
        transform = painter.worldTransform()
        painter.setClipRect(rect, QtCore.Qt.ClipOperation.IntersectClip)
        painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Multiply)
        painter.setOpacity(1)
        # Wall materials leave a world-anchored brush origin on the painter.
        # The effect's gradient must instead stay anchored to the crop center.
        painter.setBrushOrigin(QtCore.QPointF())
        painter.translate(rect.center())
        painter.scale(rect.width() / 2, rect.height() / 2)
        painter.fillRect(QtCore.QRectF(-1, -1, 2, 2), gradient)
        # A tiny, balanced noise tile decorrelates the visible 8-bit steps.
        # Soft light keeps black/white endpoints intact and perturbs midtones
        # by only about two levels. Reuse it instead of allocating a crop-sized
        # noise bitmap or generating fresh noise on every viewport repaint.
        if vignetteNoise is None:
            noiseRandom = random.Random(0x504C414E)
            # Half intensity is 127.5 in 8-bit RGB; balance around that value
            # rather than biasing the effect toward the nearest integer, 128.
            values = [value for value in range(124, 132) for _ in range(4096)]
            noiseRandom.shuffle(values)
            pixels = bytes(channel for value in values for channel in (value, value, value, 255))
            vignetteNoise = QtGui.QImage(pixels, 256, 128, 256 * 4,
                                       QtGui.QImage.Format.Format_RGBA8888).copy()
        painter.setWorldTransform(transform)
        painter.setBrushOrigin(rect.topLeft())
        painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SoftLight)
        painter.setOpacity(min(1, strength))
        noiseBrush = QtGui.QBrush(vignetteNoise)
        width, height = pixelSize if pixelSize is not None else (rect.width(), rect.height())
        noiseBrush.setTransform(QtGui.QTransform().scale(rect.width() / width, rect.height() / height))
        painter.fillRect(rect, noiseBrush)
    finally:
        painter.restore()
