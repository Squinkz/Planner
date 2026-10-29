"""Read-only checks for current scene problems, shared with recovery validation."""
import hashlib
import json
import re
from PySide6 import QtCore
from .furnishing_assets import FurnishingAssetProblems
from .coincident_records import PlanCoincidentRemoval
from .geometry_recovery import FindGeometryIssue, GeometryRepairText
from .models import Furnishing, Window, Wall, Pillar, Column, Counter, Stair, Railing, Elevator
from .project_codec import EncodeObjectRecord
from .viewport.geometry import CollisionPass
from .geometry.wall_diagnostics import WallDiagnosticRecord, PlanPotentialWallRepairs


def FindPotentialWallIssues(viewport, gridStep):
    objects = {id(wall): wall for wall in viewport.walls if type(wall) is Wall}
    records = (WallDiagnosticRecord(key, wall.objectId, (wall.firstVertex.x(), wall.firstVertex.y()),
                                    (wall.secondVertex.x(), wall.secondVertex.y()), wall.width)
               for key, wall in objects.items())
    issues = PlanPotentialWallRepairs(records, gridStep, viewport.gridOrigin, viewport.unitsMode)
    for issue in issues:
        issue["object"] = objects[issue["object"]]
        issue["objects"] = tuple(objects[key] for key in issue["objects"])
        issue["repair"] = tuple((objects[key], index, QtCore.QPointF(*target)) for key, index, target in issue["repair"])
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
        if isinstance(obj, Window) or type(obj) in (Wall, Pillar, Column, Counter, Stair, Railing, Elevator):
            valid = viewport.ArchitecturalPlacementFits(obj)
        elif isinstance(obj, Furnishing):
            valid = viewport.FurnishingFits(obj)
        else:
            valid = True
        if not valid:
            problems.append(dict(object = obj, code = "placement", label = "Invalid placement",
                description = "The object does not satisfy the current placement or collision rules. Move or resize it on the canvas, or delete it.",
                repair = None))
    contained = viewport.ContainedWalls()
    containedIds = {id(obj) for obj in contained}
    groups = viewport.CoincidentObjectGroups(includeHidden = True)
    groupById = {id(obj): group for group in groups for obj in group[1:]}
    duplicates = [obj for group in groups for obj in group[1:]]
    duplicateIds = set(groupById)
    for obj in {id(obj): obj for obj in contained + duplicates}.values():
        name = re.sub(r"(?<!^)(?=[A-Z])", " ", type(obj).__name__).lower()
        name = {"measurement guide": "dimension guide", "north arrow": "north marker"}.get(name, name)
        label = "Duplicate furnishing" if type(obj) is Furnishing else f"Coincident {name}" if id(obj) in duplicateIds else f"{name.capitalize()} contained in another object"
        group = groupById.get(id(obj))
        code = "duplicate" if type(obj) is Furnishing else "contained" if id(obj) in containedIds else "duplicate_architectural"
        problems.append(dict(object = obj, code = code, label = label,
            description = label + ". Delete the redundant object if it is unintended.",
            repair = {"removeDuplicates": True} if group else None, repairKind = "duplicates" if group else None,
            repairText = f"Remove {len(group) - 1} extra copies and keep one existing copy. Unique wall attachments are preserved." if group else ""))
    if includePotential:
        ignored = set(viewport.ignoredPotentialIssues) if not includeIgnored else set()
        problems.extend(issue for issue in FindPotentialWallIssues(viewport, viewport.GridSteps()[1] if gridStep is None else gridStep)
                        if issue["fingerprint"] not in ignored)
        for obj in viewport.windows:
            if 1 <= obj.length <= 10.000001:
                signature = ["minimum-opening", obj.objectId, obj.parentWall.objectId, obj.centerFraction, obj.length]
                fingerprint = hashlib.sha256(json.dumps(signature).encode("utf-8")).hexdigest()
                if fingerprint not in ignored:
                    problems.append(dict(object = obj, code = "potential:minimum-opening", label = "Near-zero opening length",
                        description = f"This {type(obj).__name__} is only {obj.length:.6g} mm long. Resize or delete it if unintended.",
                        repair = None, potential = True, fingerprint = fingerprint))
    return problems


def RepairCoincidentObjects(viewport, issues):
    selected = {id(issue["object"]) for issue in issues}
    replacements = PlanCoincidentRemoval(viewport.CoincidentObjectGroups(includeHidden = True), viewport.IsObjectVisible, selectedIds = selected)
    if not replacements:
        return False
    before = viewport.CaptureState()
    parents = {id(keeper) for keeper in replacements.values() if type(keeper) is Wall}
    for opening in viewport.windows:
        if id(opening.parentWall) in replacements:
            opening.parentWall = replacements[id(opening.parentWall)]
    # Reparenting can make children of duplicate walls coincide too. Preserve
    # distinct openings and remove only exact child copies on the retained walls.
    childGroups = (group for group in viewport.CoincidentObjectGroups(includeHidden = True)
                   if isinstance(group[0], Window) and id(group[0].parentWall) in parents)
    replacements.update(PlanCoincidentRemoval(childGroups, viewport.IsObjectVisible))
    removed = set(replacements)
    viewport.walls = [obj for obj in viewport.walls if id(obj) not in removed]
    viewport.windows = [obj for obj in viewport.windows if id(obj) not in removed]
    viewport.furnishings = [obj for obj in viewport.furnishings if id(obj) not in removed]
    viewport.labels = [obj for obj in viewport.labels if id(obj) not in removed]
    viewport.SetSelection([], notify = False)
    viewport.RecordEdit(before)
    viewport.selectionChanged.emit()
    viewport.update()
    return True


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
