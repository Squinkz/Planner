"""Map Qt-backed model classes onto the transport-independent record schema."""
from .models import Door, SwingingDoor, DoubleDoor, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway, Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, Fireplace
from .record_schema import openingFieldsByType, ReadArrowTipSize


openingClasses = {cls.__name__: cls for cls in (Door, SwingingDoor, DoubleDoor, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor,
                                               OpenDoorway, Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, Fireplace)}
openingFields = {openingClasses[name]: fields for name, fields in openingFieldsByType.items()}
