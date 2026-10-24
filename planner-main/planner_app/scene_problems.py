"""Read-only checks for current scene problems, shared with recovery validation."""
import math
import hashlib
import json
from itertools import combinations
from PySide6 import QtCore
from .furnishing_assets import FurnishingAssetProblems
from .geometry_recovery import FindGeometryIssue, GeometryRepairText
from .models import Furnishing, Window, Wall, Pillar, Counter, Stair, Elevator
from .project_codec import EncodeObjectRecord
from .viewport.geometry import CollisionPass
from .units import FormatLength


potentialAngleTolerance = .5
potentialDistanceTolerance = 5.0
endpointTolerance = .01


def PotentialWallIssue(viewport, wall, code, label, description, cluster, target, related = ()):
    changes = tuple((obj, index, QtCore.QPointF(target)) for obj, index in cluster["endpoints"])
    objects = {id(obj): obj for obj in (wall, *related, *(entry[0] for entry in changes))}
    source = cluster["point"]
    coordinates = [FormatLength(value, viewport.unitsMode, decimals = 4)
                   for value in (source.x(), source.y(), target.x(), target.y())]
    repairText = f"Repair will move the endpoint from ({coordinates[0]}, {coordinates[1]}) to ({coordinates[2]}, {coordinates[3]})."
    if len(changes) > 1:
        repairText += f"\nAll {len(changes)} endpoints at this junction will move together."
    # Use persistent IDs and geometry, never the runtime IDs embedded in some
    # issue codes. This survives save/reopen without hiding changed geometry.
    signature = dict(kind = code.split(":")[1], primary = wall.objectId or 0,
        objects = sorted((obj.objectId or 0, obj.firstVertex.x(), obj.firstVertex.y(),
                          obj.secondVertex.x(), obj.secondVertex.y(), float(obj.width)) for obj in objects.values()),
        changes = sorted((obj.objectId or 0, index, target.x(), target.y()) for obj, index, target in changes))
    fingerprint = hashlib.sha256(json.dumps(signature, sort_keys = True, separators = (",", ":")).encode("utf-8")).hexdigest()
    return dict(object = wall, objects = tuple(objects.values()), code = code, label = label,
                description = description, repair = changes, repairText = repairText, potential = True, fingerprint = fingerprint)


