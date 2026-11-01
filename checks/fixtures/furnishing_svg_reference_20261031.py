"""Frozen furnishing variant rendering before SVG preparation changes."""
from planner_app.graphics.furnishings import *
from planner_app.graphics.furnishings import FurnishingSvgRenderer as CurrentRenderer


class FurnishingSvgRenderer(CurrentRenderer):
    def render(self, painter, *arguments, worldSize = None):
        if isinstance(painter.device(), QtSvg.QSvgGenerator):
            # Keep fixed stroke widths while rendering at the chosen export scale,
            # then bake those widths into ordinary vector geometry.
            size = painter.device().size()
            device = ObjectPaintDevice(size, themeColors["canvas"])
            device.engine.captureBackground = False
            with QtGui.QPainter(device) as recorder:
                recorder.setWorldTransform(painter.worldTransform())
                recorder.setFont(painter.font())
                recorder.setRenderHints(painter.renderHints())
                recorder.setOpacity(painter.opacity())
                self.render(recorder, *arguments, worldSize = worldSize)
            painter.save()
            try:
                painter.resetTransform()
                device.engine.Replay(painter, QtCore.QRectF(0, 0, size.width(), size.height()))
            finally:
                painter.restore()
            return
        if not (self.lettering or self.fixedElements and worldSize) or len(arguments) != 1 or not isinstance(arguments[0], QtCore.QRectF):
            return super().render(painter, *arguments)
        bounds = arguments[0]
        viewBox = self.viewBoxF()
        if bounds.isEmpty() or viewBox.isEmpty():
            return super().render(painter, *arguments)
        world = painter.worldTransform()
        worldLinear = QtGui.QTransform(world.m11(), world.m12(), world.m21(), world.m22(), 0, 0)
        rotation, worldValid = worldLinear.inverted()
        if not worldValid:
            return super().render(painter, *arguments)
        key = (bounds.width(), bounds.height(), world.m11(), world.m12(), world.m21(), world.m22(),
               tuple(worldSize) if worldSize is not None else None)
        variant = self.letteringVariants.get(key)
        if variant is None:
            root = deepcopy(self.letteringRoot)
            elements = {element.get("id"): element for element in root.iter() if element.get("id")}
            scale = QtGui.QTransform.fromScale(bounds.width() / viewBox.width(), bounds.height() / viewBox.height())
            if worldSize is not None:
                physicalScale = QtGui.QTransform.fromScale(worldSize[0] / viewBox.width(), worldSize[1] / viewBox.height())
                for wrapperId, anchor, parentTransform, scopeTransform, nominalX, nominalY in self.fixedElements:
                    parentPhysical = parentTransform * physicalScale
                    parentInverse, parentValid = parentPhysical.inverted()
                    scopeInverse, scopeValid = scopeTransform.inverted()
                    scopePhysical = scopeTransform * physicalScale
                    xLength = math.hypot(scopePhysical.m11(), scopePhysical.m12())
                    yLength = math.hypot(scopePhysical.m21(), scopePhysical.m22())
                    if not parentValid or not scopeValid or min(xLength, yLength) <= 0:
                        continue
                    relative = QtGui.QTransform.fromScale(1 / nominalX, 1 / nominalY) * scopePhysical
                    largestScale = (math.hypot(relative.m11() + relative.m22(), relative.m12() - relative.m21())
                                    + math.hypot(relative.m11() - relative.m22(), relative.m12() + relative.m21())) / 2
                    shrink = min(1.0, abs(relative.determinant()) / max(largestScale, 1e-12))
                    cosine, sine = scopePhysical.m11() / xLength, scopePhysical.m12() / xLength
                    facing = -1 if scopePhysical.determinant() < 0 else 1
                    desiredScope = QtGui.QTransform(cosine * nominalX * shrink, sine * nominalX * shrink,
                        -sine * nominalY * shrink * facing, cosine * nominalY * shrink * facing, 0, 0)
                    desired = parentTransform * scopeInverse * desiredScope
                    offset = parentPhysical.map(anchor) - desired.map(anchor)
                    desired = QtGui.QTransform(desired.m11(), desired.m12(), desired.m21(), desired.m22(),
                                              desired.dx() + offset.x(), desired.dy() + offset.y())
                    correction = desired * parentInverse
                    elements[wrapperId].set("transform",
                        f"matrix({correction.m11()} {correction.m12()} {correction.m21()} {correction.m22()} {correction.dx()} {correction.dy()})")
            for textId, textBounds, parentTransform, scopeTransform, scopeBounds, ownTransform, ownScale, anchor in self.lettering:
                parentTotal = parentTransform * scale
                scopeTotal = scopeTransform * scale
                parentInverse, parentValid = parentTotal.inverted()
                scopeInverse, scopeValid = scopeTotal.inverted()
                if not parentValid or not scopeValid:
                    continue
                # Cancel the painter's orientation as well as SVG component
                # transforms, keeping lettering horizontal in the final drawing.
                intoScope = rotation * scopeInverse
                extentX = extentY = 0
                for x in (-textBounds.width() / 2, textBounds.width() / 2):
                    for y in (-textBounds.height() / 2, textBounds.height() / 2):
                        corner = intoScope.map(QtCore.QPointF(x, y)) - intoScope.map(QtCore.QPointF())
                        extentX = max(extentX, abs(corner.x()))
                        extentY = max(extentY, abs(corner.y()))
                # Limit the text to its authored proportion along the least-scaled
                # direction. This also shrinks it with zoom before it fills the object.
                authoredTotal = ownTransform * parentTotal * worldLinear
                largestScale = (math.hypot(authoredTotal.m11() + authoredTotal.m22(), authoredTotal.m12() - authoredTotal.m21())
                                + math.hypot(authoredTotal.m11() - authoredTotal.m22(), authoredTotal.m12() + authoredTotal.m21())) / 2
                authoredScale = abs(authoredTotal.determinant()) / max(largestScale, 1e-12)
                # Five-percent padding keeps glyphs clear of the object's outline.
                textScale = min(ownScale, authoredScale, scopeBounds.width() * .45 / max(extentX, 1e-12),
                                   scopeBounds.height() * .45 / max(extentY, 1e-12))
                uniform = QtGui.QTransform(rotation.m11() * textScale, rotation.m12() * textScale,
                    rotation.m21() * textScale, rotation.m22() * textScale, 0, 0)
                # Keep the authored glyph anchor (e.g. a washer drum center),
                # even when zoom compensation changes text size/orientation.
                targetCenter = (ownTransform * parentTotal).map(anchor)
                offset = targetCenter - uniform.map(textBounds.center())
                uniform = QtGui.QTransform(uniform.m11(), uniform.m12(), uniform.m21(), uniform.m22(), offset.x(), offset.y())
                correction = uniform * parentInverse
                element = elements[textId]
                element.set("transform",
                    f"matrix({correction.m11()} {correction.m12()} {correction.m21()} {correction.m22()} {correction.dx()} {correction.dy()})")
            variant = QtSvg.QSvgRenderer(ElementTree.tostring(root))
            self.letteringVariants[key] = variant
            while len(self.letteringVariants) > 16:
                self.letteringVariants.popitem(last = False)
        else:
            self.letteringVariants.move_to_end(key)
        return variant.render(painter, bounds)

