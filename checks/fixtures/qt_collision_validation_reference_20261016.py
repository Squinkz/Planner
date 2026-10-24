"""Frozen validation before spatial opening candidates."""

import math

from PySide6 import QtCore, QtGui, QtWidgets

from planner_app.models import *

from planner_app.viewport.geometry import CollisionPass
from planner_app.geometry.snapping import PrepareTargetIndex, NearbyTargetIndices
from planner_app.geometry.collisions import JunctionReach

from planner_app.geometry.attachments import OpeningWithinWall, OpeningIntervalsOverlap

class ReferencePlacement:

    def OpeningsOverlap(self, first, second):
        if not self.CollisionEnabled(first, second):
            return False
        if first.parentWall is second.parentWall:
            return OpeningIntervalsOverlap(first.firstFraction, first.secondFraction,
                                           second.firstFraction, second.secondFraction)
        return self.JoinedObjectsOverlap(first, second)

    @CollisionPass
    def OpeningFits(self, opening, exclude = None):
        parentLength = QtCore.QLineF(opening.parentWall.firstVertex, opening.parentWall.secondVertex).length()
        if not OpeningWithinWall(parentLength, opening.length, opening.centerFraction):
            return False
        if any(type(wall) in (Wall, Pillar, Column) and wall is not opening.parentWall and
               self.JoinedObjectsOverlap(opening, wall, contactTolerance = 1.0) for wall in self.walls):
            return False
        return not any(other is not exclude and other is not opening and self.OpeningsOverlap(opening, other)
                       for other in self.windows)

    @CollisionPass
    def OpeningsValid(self, validateFurnishings = True, before = None):
        changed = None
        if before is not None:
            oldWalls = {id(state[0]): state[1:8] for state in before[0]}
            oldOpenings = {id(state[0]): state[1:4] for state in before[3]}
            oldFurnishings = {id(state[0]): state[1:4] for state in before[5]} if len(before) > 5 else {}
            changed = {id(wall) for wall in self.walls if oldWalls.get(id(wall)) != (
                wall.firstVertex.x(), wall.firstVertex.y(), wall.secondVertex.x(), wall.secondVertex.y(),
                wall.width, wall.firstMiter, wall.secondMiter)}
            changed.update(id(opening) for opening in self.windows if oldOpenings.get(id(opening)) != (
                opening.parentWall, opening.centerFraction, opening.length))
            changed.update(id(obj) for obj in self.furnishings if oldFurnishings.get(id(obj)) != (
                obj.firstVertex, obj.secondVertex, obj.width))
        walls = self.walls if changed is None else [wall for wall in self.walls if id(wall) in changed]
        furnishings = self.furnishings if changed is None else [obj for obj in self.furnishings if id(obj) in changed]
        for wall in walls:
            length = QtCore.QLineF(wall.firstVertex, wall.secondVertex).length()
            minimumLength = self.MinimumOpeningLength(wall)
            if length < 1e-8 or length < minimumLength - 0.01:
                return False
        for index, opening in enumerate(self.windows):
            if changed is not None and id(opening) not in changed and id(opening.parentWall) not in changed:
                continue
            if not self.OpeningFits(opening):
                return False
            if any(self.OpeningsOverlap(opening, other) for other in self.windows[index + 1:]):
                return False
        return (all(self.StairFits(wall) for wall in walls if isinstance(wall, Stair))
                and all(self.CounterFits(wall) for wall in walls if isinstance(wall, Counter))
                and all(self.WallFits(wall) for wall in walls if isinstance(wall, Pillar)
                        or changed is not None and type(wall) is Wall)
                and (not validateFurnishings or all(self.FurnishingFits(obj) for obj in furnishings)))

class ReferenceScene:

    @CollisionPass
    def GroupOpeningsFit(self, openings):
        # All positions are final for this preview. Share read-only collision
        # preparation here, never across the preceding model assignments or
        # SetOpeningVertex calls, which may move/restore an opening themselves.
        for opening, index in openings:
            if not (self.OpeningFits(opening) and opening.firstFraction >= 0 and opening.secondFraction <= 1):
                return False
        return True

class ReferenceGeometry:
    def JoinedObjectBounds(self, obj, excludedWalls = ()):
        """Conservative world bounds including arbitrary-length miter joins."""
        batch = getattr(self, "collisionPassCache", None)
        key = (id(obj), frozenset(excludedWalls))
        if batch is not None and key in batch.get("joinedBounds", {}):
            return batch["joinedBounds"][key]
        bounds = self.ObjectFootprint(obj)[0]
        if type(obj) in (Wall, Stair, Counter, Railing):
            category = type(obj)
            prepared = None
            if batch is not None:
                endpointKey = (category, frozenset(excludedWalls))
                prepared = batch.get("junctionEndpoints", {}).get(endpointKey)
                if prepared is None:
                    # Index a read-only validation pass once, preserving scene
                    # and endpoint order for the native junction calculation.
                    endpoints = [(wall, endpoint, far, miter) for wall in self.walls
                                 if type(wall) is category and id(wall) not in excludedWalls
                                 for endpoint, far, miter in ((wall.firstVertex, wall.secondVertex, wall.firstMiter),
                                                             (wall.secondVertex, wall.firstVertex, wall.secondMiter))]
                    endpointIndex = PrepareTargetIndex([(endpoint.x(), endpoint.y()) for wall, endpoint, far, miter in endpoints])
                    prepared = endpoints, endpointIndex
                    batch.setdefault("junctionEndpoints", {})[endpointKey] = prepared
            else:
                members = [wall for wall in self.walls if type(wall) is category and id(wall) not in excludedWalls and wall is not obj]
            for vertex, opposite, miter in ((obj.firstVertex, obj.secondVertex, obj.firstMiter),
                                              (obj.secondVertex, obj.firstVertex, obj.secondMiter)):
                delta = opposite - vertex
                length = math.hypot(delta.x(), delta.y())
                if length < 1e-10:
                    continue
                rays = [(delta / length, obj.width / 2, miter)]
                if prepared is not None:
                    endpoints, endpointIndex = prepared
                    nearby = (endpoints[index] for index in NearbyTargetIndices(
                        (vertex.x(), vertex.y()), .02000001, endpointIndex, alignment = False))
                else:
                    nearby = ((other, endpoint, far, otherMiter) for other in members
                              for endpoint, far, otherMiter in ((other.firstVertex, other.secondVertex, other.firstMiter),
                                                                (other.secondVertex, other.firstVertex, other.secondMiter)))
                for other, endpoint, far, otherMiter in nearby:
                    if other is obj or QtCore.QLineF(vertex, endpoint).length() > .02000001:
                        continue
                    direction = far - endpoint
                    distance = math.hypot(direction.x(), direction.y())
                    if distance > 1e-10:
                        rays.append((direction / distance, other.width / 2, otherMiter))
                if len(rays) == 1:
                    continue
                radius = JunctionReach([(direction.x(), direction.y(), width, miter)
                                        for direction, width, miter in rays], self.basePixelsPerMillimeter)
                bounds = bounds.united(QtCore.QRectF(vertex.x() - radius, vertex.y() - radius, 2 * radius, 2 * radius))
        if batch is not None:
            batch.setdefault("joinedBounds", {})[key] = bounds
        return bounds