def FindPotentialWallIssues(viewport, gridStep):
    walls = [wall for wall in viewport.walls if type(wall) is Wall
             and all(math.isfinite(value) for point in (wall.firstVertex, wall.secondVertex) for value in (point.x(), point.y()))
             and QtCore.QLineF(wall.firstVertex, wall.secondVertex).length() >= 1]
    clusters, buckets, membership = [], {}, {}
    for wall in walls:
        for index, vertex in enumerate((wall.firstVertex, wall.secondVertex)):
            cell = math.floor(vertex.x() / endpointTolerance), math.floor(vertex.y() / endpointTolerance)
            candidates = sorted({candidate for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                                 for candidate in buckets.get((cell[0] + dx, cell[1] + dy), ())})
            clusterIndex = next((candidate for candidate in candidates
                                 if QtCore.QLineF(vertex, clusters[candidate]["point"]).length() <= endpointTolerance), None)
            if clusterIndex is None:
                clusterIndex = len(clusters)
                clusters.append(dict(point = QtCore.QPointF(vertex), endpoints = []))
                buckets.setdefault(cell, []).append(clusterIndex)
            clusters[clusterIndex]["endpoints"].append((wall, index))
            membership[id(wall), index] = clusterIndex
    issues = []
    for wall in walls:
        direction = wall.secondVertex - wall.firstVertex
        angle = math.degrees(math.atan2(direction.y(), direction.x()))
        deviation = abs((angle + 45) % 90 - 45)
        if 1e-6 < deviation <= potentialAngleTolerance + 1e-9:
            # Prefer moving a free endpoint over disturbing a larger junction.
            index = min((1, 0), key = lambda index: len(clusters[membership[id(wall), index]]["endpoints"]))
            cluster = clusters[membership[id(wall), index]]
            vertex = wall.firstVertex if index == 0 else wall.secondVertex
            opposite = wall.secondVertex if index == 0 else wall.firstVertex
            target = (QtCore.QPointF(vertex.x(), opposite.y()) if abs(direction.x()) >= abs(direction.y())
                      else QtCore.QPointF(opposite.x(), vertex.y()))
            if QtCore.QLineF(vertex, target).length() > endpointTolerance:
                issues.append(PotentialWallIssue(viewport, wall, "potential:axis", "Wall almost aligned to an axis",
                    f"The wall is {deviation:.4g}\u00b0 from {'horizontal' if abs(direction.x()) >= abs(direction.y()) else 'vertical'}.",
                    cluster, target))
    gapBuckets = {}
    for clusterIndex, cluster in enumerate(clusters):
        point = cluster["point"]
        if math.isfinite(gridStep) and gridStep > 0:
            originX, originY = viewport.gridOrigin
            target = QtCore.QPointF(originX + round((point.x() - originX) / gridStep) * gridStep,
                                   originY + round((point.y() - originY) / gridStep) * gridStep)
            distance = QtCore.QLineF(point, target).length()
            if endpointTolerance < distance <= min(potentialDistanceTolerance, gridStep * .05):
                wall, index = cluster["endpoints"][0]
                issues.append(PotentialWallIssue(viewport, wall, f"potential:grid:{index}", "Endpoint just off grid",
                    f"The endpoint is {FormatLength(distance, viewport.unitsMode, decimals = 4)} from a grid intersection. "
                    f"Checked grid spacing: {FormatLength(gridStep, viewport.unitsMode, decimals = 4)}.", cluster, target))
        for (first, firstIndex), (second, secondIndex) in combinations(cluster["endpoints"], 2):
            if first is second:
                continue
            firstFar = first.secondVertex if firstIndex == 0 else first.firstVertex
            secondFar = second.secondVertex if secondIndex == 0 else second.firstVertex
            firstDirection, secondDirection = firstFar - point, secondFar - point
            lengths = math.hypot(firstDirection.x(), firstDirection.y()) * math.hypot(secondDirection.x(), secondDirection.y())
            if lengths < 1e-8:
                continue
            angle = math.degrees(math.acos(max(-1, min(1, QtCore.QPointF.dotProduct(firstDirection, secondDirection) / lengths))))
            if not 1e-6 < abs(angle - 90) <= potentialAngleTolerance + 1e-9:
                continue
            moving, movingIndex, reference = second, 1 - secondIndex, first
            if len(clusters[membership[id(first), 1 - firstIndex]]["endpoints"]) < len(clusters[membership[id(second), 1 - secondIndex]]["endpoints"]):
                moving, movingIndex, reference = first, 1 - firstIndex, second
            movingCluster = clusters[membership[id(moving), movingIndex]]
            referenceDirection = firstDirection if reference is first else secondDirection
            normal = QtCore.QPointF(-referenceDirection.y(), referenceDirection.x()) / math.hypot(referenceDirection.x(), referenceDirection.y())
            target = point + normal * QtCore.QPointF.dotProduct(movingCluster["point"] - point, normal)
            if QtCore.QLineF(movingCluster["point"], target).length() > endpointTolerance:
                issues.append(PotentialWallIssue(viewport, moving, f"potential:right-angle:{id(reference)}:{movingIndex}",
                    "Almost right-angle join", f"Walls {first.objectId} and {second.objectId} meet at {angle:.4f}\u00b0, "
                    f"{abs(angle - 90):.4g}\u00b0 from a right angle. The shared junction will stay fixed.",
                    movingCluster, target, related = (reference,)))
        cell = math.floor(point.x() / potentialDistanceTolerance), math.floor(point.y() / potentialDistanceTolerance)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for otherIndex in gapBuckets.get((cell[0] + dx, cell[1] + dy), ()):
                    other = clusters[otherIndex]
                    if {id(obj) for obj, index in cluster["endpoints"]} & {id(obj) for obj, index in other["endpoints"]}:
                        continue
                    distance = QtCore.QLineF(point, other["point"]).length()
                    if not endpointTolerance < distance <= potentialDistanceTolerance:
                        continue
                    moving, fixed = (cluster, other) if len(cluster["endpoints"]) <= len(other["endpoints"]) else (other, cluster)
                    wall, index = moving["endpoints"][0]
                    targetWall, targetIndex = fixed["endpoints"][0]
                    issues.append(PotentialWallIssue(viewport, wall, f"potential:gap:{index}:{id(targetWall)}:{targetIndex}",
                        "Nearby endpoints are not connected", f"The endpoints are {FormatLength(distance, viewport.unitsMode, decimals = 4)} apart. "
                        "Repair will join them at the existing target endpoint.", moving, fixed["point"],
                        related = tuple(obj for obj, index in fixed["endpoints"])))
        gapBuckets.setdefault(cell, []).append(clusterIndex)
    return issues


