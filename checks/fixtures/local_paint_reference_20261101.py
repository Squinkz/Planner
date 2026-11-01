"""Placement previews, opening fitting, collision validation and sidebar drops."""
from planner_app.models import AngleGuide

from planner_app.models import Elevator

import math
from contextlib import contextmanager
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import OpenDoorway, Door, SwingingDoor, DoubleDoor, Furnishing, PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, SlidingDoor, MeasurementGuide, BoundaryLine, DashedLine, SolidLine, Arrow, Counter, Railing, Stair, Wall, Pillar, Column, Label, RoomLabel, Window, NorthArrow, Fireplace
from planner_app.viewport.geometry import CollisionPass
from planner_app.viewport.collision_types import CollisionFlags
from planner_app.geometry.collisions import ExcludesFootprintCollision
from planner_app.geometry.opening_placement import (ProjectOpening, OpeningGap,
    BlockedOpeningIntervals, OpeningPlacementSpan, CenteredOpeningSpan, OpeningVertexFraction)
from planner_app.geometry.opening_collisions import OpeningCollisionIndex
from planner_app.geometry.reserved_doors import ReservedDoorWithinHost, ReservedDoorWallContact, ReservedDoorPlacementBounds, ReservedDoorEditCenter
from planner_app.geometry.opening_candidates import OpeningFacingChanges, FireplaceDepthSnap, FireplacePlacementCandidates
from planner_app.viewport.placement_types import OpeningFacingPolicy
from planner_app.viewport.spatial_index import BoundsIndex
from planner_app.geometry.attachments import FitOpeningCenters, OpeningWithinWall, OpeningIntervalsOverlap
from planner_app.placement_sizing import NominalPlacementSize, FurnishingPlacementSize



