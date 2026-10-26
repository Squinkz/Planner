"""Compact exterior chains for openings, room divisions and overall spans."""
import math
from PySide6 import QtCore
from planner_app.models import Wall


def BuildMeasurementStacks(totals, openingSpans, walls, rooms, reference = "Wall faces"):
    inner, additional = [], []
    axes = []
    for wall in walls:
        if type(wall) is not Wall:
            continue
        delta = wall.secondVertex - wall.firstVertex
        length = math.hypot(delta.x(), delta.y())
        if length > .0001:
            axes.append((wall, delta / length, length))
    for first, second, owners in totals:
        length = QtCore.QLineF(first, second).length()
        if length < .0001:
            continue
        direction = (second - first) / length
        normal = QtCore.QPointF(-direction.y(), direction.x())
        width = max((owner.width for owner in owners), default = 0)
        axisOrigin = first
        # Boundary spans already follow the exterior wall faces. Centerline
        # references shorten/extend their ends to the intersecting wall axes,
        # keeping the guide on the exterior side of the building.
        if reference == "Centerline":
            owner = next((owner for owner in owners if type(owner) is Wall), None)
            offset = ((first.x() - owner.firstVertex.x()) * normal.x() +
                      (first.y() - owner.firstVertex.y()) * normal.y()) if owner is not None else 0
            axisOrigin = first - normal * offset
            endCuts = [[], []]
            for wall, axis, wallLength in axes:
                cross = direction.x() * axis.y() - direction.y() * axis.x()
                if abs(cross) < 1e-6:
                    continue
                delta = wall.firstVertex - axisOrigin
                along = (delta.x() * axis.y() - delta.y() * axis.x()) / cross
                onWall = (delta.x() * direction.y() - delta.y() * direction.x()) / cross
                if not -width / abs(cross) - .01 <= onWall <= wallLength + width / abs(cross) + .01:
                    continue
                alongOffset = abs(offset * (direction.x() * axis.x() + direction.y() * axis.y()) / cross)
                allowance = wall.width / (2 * abs(cross)) + alongOffset + .01
                for index, end in enumerate((0, length)):
                    if abs(along - end) <= allowance:
                        endCuts[index].append(along)
            low = min(endCuts[0], key = abs) if endCuts[0] else 0
            high = min(endCuts[1], key = lambda value: abs(value - length)) if endCuts[1] else length
            if high - low > .01:
                first, second = first + direction * low, first + direction * high
                axisOrigin += direction * low
                length = high - low
        roomCuts = []
        for wall, axis, wallLength in axes:
            cross = direction.x() * axis.y() - direction.y() * axis.x()
            if abs(cross) < 1e-6:
                continue
            delta = wall.firstVertex - axisOrigin
            along = (delta.x() * axis.y() - delta.y() * axis.x()) / cross
            onWall = (delta.x() * direction.y() - delta.y() * direction.x()) / cross
            allowance = width / abs(cross) + .01
            if not .01 < along < length - .01 or not -allowance <= onWall <= wallLength + allowance:
                continue
            # A T junction only divides the chain when it separates two rooms.
            # Probe beyond both wall faces, rather than treating a free stub as
            # a room boundary. Follow an angled partition into the interior.
            across = axis.x() * normal.x() + axis.y() * normal.y()
            distance = width + .05
            sideStep = wall.width / (2 * abs(cross)) + .05
            junction = axisOrigin + direction * along
            for sign in (-1, 1):
                center = junction + axis * (sign * distance / across)
                before, after = center - direction * sideStep, center + direction * sideStep
                beforeRoom = next((index for index, room in enumerate(rooms) if room.contains(before)), None)
                afterRoom = next((index for index, room in enumerate(rooms) if room.contains(after)), None)
                halfWidth = wall.width / (2 * abs(cross))
                lowFace, highFace = along - halfWidth, along + halfWidth
                if beforeRoom is None or afterRoom is None:
                    # Several touching/overlapping walls can form one partition.
                    # Find its complete cross-section at the probe, so stepping
                    # beyond one wall does not leave the probe inside another.
                    sections = []
                    for member, memberAxis, memberLength in axes:
                        memberCross = direction.x() * memberAxis.y() - direction.y() * memberAxis.x()
                        if abs(memberCross) < 1e-6:
                            continue
                        delta = member.firstVertex - center
                        at = (delta.x() * memberAxis.y() - delta.y() * memberAxis.x()) / memberCross
                        onMember = (delta.x() * direction.y() - delta.y() * direction.x()) / memberCross
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
                        before = center + direction * (group[0] - .05)
                        after = center + direction * (group[1] + .05)
                        beforeRoom = next((index for index, room in enumerate(rooms) if room.contains(before)), None)
                        afterRoom = next((index for index, room in enumerate(rooms) if room.contains(after)), None)
                        faces = []
                        for member, memberAxis, memberCross in group[2]:
                            delta = member.firstVertex - axisOrigin
                            at = (delta.x() * memberAxis.y() - delta.y() * memberAxis.x()) / memberCross
                            extent = member.width / (2 * abs(memberCross))
                            faces.extend((at - extent, at + extent))
                        lowFace, highFace = min(faces), max(faces)
                if beforeRoom is not None and afterRoom is not None and beforeRoom != afterRoom:
                    if reference == "Wall faces":
                        roomCuts.extend((max(0, lowFace), min(length, highFace)))
                    else:
                        roomCuts.append((lowFace + highFace) / 2)
                    break
        projected = []
        for start, end, spanOwners in openingSpans:
            delta = end - start
            if abs(delta.x() * direction.y() - delta.y() * direction.x()) > .01:
                continue
            offset = start - first
            if abs(offset.x() * direction.y() - offset.y() * direction.x()) > .01:
                continue
            low = offset.x() * direction.x() + offset.y() * direction.y()
            high = (end.x() - first.x()) * direction.x() + (end.y() - first.y()) * direction.y()
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
            inner.append((first + direction * low, first + direction * high, spanOwners))
        hasRoomRow = len(roomStops) > 2 and len(stops) > len(roomStops)
        if hasRoomRow:
            additional.extend((first + direction * low, first + direction * high, owners, 1)
                              for low, high in zip(roomStops, roomStops[1:]))
        if len(stops) > 2:
            additional.append((first, second, owners, 2 if hasRoomRow else 1))
    return inner, additional