@CollisionPass
def FindSceneProblems(viewport, includePotential = True, gridStep = None, includeIgnored = False):
    objects = viewport.walls + viewport.windows + viewport.furnishings + viewport.labels
    indices = {id(obj): index for index, obj in enumerate(objects)}
    for opening in viewport.windows:
        indices.setdefault(id(opening.parentWall), -1)
    records = [EncodeObjectRecord(obj, indices) for obj in objects]
    # Recovery's Highlight choice acknowledges an issue, but the checker must
    # still report it while its geometry remains invalid.
    for record in records:
        record.pop("geometryIssues", None)
    data = {"scene": {"objects": records}, "settings": {
        "wallWidth": viewport.newWallWidth, "collisionSettings": viewport.collisionSettings}}
    problems = []
    for index, obj in enumerate(objects):
        if type(obj) is Furnishing:
            assets = FurnishingAssetProblems(getattr(obj, "definitionKey", obj.definition["key"]),
                                             viewport.furnishingDefinitions, obj.definition)
            for key, kind in sorted(assets.items()):
                label = ("Missing definition: " if kind == "missing" else "Missing graphic: ") + key
                problems.append(dict(object = obj, code = "asset:" + key, label = label,
                    description = label + ". Restore the asset or delete the affected object. No automatic repair is available.",
                    repair = None))
        issue = FindGeometryIssue(index, data, viewport.furnishingDefinitions)
        if issue is not None:
            problems.append(dict(object = obj, code = issue["code"], label = "Invalid geometry",
                                 description = issue["description"], repair = issue["repair"],
                                 repairText = GeometryRepairText(records[index], issue["repair"]) if issue["repair"] is not None else ""))
            continue
        if isinstance(obj, Window):
            valid = viewport.OpeningFits(obj)
        elif isinstance(obj, Stair):
            valid = viewport.StairFits(obj)
        elif isinstance(obj, Counter):
            valid = viewport.CounterFits(obj)
        elif type(obj) is Wall or isinstance(obj, (Pillar, Elevator)):
            valid = viewport.WallFits(obj)
        elif isinstance(obj, Furnishing):
            valid = viewport.FurnishingFits(obj)
        else:
            valid = True
        if not valid:
            problems.append(dict(object = obj, code = "placement", label = "Invalid placement",
                description = "The object does not satisfy the current placement or collision rules. Move or resize it on the canvas, or delete it.",
                repair = None))
    # These warnings already have error highlights on the editing canvas.
    for label, code, affected in (("Wall contained in another wall", "contained", viewport.ContainedWalls()),
                                   ("Duplicate furnishing", "duplicate", viewport.DuplicateFurnishings(includeHidden = True))):
        for obj in affected:
            problems.append(dict(object = obj, code = code, label = label,
                                 description = label + ". Delete the redundant object if it is unintended.", repair = None))
    if includePotential:
        ignored = set(viewport.ignoredPotentialIssues) if not includeIgnored else set()
        problems.extend(issue for issue in FindPotentialWallIssues(viewport, viewport.GridSteps()[1] if gridStep is None else gridStep)
                        if issue["fingerprint"] not in ignored)
    return problems


def RepairPotentialIssue(viewport, issue):
    before = viewport.CaptureState()
    existing = FindSceneProblems(viewport, includePotential = False)
    changedIds = {id(obj) for obj, index, target in issue["repair"]}
    if any(id(problem["object"]) in changedIds or isinstance(problem["object"], Window)
           and id(problem["object"].parentWall) in changedIds for problem in existing):
        return False, "Resolve the existing problems on the affected walls and their attachments first."
    for obj, index, target in issue["repair"]:
        if index == 0:
            obj.firstVertex = QtCore.QPointF(target)
        else:
            obj.secondVertex = QtCore.QPointF(target)
    # Use the normal wall-edit fitting rules, but keep openings on unchanged
    # parents intact even when the scene already contains recovery problems.
    try:
        fitted = viewport.FitWallOpenings(before, validateFurnishings = False, validateScene = False)
        viewport.RestoreOpeningStates(tuple(state for state in before[3] if id(state[1]) not in changedIds))
        previousKeys = {(id(problem["object"]), problem["code"]) for problem in existing}
        current = FindSceneProblems(viewport, includePotential = False)
        introduced = any((id(problem["object"]), problem["code"]) not in previousKeys for problem in current)
        valid = fitted and not introduced
    except (ValueError, ZeroDivisionError, OverflowError):
        valid = False
    if not valid:
        for state in before[0]:
            if id(state[0]) in changedIds:
                state[0].firstVertex = QtCore.QPointF(state[1], state[2])
                state[0].secondVertex = QtCore.QPointF(state[3], state[4])
        viewport.RestoreOpeningStates(before[3])
        viewport.update()
        return False, "The proposed repair would invalidate geometry, openings or object placement. No changes were made."
    viewport.RecordEdit(before)
    viewport.selectionChanged.emit()
    viewport.update()
    return True, ""
