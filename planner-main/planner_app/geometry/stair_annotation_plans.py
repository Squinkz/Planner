"""Numeric stair connectivity, directed arrows and landing inset decisions."""
from dataclasses import dataclass
import math


@dataclass(frozen = True, slots = True)
class StairAnnotationRecord:
    key: object
    first: tuple
    second: tuple
    width: float
    reversed: bool = False


def StairEndpointNeighbors(stairs, distance = math.hypot, values = None):
    """Match endpoints in bucket traversal order, preserving duplicate peers.

    Values can map numeric keys to opaque adapter payloads, avoiding a second
    pass to rebuild neighbor lists after matching.
    """
    buckets, neighbors = {}, {}
    for stair in stairs:
        value = stair.key if values is None else values[stair.key]
        for vertex in (stair.first, stair.second):
            cell = math.floor(vertex[0] / .01), math.floor(vertex[1] / .01)
            buckets.setdefault(cell, []).append((stair.key, vertex, value))
    for stair in stairs:
        for index, vertex in enumerate((stair.first, stair.second)):
            x, y = math.floor(vertex[0] / .01), math.floor(vertex[1] / .01)
            neighbors[(stair.key, index)] = [value for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                for other, point, value in buckets.get((x + dx, y + dy), ())
                if other != stair.key and distance(vertex[0] - point[0], vertex[1] - point[1]) <= .01]
    return neighbors


def PrepareStairInset(stairs, neighbors, scale):
    inset = min(25, min(stair.width for stair in stairs) / 4) * scale
    terminals = []
    for stair in stairs:
        x, y = stair.second[0] - stair.first[0], stair.second[1] - stair.first[1]
        length = math.hypot(x, y)
        if length < .0001:
            continue
        axis = x / length, -y / length
        for index, vertex, direction in ((0, stair.first, axis), (1, stair.second, (-axis[0], -axis[1]))):
            if not neighbors[(stair.key, index)]:
                terminals.append(((vertex[0] * scale, -vertex[1] * scale), direction, stair.width * scale / 2))
    return inset, terminals


def PlanStairInsetLines(contours, terminals, inset, scale, ownerAtPoint, distance = math.hypot):
    """Trim terminal caps and extend side edges; containment stays a backend primitive."""
    for vertices in contours:
        for first, second in zip(vertices, vertices[1:]):
            x, y = second[0] - first[0], second[1] - first[1]
            length = math.hypot(x, y)
            if length < 1e-8:
                continue
            midpoint = (first[0] + second[0]) / 2, (first[1] + second[1]) / 2
            unitX, unitY = x / length, y / length
            if any(abs((midpoint[0] - vertex[0]) * axis[0] + (midpoint[1] - vertex[1]) * axis[1] - inset) < .001 * scale
                   and abs(unitX * axis[0] + unitY * axis[1]) < 1e-6
                   and distance(midpoint[0] - vertex[0], midpoint[1] - vertex[1]) <= halfWidth + inset
                   for vertex, axis, halfWidth in terminals):
                continue
            endpoints = []
            for point in (first, second):
                px, py = point
                for vertex, axis, halfWidth in terminals:
                    if (abs((px - vertex[0]) * axis[0] + (py - vertex[1]) * axis[1] - inset) < .001 * scale
                            and distance(px - vertex[0], py - vertex[1]) <= halfWidth + inset):
                        px, py = px - axis[0] * inset, py - axis[1] * inset
                        break
                endpoints.append((px, py))
            yield ownerAtPoint(midpoint), endpoints[0], endpoints[1]


def PlanStairArrowRuns(stairs, neighbors, trims, distance = math.hypot, peers = ()):
    arrows, links = [], {}
    byKey = {stair.key: stair for stair in stairs}
    byKey.update((stair.key, stair) for stair in peers)
    connections, dependents, landingIds, blocked = {}, {}, set(), set()
    for stair in stairs:
        startIndex, endIndex = (1, 0) if stair.reversed else (0, 1)
        start, tip = (stair.second, stair.first) if stair.reversed else (stair.first, stair.second)
        incoming, outgoing = neighbors[(stair.key, startIndex)], neighbors[(stair.key, endIndex)]
        before = after = None
        if len(incoming) == 1:
            peer = byKey[incoming[0]]
            point = peer.first if peer.reversed else peer.second
            if distance(start[0] - point[0], start[1] - point[1]) <= .01:
                before = peer.key
        if len(outgoing) == 1:
            peer = byKey[outgoing[0]]
            point = peer.second if peer.reversed else peer.first
            if distance(tip[0] - point[0], tip[1] - point[1]) <= .01:
                after = peer.key
        connections[stair.key] = before, after
        for peer in (before, after):
            if peer is not None:
                dependents.setdefault(peer, []).append(stair.key)
        length = distance(stair.second[0] - stair.first[0], stair.second[1] - stair.first[1])
        if length < .0001:
            blocked.add(stair.key)
        elif sum(trims[stair.key]) >= length - 1e-8:
            landingIds.add(stair.key)
            if before is None or after is None:
                blocked.add(stair.key)
    pending = list(blocked)
    while pending:
        for key in dependents.get(pending.pop(), ()):
            if key in landingIds and key not in blocked:
                blocked.add(key)
                pending.append(key)
    for stair in stairs:
        if stair.key in blocked:
            continue
        firstTrim, secondTrim = trims[stair.key]
        x, y = stair.second[0] - stair.first[0], stair.second[1] - stair.first[1]
        length = math.hypot(x, y)
        if length < .0001:
            continue
        x, y = x / length, y / length
        first = stair.first[0] + x * firstTrim, stair.first[1] + y * firstTrim
        second = stair.second[0] - x * secondTrim, stair.second[1] - y * secondTrim
        start, tip = (second, first) if stair.reversed else (first, second)
        trueStart, trueTip = (stair.second, stair.first) if stair.reversed else (stair.first, stair.second)
        before, after = connections[stair.key]
        joinsStart, joinsEnd = before is not None and before not in blocked, after is not None and after not in blocked
        if firstTrim + secondTrim >= length - 1e-8 and not (joinsStart and joinsEnd):
            continue
        arrows.append((stair.key, trueStart if joinsStart else start, trueTip if joinsEnd else tip, not joinsEnd))
        links[stair.key] = after if joinsEnd else None
    # Each directed cycle retains one visible direction head. Preserve the
    # original insertion order, including which member receives that head.
    positions = {key: index for index, (key, start, tip, showTip) in enumerate(arrows)}
    visited = set()
    for key in positions:
        chain, active, current = [], set(), key
        while current in positions and current not in visited:
            chain.append(positions[current])
            active.add(current)
            visited.add(current)
            current = links[current]
        if current in active:
            index = chain[0]
            key, start, tip, showTip = arrows[index]
            arrows[index] = key, start, tip, True
    return arrows
