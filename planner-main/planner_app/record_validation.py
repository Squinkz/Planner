"""Transport value validation independent of scene models and Qt."""
import math


projectFileLimit = 64 * 1024 * 1024


def ValidateNumber(value, minimum = -1e12, maximum = 1e12):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError("The project contains an invalid numeric value.")
    return float(value)


def ValidateCoordinates(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("The project contains an invalid position.")
    return ValidateNumber(value[0]), ValidateNumber(value[1])


def ValidateFlags(values, names):
    if not isinstance(values, dict) or any(type(values.get(name)) is not bool for name in names):
        raise ValueError("The project contains invalid option settings.")
    return {name: values[name] for name in names}




def Finite(value, minimum = -1e12, maximum = 1e12):
    return type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum
