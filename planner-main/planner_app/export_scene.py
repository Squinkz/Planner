"""Remove editor-only warning objects from an independent export viewport."""
from .models import Furnishing, Wall, Pillar, Column
from .furnishing_assets import FurnishingAssetProblems
from .geometry_recovery import ActiveGeometryIssues


def PrepareExportScene(viewport):
    visibleWalls = [obj for obj in viewport.walls if type(obj) in (Wall, Pillar, Column) and viewport.IsObjectVisible(obj)]
    excluded = {id(obj) for obj in viewport.ContainedWalls(visibleWalls) + viewport.DuplicateFurnishings()}
    for obj in viewport.furnishings:
        if type(obj) is not Furnishing or not viewport.IsObjectVisible(obj):
            continue
        key = getattr(obj, "definitionKey", obj.definition["key"])
        problems = FurnishingAssetProblems(key, viewport.furnishingDefinitions, obj.definition)
        if obj.definition["key"] == "null" or key in problems or not viewport.FurnishingFits(obj):
            excluded.add(id(obj))
    excluded.update(id(obj) for obj in viewport.windows
                    if id(obj.parentWall) in excluded or getattr(obj, "geometryIssues", ()) and ActiveGeometryIssues(obj, viewport))
    viewport.walls = [obj for obj in viewport.walls if id(obj) not in excluded]
    viewport.windows = [obj for obj in viewport.windows if id(obj) not in excluded]
    viewport.furnishings = [obj for obj in viewport.furnishings if id(obj) not in excluded]
    viewport.furnishingRenderers = viewport.furnishingRenderers.Copy(excludeErrors = True)
