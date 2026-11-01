# Frozen pre-optimization accounting. Key wrapper remains shared.
import sys
from PySide6 import QtCore, QtGui
from planner_app.viewport.geometry_cache import GeometryCacheKey

def GeometryCacheCost(key, value, sharedIds = ()):
    """Estimate Python storage and native elements, without following model graphs."""
    pending, seen = [key, value], set(sharedIds)
    byteCount, pointCount = 512, 0
    if isinstance(key, GeometryCacheKey):
        byteCount += sys.getsizeof(key.__dict__) + sys.getsizeof(key.cachedHash)
    while pending:
        item = pending.pop()
        identity = id(item)
        if identity in seen:
            continue
        seen.add(identity)
        byteCount += sys.getsizeof(item)
        if isinstance(item, QtGui.QPainterPath):
            points = item.elementCount()
            pointCount += points
            byteCount += 256 + points * 32
        elif isinstance(item, QtGui.QPolygonF):
            points = len(item)
            pointCount += points
            byteCount += 64 + points * 16
        elif isinstance(item, QtCore.QPointF):
            pointCount += 1
            byteCount += 16
        elif isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, (tuple, list, set, frozenset)):
            pending.extend(item)
    return byteCount, pointCount
