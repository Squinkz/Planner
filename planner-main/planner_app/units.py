"""Display-only unit conversions; scene geometry remains in millimeters."""
import math
import re
from .models import Furnishing, Stair, Label

imperialModes = ("Feet and Inches", "Inches")
unitModes = ("Adaptive Metric", "Meters", "Centimeters", "Millimeters") + imperialModes
measurementPrecisions = {"High": 1, "Medium": 5, "Low": 20}


def MetricUnit(mode, adaptive = "m"):
    if mode in imperialModes:
        return (304.8, "ft") if mode == "Feet and Inches" else (25.4, "in")
    unit = {"Meters": "m", "Centimeters": "cm", "Millimeters": "mm"}.get(mode, adaptive)
    return {"m": 1000.0, "cm": 10.0, "mm": 1.0}[unit], unit


def PropertyUnit(fieldName, obj, mode):
    adaptive = "cm" if fieldName in ("sillDepth", "stepSize") or fieldName == "width" and not isinstance(obj, Stair) or fieldName == "length" and isinstance(obj, Furnishing) else "m"
    return MetricUnit(mode, adaptive)


def GridUnit(majorStep, mode):
    if majorStep >= 100.0:
        adaptive = "m"
    elif majorStep >= 10.0:
        adaptive = "cm"
    else:
        adaptive = "mm"
    return MetricUnit(mode, adaptive)


def FormatLength(millimeters, mode, adaptive = "m", decimals = 3, includeUnit = True, snapToInteger = False, precision = None):
    if mode in imperialModes:
        decimals = min(decimals, 3)
        inches = abs(millimeters) / 25.4
        sign = "-" if millimeters < 0 else ""
        if precision is not None:
            denominator = {"High": 16, "Medium": 4, "Low": 1}[precision]
            ticks = math.floor(inches * denominator + .5 + 1e-9)
            feet, ticks = divmod(ticks, 12 * denominator) if mode == "Feet and Inches" else (0, ticks)
            whole, numerator = divmod(ticks, denominator)
            if numerator:
                divisor = math.gcd(numerator, denominator)
                fraction = f"{numerator // divisor}/{denominator // divisor}"
                text = f"{whole} {fraction}" if whole else fraction
            else:
                text = str(whole)
        else:
            inches = round(inches, decimals)
            feet = math.floor(inches / 12) if mode == "Feet and Inches" else 0
            remainder = round(inches - feet * 12, decimals)
            text = f"{remainder:.{decimals}f}".rstrip("0").rstrip(".") if decimals else str(round(remainder))
        if text == "0" and feet == 0:
            sign = ""
        # Mixed imperial values always need marks to distinguish the two components.
        return f"{sign}{feet}' {text}\"" if feet else f"{sign}{text}\""
    if precision is not None:
        step = measurementPrecisions[precision]
        millimeters = math.copysign(math.floor(abs(millimeters) / step + .5 + 1e-9) * step, millimeters)
    divisor, unit = MetricUnit(mode, adaptive)
    if mode == "Millimeters":
        decimals = 0
    value = round(millimeters / divisor, decimals) or 0.0
    # Clean up near-integer annotations without changing scene geometry or
    # the precision used by editable property fields.
    if snapToInteger and abs(value - round(value)) <= .001 + 1e-9:
        value = round(value)
    text = f"{value:.{decimals}f}".rstrip("0").rstrip(".") if decimals else str(round(value))
    return f"{text} {unit}" if includeUnit else text


def ParseImperialLength(text, mode):
    """Return millimeters; bare values mean decimal feet or inches for that mode."""
    text = text.strip().lower().replace("′", "'").replace("″", '"')
    number = r"(?:\d+(?:\.\d*)?|\.\d+)"
    match = re.fullmatch(r"([+-]?)\s*(?:((?:" + number + r"))\s*(?:'|ft|feet)\s*)?(?:((?:" + number + r"))\s*(?:\"|in|inch|inches))?", text)
    if match and (match[2] is not None or match[3] is not None):
        value = float(match[2] or 0) * 304.8 + float(match[3] or 0) * 25.4
        if not math.isfinite(value):
            raise ValueError("Length must be finite.")
        return -value if match[1] == "-" else value
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("Length must be finite.")
    return value * (304.8 if mode == "Feet and Inches" else 25.4)
