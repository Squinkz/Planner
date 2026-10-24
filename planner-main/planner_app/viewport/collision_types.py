"""Classify desktop models for the numeric collision policy."""
from functools import lru_cache
from planner_app.models import (NorthArrow, Window, Furnishing, Wall, Pillar, Column,
    Label, Arrow, MeasurementGuide, Railing, Elevator)
from planner_app.geometry.collisions import (northFlag, openingFlag, furnishingFlag, structuralFlag,
    annotationFlag, railingFlag, wallFlag, elevatorFlag)


@lru_cache(maxsize = 128)
def CollisionFlags(objectType):
    flags = 0
    for matches, flag in ((issubclass(objectType, NorthArrow), northFlag),
                          (issubclass(objectType, Window), openingFlag),
                          (issubclass(objectType, Furnishing), furnishingFlag),
                          (objectType in (Wall, Pillar, Column), structuralFlag),
                          (issubclass(objectType, (Label, Arrow, MeasurementGuide)), annotationFlag),
                          (issubclass(objectType, Railing), railingFlag),
                          (issubclass(objectType, Wall), wallFlag),
                          (issubclass(objectType, Elevator), elevatorFlag)):
        if matches:
            flags |= flag
    return flags
