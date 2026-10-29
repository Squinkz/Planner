"""Numeric exterior dimension rows, room partitions and opening projections."""
from dataclasses import dataclass
import math


@dataclass(frozen = True, slots = True)
class StackWall:
    first: tuple
    second: tuple
    width: float


@dataclass(frozen = True, slots = True)
class StackSpan:
    first: tuple
    second: tuple
    owners: object
    width: float
    ownerFirst: tuple | None = None


def PlanMeasurementStacks(totals, openingSpans, walls, roomAtPoint, reference = "Wall faces", distance = math.hypot):
    """Return inner and additional rows, borrowing opaque owner payloads.

    Native room containment and scalar length rounding can be supplied by an
    adapter. None indicates no rooms and skips partition probes. All cut
    selection, overlap grouping and row compaction stay here.
    """
    inner, additional, axes = [], [], []
    for wall in walls:
        x, y = wall.second[0] - wall.first[0], wall.second[1] - wall.first[1]
        length = math.hypot(x, y)
        if length > .0001:
            axes.append((wall, (x / length, y / length), length))
    for span in totals:
        first, second, owners, width = span.first, span.second, span.owners, span.width
        length = distance(second[0] - first[0], second[1] - first[1])
        if length < .0001:
            continue
        direction = (second[0] - first[0]) / length, (second[1] - first[1]) / length
        normal = -direction[1], direction[0]
        axisOrigin = first
        if reference == "Centerline":
            offset = ((first[0] - span.ownerFirst[0]) * normal[0] + (first[1] - span.ownerFirst[1]) * normal[1]
                      if span.ownerFirst is not None else 0)
            axisOrigin = first[0] - normal[0] * offset, first[1] - normal[1] * offset
            endCuts = [[], []]
            for wall, axis, wallLength in axes:
                cross = direction[0] * axis[1] - direction[1] * axis[0]
                if abs(cross) < 1e-6:
                    continue
                x, y = wall.first[0] - axisOrigin[0], wall.first[1] - axisOrigin[1]
                along = (x * axis[1] - y * axis[0]) / cross
                onWall = (x * direction[1] - y * direction[0]) / cross
                if not -width / abs(cross) - .01 <= onWall <= wallLength + width / abs(cross) + .01:
                    continue
                alongOffset = abs(offset * (direction[0] * axis[0] + direction[1] * axis[1]) / cross)
                allowance = wall.width / (2 * abs(cross)) + alongOffset + .01
                for index, end in enumerate((0, length)):
                    if abs(along - end) <= allowance:
                        endCuts[index].append(along)
            low = min(endCuts[0], key = abs) if endCuts[0] else 0
            high = min(endCuts[1], key = lambda value: abs(value - length)) if endCuts[1] else length
            if high - low > .01:
                first, second = ((first[0] + direction[0] * low, first[1] + direction[1] * low),
                                 (first[0] + direction[0] * high, first[1] + direction[1] * high))
                axisOrigin = axisOrigin[0] + direction[0] * low, axisOrigin[1] + direction[1] * low
                length = high - low
        roomCuts = []
        for wall, axis, wallLength in (axes if roomAtPoint is not None else ()):
            cross = direction[0] * axis[1] - direction[1] * axis[0]
            if abs(cross) < 1e-6:
                continue
            x, y = wall.first[0] - axisOrigin[0], wall.first[1] - axisOrigin[1]
            along = (x * axis[1] - y * axis[0]) / cross
            onWall = (x * direction[1] - y * direction[0]) / cross
            allowance = width / abs(cross) + .01
            if not .01 < along < length - .01 or not -allowance <= onWall <= wallLength + allowance:
                continue
            # A free wall stub does not separate rooms. Probe beyond both faces
            # of the partition, following angled walls into the interior.
            across = axis[0] * normal[0] + axis[1] * normal[1]
            probeDistance = width + .05
            sideStep = wall.width / (2 * abs(cross)) + .05
            junction = axisOrigin[0] + direction[0] * along, axisOrigin[1] + direction[1] * along
            for sign in (-1, 1):
                travel = sign * probeDistance / across
                center = junction[0] + axis[0] * travel, junction[1] + axis[1] * travel
                before = center[0] - direction[0] * sideStep, center[1] - direction[1] * sideStep
                after = center[0] + direction[0] * sideStep, center[1] + direction[1] * sideStep
                beforeRoom, afterRoom = roomAtPoint(before), roomAtPoint(after)
                halfWidth = wall.width / (2 * abs(cross))
                lowFace, highFace = along - halfWidth, along + halfWidth
                if beforeRoom is None or afterRoom is None:
                    sections = []
                    for member, memberAxis, memberLength in axes:
                        memberCross = direction[0] * memberAxis[1] - direction[1] * memberAxis[0]
                        if abs(memberCross) < 1e-6:
                            continue
                        x, y = member.first[0] - center[0], member.first[1] - center[1]
                        at = (x * memberAxis[1] - y * memberAxis[0]) / memberCross
                        onMember = (x * direction[1] - y * direction[0]) / memberCross
                        if -.01 <= onMember <= memberLength + .01:
                            extent = member.width / (2 * abs(memberCross))
                            sections.append((at - extent, at + extent, member, memberAxis, memberCross))
                    groups = []
                    for start, end, member, memberAxis, memberCross in sorted(sections, key = lambda entry: entry[0]):
                        if groups and start <= groups[-1][1] + .01:
                            groups[-1][1] = max(groups[-1][1], end)
                            groups[-1][2].append((member, memberAxis, memberCross))
                        else:
                            groups.append([start, end, [(member, memberAxis, memberCross)]])
                    group = next((group for group in groups if group[0] <= 0 <= group[1]), None)
                    if group is not None:
                        before = center[0] + direction[0] * (group[0] - .05), center[1] + direction[1] * (group[0] - .05)
                        after = center[0] + direction[0] * (group[1] + .05), center[1] + direction[1] * (group[1] + .05)
                        beforeRoom, afterRoom = roomAtPoint(before), roomAtPoint(after)
                        faces = []
                        for member, memberAxis, memberCross in group[2]:
                            x, y = member.first[0] - axisOrigin[0], member.first[1] - axisOrigin[1]
                            at = (x * memberAxis[1] - y * memberAxis[0]) / memberCross
                            extent = member.width / (2 * abs(memberCross))
                            faces.extend((at - extent, at + extent))
                        lowFace, highFace = min(faces), max(faces)
                if beforeRoom is not None and afterRoom is not None and beforeRoom != afterRoom:
                    # At an angled facade corner a partition can meet two rooms
                    # without dividing this span. Its projected thickness then
                    # crosses the span endpoint; clipping it creates a false
                    # short dimension for the corner itself.
                    if lowFace <= .01 or highFace >= length - .01:
                        continue
                    if reference == "Wall faces":
                        roomCuts.extend((max(0, lowFace), min(length, highFace)))
                    else:
                        roomCuts.append((lowFace + highFace) / 2)
                    break
        projected = []
        for start, end, spanOwners in openingSpans:
            x, y = end[0] - start[0], end[1] - start[1]
            if abs(x * direction[1] - y * direction[0]) > .01:
                continue
            x, y = start[0] - first[0], start[1] - first[1]
            if abs(x * direction[1] - y * direction[0]) > .01:
                continue
            low = x * direction[0] + y * direction[1]
            high = (end[0] - first[0]) * direction[0] + (end[1] - first[1]) * direction[1]
            low, high = sorted((low, high))
            if low >= -.01 and high <= length + .01:
                projected.append((max(0, low), min(length, high), spanOwners))
        roomStops = [0.0]
        for value in sorted(roomCuts):
            if .01 < value < length - .01 and value - roomStops[-1] > .01:
                roomStops.append(value)
        roomStops.append(length)
        stops = [0.0]
        for value in sorted(roomStops[1:-1] + [value for low, high, spanOwners in projected for value in (low, high)]):
            if .01 < value < length - .01 and value - stops[-1] > .01:
                stops.append(value)
        stops.append(length)
        for low, high in zip(stops, stops[1:]):
            midpoint = (low + high) / 2
            spanOwners = next((members for start, end, members in projected if start - .01 <= midpoint <= end + .01), owners)
            inner.append(((first[0] + direction[0] * low, first[1] + direction[1] * low),
                          (first[0] + direction[0] * high, first[1] + direction[1] * high), spanOwners))
        hasRoomRow = len(roomStops) > 2 and len(stops) > len(roomStops)
        if hasRoomRow:
            additional.extend(((first[0] + direction[0] * low, first[1] + direction[1] * low),
                               (first[0] + direction[0] * high, first[1] + direction[1] * high), owners, 1)
                              for low, high in zip(roomStops, roomStops[1:]))
        if len(stops) > 2:
            additional.append((first, second, owners, 2 if hasRoomRow else 1))
    return inner, additional
