"""Numeric wall junctions, ownership sectors and translating chamfer planes."""
import math
from .polygons import ClipHalfPlane


def BuildWallJunction(joint, rays, jointMiters, weldOverlap):
    """Build a junction in caller coordinates using opaque owner keys.

    Rays contain ((directionX, directionY), halfWidth, ownerKey). Directions
    are already normalized. Ray order is sorted in place, as in the adapter's
    original implementation. Outputs preserve polygon and ownership order.
    Return polygons, owner patches, transitions, owner sectors and footprint planes.
    A plane is (point, outward unit normal); retain dot(position-point, normal)
    <= 0. Historical jointMiters values now mean chamfer amounts: zero is sharp.
    """
    polygons, materialJoins, materialTransitions = [], [], []
    materialCuts = {owner: [] for direction, width, owner in rays}
    footprintCuts = {owner: [] for direction, width, owner in rays}
    chamfer = min(1.0, max(0.0, max(jointMiters, default = 0.0)))
    jointX, jointY = joint
    rays.sort(key = lambda ray: math.atan2(ray[0][1], ray[0][0]))
    for rayIndex, (firstDirection, firstHalfWidth, firstOwner) in enumerate(rays):
        secondDirection, secondHalfWidth, secondOwner = rays[(rayIndex + 1) % len(rays)]
        firstX, firstY = firstDirection
        secondX, secondY = secondDirection
        cross = firstX * secondY - firstY * secondX
        if abs(cross) < 1e-6:
            dot = firstX * secondX + firstY * secondY
            if dot < 0:
                # Weld opposing caps with the same subpixel overlap as before.
                halfWidth = min(firstHalfWidth, secondHalfWidth)
                normalX, normalY = -firstY * halfWidth, firstX * halfWidth
                overlapX, overlapY = firstX * weldOverlap, firstY * weldOverlap
                polygons.append([(jointX + normalX + overlapX, jointY + normalY + overlapY),
                                 (jointX - normalX + overlapX, jointY - normalY + overlapY),
                                 (jointX - normalX - overlapX, jointY - normalY - overlapY),
                                 (jointX + normalX - overlapX, jointY + normalY - overlapY)])
                materialJoins.append((firstOwner, [(jointX + normalX, jointY + normalY),
                    (jointX - normalX, jointY - normalY), (jointX - normalX + overlapX, jointY - normalY + overlapY),
                    (jointX + normalX + overlapX, jointY + normalY + overlapY)]))
                materialJoins.append((secondOwner, [(jointX + normalX, jointY + normalY),
                    (jointX - normalX, jointY - normalY), (jointX - normalX - overlapX, jointY - normalY - overlapY),
                    (jointX + normalX - overlapX, jointY + normalY - overlapY)]))
                if len(rays) > 2 and abs(firstHalfWidth - secondHalfWidth) > 1e-6:
                    # An unequal-width T transitions at the branch face.
                    thinX, thinY = firstDirection if firstHalfWidth < secondHalfWidth else secondDirection
                    branches = [(direction, halfWidth) for direction, halfWidth, owner in rays
                                if abs(thinX * direction[1] - thinY * direction[0]) > 1e-6]
                    (branchX, branchY), branchHalfWidth = max(branches,
                        key = lambda ray: thinX * ray[0][0] + thinY * ray[0][1])
                    branchNormalX, branchNormalY = -branchY, branchX
                    if branchNormalX * thinX + branchNormalY * thinY < 0:
                        branchNormalX, branchNormalY = -branchNormalX, -branchNormalY
                    wideWidth, thinWidth = max(firstHalfWidth, secondHalfWidth), min(firstHalfWidth, secondHalfWidth)
                    wideOffset = (jointX + -firstY * wideWidth, jointY + firstX * wideWidth)
                    thinOffset = (jointX + -firstY * thinWidth, jointY + firstX * thinWidth)
                    deltaX = jointX + branchNormalX * branchHalfWidth - wideOffset[0]
                    deltaY = jointY + branchNormalY * branchHalfWidth - wideOffset[1]
                    denominator = thinX * branchY - thinY * branchX
                    extension = (deltaX * branchY - deltaY * branchX) / denominator
                    extension = max(0.0, extension) * (1.0 - chamfer)
                    if extension > 1e-6:
                        polygons.append([wideOffset, (wideOffset[0] + thinX * extension, wideOffset[1] + thinY * extension),
                            (thinOffset[0] + thinX * extension, thinOffset[1] + thinY * extension), thinOffset])
                        materialTransitions.append((firstOwner if firstHalfWidth > secondHalfWidth else secondOwner, polygons[-1]))
            continue
        firstOffset = (jointX + -firstY * firstHalfWidth, jointY + firstX * firstHalfWidth)
        secondOffset = (jointX - -secondY * secondHalfWidth, jointY - secondX * secondHalfWidth)
        deltaX, deltaY = secondOffset[0] - firstOffset[0], secondOffset[1] - firstOffset[1]
        distance = (deltaX * secondY - deltaY * secondX) / cross
        intersection = (firstOffset[0] + firstX * distance, firstOffset[1] + firstY * distance)
        bevel = ((firstOffset[0] + secondOffset[0]) / 2, (firstOffset[1] + secondOffset[1]) / 2)
        # Unequal, nearly straight faces can intersect far down the wall.
        # Keep their transition local rather than stretching the material seam.
        localTransition = (firstX * secondX + firstY * secondY < 0
                           and abs(firstHalfWidth - secondHalfWidth) > 1e-6
                           and math.hypot(intersection[0] - jointX, intersection[1] - jointY) > 4 * max(firstHalfWidth, secondHalfWidth))
        if localTransition:
            intersection = bevel
        # Retain the uncut seam and its rounding on the common zero-chamfer path.
        miterPoint = (bevel[0] + (intersection[0] - bevel[0]),
                      bevel[1] + (intersection[1] - bevel[1]))
        points = [joint, firstOffset, miterPoint, secondOffset]
        plane = None
        if chamfer > 0 and cross < 0 and not localTransition:
            # Only the exterior sector has an exposed convex tip. The negative
            # ray sum points out of that corner, independent of the wall widths.
            normalX, normalY = -firstX - secondX, -firstY - secondY
            normalLength = math.hypot(normalX, normalY)
            normal = (normalX / normalLength, normalY / normalLength)
            # At one, pass through the old bevel midpoint. Unequal widths need
            # actual edge/plane intersections and may also trim a wall body.
            cutPoint = (miterPoint[0] + (bevel[0] - miterPoint[0]) * chamfer,
                        miterPoint[1] + (bevel[1] - miterPoint[1]) * chamfer)
            plane = (cutPoint, normal)
            points = ClipHalfPlane(points, *plane)
            footprintCuts[firstOwner].append(plane)
            footprintCuts[secondOwner].append(plane)
        polygons.append(points)
        if localTransition:
            materialJoins.extend(((firstOwner, points), (secondOwner, points)))
        else:
            firstJoin, secondJoin = [joint, firstOffset, miterPoint], [joint, miterPoint, secondOffset]
            if plane is not None:
                firstJoin, secondJoin = ClipHalfPlane(firstJoin, *plane), ClipHalfPlane(secondJoin, *plane)
            materialJoins.extend(((firstOwner, firstJoin), (secondOwner, secondJoin)))
        boundary = (miterPoint[0] - jointX, miterPoint[1] - jointY)
        if localTransition:
            # Keep the wider body intact up to its endpoint cap.
            wideX, wideY = firstDirection if firstHalfWidth > secondHalfWidth else secondDirection
            boundary = (-wideY, wideX)
        for owner, direction in ((firstOwner, firstDirection), (secondOwner, secondDirection)):
            side = boundary[0] * direction[1] - boundary[1] * direction[0]
            if abs(side) > 1e-10:
                materialCuts[owner].append((joint, boundary, 1 if side > 0 else -1))
                if (len(rays) == 2 and cross < 0 and not localTransition
                        and abs(firstHalfWidth - secondHalfWidth) > 1e-6):
                    # Unequal widths can put a rectangular cap beyond the other
                    # wall's edge. This is a real footprint trim, not just a
                    # material seam: retain the side containing the owner's ray.
                    sign = 1 if side > 0 else -1
                    length = math.hypot(*boundary)
                    normal = (boundary[1] * sign / length, -boundary[0] * sign / length)
                    footprintCuts[owner].insert(0, (joint, normal))
    return polygons, materialJoins, materialTransitions, materialCuts, footprintCuts
