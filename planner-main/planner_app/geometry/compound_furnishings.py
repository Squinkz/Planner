"""Affine compound expansion, fixed-size policy and numeric child footprints."""
import math
from .footprints import PolygonAxes
from .affine import RotationComponents, NeedsNativeAffine
from planner_app.furnishing_limits import FurnishingExpansionSizes


def CompoundAuthoredBounds(components):
    """Bound authored SVG children without retaining every transformed corner.

    SVG layout deliberately uses ordinary trig at cardinal angles; the runtime
    affine backend's exact cardinal components must not change authored sizes.
    """
    FurnishingExpansionSizes([{"components": components}])
    hasCorners = False
    for child in components:
        angle = math.radians(child["angle"])
        cosine, sine = math.cos(angle), math.sin(angle)
        for x in (-child["width"] / 2, child["width"] / 2):
            for y in (-child["length"] / 2, child["length"] / 2):
                px = child["x"] + x * cosine - y * sine
                py = child["y"] + x * sine + y * cosine
                if not hasCorners:
                    left = right = px
                    bottom = top = py
                    hasCorners = True
                else:
                    if px < left:
                        left = px
                    if px > right:
                        right = px
                    if py < bottom:
                        bottom = py
                    if py > top:
                        top = py
    if not hasCorners:
        raise ValueError("A compound needs at least one component")
    return left, bottom, right, top


def CompoundTransform(center, angle, width, length, definition, flipHorizontal, flipVertical, backend = None):
    scaleX = width / definition["width"] * (-1 if flipHorizontal else 1)
    scaleY = length / definition["length"] * (-1 if flipVertical else 1)
    if backend is not None:
        return backend("root", center, angle, scaleX, scaleY, definition["compoundCenter"])
    cosine, sine = RotationComponents(angle)
    a, b, c, d = cosine * scaleX, sine * scaleX, -sine * scaleY, cosine * scaleY
    x, y = definition["compoundCenter"]
    return a, b, c, d, center[0] + (-x * a + -y * c), center[1] + (-x * b + -y * d)


def ComponentFrame(component, frame, allowFixed = True, backend = None):
    a, b, c, d, x, y = frame
    cosine, sine = RotationComponents(component["angle"])
    localX, localY = component["x"], component["y"]
    local = cosine, sine, -sine, cosine, localX, localY
    actual = (cosine * a + sine * c, cosine * b + sine * d,
              -sine * a + cosine * c, -sine * b + cosine * d,
              localX * a + localY * c + x, localX * b + localY * d + y)
    if backend is not None and (NeedsNativeAffine(local) or NeedsNativeAffine(frame)):
        actual = backend("compose", local, frame)
    if not allowFixed or not component.get("fixedSize", False):
        return actual
    xLength = math.hypot(a, b)
    largestScale = (math.hypot(a + d, b - c) + math.hypot(a - d, b + c)) / 2
    if xLength <= 0 or largestScale <= 0:
        return actual
    determinant = a * d - c * b
    shrink = min(1.0, abs(determinant) / largestScale)
    cosineX, sineX = a / xLength, b / xLength
    facing = -1 if determinant < 0 else 1
    a, b = cosineX * shrink, sineX * shrink
    c, d = -sineX * shrink * facing, cosineX * shrink * facing
    desiredX, desiredY = localX * a + localY * c, localX * b + localY * d
    # Keep the original cancellation order when restoring the transformed
    # position; replacing this with actual[4:6] changes distant coordinates.
    desired = (cosine * a + sine * c, cosine * b + sine * d,
               -sine * a + cosine * c, -sine * b + cosine * d, desiredX, desiredY)
    uniform = a, b, c, d, 0.0, 0.0
    if backend is not None and (NeedsNativeAffine(local) or NeedsNativeAffine(uniform)):
        desired = backend("compose", local, uniform)
    return (*desired[:4], desired[4] + (actual[4] - desired[4]), desired[5] + (actual[5] - desired[5]))


def PlanCompoundFootprints(definition, frame, validated = False, backend = None):
    """Yield numeric bounds, consistently wound corners and collision axes.

    Retain the original depth-first stack order: leaf children are yielded
    immediately, while nested children are visited in reverse discovery order.
    A desktop cache can skip revalidation after checking the graph itself.
    """
    if not validated:
        FurnishingExpansionSizes([definition])
    pending = [(definition, frame, True)]
    while pending:
        current, frame, allowFixed = pending.pop()
        for component in current["components"]:
            child = component["definition"]
            local = ComponentFrame(component, frame, allowFixed, backend)
            a, b, c, d, x, y = local
            if child.get("components"):
                scaleX = component["width"] / child["width"] * (-1 if component.get("flipHorizontal", False) else 1)
                scaleY = component["length"] / child["length"] * (-1 if component.get("flipVertical", False) else 1)
                a, b, c, d = a * scaleX, b * scaleX, c * scaleY, d * scaleY
                centerX, centerY = child["compoundCenter"]
                nested = (a, b, c, d, x + (-centerX * a + -centerY * c), y + (-centerX * b + -centerY * d))
                if backend is not None and (NeedsNativeAffine(local) or NeedsNativeAffine(nested)):
                    nested = backend("nested", local, scaleX, scaleY, (centerX, centerY))
                pending.append((child, nested, allowFixed and not component.get("fixedSize", False)))
                continue
            width, length = component["width"] / 2, component["length"] / 2
            corners = tuple((a * px + c * py + x, b * px + d * py + y)
                            for px, py in ((-width, -length), (width, -length), (width, length), (-width, length)))
            left = min(point[0] for point in corners)
            top = min(point[1] for point in corners)
            bounds = left, top, max(point[0] for point in corners) - left, max(point[1] for point in corners) - top
            if backend is not None and NeedsNativeAffine(local):
                bounds, corners = backend("rectangle", local, width, length)
            if sum(corners[index][0] * corners[(index + 1) % 4][1] - corners[(index + 1) % 4][0] * corners[index][1]
                   for index in range(4)) < 0:
                corners = tuple(reversed(corners))
            yield bounds, corners, tuple(PolygonAxes(corners))


def PlanFurnishingParts(definition, frame, mirrored, backend = None):
    """Yield immediate decomposition records in stable authored paint order.

    Rectangular models approximate shear by retaining center, axis lengths and
    direction. Nested compounds remain immediate parts, just as before.
    """
    FurnishingExpansionSizes([definition])
    for index, component in sorted(enumerate(definition["components"]), key = lambda entry: (entry[1]["zIndex"], entry[0])):
        a, b, c, d, x, y = ComponentFrame(component, frame, backend = backend)
        yield (component["definition"], component.get("definitionKey", component["definition"]["key"]),
               (x, y), component["width"] * math.hypot(a, b), component["length"] * math.hypot(c, d) / 2,
               math.degrees(math.atan2(d, c)) - 90,
               component.get("flipHorizontal", False) != mirrored, component.get("flipVertical", False))
