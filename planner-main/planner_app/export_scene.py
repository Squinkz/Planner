"""Remove editor-only warning objects from an independent export viewport."""
from .models import Furnishing, Wall, Pillar, Column, Counter, Elevator
from .furnishing_assets import FurnishingAssetProblems
from .geometry_recovery import ActiveGeometryIssues


def PrepareExportScene(viewport):
    viewport.exportRender = True
    visibleWalls = [obj for obj in viewport.walls if type(obj) in (Wall, Pillar, Column, Counter, Elevator) and viewport.IsObjectVisible(obj)]
    excluded = {id(obj) for obj in viewport.ContainedWalls(visibleWalls) + viewport.DuplicateFurnishings() + viewport.DuplicateArchitecturalObjects()}
    for obj in viewport.furnishings:
        if type(obj) is not Furnishing or not viewport.IsObjectVisible(obj):
            continue
        key = getattr(obj, "definitionKey", obj.definition["key"])
        problems = FurnishingAssetProblems(key, viewport.furnishingDefinitions, obj.definition)
        if obj.definition["key"] == "null" or key in problems or not viewport.FurnishingFits(obj):
            excluded.add(id(obj))
    viewport.windows = [obj for obj in viewport.windows if id(obj) not in excluded and id(obj.parentWall) not in excluded]
    excluded.update(id(obj) for obj in viewport.windows
                    if getattr(obj, "geometryIssues", ()) and ActiveGeometryIssues(obj, viewport))
    viewport.walls = [obj for obj in viewport.walls if id(obj) not in excluded]
    viewport.windows = [obj for obj in viewport.windows if id(obj) not in excluded]
    viewport.furnishings = [obj for obj in viewport.furnishings if id(obj) not in excluded]
    viewport.furnishingRenderers = viewport.furnishingRenderers.Copy(excludeErrors = True)
