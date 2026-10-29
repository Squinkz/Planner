"""Numeric affine primitives with optional native rounding compatibility."""
import math


def RotationComponents(angle):
    # Preserve the exact cardinal components used by the existing affine
    # backend. Other angles, including negative 180 and full turns, use trig.
    if angle == 90 or angle == -270:
        return 0.0, 1.0
    if angle == 270 or angle == -90:
        return 0.0, -1.0
    if angle == 180:
        return -1.0, 0.0
    radians = math.radians(angle)
    return math.cos(radians), math.sin(radians)


def NeedsNativeAffine(frame):
    a, b, c, d, x, y = frame
    return (0 < abs(b) <= 1e-12 or 0 < abs(c) <= 1e-12
            or a != 1 and abs(a - 1) <= 1e-12 * min(abs(a), 1)
            or d != 1 and abs(d - 1) <= 1e-12 * min(abs(d), 1)
            or 0 < abs(x) <= 1e-12 or 0 < abs(y) <= 1e-12)


def ReflectionFrame(center, angle, horizontal, backend = None):
    if backend is not None:
        return backend("reflection", center, angle, horizontal)
    cosine, sine = RotationComponents(angle)
    scaleX, scaleY = (-1, 1) if horizontal else (1, -1)
    a, b, c, d = cosine * scaleX, sine * scaleX, -sine * scaleY, cosine * scaleY
    a, b, c, d = cosine * a - sine * c, cosine * b - sine * d, sine * a + cosine * c, sine * b + cosine * d
    return a, b, c, d, center[0] + (-center[0] * a - center[1] * c), center[1] + (-center[0] * b - center[1] * d)


def TransformAffinePoint(point, frame, backend = None):
    if backend is not None and NeedsNativeAffine(frame):
        return backend("point", point, frame)
    a, b, c, d, x, y = frame
    return a * point[0] + c * point[1] + x, b * point[0] + d * point[1] + y


def TransformAffinePoints(points, frame, backend = None):
    if backend is not None and NeedsNativeAffine(frame):
        return tuple(backend("point", point, frame) for point in points)
    a, b, c, d, x, y = frame
    return tuple((a * point[0] + c * point[1] + x, b * point[0] + d * point[1] + y) for point in points)
