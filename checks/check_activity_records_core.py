"""Activity record validation, naming and fingerprints without Qt."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import zlib


def CheckWithoutQt():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
    from planner_app.activity_records import DecodeActivityLog, ActivityRecordFingerprint, DescribeRecordChanges, DescribeReferenceChange, EncodeActivityLog, EncodeActivityStacks, RestoreActivityStacks
    data = dict(entries = [], undo = [], redo = [], issues = {}, gridStep = 100)
    packed = dict(version = 1, encoding = "zlib-base64", data = base64.b64encode(zlib.compress(json.dumps(data).encode())).decode())
    assert DecodeActivityLog(packed) == data
    assert DecodeActivityLog(EncodeActivityLog(data)) == data
    calls = []
    stacks = dict(undo = [(11, "first"), (12, "second")], redo = [(13, "third")])
    links, digests = {11: 4, 13: 5}, {13: "existing"}
    def Fingerprint(edit):
        calls.append(edit)
        return "digest"
    encoded = EncodeActivityStacks(stacks, links, digests, Fingerprint)
    assert encoded == dict(undo = [[4, "digest"], None], redo = [[5, "existing"]]) and calls == ["first"]
    restored, restoredDigests = RestoreActivityStacks(encoded, stacks, lambda edit: "existing" if edit == "third" else "digest")
    assert restored == links and restoredDigests == digests
    assert RestoreActivityStacks(dict(undo = [], redo = []), stacks, Fingerprint) == ({}, {})

    assert ActivityRecordFingerprint({"width": 200}) == ActivityRecordFingerprint({"width": 200.0})
    assert DescribeReferenceChange({"width"})[0] == "Resized Reference Image"
    first = dict(first = [0, 0], second = [100, 0])
    second = dict(first = [5, 0], second = [105, 0])
    changes = [(0, "Wall", "Wall", 7, False, False, first, second)]
    assert DescribeRecordChanges(changes) == ("Moved Wall #0007", "Moved Wall #0007", [7])
    assert DescribeRecordChanges([], groups = True)[0] == "Changed object groups"
    try:
        DecodeActivityLog(dict(packed, data = packed["data"] + "extra"))
    except ValueError:
        pass
    else:
        raise AssertionError("Trailing compressed data accepted")
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: portable activity transport, fingerprints and descriptions")


if __name__ == "__main__":
    if "--without-qt" in sys.argv:
        CheckWithoutQt()
    else:
        result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"], capture_output = True, text = True, timeout = 10)
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout.strip())
