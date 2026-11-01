"""Map Qt-backed model classes onto the transport-independent record schema."""
from .models import Door, SwingingDoor, DoubleDoor, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway, Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, Fireplace
from .record_schema import openingFieldsByType, ReadArrowTipSize
from .models import (Furnishing, Label, RoomLabel, NorthArrow, AngleGuide, MeasurementGuide,
                     DashedLine, Arrow, Railing, Stair)


openingClasses = {cls.__name__: cls for cls in (Door, SwingingDoor, DoubleDoor, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor,
                                               OpenDoorway, Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, Fireplace)}
openingFields = {openingClasses[name]: fields for name, fields in openingFieldsByType.items()}


def EncodeObjectRecord(obj, indices, values = None):
    """Shared project/history record schema; snapshots supply saved field values."""
    record = {"type": type(obj).__name__, "id": obj.objectId, "measurementHidden": obj.measurementHidden}
    if hasattr(obj, "originalMaterial"):
        record["originalMaterial"] = obj.originalMaterial
    if getattr(obj, "geometryIssues", ()):
        record["geometryIssues"] = list(obj.geometryIssues)
    if values is not None:
        record.update(values)
        if isinstance(obj, Furnishing) and not isinstance(obj, (Label, NorthArrow)):
            record["definition"] = getattr(obj, "definitionKey", obj.definition["key"])
        if isinstance(obj, Arrow):
            record["tipSizeMode"] = "millimeters"
        return record
    if isinstance(obj, Window):
        record.update(parent = indices[id(obj.parentWall)], center = obj.centerFraction, length = obj.length)
        for name in openingFields[type(obj)]:
            if hasattr(obj, name):
                record[name] = getattr(obj, name)
        if isinstance(obj, Fireplace) and (obj.manualDepth != obj.depth or obj.manualDepthOffset != obj.depthOffset):
            record.update(manualDepth = obj.manualDepth, manualDepthOffset = obj.manualDepthOffset)
    else:
        record.update(first = [obj.firstVertex.x(), obj.firstVertex.y()],
                      second = [obj.secondVertex.x(), obj.secondVertex.y()], width = obj.width)
        if isinstance(obj, Label):
            record["text"] = obj.text
            record["intensity"] = obj.intensity
            if isinstance(obj, RoomLabel) and obj.unitsOverride is not None:
                record["unitsOverride"] = obj.unitsOverride
        elif isinstance(obj, NorthArrow):
            record["intensity"] = obj.intensity
        elif isinstance(obj, Furnishing):
            record["definition"] = getattr(obj, "definitionKey", obj.definition["key"])
            record["behindCounters"] = obj.behindCounters
            record["flipHorizontal"] = obj.flipHorizontal
            record["flipVertical"] = obj.flipVertical
        else:
            record.update(material = obj.material, firstMiter = obj.firstMiter, secondMiter = obj.secondMiter)
            if isinstance(obj, AngleGuide):
                record.update(middle = [obj.middleVertex.x(), obj.middleVertex.y()])
            if isinstance(obj, MeasurementGuide):
                record["textOffset"] = [obj.textOffset.x(), obj.textOffset.y()]
            if type(obj) is MeasurementGuide and obj.depth != 0:
                record["depth"] = obj.depth
            if isinstance(obj, DashedLine):
                record["weightClass"] = obj.weightClass
            if isinstance(obj, Arrow):
                record.update(solidTip = obj.solidTip, tipSize = obj.tipSize, intensity = obj.intensity, tipSizeMode = "millimeters")
                if obj.directionReversed:
                    record["directionReversed"] = True
            if isinstance(obj, Railing):
                record.update(autosize = obj.autosize, manualPostCount = obj.manualPostCount)
            if isinstance(obj, Stair):
                record["directionReversed"] = obj.directionReversed
                record.update(autosize = obj.autosize, manualStepCount = obj.manualStepCount)
    return record

