"""Translate desktop opening classes into numeric facing policies."""
from functools import lru_cache
from planner_app.models import (Door, SwingingDoor, SlidingDoor, PocketDoor,
    CasementWindow, Window, SilledWindow, AwningWindow, DoubleCasementWindow,
    DoubleDoor, BarnDoor, BifoldDoor)


@lru_cache(maxsize = 128)
def OpeningFacingPolicy(objectType):
    sliding = issubclass(objectType, SlidingDoor)
    hingeSign = -1 if sliding else 1 if issubclass(objectType,
        (Door, SwingingDoor, PocketDoor, CasementWindow)) else 0
    if sliding:
        return hingeSign, "panelsFlipped", -1
    # Window facing deliberately applies to exact built-in types. Door facing
    # also applies to subclasses, matching the model behavior before extraction.
    if objectType in (Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow):
        return hingeSign, "swingsOutwards", 1
    if issubclass(objectType, (Door, DoubleDoor, BarnDoor, BifoldDoor)):
        return hingeSign, "swingsOutwards", -1
    return hingeSign, None, 0
