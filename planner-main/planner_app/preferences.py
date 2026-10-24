"""Default project preferences; Build dimensions are expressed in centimeters."""
wallPresetWidths = (10, 15, 20, 30)
wallPresetNames = ("Thin Wall", "Interior Wall", "Thick Interior Wall", "Exterior Wall")
openingDefaultSizes = {"Door": 90, "SlidingDoor": 90, "PocketDoor": 90, "BarnDoor": 90, "BifoldDoor": 120, "OpenDoorway": 90,
                       "Window": 120, "SilledWindow": 120, "CasementWindow": 60}
miscDefaultSizes = {"Stair": 100, "Counter": 60, "Railing": 8, "Pillar": 30, "Column": 30, "Fireplace": 120, "Elevator": 120}
measurementDefaults = {"doors": 1, "windows": 1, "stairs": 2, "counters": 2}  # 0: both sides, 1: facing side, 2: no cuts.
measurementVisibilityDefaults = {"walls": True, "stairs": False, "counters": False, "railings": False, "elevators": False}
collisionDefaults = {"walls": True, "architectural": True, "furnishings": True}
railingSpacingDefaults = {"minimum": 90, "maximum": 150, "target": 120}
stairStepSizeDefaults = {"minimum": 25, "maximum": 30}
lineworkDefaults = {"baseWidth": 4.0, "walls": 1.0, "architectural": .5, "furnishings": .25, "dimensions": .25}
