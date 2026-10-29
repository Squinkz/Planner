"""Adapt portable furnishing catalog resolution to native compound artwork."""
from planner_app.paths import furnishingsDirectory as furnishingsFolder
from planner_app.paths import bundledFurnishingsDirectory
from pathlib import Path
from planner_app.graphics.furnishings import CompoundFurnishingSvg
from .catalog_metadata import FurnishingCategories
from .catalog_records import ReadFurnishingCatalog


def LoadFurnishings(folder = furnishingsFolder, definitionOverrides = None, builtInFolder = None):
    from .project_codec import DecodeFurnishingDefinitions
    if builtInFolder is None:
        builtInFolder = bundledFurnishingsDirectory if Path(folder) == furnishingsFolder else folder
    return ReadFurnishingCatalog(folder, CompoundFurnishingSvg, DecodeFurnishingDefinitions,
                                 definitionOverrides = definitionOverrides, builtInFolder = builtInFolder)
