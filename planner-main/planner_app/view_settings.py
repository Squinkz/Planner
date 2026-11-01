"""Shared project/export view mapping without widgets, themes, or rendering.

Values returned by capture belong to the caller. Applying them never borrows
mutable option groups from a project snapshot or export overrides.
"""
from .export_settings import measurementDefaultTextSize

viewScalarFields = ("showGrid", "solidRooms", "showMeasurements", "wallMeasurementMode",
                    "wallMeasurementReference", "unitsMode", "measurementPrecision")
viewMappingFields = {"viewportSettings": "gridIntensities", "lineworkSettings": "lineworkSettings",
                     "measurementVisibility": "measurementVisibility", "measurementSettings": "measurementSettings",
                     "visibility": "visibility"}
viewSettingNames = (*viewScalarFields, *viewMappingFields, "roomStyle")


def CaptureViewportView(viewport, canvasTheme = None):
    view = {name: getattr(viewport, name) for name in viewScalarFields}
    view.update((name, dict(getattr(viewport, attribute))) for name, attribute in viewMappingFields.items())
    view["roomStyle"] = "Tinted" if viewport.floors else "Canvas"
    if canvasTheme is not None:
        view["canvasTheme"] = canvasTheme
    return view


def ApplyViewportView(viewport, view):
    # This size belongs only to Export; restoring the editor clears it.
    viewport.measurementTextSize = view.get("measurementTextSize", 0)
    viewport.borderTextSize = view.get("borderTextSize", measurementDefaultTextSize)
    viewport.drawOpeningOutlines = view.get("drawOpeningOutlines", True)
    for name in viewScalarFields:
        if name in view:
            setattr(viewport, name, view[name])
    for name, attribute in viewMappingFields.items():
        if name in view:
            setattr(viewport, attribute, dict(view[name]))
    if "roomStyle" in view:
        viewport.floors = view["roomStyle"] == "Tinted"