class ReferencePlacement:

    @CollisionPass
    def InvalidArchitecturalObjects(self):
        """Validate a read-only paint snapshot, retaining unaffected clear objects."""
        if getattr(self, "exportRender", False):
            return set()
        changes = self.renderChanges
        policyKey = (changes.appearance, changes.topology, changes.visibility,
                     tuple(self.visibility.items()), tuple(self.collisionSettings.items()), self.basePixelsPerMillimeter)
        key = changes.geometry, policyKey
        previous = getattr(self, "architecturalValidation", None)
        if previous is not None and previous[0] == key:
            return previous[1]
        if previous is not None and previous[0][1] == policyKey and len(previous) == 4:
            incremental = self.RefreshArchitecturalValidation(previous, key)
            if incremental is not None:
                return incremental
        records = previous[2] if previous is not None and previous[0][1] == policyKey else {}
        objects = self.walls + self.windows + self.furnishings + self.labels
        categories = {
            "wall": self.furnishings + [obj for obj in self.walls if isinstance(obj, (Counter, Railing, Stair, Elevator))] + self.windows,
            "counter": [obj for obj in self.walls if not isinstance(obj, Counter)],
            "stair": [obj for obj in objects if not isinstance(obj, (Stair, Arrow, MeasurementGuide, Label, NorthArrow))],
            "elevator": self.walls + self.windows + self.furnishings}
        scope = {"objects": objects, "categories": categories, "index": None, "nearby": {}, "furnishingBounds": {}}
        batch = self.collisionPassCache
        previousScope = batch.get("placementValidation")
        batch["placementValidation"] = scope
        invalid, current = set(), {}
        try:
            with self.OpeningCandidatePass(len(self.windows)):
                for obj in self.walls + self.windows:
                    if not self.IsObjectVisible(obj):
                        continue
                    if isinstance(obj, Window):
                        # Host fitting, shared-parent intervals and reserved-door
                        # support can depend on geometry beyond the local bounds.
                        signature = key
                    elif type(obj) in (Wall, Pillar, Column, Counter, Stair, Railing, Elevator):
                        kind = ("stair" if isinstance(obj, Stair) else "counter" if isinstance(obj, Counter)
                                else "elevator" if isinstance(obj, Elevator) else "wall")
                        blockers = self.PlacementBlockers(obj, kind)
                        # Joined footprints can change through an unchanged
                        # neighbor. Keep conservative global invalidation wherever
                        # a collision is possible; clear objects need only their
                        # own size/position checked again after movement.
                        signature = (obj.firstVertex.x(), obj.firstVertex.y(), obj.secondVertex.x(),
                                     obj.secondVertex.y(), obj.width, changes.geometry if blockers else None)
                    else:
                        continue
                    cached = records.get(id(obj))
                    fits = cached[1] if cached is not None and cached[0] == signature else self.ArchitecturalPlacementFits(obj)
                    current[id(obj)] = (signature, fits)
                    if not fits:
                        invalid.add(id(obj))
        finally:
            if previousScope is None:
                batch.pop("placementValidation", None)
            else:
                batch["placementValidation"] = previousScope
        # Reuse this immutable broad phase while only furnishings/annotations
        # move. A small overlay replaces stale furnishing entries in queries.
        scope["nearby"] = {}
        scope["movingBounds"] = {}
        state = {"scope": scope, "furnishingBounds": scope["furnishingBounds"]}
        self.architecturalValidation = key, invalid, current, state
        changes.placementChanges = {"objects": {}, "events": 0}
        return invalid


    def RefreshArchitecturalValidation(self, previous, key):
        """Revalidate architecture near furnishing edits; structural edits fall back."""
        changes = self.renderChanges
        journal = changes.placementChanges
        if journal is None or key[0] - previous[0][0] != journal["events"]:
            return None
        state = previous[3]
        edited = journal["objects"].values()
        if any(obj is None or not (type(obj) is Furnishing or isinstance(obj, (Label, NorthArrow))) for obj in edited):
            return None
        scope = state["scope"]
        if "architecture" not in state:
            state["architecture"] = {id(obj): order for order, obj in enumerate(self.walls)
                                     if id(obj) in previous[2] and type(obj) is not Counter}
            scope["members"] = {id(obj): obj for obj in scope["objects"]}
        movingBounds = dict(scope["movingBounds"])
        affected = set()
        for obj in edited:
            if type(obj) is not Furnishing or scope["index"] is None:
                continue
            bounds = self.JoinedObjectBounds(obj)
            if not all(math.isfinite(value) for value in bounds.getCoords()):
                return None
            oldBounds = movingBounds.get(id(obj), state["furnishingBounds"].get(id(obj)))
            if oldBounds is None or not all(math.isfinite(value) for value in oldBounds.getCoords()):
                return None
            for region in (oldBounds, bounds):
                affected.update(id(member) for member in scope["index"].Query(
                    region.normalized().adjusted(-.01, -.01, .01, .01)) if id(member) in state["architecture"])
            affected.update(id(member) for member in scope.get("fallback", ()) if id(member) in state["architecture"])
            movingBounds[id(obj)] = bounds
        # Bound both overlay queries and retained historical bounds. Rebuild
        # normally once many distinct furnishings have moved since preparation.
        if len(movingBounds) > 256:
            return None
        updatedScope = dict(scope, movingBounds = movingBounds, nearby = {})
        invalid = set(previous[1]) if affected else previous[1]
        batch = self.collisionPassCache
        previousScope = batch.get("placementValidation")
        batch["placementValidation"] = updatedScope
        try:
            for identity in sorted(affected, key = state["architecture"].__getitem__):
                if self.ArchitecturalPlacementFits(scope["members"][identity]):
                    invalid.discard(identity)
                else:
                    invalid.add(identity)
        finally:
            if previousScope is None:
                batch.pop("placementValidation", None)
            else:
                batch["placementValidation"] = previousScope
        # Publish only after all exact predicates succeed. A failed validation
        # must retain old bounds so the next attempt still checks old neighbors.
        updatedScope["nearby"] = {}
        updatedState = dict(state, scope = updatedScope)
        self.architecturalValidation = key, invalid, previous[2], updatedState
        journal["objects"].clear()
        journal["events"] = 0
        return invalid


    def PlacementBlockers(self, obj, kind):
        """Ordered broad phase confined to one immutable validation scope."""
        scope = (getattr(self, "collisionPassCache", None) or {}).get("placementValidation")
        if scope is None:
            return None
        enabled = scope.setdefault("enabledCategories", {})
        categoryKey = kind, type(obj)
        if categoryKey not in enabled:
            # The exact predicate rejects these pairs before reading geometry.
            # Do the same before broad-phase work and validity signatures, so
            # disabled collisions cannot make unchanged objects look dirty.
            members = tuple(member for member in scope["categories"][kind]
                            if self.CollisionEnabled(obj, member)
                            and not ExcludesFootprintCollision(CollisionFlags(type(obj)), CollisionFlags(type(member))))
            enabled[categoryKey] = members, {id(member) for member in members}
        members, enabledIds = enabled[categoryKey]
        if not members:
            return ()
        if scope["index"] is None:
            index = BoundsIndex(2000)
            fallback = []
            for member in scope["objects"]:
                if isinstance(member, (Arrow, MeasurementGuide, Label, NorthArrow)):
                    continue
                bounds = self.JoinedObjectBounds(member)
                if type(member) is Furnishing:
                    scope["furnishingBounds"][id(member)] = bounds
                if all(math.isfinite(value) for value in bounds.getCoords()):
                    index.Insert(bounds.normalized().adjusted(-.01, -.01, .01, .01), member)
                else:
                    fallback.append(member)
            scope["index"], scope["fallback"] = index, fallback
            scope["orders"] = {name: {id(member): position for position, member in enumerate(values)}
                               for name, values in scope["categories"].items()}
        identity = id(obj), kind
        if identity not in scope["nearby"]:
            bounds = self.JoinedObjectBounds(obj)
            if not all(math.isfinite(value) for value in bounds.getCoords()):
                nearby = [member for member in members if member is not obj]
            else:
                order = scope["orders"][kind]
                movingBounds = scope.get("movingBounds", {})
                nearby = [member for member in scope["index"].Query(bounds.normalized().adjusted(-.01, -.01, .01, .01))
                          + scope["fallback"] if id(member) in enabledIds and member is not obj and id(member) not in movingBounds]
                if movingBounds:
                    queryBounds = bounds.normalized().adjusted(-.01, -.01, .01, .01)
                    nearby.extend(scope["members"][identity] for identity, currentBounds in movingBounds.items()
                                  if identity in enabledIds and identity != id(obj)
                                  and queryBounds.intersects(currentBounds.normalized().adjusted(-.01, -.01, .01, .01)))
                nearby.sort(key = lambda member: order[id(member)])
            scope["nearby"][identity] = tuple(nearby)
        return scope["nearby"][identity]

