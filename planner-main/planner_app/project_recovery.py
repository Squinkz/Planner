"""Repair project metadata without changing, dropping or repositioning scene geometry."""
import copy
from collections import Counter
from pathlib import Path
from PySide6 import QtSvg
from .project_codec import DecodeProject, ValidateEditorUi, ValidateNumber, ValidatePoint, ValidateProjectSettings
from .graphics.theme import wallMaterials
from .graphics.palette import themeDefinitions
from .catalog_metadata import FurnishingCategories
from .reference_image import ValidateReferenceImage
from .furnishing_assets import FurnishingAssetProblems
from .models import Furnishing
from .recovery_records import RepairRecoverySettings, RepairRecoveryScene, RepairRecoveryDefinitions


def RecoverProject(data, definitions, defaults, chooseGeometry = None):
    if (not isinstance(data, dict) or data.get("format") != "Planner Project"
            or type(data.get("version")) is not int or data["version"] != 1
            or not isinstance(data.get("scene"), dict)):
        return DecodeProject(data, definitions), []
    repaired = copy.deepcopy(data)
    notices = []
    if "activityLog" in repaired:
        from .activity_records import DecodeActivityLog
        try:
            DecodeActivityLog(repaired["activityLog"])
        except ValueError:
            repaired.pop("activityLog")
            notices.append("Removed invalid activity log.")
    probe = {"format": "Planner Project", "version": 1,
             "scene": {"objects": [], "groups": [], "hidden": []}, "settings": copy.deepcopy(defaults["settings"])}
    probe["settings"]["exportSettings"] = {}
    probe["settings"].setdefault("imperialAutoSizes", {})
    probe["settings"].pop("referenceImage", None)

    def CheckSettings(settings):
        ValidateProjectSettings(settings)

    settings, referenceRecord, settingNotices = RepairRecoverySettings(repaired.get("settings"), defaults["settings"],
                                                                      CheckSettings, themeDefinitions)
    repaired["settings"] = settings
    notices.extend(settingNotices)

    def DecodeRecoveredProject():
        # Validate raster bytes once, outside the per-setting/resource probes.
        validatedImages = set()
        if referenceRecord is not None:
            try:
                repaired["settings"]["referenceImage"] = ValidateReferenceImage(referenceRecord, validatedImages)
            except (ValueError, TypeError, RuntimeError):
                repaired["settings"].pop("referenceImage", None)
                notices.append("Removed invalid reference image settings.")
        return DecodeProject(repaired, definitions, validatedImages = validatedImages)
    view = repaired.get("view", {"zoom": 1, "pan": [0, 0]})
    if not isinstance(view, dict):
        view = {}
    repaired["view"] = {}
    for name, fallback in (("zoom", 1), ("pan", [0, 0])):
        try:
            value = view[name]
            if name == "zoom":
                ValidateNumber(value, minimum = 1e-6, maximum = 1e6)
            else:
                ValidatePoint(value)
            repaired["view"][name] = value
        except (ValueError, TypeError, KeyError, IndexError, OverflowError):
            repaired["view"][name] = fallback
            notices.append(f"Reset invalid camera {name} to its default.")
    if repaired.get("ui") is not None:
        try:
            ValidateEditorUi(repaired["ui"])
        except (ValueError, TypeError, KeyError, IndexError, OverflowError):
            repaired["ui"] = copy.deepcopy(defaults.get("ui"))
            notices.append("Reset invalid saved panel layout to defaults.")

    scene = repaired["scene"]
    records = scene.get("objects")
    if not isinstance(records, list) or len(records) > 100000:
        return DecodeRecoveredProject(), notices
    identityChanged, sceneNotices = RepairRecoveryScene(scene, wallMaterials)
    notices.extend(sceneNotices)

    def ValidateDefinition(key, candidate):
        DecodeProject(dict(probe, furnishingDefinitions = {key: candidate}), definitions)

    validEmbedded, definitionNotices = RepairRecoveryDefinitions(repaired.get("furnishingDefinitions", {}), definitions,
        ValidateDefinition, lambda payload: QtSvg.QSvgRenderer(payload).isValid())
    repaired["furnishingDefinitions"] = validEmbedded
    notices.extend(definitionNotices)
    available = {**definitions, **validEmbedded}
    missingChildren = Counter(component["definition"] for definition in validEmbedded.values()
                              for component in definition.get("components", []) if component["definition"] not in available)
    for key in sorted(missingChildren):
        count = missingChildren[key]
        notices.append(f"Missing compound child {key}: {count} reference{'s' if count != 1 else ''} in compound definitions. Using Null while retaining the references.")
    missing = Counter(record["definition"] for record in records if isinstance(record, dict) and record.get("type") == "Furnishing"
                      and isinstance(record.get("definition"), str) and record["definition"] not in available)
    for key in sorted(missing):
        count = missing[key]
        notices.append(f"Missing furnishing {key}: {count} object{'s' if count != 1 else ''} affected. Using serialized children when available, otherwise Null.")
    history = repaired.get("history")
    if identityChanged and history is not None:
        repaired.pop("history")
        notices.append("Discarded undo history because object IDs were repaired.")
    if chooseGeometry is not None:
        from .geometry_recovery import ResolveGeometry
        repaired, geometryNotices = ResolveGeometry(repaired, available, chooseGeometry)
        notices.extend(geometryNotices)
    decoded = DecodeRecoveredProject()
    # Catalog compounds and already recovered embedded artwork may still have
    # asset errors even when every top-level definition key exists.
    resolvedDefinitions = {**definitions, **decoded[5]["embeddedFurnishings"]}
    problemCounts = Counter()
    for obj in decoded[2]:
        if type(obj) is Furnishing:
            for key, reason in FurnishingAssetProblems(obj.definitionKey, resolvedDefinitions, obj.definition).items():
                problemCounts[(key, reason)] += 1
    reportedKeys = set(missing) | set(missingChildren)
    for (key, reason), count in sorted(problemCounts.items()):
        if key in reportedKeys:
            continue
        prefix = "Missing furnishing" if reason == "missing" else "Unavailable furnishing artwork"
        notices.append(f"{prefix} {key}: {count} object{'s' if count != 1 else ''} affected. Restore the asset or remove its references.")
    if history is not None and not identityChanged and decoded[5].get("history", {"undo": [], "redo": []}) == {"undo": [], "redo": []}:
        if not isinstance(history, dict) or history.get("format") != "Planner Changes" or history.get("version") != 1 or history.get("undo") or history.get("redo"):
            notices.append("Discarded incompatible or damaged undo history.")
    notices = list(dict.fromkeys(notices))
    decoded[5]["recoveryNotices"] = notices
    return decoded, notices
