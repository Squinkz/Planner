"""Conservative wall diagnostics and endpoint repair proposals without Qt."""
from dataclasses import dataclass
import hashlib
from itertools import combinations
import json
import math
from planner_app.measurement_units import FormatLength


potentialAngleTolerance = .5
potentialDistanceTolerance = 5.0
endpointTolerance = .01
# Connectivity is tighter than the minimum useful diagnostic correction. Keep
# harmless sub-tenth-millimeter drift from flooding the potential-issues list.
potentialCorrectionTolerance = .1
endpointComparisonSlack = 1e-9


@dataclass(frozen = True, slots = True)
class WallDiagnosticRecord:
    key: int
    objectId: int | None
    first: tuple
    second: tuple
    width: float


def PotentialWallRepair(wall, code, label, description, cluster, target, records, unitsMode, related = ()):
    # Persisted fingerprints use floats even when numeric inputs are integers.
    target = (float(target[0]), float(target[1]))
    changes = tuple((key, index, target) for key, index in cluster["endpoints"])
    objects = dict.fromkeys((wall.key, *related, *(entry[0] for entry in changes)))
    source = cluster["point"]
    coordinates = [FormatLength(value, unitsMode, decimals = 4, preserveDecimals = True) for value in (*source, *target)]
    repairText = f"Repair will move the endpoint from ({coordinates[0]}, {coordinates[1]}) to ({coordinates[2]}, {coordinates[3]})."
    if len(changes) > 1:
        repairText += f"\nAll {len(changes)} endpoints at this junction will move together."
    signature = dict(kind = code.split(":")[1], primary = wall.objectId or 0,
        objects = sorted((records[key].objectId or 0, *(float(value) for value in (*records[key].first, *records[key].second)),
                          float(records[key].width)) for key in objects),
        changes = sorted((records[key].objectId or 0, index, *target) for key, index, target in changes))
    fingerprint = hashlib.sha256(json.dumps(signature, sort_keys = True, separators = (",", ":")).encode("utf-8")).hexdigest()
    return dict(object = wall.key, objects = tuple(objects), code = code, label = label, description = description,
                repair = changes, repairText = repairText, potential = True, fingerprint = fingerprint)


