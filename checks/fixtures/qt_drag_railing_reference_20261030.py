"""Frozen pre-optimization placement and railing methods for parity checks."""
import math
from PySide6 import QtCore, QtGui
from planner_app.models import *
from planner_app.viewport.geometry import CollisionPass, FootprintGeometry
from planner_app.graphics.path_operations import Paths
from planner_app.geometry.attachments import OpeningWithinWall
from planner_app.geometry.reserved_doors import ReservedDoorWithinHost
from planner_app.viewport.widget import DrawingViewport

class ReferencePlacement:
    def ArchitecturalPlacementFits(self, obj):
        if isinstance(obj, Window):
            return self.OpeningFits(obj)
        if isinstance(obj, Stair):
            return self.StairFits(obj)
        if isinstance(obj, Counter):
            return self.CounterFits(obj)
        return self.WallFits(obj)

    def CounterFits(self, counter, excludeIds = frozenset()):
        if counter.width < 1 or QtCore.QLineF(counter.firstVertex, counter.secondVertex).length() < 1:
            return False
        blockers = [wall for wall in self.walls if not isinstance(wall, Counter) and id(wall) not in excludeIds]
        return not any(self.JoinedObjectsOverlap(counter, obj, contactTolerance = 1.0, excludedWalls = excludeIds) for obj in blockers)

    def WallFits(self, wall, blockers = None, excludeIds = frozenset()):
        if isinstance(wall, AngleGuide):
            return True
        if isinstance(wall, (Arrow, MeasurementGuide)):
            return QtCore.QLineF(wall.firstVertex, wall.secondVertex).length() >= 1
        if wall.width < 1 or QtCore.QLineF(wall.firstVertex, wall.secondVertex).length() < 1:
            return False
        if isinstance(wall, Elevator):
            blockers = [obj for obj in self.walls + self.windows + self.furnishings if obj is not wall]
        if blockers is None:
            blockers = (self.furnishings + [obj for obj in self.walls if isinstance(obj, (Counter, Railing, Stair, Elevator))]
                        + [opening for opening in self.windows if opening.parentWall is not wall
                           and not (isinstance(opening, PocketDoor) and type(wall) is Wall
                                    and not self.OpeningWallObstructs(opening, wall))])
        return not any(self.JoinedObjectsOverlap(wall, obj, contactTolerance = 1.0, excludedWalls = excludeIds)
                       for obj in blockers if id(obj) not in excludeIds)

    def FurnishingFits(self, furnishing):
        if isinstance(furnishing, Pillar):
            return self.WallFits(furnishing)
        if isinstance(furnishing, (Label, NorthArrow)):
            return True
        return (furnishing.width >= 1 and furnishing.length >= 1
                and not any(self.JoinedObjectsOverlap(furnishing, other, contactTolerance = 1.0)
                            for other in self.walls if not isinstance(other, Counter)))

    @CollisionPass
    def OpeningFits(self, opening, exclude = None, excludeIds = frozenset()):
        parentLength = QtCore.QLineF(opening.parentWall.firstVertex, opening.parentWall.secondVertex).length()
        fits = (ReservedDoorWithinHost(parentLength, opening.length, opening.centerFraction, opening.hingeAtSecond,
                                  self.ReservedDoorSupport(opening.parentWall)) if isinstance(opening, PocketDoor) else
                OpeningWithinWall(parentLength, opening.length, opening.centerFraction))
        if not fits:
            return False
        walls, openings = self.walls, self.windows
        batch = getattr(self, "collisionPassCache", None)
        scope = (batch or {}).get("openingCandidates")
        prepared = None
        if scope is not None:
            if not scope["primed"]:
                scope["primed"] = True
            else:
                prepared = scope["prepared"]
                if prepared is None:
                    prepared = self.BuildOpeningCollisionIndex()
                    scope["prepared"] = prepared
        if prepared is not None:
            candidateIndex, indexedWalls, indexedOpenings = prepared
            bounds = self.JoinedObjectBounds(opening)
            wallIndices, openingIndices = candidateIndex.Query(
                (bounds.left(), bounds.top(), bounds.right(), bounds.bottom()), id(opening.parentWall))
            walls = (indexedWalls[index] for index in wallIndices)
            openings = (indexedOpenings[index] for index in openingIndices)
        if any(type(wall) in (Wall, Pillar, Column) and self.OpeningWallObstructs(opening, wall) for wall in walls):
            return False
        return not any(other is not exclude and other is not opening and (not excludeIds or id(other) not in excludeIds)
                       and self.OpeningsOverlap(opening, other)
                       for other in openings)

    def StairFits(self, stair, exclude = None, excludeIds = frozenset()):
        if stair.width < 1 or QtCore.QLineF(stair.firstVertex, stair.secondVertex).length() < 1:
            return False
        for other in self.walls + self.windows + self.furnishings + self.labels:
            # Snapped faces can differ by sub-millimeter amounts after endpoint
            # rotation and screen/world conversion. Treat that as edge contact.
            if (isinstance(other, Stair) or other is exclude or id(other) in excludeIds
                    or not self.JoinedObjectsOverlap(stair, other, contactTolerance = 1.0, excludedWalls = excludeIds)):
                continue
            return False
        return True

class ReferenceRailing:
    def ConnectedRailingPath(self, railings, includeMeasurements = True):
        if not hasattr(self, "railingWorkspace"):
            self.railingWorkspace = FootprintGeometry(self.basePixelsPerMillimeter, self)
        workspace = self.railingWorkspace
        workspace.zoom = self.zoom
        footprint = workspace.ConnectedWallPath(railings)
        key = tuple((id(obj), obj.firstVertex.x(), obj.firstVertex.y(), obj.secondVertex.x(), obj.secondVertex.y(),
                     obj.width, obj.firstMiter, obj.secondMiter, obj.postCount) for obj in railings)
        if key != getattr(self, "railingSymbolKey", None):
            symbol = QtGui.QPainterPath()
            symbol.setFillRule(QtCore.Qt.FillRule.WindingFill)
            transform = QtGui.QTransform().scale(self.basePixelsPerMillimeter, -self.basePixelsPerMillimeter)
            # A shared endpoint owns one post, even if multiple runs meet there.
            posts = []
            for railing in railings:
                run = railing.secondVertex - railing.firstVertex
                length = math.hypot(run.x(), run.y())
                if length < 1e-10:
                    continue
                direction = run / length
                normal = QtCore.QPointF(-direction.y(), direction.x())
                offset = normal * (railing.width * .75 / 2)
                bar = QtGui.QPainterPath()
                bar.addPolygon(transform.map(QtGui.QPolygonF([railing.firstVertex - offset, railing.secondVertex - offset,
                    railing.secondVertex + offset, railing.firstVertex + offset])))
                bar.closeSubpath()
                symbol = Paths.Union(symbol, bar)
                for index in range(railing.postCount):
                    center = railing.firstVertex + run * (index / (railing.postCount - 1))
                    existing = next((post for post in posts if QtCore.QLineF(center, post[0]).length() <= .01), None)
                    if existing is None:
                        posts.append([center, direction, normal, railing.width])
                    elif railing.width > existing[3]:
                        existing[1:] = [direction, normal, railing.width]
            postOutlines = QtGui.QPainterPath()
            for center, direction, normal, width in posts:
                a, b = direction * (width / 2), normal * (width / 2)
                post = QtGui.QPainterPath()
                post.addPolygon(transform.map(QtGui.QPolygonF([center - a - b, center + a - b, center + a + b, center - a + b])))
                post.closeSubpath()
                postOutlines.addPath(post)
                symbol = Paths.Union(symbol, post)
            self.railingSymbolKey, self.railingSymbolPath = key, symbol
            self.railingPostOutlinePath = postOutlines
        origin = self.WorldToViewport(QtCore.QPointF())
        transform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(self.zoom, self.zoom)
        dimensions = workspace.WallDimensions(railings, footprint, [], cachedBoundary = True) if includeMeasurements else []
        return transform.map(self.railingSymbolPath), dimensions


class ReferenceViewport(ReferencePlacement, ReferenceRailing, DrawingViewport):
    @CollisionPass
    def InvalidArchitecturalObjects(self):
        return {id(obj) for obj in self.walls + self.windows
                if not getattr(self, "exportRender", False) and self.IsObjectVisible(obj)
                and (isinstance(obj, Window) or type(obj) in (Wall, Pillar, Column, Counter, Stair, Railing, Elevator))
                and not self.ArchitecturalPlacementFits(obj)}
