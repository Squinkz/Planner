"""Landing-aware inset edges and directed stair centerlines."""
import math
from PySide6 import QtCore, QtGui
from planner_app.graphics.path_operations import Paths


def StairInsetLines(components, polygons, scale):
    lines = []
    footprints = {}
    for owner, polygon in polygons:
        footprints.setdefault(id(owner), []).append(polygon)
    endpointBuckets = {}
    for key, members, boundary in components:
        for stair in members:
            for vertex in (stair.firstVertex, stair.secondVertex):
                cell = math.floor(vertex.x() / .01), math.floor(vertex.y() / .01)
                endpointBuckets.setdefault(cell, []).append((stair, vertex))
    for key, members, boundary in components:
        if len(members) == 1:
            continue  # Standalone flights use the direct symbol renderer.
        owned = [(stair, polygon) for stair in members for polygon in footprints.get(id(stair), ())]
        inset = min(25, min(stair.width for stair in members) / 4) * scale
        stroke = Paths.PrepareStroke(width = 2 * inset, cap = 'square', join = 'miter')
        inside = Paths.Difference(boundary, stroke(boundary))
        terminals = []
        for stair in members:
            delta = stair.secondVertex - stair.firstVertex
            length = math.hypot(delta.x(), delta.y())
            if length < .0001:
                continue
            axis = QtCore.QPointF(delta.x(), -delta.y()) / length
            for vertex, direction in ((stair.firstVertex, axis), (stair.secondVertex, -axis)):
                x, y = math.floor(vertex.x() / .01), math.floor(vertex.y() / .01)
                if not any(other is not stair and QtCore.QLineF(vertex, point).length() <= .01
                           for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                           for other, point in endpointBuckets.get((x + dx, y + dy), ())):
                    terminals.append((QtCore.QPointF(vertex.x(), -vertex.y()) * scale, direction, stair.width * scale / 2))
        for polygon in Paths.Contours(inside):
            vertices = list(polygon)
            for first, second in zip(vertices, vertices[1:]):
                delta = second - first
                length = math.hypot(delta.x(), delta.y())
                if length < 1e-8:
                    continue
                midpoint = (first + second) / 2
                cap = any(abs(QtCore.QPointF.dotProduct(midpoint - vertex, axis) - inset) < .001 * scale
                          and abs(QtCore.QPointF.dotProduct(delta / length, axis)) < 1e-6
                          and QtCore.QLineF(midpoint, vertex).length() <= halfWidth + inset
                          for vertex, axis, halfWidth in terminals)
                if cap:
                    continue
                endpoints = [QtCore.QPointF(first), QtCore.QPointF(second)]
                for point in endpoints:
                    for vertex, axis, halfWidth in terminals:
                        if abs(QtCore.QPointF.dotProduct(point - vertex, axis) - inset) < .001 * scale and QtCore.QLineF(point, vertex).length() <= halfWidth + inset:
                            point -= axis * inset
                            break
                owner = next((stair for stair, footprint in owned if footprint.containsPoint(midpoint, QtCore.Qt.FillRule.WindingFill)), members[0])
                lines.append((owner, QtCore.QLineF(*endpoints)))
    return lines


def StairArrowRuns(stairs, neighbors, trims):
    arrows = []
    links = {}
    connections, dependents, landingIds, blocked = {}, {}, set(), set()
    for stair in stairs:
        startIndex, endIndex = (1, 0) if stair.directionReversed else (0, 1)
        start, tip = ((stair.secondVertex, stair.firstVertex) if stair.directionReversed else
                      (stair.firstVertex, stair.secondVertex))
        incoming, outgoing = neighbors[(id(stair), startIndex)], neighbors[(id(stair), endIndex)]
        before = incoming[0] if len(incoming) == 1 and QtCore.QLineF(start, incoming[0].firstVertex if incoming[0].directionReversed else incoming[0].secondVertex).length() <= .01 else None
        after = outgoing[0] if len(outgoing) == 1 and QtCore.QLineF(tip, outgoing[0].secondVertex if outgoing[0].directionReversed else outgoing[0].firstVertex).length() <= .01 else None
        connections[id(stair)] = before, after
        for peer in (before, after):
            if peer is not None:
                dependents.setdefault(id(peer), []).append(id(stair))
        length = QtCore.QLineF(stair.firstVertex, stair.secondVertex).length()
        if length < .0001:
            blocked.add(id(stair))
        elif sum(trims[id(stair)]) >= length - 1e-8:
            landingIds.add(id(stair))
            if before is None or after is None:
                blocked.add(id(stair))
    pending = list(blocked)
    while pending:
        for identity in dependents.get(pending.pop(), ()):
            if identity in landingIds and identity not in blocked:
                blocked.add(identity)
                pending.append(identity)
    for stair in stairs:
        if id(stair) in blocked:
            continue
        firstTrim, secondTrim = trims[id(stair)]
        delta = stair.secondVertex - stair.firstVertex
        length = math.hypot(delta.x(), delta.y())
        if length < .0001:
            continue
        axis = delta / length
        first, second = stair.firstVertex + axis * firstTrim, stair.secondVertex - axis * secondTrim
        startIndex, endIndex = (1, 0) if stair.directionReversed else (0, 1)
        start, tip = (second, first) if stair.directionReversed else (first, second)
        trueStart, trueTip = ((stair.secondVertex, stair.firstVertex) if stair.directionReversed else
                              (stair.firstVertex, stair.secondVertex))
        before, after = connections[id(stair)]
        joinsStart = before is not None and id(before) not in blocked
        joinsEnd = after is not None and id(after) not in blocked
        if firstTrim + secondTrim >= length - 1e-8 and not (joinsStart and joinsEnd):
            continue
        arrows.append((stair, trueStart if joinsStart else start, trueTip if joinsEnd else tip, not joinsEnd))
        links[id(stair)] = id(after) if joinsEnd else None
    # A directed cycle still needs a visible indication of its direction.
    positions = {id(stair): index for index, (stair, start, tip, showTip) in enumerate(arrows)}
    visited = set()
    for identity in positions:
        chain, active = [], set()
        current = identity
        while current in positions and current not in visited:
            chain.append(positions[current])
            active.add(current)
            visited.add(current)
            current = links[current]
        if current in active:
            index = chain[0]
            stair, start, tip, showTip = arrows[index]
            arrows[index] = (stair, start, tip, True)
    return arrows
