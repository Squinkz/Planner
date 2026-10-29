"""Recovery policies for preferences, scene metadata and embedded definitions without Qt."""
import copy
from pathlib import Path
from .record_validation import ValidateNumber
from .record_schema import geometryIssueNames
from .catalog_metadata import FurnishingCategories


def RepairRecoverySettings(original, defaultSettings, validateSettings, themeDefinitions):
    notices = []
    baseSettings = copy.deepcopy(defaultSettings)
    baseSettings["exportSettings"] = {}
    baseSettings.setdefault("imperialAutoSizes", {})
    baseSettings.pop("referenceImage", None)
    if not isinstance(original, dict):
        original = {}
        notices.append("Replaced invalid editor settings with defaults.")
    # Normalize legacy paint settings before filtering against current defaults.
    # Keep the same precedence and strict boolean validation as DecodeProject.
    if "floors" in original:
        floors = original.pop("floors")
        if type(floors) is bool:
            original.setdefault("roomStyle", "Tinted" if floors else "Canvas")
        else:
            notices.append("Reset invalid floors setting to its default.")
    referenceRecord = original.get("referenceImage", defaultSettings.get("referenceImage"))

    settings = copy.deepcopy(baseSettings)
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
            validateSettings(candidate)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError):
            notices.append(f"Reset invalid {name} setting to its default.")
        else:
            settings = candidate
    enabled = original.get("snapEnabled", baseSettings["snapEnabled"])
    if type(enabled) is not bool:
        enabled = baseSettings["snapEnabled"]
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
            validateSettings(candidate)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError):
            notices.append(f"Reset invalid or unsupported export option: {name}.")
        else:
            settings = candidate
    theme = settings["exportSettings"].get("canvasTheme")
    if theme is not None and (theme not in themeDefinitions or themeDefinitions[theme]["type"] != "canvas"):
        settings["exportSettings"].pop("canvasTheme")
        notices.append("Removed missing export theme override.")
    return settings, referenceRecord, notices


def RepairRecoveryScene(scene, materials):
    records = scene["objects"]
    notices = []
    usedIds = {record["id"] for record in records if isinstance(record, dict) and type(record.get("id")) is int and record["id"] > 0}
    nextId = max(usedIds, default = 0) + 1
    seenIds = set()
    identityChanged = False
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        if "geometryIssues" in record:
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
            if material not in materials and not (record.get("type") == "Fireplace" and material is None):
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

    return identityChanged, notices


def RepairRecoveryDefinitions(embedded, definitions, validateDefinition, validSvg):
    notices = []
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
        try:
            validateDefinition(key, candidate)
            if not validSvg(candidate["svg"].encode("utf-8")):
                raise ValueError("SVG is unsupported by the renderer.")
        except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError):
            # Retain usable artwork even when compound metadata is damaged.
            flat = {name: candidate[name] for name in ("name", "category", "keywords", "width", "length", "svg") if name in candidate}
            try:
                validateDefinition(key, flat)
                if not validSvg(flat["svg"].encode("utf-8")):
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
    return validEmbedded, notices
