"""Rectangle adapter for the Qt-independent ordered spatial index."""
from planner_app.geometry.spatial_index import BoundsIndex as CoordinateBoundsIndex


class BoundsIndex(CoordinateBoundsIndex):
    def Insert(self, bounds, value):
        super().Insert((bounds.left(), bounds.top(), bounds.right(), bounds.bottom()), value)

    def Query(self, bounds):
        return super().Query((bounds.left(), bounds.top(), bounds.right(), bounds.bottom()))
