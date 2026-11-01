"""Frozen pre-follow-up paint preparation for exact behavior comparisons."""
import math
from planner_app.models import *
from planner_app.viewport.geometry import CollisionPass
from planner_app.viewport.spatial_index import BoundsIndex
from planner_app.coincident_records import GroupCoincidentRecords
from planner_app.viewport.widget import DrawingViewport


class ReferenceViewport(DrawingViewport):
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
        records = previous[2] if previous is not None and previous[0][1] == policyKey else {}
        objects = self.walls + self.windows + self.furnishings + self.labels
        categories = {
            "wall": self.furnishings + [obj for obj in self.walls if isinstance(obj, (Counter, Railing, Stair, Elevator))] + self.windows,
            "counter": [obj for obj in self.walls if not isinstance(obj, Counter)],
            "stair": [obj for obj in objects if not isinstance(obj, (Stair, Arrow, MeasurementGuide, Label, NorthArrow))],
            "elevator": self.walls + self.windows + self.furnishings}
        scope = {"objects": objects, "categories": categories, "index": None, "nearby": {}}
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
        self.architecturalValidation = key, invalid, current
        return invalid

    def PlacementBlockers(self, obj, kind):
        """Ordered broad phase confined to one immutable validation scope."""
        scope = (getattr(self, "collisionPassCache", None) or {}).get("placementValidation")
        if scope is None:
            return None
        members = scope["categories"][kind]
        if not members:
            return ()
        if scope["index"] is None:
            index = BoundsIndex(2000)
            fallback = []
            for member in scope["objects"]:
                if isinstance(member, (Arrow, MeasurementGuide, Label, NorthArrow)):
                    continue
                bounds = self.JoinedObjectBounds(member)
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
                nearby = [member for member in scope["index"].Query(bounds.normalized().adjusted(-.01, -.01, .01, .01))
                          + scope["fallback"] if id(member) in order and member is not obj]
                nearby.sort(key = lambda member: order[id(member)])
            scope["nearby"][identity] = tuple(nearby)
        return scope["nearby"][identity]

    def CoincidentObjectGroups(self, includeHidden = False):
        """Keep paint order and visual identity consistent for duplicate repairs."""
        from planner_app.project_codec import EncodeObjectRecord
        objects = self.walls + self.windows + sorted(self.furnishings, key = lambda obj: not obj.behindCounters) + self.labels
        indices = {id(obj): index for index, obj in enumerate(objects)}
        groups = {}
        def Records():
            for obj in objects:
                if not includeHidden and not self.IsObjectVisible(obj):
                    continue
                if type(obj) is Furnishing:
                    record = ("Furnishing", getattr(obj, "definitionKey", obj.definition["key"]), obj.firstVertex.x(), obj.firstVertex.y(),
                              obj.secondVertex.x(), obj.secondVertex.y(), obj.width, obj.flipHorizontal, obj.flipVertical)
                    # Preserve the furnishing fast path: no encoded dictionary,
                    # yielded pair or extra serialization is needed.
                    groups.setdefault(record, []).append(obj)
                else:
                    record = EncodeObjectRecord(obj, indices)
                    yield obj, record
        return GroupCoincidentRecords(Records(), groups = groups, consumeRecords = True)

