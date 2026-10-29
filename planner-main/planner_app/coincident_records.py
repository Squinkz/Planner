"""Visual duplicate grouping and keeper proposals without Qt or model mutation."""
import json


coincidentEncoder = json.JSONEncoder(sort_keys = True, separators = (",", ":"))


def GroupCoincidentRecords(records, groups = None, consumeRecords = False):
    """Group records, optionally sharing an accumulator with a backend fast path.

    Only freshly encoded, private records may opt into consumption. Shared
    caller-owned records remain unchanged under the default behavior.
    """
    groups = {} if groups is None else groups
    for obj, record in records:
        if isinstance(record, dict):
            comparable = record if consumeRecords else record.copy()
            for name in ("id", "measurementHidden", "measurementFlipped", "geometryIssues"):
                comparable.pop(name, None)
            key = coincidentEncoder.encode(comparable)
        else:
            key = record
        groups.setdefault(key, []).append(obj)
    return [tuple(group) for group in groups.values() if len(group) > 1]


def PlanCoincidentRemoval(groups, isVisible, selectedIds = None):
    """The visibility query is read-only and stops at the first visible keeper."""
    replacements = {}
    for group in groups:
        if selectedIds is not None and not any(id(obj) in selectedIds for obj in group[1:]):
            continue
        keeper = next((obj for obj in group if isVisible(obj)), group[0])
        replacements.update({id(obj): keeper for obj in group if obj is not keeper})
    return replacements
