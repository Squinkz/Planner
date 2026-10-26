"""Repair project metadata without changing, dropping or repositioning scene geometry."""
import copy
from collections import Counter
from pathlib import Path
from PySide6 import QtSvg
from .project_codec import DecodeProject, ValidateEditorUi, ValidateNumber, ValidatePoint
from .graphics.theme import wallMaterials
from .graphics.palette import themeDefinitions
from .catalog import FurnishingCategories
from .reference_image import ValidateReferenceImage
from .furnishing_assets import FurnishingAssetProblems
from .models import Furnishing


def RecoverProject(data, definitions, defaults, chooseGeometry = None):
    if (not isinstance(data, dict) or data.get("format") != "Planner Project"
            or type(data.get("version")) is not int or data["version"] != 1
            or not isinstance(data.get("scene"), dict)):
        return DecodeProject(data, definitions), []
    repaired = copy.deepcopy(data)
    notices = []
    probe = {"format": "Planner Project", "version": 1,
             "scene": {"objects": [], "groups": [], "hidden": []}, "settings": copy.deepcopy(defaults["settings"])}
    probe["settings"]["exportSettings"] = {}
    probe["settings"].setdefault("imperialAutoSizes", {})
    probe["settings"].pop("referenceImage", None)

    def CheckSettings(settings):
        candidate = dict(probe, settings = settings)
        DecodeProject(candidate, definitions)

    original = repaired.get("settings")
    if not isinstance(original, dict):
        original = {}
        notices.append("Replaced invalid editor settings with defaults.")
    referenceRecord = original.get("referenceImage", defaults["settings"].get("referenceImage"))

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
    settings = copy.deepcopy(probe["settings"])
    settings["snapEnabled"] = False
    required = {"wallWidth", "wallMaterial", "doorType", "windowType", "snapEnabled", "snap", "visibility",
                "connectedVertices", "connectedObjects", "groupMode", "showGrid", "showMeasurements"}
    for name in required - original.keys():
        notices.append(f"Restored missing {name} setting to its default.")
    for name, value in original.items():
        if name in ("exportSettings", "snapEnabled", "theme", "uiTheme", "canvasTheme", "showTips", "showFpsCounter", "referenceImage"):
            continue
        if name not in settings and name not in ("exportFolder", "exportFileName", "wallMeasurementMode", "wallMeasurementReference"):
            notices.append(f"Ignored unknown editor setting: {name}.")
            continue
        candidate = copy.deepcopy(settings)
        candidate[name] = value
        try:
            CheckSettings(candidate)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError):
            notices.append(f"Reset invalid {name} setting to its default.")
        else:
            settings = candidate
    enabled = original.get("snapEnabled", probe["settings"]["snapEnabled"])
    if type(enabled) is not bool:
        enabled = probe["settings"]["snapEnabled"]
        notices.append("Reset invalid snapping switch to its default.")
    if enabled and not any(settings["snap"].values()):
        enabled = False
        notices.append("Disabled snapping because no snapping modes were selected.")
    settings["snapEnabled"] = enabled
    export = original.get("exportSettings", {})
    if not isinstance(export, dict):
        notices.append("Reset invalid export settings to defaults.")
        export = {}
    for name, value in export.items():
        candidate = copy.deepcopy(settings)
        candidate["exportSettings"][name] = value
        try:
            CheckSettings(candidate)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError):
            notices.append(f"Reset invalid or unsupported export option: {name}.")
        else:
            settings = candidate
    theme = settings["exportSettings"].get("canvasTheme")
    if theme is not None and (theme not in themeDefinitions or themeDefinitions[theme]["type"] != "canvas"):
        settings["exportSettings"].pop("canvasTheme")
        notices.append("Removed missing export theme override.")
    repaired["settings"] = settings
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
    usedIds = {record["id"] for record in records if isinstance(record, dict) and type(record.get("id")) is int and record["id"] > 0}
    nextId = max(usedIds, default = 0) + 1
    seenIds = set()
    identityChanged = False
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        if "geometryIssues" in record:
            from .geometry_recovery import geometryIssueNames
            codes = record["geometryIssues"]
            valid = list(dict.fromkeys(code for code in codes if isinstance(code, str) and code in geometryIssueNames)) if isinstance(codes, list) else []
            if codes != valid:
                record["geometryIssues"] = valid
                notices.append(f"Reset invalid geometry highlight flags on object {index + 1}.")
        for name in ("measurementHidden", "measurementFlipped", "behindCounters", "flipHorizontal", "flipVertical", "windowWell", "wellDashed"):
            if name in record and type(record[name]) is not bool:
                record[name] = False
                notices.append(f"Reset invalid {name} flag on object {index + 1}.")
        objectId = record.get("id")
        if objectId is not None:
            if type(objectId) is not int or objectId < 1 or objectId in seenIds:
                record["id"] = nextId
                nextId += 1
                identityChanged = True
                notices.append(f"Regenerated invalid or duplicate ID for object {index + 1}.")
            seenIds.add(record["id"])
        if record.get("type") in ("Wall", "Pillar", "Column", "Elevator", "Stair", "Counter", "Railing", "Arrow", "MeasurementGuide", "BoundaryLine", "DashedLine", "SolidLine", "AngleGuide", "Fireplace"):
            material = record.get("material")
            if material not in wallMaterials and not (record.get("type") == "Fireplace" and material is None):
                if isinstance(material, str):
                    record["originalMaterial"] = material
                record["material"] = "Generic"
                notices.append(f"Used Generic for missing material on object {index + 1}: {material}.")
    groups = scene.get("groups", [])
    validGroups, grouped = [], set()
    if isinstance(groups, list):
        for group in groups:
            valid = []
            if isinstance(group, list):
                for index in group:
                    if type(index) is int and 0 <= index < len(records) and index not in grouped and index not in valid:
                        valid.append(index)
            if len(valid) >= 2:
                validGroups.append(valid)
                grouped.update(valid)
    if groups != validGroups:
        notices.append("Repaired invalid or conflicting group membership.")
    elif "groups" not in scene:
        notices.append("Restored missing group list.")
    scene["groups"] = validGroups
    hidden = scene.get("hidden", [])
    validHidden = list(dict.fromkeys(index for index in hidden if type(index) is int and 0 <= index < len(records))) if isinstance(hidden, list) else []
    if hidden != validHidden:
        notices.append("Repaired invalid hidden-object references.")
    elif "hidden" not in scene:
        notices.append("Restored missing hidden-object list.")
    scene["hidden"] = validHidden

    embedded = repaired.get("furnishingDefinitions", {})
    if not isinstance(embedded, dict):
        embedded = {}
        notices.append("Discarded invalid embedded furnishing catalogue; using available assets or Null.")
    if len(embedded) > 100000:
        raise ValueError("The project contains too many embedded furnishing definitions.")
    validEmbedded = {}
    null = definitions["null"]
    nullSvg = (null.get("graphicData") or Path(null["imagePath"]).read_bytes()).decode("utf-8-sig")
    for key, record in embedded.items():
        if not isinstance(key, str) or not key:
            notices.append("Discarded an embedded definition with an invalid key.")
            continue
        candidate = copy.deepcopy(record) if isinstance(record, dict) else {}
        metadataRepaired = False
        if not isinstance(candidate.get("name"), str) or not candidate["name"]:
            candidate["name"] = key
            metadataRepaired = True
        try:
            FurnishingCategories(candidate.get("category"))
            if not candidate.get("category"):
                raise ValueError("Missing category")
        except ValueError:
            candidate["category"] = "Miscellaneous"
            metadataRepaired = True
        words = candidate.get("keywords", [])
        if not isinstance(words, list) or any(not isinstance(word, str) for word in words):
            candidate["keywords"] = [word for word in words if isinstance(word, str)] if isinstance(words, list) else []
            metadataRepaired = True
        for name in ("width", "length"):
            try:
                ValidateNumber(candidate.get(name), minimum = 1e-8, maximum = 1e12)
            except ValueError:
                candidate[name] = definitions.get(key, null)[name]
                metadataRepaired = True
        if metadataRepaired:
            notices.append(f"Repaired embedded furnishing metadata: {key}.")
        candidateProbe = dict(probe, furnishingDefinitions = {key: candidate})
        try:
            DecodeProject(candidateProbe, definitions)
            if not QtSvg.QSvgRenderer(candidate["svg"].encode("utf-8")).isValid():
                raise ValueError("SVG is unsupported by the renderer.")
        except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError):
            # Retain usable artwork even when compound metadata is damaged.
            flat = {name: candidate[name] for name in ("name", "category", "keywords", "width", "length", "svg") if name in candidate}
            try:
                DecodeProject(dict(probe, furnishingDefinitions = {key: flat}), definitions)
                if not QtSvg.QSvgRenderer(flat["svg"].encode("utf-8")).isValid():
                    raise ValueError("Invalid renderer")
                candidate = flat
                notices.append(f"Kept embedded artwork for {key}; removed damaged compound metadata.")
            except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError):
                candidate = {"name": key, "category": "Miscellaneous", "keywords": [],
                             "width": null["width"], "length": null["length"], "svg": nullSvg}
                notices.append(f"Used Null artwork for damaged embedded furnishing: {key}.")
        validEmbedded[key] = candidate
    # Detect cycles across separately valid definitions; their flattened SVGs
    # remain usable, so only decomposition metadata needs to be removed.
    for key in validEmbedded:
        pending = [(key, ())]
        visited = set()
        damaged = False
        while pending:
            current, ancestors = pending.pop()
            if current in ancestors or len(ancestors) >= 64:
                damaged = True
                break
            if current in visited:
                continue
            visited.add(current)
            for component in validEmbedded.get(current, {}).get("components", []):
                child = component["definition"]
                if child in validEmbedded:
                    pending.append((child, ancestors + (current,)))
        if damaged:
            validEmbedded[key].pop("components", None)
            validEmbedded[key].pop("compoundCenter", None)
            notices.append(f"Kept artwork for {key}; removed cyclic or excessively nested compound metadata.")
    repaired["furnishingDefinitions"] = validEmbedded
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