def PlanPotentialWallRepairs(walls, gridStep, gridOrigin, unitsMode):
    walls = [wall for wall in walls if all(math.isfinite(value) for point in (wall.first, wall.second) for value in point)
             and math.hypot(wall.second[0] - wall.first[0], wall.second[1] - wall.first[1]) >= 1]
    records = {wall.key: wall for wall in walls}
    clusters, buckets, membership = [], {}, {}
    for wall in walls:
        for index, vertex in enumerate((wall.first, wall.second)):
            cell = math.floor(vertex[0] / endpointTolerance), math.floor(vertex[1] / endpointTolerance)
            candidates = sorted({candidate for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                                 for candidate in buckets.get((cell[0] + dx, cell[1] + dy), ())})
            clusterIndex = next((candidate for candidate in candidates
                                 if math.hypot(vertex[0] - clusters[candidate]["point"][0], vertex[1] - clusters[candidate]["point"][1]) <= endpointTolerance + endpointComparisonSlack), None)
            if clusterIndex is None:
                clusterIndex = len(clusters)
                clusters.append(dict(point = vertex, endpoints = []))
                buckets.setdefault(cell, []).append(clusterIndex)
            clusters[clusterIndex]["endpoints"].append((wall.key, index))
            membership[wall.key, index] = clusterIndex
    issues = []
    for wall in walls:
        directionX, directionY = wall.second[0] - wall.first[0], wall.second[1] - wall.first[1]
        angle = math.degrees(math.atan2(directionY, directionX))
        deviation = abs((angle + 45) % 90 - 45)
        if 1e-6 < deviation <= potentialAngleTolerance + 1e-9:
            index = min((1, 0), key = lambda index: len(clusters[membership[wall.key, index]]["endpoints"]))
            cluster = clusters[membership[wall.key, index]]
            vertex, opposite = (wall.first, wall.second) if index == 0 else (wall.second, wall.first)
            target = (vertex[0], opposite[1]) if abs(directionX) >= abs(directionY) else (opposite[0], vertex[1])
            if math.hypot(vertex[0] - target[0], vertex[1] - target[1]) > potentialCorrectionTolerance + endpointComparisonSlack:
                issues.append(PotentialWallRepair(wall, "potential:axis", "Wall almost aligned to an axis",
                    f"The wall is {deviation:.4g}\u00b0 from {'horizontal' if abs(directionX) >= abs(directionY) else 'vertical'}.",
                    cluster, target, records, unitsMode))
    gapBuckets = {}
    for clusterIndex, cluster in enumerate(clusters):
        point = cluster["point"]
        if math.isfinite(gridStep) and gridStep > 0:
            originX, originY = gridOrigin
            target = (originX + round((point[0] - originX) / gridStep) * gridStep,
                      originY + round((point[1] - originY) / gridStep) * gridStep)
            distance = math.hypot(point[0] - target[0], point[1] - target[1])
            if potentialCorrectionTolerance + endpointComparisonSlack < distance <= min(potentialDistanceTolerance, gridStep * .05):
                key, index = cluster["endpoints"][0]
                issues.append(PotentialWallRepair(records[key], f"potential:grid:{index}", "Endpoint just off grid",
                    f"The endpoint is {FormatLength(distance, unitsMode, decimals = 4, preserveDecimals = True)} from a grid intersection. "
                    f"Checked grid spacing: {FormatLength(gridStep, unitsMode, decimals = 4, preserveDecimals = True)}.", cluster, target, records, unitsMode))
        for (firstKey, firstIndex), (secondKey, secondIndex) in combinations(cluster["endpoints"], 2):
            if firstKey == secondKey:
                continue
            first, second = records[firstKey], records[secondKey]
            firstFar = first.second if firstIndex == 0 else first.first
            secondFar = second.second if secondIndex == 0 else second.first
            firstNear = first.first if firstIndex == 0 else first.second
            secondNear = second.first if secondIndex == 0 else second.second
            # Clustered endpoints can differ slightly. Measuring both rays from
            # the cluster representative tilts an otherwise perpendicular wall,
            # and amplifies that error when its neighbour is much longer.
            firstDirection = (firstFar[0] - firstNear[0], firstFar[1] - firstNear[1])
            secondDirection = (secondFar[0] - secondNear[0], secondFar[1] - secondNear[1])
            lengths = math.hypot(*firstDirection) * math.hypot(*secondDirection)
            if lengths < 1e-8:
                continue
            angle = math.degrees(math.acos(max(-1, min(1, (firstDirection[0] * secondDirection[0] + firstDirection[1] * secondDirection[1]) / lengths))))
            if not 1e-6 < abs(angle - 90) <= potentialAngleTolerance + 1e-9:
                continue
            moving, movingIndex, reference = second, 1 - secondIndex, first
            if len(clusters[membership[first.key, 1 - firstIndex]]["endpoints"]) < len(clusters[membership[second.key, 1 - secondIndex]]["endpoints"]):
                moving, movingIndex, reference = first, 1 - firstIndex, second
            movingCluster = clusters[membership[moving.key, movingIndex]]
            referenceDirection = firstDirection if reference is first else secondDirection
            referenceLength = math.hypot(*referenceDirection)
            # Reciprocal multiplication changes rounding and saved fingerprints.
            normal = (-referenceDirection[1] / referenceLength, referenceDirection[0] / referenceLength)
            movingNear = firstNear if moving is first else secondNear
            offset = (movingCluster["point"][0] - movingNear[0], movingCluster["point"][1] - movingNear[1])
            projection = offset[0] * normal[0] + offset[1] * normal[1]
            target = (movingNear[0] + normal[0] * projection, movingNear[1] + normal[1] * projection)
            if math.hypot(movingCluster["point"][0] - target[0], movingCluster["point"][1] - target[1]) > potentialCorrectionTolerance + endpointComparisonSlack:
                issues.append(PotentialWallRepair(moving, f"potential:right-angle:{reference.key}:{movingIndex}",
                    "Almost right-angle join", f"Walls {first.objectId} and {second.objectId} meet at {angle:.4f}\u00b0, "
                    f"{abs(angle - 90):.4g}\u00b0 from a right angle. The shared junction will stay fixed.",
                    movingCluster, target, records, unitsMode, related = (reference.key,)))
        cell = math.floor(point[0] / potentialDistanceTolerance), math.floor(point[1] / potentialDistanceTolerance)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for otherIndex in gapBuckets.get((cell[0] + dx, cell[1] + dy), ()):
                    other = clusters[otherIndex]
                    if {key for key, index in cluster["endpoints"]} & {key for key, index in other["endpoints"]}:
                        continue
                    distance = math.hypot(point[0] - other["point"][0], point[1] - other["point"][1])
                    if not potentialCorrectionTolerance + endpointComparisonSlack < distance <= potentialDistanceTolerance:
                        continue
                    moving, fixed = (cluster, other) if len(cluster["endpoints"]) <= len(other["endpoints"]) else (other, cluster)
                    key, index = moving["endpoints"][0]
                    targetKey, targetIndex = fixed["endpoints"][0]
                    issues.append(PotentialWallRepair(records[key], f"potential:gap:{index}:{targetKey}:{targetIndex}",
                        "Nearby endpoints are not connected", f"The endpoints are {FormatLength(distance, unitsMode, decimals = 4, preserveDecimals = True)} apart. "
                        "Repair will join them at the existing target endpoint.", moving, fixed["point"], records, unitsMode,
                        related = tuple(key for key, index in fixed["endpoints"])))
        gapBuckets.setdefault(cell, []).append(clusterIndex)
    return issues
